"""
MLA Scraper Agent — Slice #1 base layer.

Scrapes the Wikipedia "Members of Legislative Assembly" table for the current
(17th) Tamil Nadu Assembly into the local SQLite staging DB. This is the cheapest,
cleanest single source for all ~234 seats (CONTEXT.md §8 "Start with Wikipedia").

Shape per CONTEXT.md §9 Rule 4:  fetch() -> parse() -> store() -> report().
Resilient (Rule 7), idempotent (Rule 8), every row sourced (Rule 5), async (Rule 2).

Scope note (ruling: master-table-only for v1):
    Vote margin, vote share, and total electors live on the per-constituency
    articles, not this table. Fetching 234 of them costs ~12 min/run for marginal
    gain, so it is deferred to a later enrichment pass. See TODO(enrichment) below.

Vacant / by-election handling (discovered via scripts/probe_wikipedia.py):
    The members table lists 240 rows for 234 seats. Five seats have a "Vacant" row
    (member resigned, by-election pending) and one seat (Mannargudi) lists the same
    member twice after a party switch. parse() therefore:
      * SKIPS rows whose member name is a vacancy marker -> currently-vacant seats
        get NO mla row (the honest civic state; the constituency still exists).
      * De-dupes the rest by constituency number, keeping the LAST row, which is
        the most-current entry (e.g. the post-switch party for Mannargudi).
    Net: one staged row per currently-sitting MLA. To instead retain a placeholder
    for vacant seats, change KEEP_VACANT_SEATS below.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import httpx

from . import staging
from .models import AgentRunReport, FetchedPage, RawMLARecord, SourcePageType
from .wikitable import cell_link, cell_text, find_wikitable, resolve_columns, table_to_grid

MEMBERS_URL = "https://en.wikipedia.org/wiki/17th_Tamil_Nadu_Assembly"
USER_AGENT = "TNWatch/0.1 (civic-accountability data; +https://github.com/tnwatch; contact prasathcodes@gmail.com)"

# Header substrings that uniquely identify the members table. "constituency" +
# "name" + "party" alone also matches the Council of Ministers table, so we key on
# the members table's distinctive columns: alliance + remarks (alongside constituency).
MEMBERS_TABLE_HEADERS = ["constituency", "alliance", "remarks"]
COLUMN_SPEC = {
    "number": ["no."],
    "constituency": ["constituency"],
    "name": ["name"],
    "district": ["district"],
    "party": ["party"],
    "alliance": ["alliance"],
    "remarks": ["remarks"],
}

VACANCY_MARKERS = {"vacant", "vacant seat", "tbd"}
KEEP_VACANT_SEATS = False  # flip to stage a placeholder row for currently-vacant seats


class MLAScraperAgent:
    """Scrapes the Wikipedia members list of current TN MLAs into SQLite staging."""

    AGENT_NAME = "mla_scraper"

    def __init__(self, db_path: str, client: httpx.AsyncClient | None = None, rate_limit_s: float = 3.0) -> None:
        """
        Args:
            db_path: path to the local SQLite staging DB.
            client: optional shared httpx.AsyncClient (one is created per-run if None).
            rate_limit_s: polite delay between requests (Rule 12); used once per-page
                source is added in the enrichment pass.
        """
        self.db_path = db_path
        self._client = client
        self.rate_limit_s = rate_limit_s

    async def fetch(self) -> list[FetchedPage]:
        """
        Download the members-list page. Sets a real User-Agent and follows
        redirects (Rule 12). Returns whatever it successfully fetched; a failed
        fetch returns [] and is surfaced as a failed/partial run by run(), never
        raised into the orchestrator (Rule 7).

        TODO(enrichment): add per-constituency fetches here (rate-limited by
        self.rate_limit_s) to enrich vote_margin / vote_share_pct / total_electors.
        """
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0
        )
        try:
            resp = await client.get(MEMBERS_URL)
            return [
                FetchedPage(
                    url=str(resp.url),
                    page_type=SourcePageType.MEMBERS_LIST,
                    html=resp.text,
                    fetched_at=datetime.now(timezone.utc),
                    http_status=resp.status_code,
                )
            ]
        finally:
            if owns_client:
                await client.aclose()

    def parse(self, pages: list[FetchedPage]) -> list[RawMLARecord]:
        """
        Turn fetched members-list HTML into RawMLARecords — one per currently-
        sitting MLA. Expands the table's rowspan/colspan into a grid, resolves
        columns from the header (resilient to column reordering), skips vacant
        seats, and de-dupes repeated seats keeping the most-current row. Values
        stay raw text (the Normaliser types/cleans them). Rows without a numeric
        constituency number are dropped (not raised).
        """
        # Rows are in document order; the LAST row for a seat is its current state.
        # by_seat[number] is None when that current state is "Vacant" (resigned,
        # by-election pending) so the seat is dropped unless KEEP_VACANT_SEATS.
        by_seat: dict[int, RawMLARecord | None] = {}
        for page in pages:
            if page.http_status != 200 or page.page_type is not SourcePageType.MEMBERS_LIST:
                continue
            table = find_wikitable(page.html, contains_headers=MEMBERS_TABLE_HEADERS)
            grid = table_to_grid(table)
            if not grid:
                continue
            cols = resolve_columns(grid[0], COLUMN_SPEC)
            for row in grid[1:]:
                number_txt = cell_text(row[cols["number"]]) if cols["number"] < len(row) else ""
                if not number_txt.isdigit():
                    continue  # group/sub-header row, never a real member
                number = int(number_txt)
                name = cell_text(row[cols["name"]])
                is_vacant = name.strip().lower() in VACANCY_MARKERS
                if is_vacant and not KEEP_VACANT_SEATS:
                    by_seat[number] = None  # latest state is vacant -> drop the seat
                    continue
                name_cell = row[cols["name"]]
                by_seat[number] = RawMLARecord(
                    constituency_number_raw=number_txt,
                    constituency_name_raw=cell_text(row[cols["constituency"]]) or None,
                    district_raw=cell_text(row[cols["district"]]) or None,
                    mla_name_raw=name or None,
                    mla_wiki_url=_abs_wiki(cell_link(name_cell)),
                    party_raw=cell_text(row[cols["party"]]) or None,
                    alliance_raw=cell_text(row[cols["alliance"]]) or None,
                    remarks_raw=cell_text(row[cols["remarks"]]) or None,
                    source_url=page.url,
                    source_page_type=SourcePageType.MEMBERS_LIST,
                    scraped_at=page.fetched_at,
                    staging_key=f"members_list:AC-{number:03d}",
                )
        return [by_seat[n] for n in sorted(by_seat) if by_seat[n] is not None]

    async def store(self, records: list[RawMLARecord]) -> int:
        """Idempotent upsert of raw records into SQLite staging (off the event loop)."""
        return await asyncio.to_thread(self._store_sync, records)

    async def report(self, run: AgentRunReport) -> None:
        """Append the run's outcome to the local agent_runs audit table."""
        await asyncio.to_thread(self._report_sync, run)

    async def run(self) -> AgentRunReport:
        """
        Orchestrate fetch -> parse -> store, wrapping everything so any failure
        becomes a 'failed'/'partial' agent_runs row rather than crashing the
        APScheduler orchestrator (Rule 7). Always writes a report. Returns it.
        """
        started = datetime.now(timezone.utc)
        rows_written = 0
        status = "success"
        error_message: str | None = None
        try:
            pages = await self.fetch()
            ok_pages = [p for p in pages if p.http_status == 200]
            if not ok_pages:
                status = "failed"
                error_message = "no pages fetched (HTTP 200)"
            else:
                records = self.parse(ok_pages)
                rows_written = await self.store(records)
                if len(ok_pages) < len(pages):
                    status = "partial"
                if rows_written == 0:
                    status = "failed"
                    error_message = "0 rows parsed from fetched HTML"
        except Exception as exc:  # noqa: BLE001 - agent must never crash the orchestrator
            status = "failed"
            error_message = f"{type(exc).__name__}: {exc}"

        report = AgentRunReport(
            agent_name=self.AGENT_NAME,
            status=status,
            rows_written=rows_written,
            error_message=error_message,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
        await self.report(report)
        return report

    # --- sync helpers run via asyncio.to_thread ---

    def _store_sync(self, records: list[RawMLARecord]) -> int:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            return staging.upsert_raw_mla(conn, records)
        finally:
            conn.close()

    def _report_sync(self, run: AgentRunReport) -> None:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            staging.insert_agent_run(conn, run)
        finally:
            conn.close()


def _abs_wiki(href: str | None) -> str | None:
    """Resolve a relative wiki href to an absolute URL; drop redlink edit URLs."""
    if not href:
        return None
    if href.startswith("/w/index.php"):  # redlink: member has no article yet
        return None
    if href.startswith("/"):
        return f"https://en.wikipedia.org{href}"
    return href


__all__ = ["MLAScraperAgent", "MEMBERS_URL", "USER_AGENT"]


if __name__ == "__main__":  # manual run: python -m agents.mla_scraper [db_path]
    import sys

    db = sys.argv[1] if len(sys.argv) > 1 else "data/staging.db"

    async def _main() -> None:
        agent = MLAScraperAgent(db_path=db)
        report = await agent.run()
        print(report.model_dump_json(indent=2))

    asyncio.run(_main())
