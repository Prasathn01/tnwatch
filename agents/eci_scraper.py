"""
ECI Scraper Agent — myneta.info affidavit-data enrichment for TN 2026 MLAs.

Scrapes the MyNeta TamilNadu2026 index to discover all elected-candidate URLs,
then fetches each affidavit page to extract:
    total_assets, total_liabilities, criminal_cases, criminal_cases_serious,
    education, age, candidate_id_eci

Pipeline shape (CONTEXT.md §9 Rule 4):
    fetch() -> parse() -> store() -> match_and_push() -> run()

Properties:
  * Resilient (Rule 7): any page failure logs + continues; never crashes orchestrator.
  * Idempotent (Rule 8): SQLite upsert keyed on 'eci:myneta:{candidate_id}'.
  * Every row sourced (Rule 5): source_url on every RawECIRecord.
  * Polite (Rule 12): RATE_LIMIT_S delay between candidate-page requests.

Pre-conditions:
  * Run probe_myneta.py first and verify HTML structure before a full run.
  * `mlas` table must already contain rows (from Normaliser) for matching.
  * Supabase env vars set: SUPABASE_URL + SUPABASE_SERVICE_KEY.

Column migration (run once in Supabase SQL editor before first push):
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS criminal_cases_serious int DEFAULT 0;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS candidate_id_eci text;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS eci_source_url text;
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import httpx
from bs4 import BeautifulSoup, Tag

from . import staging, supabase_io
from .models import AgentRunReport, FetchedPage, RawECIRecord, SourcePageType

log = logging.getLogger("tnwatch.eci_scraper")

BASE_URL = "https://myneta.info/TamilNadu2026"
INDEX_URL = f"{BASE_URL}/"
USER_AGENT = (
    "TNWatch/0.1 (civic-accountability data; "
    "+https://github.com/Prasathn01/tnwatch; contact prasathcodes@gmail.com)"
)

RATE_LIMIT_S: float = 1.5   # polite delay between candidate-page requests
MAX_CONCURRENT: int = 4     # simultaneous in-flight requests
FUZZY_THRESHOLD: float = 80.0   # rapidfuzz WRatio minimum score to accept a match

# IPC sections classified as "serious" by the ECI / Model Code of Conduct framework.
# Covers murder, attempt to murder, rape, kidnapping, dacoity, extortion, forgery, etc.
_SERIOUS_IPC: frozenset[int] = frozenset([
    302, 303, 304, 307,          # murder / culpable homicide / attempt to murder
    354, 355,                    # assault on woman
    363, 364, 365, 366,          # kidnapping / abduction
    376, 377,                    # rape / unnatural offence
    384, 385, 386, 387, 388,     # extortion
    392, 393, 394, 395, 396,     # robbery / dacoity
    420,                         # cheating
    467, 468, 471,               # forgery
    489,                         # counterfeiting currency
])


# ---------------------------------------------------------------------------
# HTML parsing helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _all_table_kv(soup: BeautifulSoup) -> dict[str, str]:
    """
    Walk every <table> on the page and collect (label_lower -> value) pairs from
    two-cell rows.  Later tables overwrite earlier ones for the same label, so the
    affidavit-specific tables (which come last on myneta pages) win.
    """
    kv: dict[str, str] = {}
    for tbl in soup.find_all("table"):
        if not isinstance(tbl, Tag):
            continue
        for row in tbl.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(" ", strip=True).lower().strip(": ")
                value = cells[1].get_text(" ", strip=True)
                if label:
                    kv[label] = value
    return kv


def _find_kv(kv: dict[str, str], *keys: str) -> str | None:
    """Return the first matching value for any of the given label substrings."""
    for key in keys:
        for label, val in kv.items():
            if key in label:
                return val or None
    return None


_RS_RE = re.compile(r"Rs\.?\s*([\d,]+(?:\.\d+)?)", re.I)
_DIGIT_RE = re.compile(r"\d+")
_IPC_RE = re.compile(r"\b(\d{3})\b")   # IPC section number in criminal case rows


def _parse_rupees_to_crore(raw: str | None) -> Decimal | None:
    """Convert 'Rs 1,23,45,678' -> Decimal('1.23') (crore, 2 d.p.). Returns None on failure."""
    if not raw:
        return None
    raw_clean = raw.strip()
    if raw_clean.lower() in {"nil", "0", "-", "n/a", ""}:
        return Decimal("0.00")
    m = _RS_RE.search(raw_clean)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    try:
        crore = Decimal(digits) / Decimal("10000000")
        return crore.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_int(raw: str | None) -> int | None:
    """Extract first integer from a string, or None."""
    if not raw:
        return None
    m = _DIGIT_RE.search(raw.strip())
    return int(m.group()) if m else None


def _count_serious_cases(soup: BeautifulSoup) -> int:
    """
    Count criminal cases whose text contains a serious IPC section number.
    MyNeta displays individual charges in table rows; we look for 3-digit numbers
    matching _SERIOUS_IPC inside any row that also mentions 'IPC' or a section marker.
    """
    count = 0
    seen_rows: set[str] = set()
    for tbl in soup.find_all("table"):
        if not isinstance(tbl, Tag):
            continue
        text = tbl.get_text(" ")
        if not re.search(r"\bIPC\b|\bsection\b|\bcase\b", text, re.I):
            continue
        for row in tbl.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            row_text = row.get_text(" ", strip=True)
            if row_text in seen_rows:
                continue
            seen_rows.add(row_text)
            if not re.search(r"\bIPC\b|\bsection\b", row_text, re.I):
                continue
            for m in _IPC_RE.finditer(row_text):
                if int(m.group(1)) in _SERIOUS_IPC:
                    count += 1
                    break  # one match per row is enough
    return count


def _extract_eci_id(soup: BeautifulSoup) -> str | None:
    """Extract the ECI affidavit reference number / S.No. from the page."""
    text = soup.get_text(" ")
    patterns = [
        r"(?:Affidavit\s*(?:No\.?|ID|Serial)|S\.?\s*No\.?)\s*[:\-]?\s*([A-Z0-9/\-]{5,30})",
        r"\bECI\s+ID\s*[:\-]?\s*([A-Z0-9/\-]{5,30})",
        r"\bSerial\s+No\.?\s*[:\-]?\s*(\d{5,})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Index-page discovery
# ---------------------------------------------------------------------------

def _parse_candidate_urls(html: str) -> list[str]:
    """
    Return deduplicated absolute candidate-page URLs found on the index page.
    Handles both relative ('candidate.php?candidate_id=5') and absolute hrefs.
    """
    soup = _soup(html)
    seen: dict[str, str] = {}  # candidate_id -> full URL (dedup by id)
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href: str = a["href"]
        if "candidate.php" not in href or "candidate_id=" not in href:
            continue
        m = re.search(r"candidate_id=(\d+)", href)
        if not m:
            continue
        cid = m.group(1)
        if cid in seen:
            continue
        if href.startswith("http"):
            full = href
        elif href.startswith("/"):
            full = f"https://myneta.info{href}"
        else:
            full = f"{BASE_URL}/{href.lstrip('/')}"
        seen[cid] = full
    return list(seen.values())


# ---------------------------------------------------------------------------
# Candidate-page parser
# ---------------------------------------------------------------------------

def _parse_candidate_page(
    html: str, url: str, fetched_at: datetime
) -> RawECIRecord | None:
    """
    Parse one candidate affidavit page into a RawECIRecord.
    All extracted values stay as raw strings — typing/cleaning is the push step's job.
    Returns None if the page looks like a 404 / error page (no recognisable candidate data).
    """
    m = re.search(r"candidate_id=(\d+)", url)
    if not m:
        log.warning("No candidate_id in URL %r — skipping", url)
        return None
    cid = m.group(1)

    s = _soup(html)
    kv = _all_table_kv(s)

    # -- Basic identity fields --
    candidate_name = (
        _find_kv(kv, "candidate name", "candidate", "name")
        or _find_kv(kv, "winner", "elected")
    )
    constituency = _find_kv(kv, "constituency", "assembly constituency", "ac name")
    party = _find_kv(kv, "party")

    # Sanity-check: if we found none of the three, page is likely an error / redirect
    if not any([candidate_name, constituency, party]):
        # Try regex on full text as a last resort
        full_text = s.get_text(" ")
        if not re.search(r"total assets|criminal case|education", full_text, re.I):
            log.debug("candidate_id=%s page has no recognisable affidavit data", cid)
            return None

    # -- Assets & liabilities --
    assets_raw = _find_kv(kv,
        "total assets", "gross total assets", "total value of assets",
    )
    liab_raw = _find_kv(kv,
        "total liabilities", "total liability", "liabilities",
    )

    # Fallback: regex on full text (handles varying label spellings)
    full_text = s.get_text(" ")
    if not assets_raw:
        ma = re.search(r"Total\s+Assets?[^Rs\d]{0,30}(Rs\.?\s*[\d,]+)", full_text, re.I)
        assets_raw = ma.group(0).strip() if ma else None
    if not liab_raw:
        ml = re.search(r"Total\s+Liabilit\w+[^Rs\d]{0,30}(Rs\.?\s*[\d,]+)", full_text, re.I)
        liab_raw = ml.group(0).strip() if ml else None

    # -- Criminal cases --
    criminal_total_raw = _find_kv(kv,
        "total criminal cases", "number of criminal cases",
        "criminal cases", "no. of criminal cases",
    )
    if not criminal_total_raw:
        mc = re.search(r"(?:Total\s+)?Criminal\s+Cases?[^\d]{0,20}(\d+)", full_text, re.I)
        criminal_total_raw = mc.group(1) if mc else "0"

    # Serious cases: count rows with matching IPC section numbers
    criminal_serious = _count_serious_cases(s)

    # -- Personal details --
    education_raw = _find_kv(kv, "education", "educational qualification")
    age_raw = _find_kv(kv, "age")
    if not age_raw:
        ma2 = re.search(r"\bAge[^\d]{0,10}(\d{2,3})\b", full_text, re.I)
        age_raw = ma2.group(1) if ma2 else None

    # -- ECI affidavit reference --
    eci_id_raw = _extract_eci_id(s)

    return RawECIRecord(
        candidate_id_myneta=cid,
        candidate_url=url,
        candidate_name_raw=candidate_name,
        constituency_name_raw=constituency,
        party_raw=party,
        total_assets_raw=assets_raw,
        total_liabilities_raw=liab_raw,
        criminal_cases_raw=criminal_total_raw,
        criminal_cases_serious_raw=str(criminal_serious),
        education_raw=education_raw,
        age_raw=age_raw,
        candidate_id_eci_raw=eci_id_raw,
        source_url=url,
        scraped_at=fetched_at,
        staging_key=f"eci:myneta:{cid}",
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ECIScraperAgent:
    """
    Scrapes myneta.info affidavit data for TN 2026 candidates, stores raw records
    in SQLite eci_staging, fuzzy-matches to the Supabase mlas table, and enriches
    matching rows with ECI-sourced financial/criminal/biographical fields.
    """

    AGENT_NAME = "eci_scraper"

    def __init__(
        self,
        db_path: str,
        client=None,
        rate_limit_s: float = RATE_LIMIT_S,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
    ) -> None:
        """
        Args:
            db_path: path to the local SQLite staging DB.
            client: optional shared Supabase client (built from .env if None).
            rate_limit_s: seconds between candidate-page requests (polite scraping).
            fuzzy_threshold: minimum rapidfuzz WRatio score (0-100) to accept a match.
        """
        self.db_path = db_path
        self._supabase = client
        self.rate_limit_s = rate_limit_s
        self.fuzzy_threshold = fuzzy_threshold

    # ------------------------------------------------------------------
    # fetch()
    # ------------------------------------------------------------------

    async def fetch(self) -> list[FetchedPage]:
        """
        Download the index page, discover candidate URLs, then fetch each
        candidate affidavit page with polite rate-limiting.

        Returns a list of FetchedPage objects — index page first, then one per
        candidate.  HTTP errors are logged but never raised (Rule 7).
        """
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            # Step 1 — index page
            index_page = await self._fetch_one(client, INDEX_URL, SourcePageType.MEMBERS_LIST)
            pages: list[FetchedPage] = [index_page]

            if index_page.http_status != 200:
                log.error("Index page returned HTTP %d — aborting fetch", index_page.http_status)
                return pages

            # Step 2 — discover candidate URLs from index
            candidate_urls = _parse_candidate_urls(index_page.html)
            log.info("Discovered %d candidate URLs from index page", len(candidate_urls))

            # Step 3 — fetch each candidate page (rate-limited, bounded concurrency)
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            async def _bounded(url: str) -> FetchedPage:
                async with semaphore:
                    page = await self._fetch_one(client, url, SourcePageType.ECI_CANDIDATE)
                    await asyncio.sleep(self.rate_limit_s)
                    return page

            tasks = [asyncio.create_task(_bounded(u)) for u in candidate_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, FetchedPage):
                    pages.append(r)
                else:
                    log.warning("Candidate fetch raised: %s", r)

        return pages

    async def _fetch_one(
        self, client: httpx.AsyncClient, url: str, page_type: SourcePageType
    ) -> FetchedPage:
        """Fetch a single URL; return a FetchedPage regardless of HTTP status."""
        fetched_at = datetime.now(timezone.utc)
        try:
            resp = await client.get(url)
            return FetchedPage(
                url=str(resp.url),
                page_type=page_type,
                html=resp.text,
                fetched_at=fetched_at,
                http_status=resp.status_code,
            )
        except Exception as exc:
            log.warning("Failed to fetch %s: %s", url, exc)
            return FetchedPage(
                url=url,
                page_type=page_type,
                html="",
                fetched_at=fetched_at,
                http_status=0,
            )

    # ------------------------------------------------------------------
    # parse()
    # ------------------------------------------------------------------

    def parse(self, pages: list[FetchedPage]) -> list[RawECIRecord]:
        """
        Extract RawECIRecord from each candidate FetchedPage.
        Skips pages with non-200 status or no recognisable affidavit data.
        Never raises; failures are logged.
        """
        records: list[RawECIRecord] = []
        for page in pages:
            if page.page_type is not SourcePageType.ECI_CANDIDATE:
                continue
            if page.http_status != 200:
                log.warning("Skipping %s — HTTP %d", page.url, page.http_status)
                continue
            try:
                rec = _parse_candidate_page(page.html, page.url, page.fetched_at)
                if rec is not None:
                    records.append(rec)
            except Exception as exc:
                log.error("Parse error on %s: %s", page.url, exc, exc_info=True)
        log.info("Parsed %d candidate records", len(records))
        return records

    # ------------------------------------------------------------------
    # store()
    # ------------------------------------------------------------------

    async def store(self, records: list[RawECIRecord]) -> int:
        """Idempotent upsert of raw records into SQLite eci_staging (off the event loop)."""
        return await asyncio.to_thread(self._store_sync, records)

    def _store_sync(self, records: list[RawECIRecord]) -> int:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            return staging.upsert_raw_eci(conn, records)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # match_and_push()
    # ------------------------------------------------------------------

    async def match_and_push(self) -> int:
        """
        Read pending eci_staging rows, fuzzy-match each to an MLA in Supabase,
        and enrich the matched mlas row with ECI financial/criminal/biographical data.
        Returns the number of mlas rows successfully updated.
        """
        return await asyncio.to_thread(self._match_and_push_sync)

    def _match_and_push_sync(self) -> int:
        from rapidfuzz import fuzz, process

        supa = self._supabase or supabase_io.create_client()

        # Load all current MLAs with their constituency names (for matching)
        mla_rows = supabase_io.load_mlas_for_matching(supa)
        if not mla_rows:
            log.warning("No MLA rows found in Supabase — run Normaliser first")
            return 0

        # Build lookup structures
        #   key: constituency_name (lower, stripped) -> MlaMatchRow
        exact_index: dict[str, supabase_io.MlaMatchRow] = {
            row.constituency_name.lower().strip(): row for row in mla_rows
        }
        # Also build a party-qualified index for disambiguation
        party_index: dict[tuple[str, str], supabase_io.MlaMatchRow] = {
            (row.constituency_name.lower().strip(), row.party.upper()): row
            for row in mla_rows
        }
        candidate_names = [row.constituency_name for row in mla_rows]

        conn = staging.connect(self.db_path)
        try:
            pending = staging.load_pending_eci(conn)
            log.info("Matching %d pending ECI rows against %d MLAs", len(pending), len(mla_rows))

            updated = 0
            pushed_keys: list[str] = []

            for row in pending:
                staging_key: str = row["staging_key"]
                cname_raw: str | None = row["constituency_name_raw"]
                party_raw: str | None = row["party_raw"]

                # --- fuzzy match ---
                match = self._match_mla(
                    cname_raw, party_raw,
                    exact_index, party_index, candidate_names, mla_rows,
                    process, fuzz,
                )
                if match is None:
                    log.warning(
                        "No match for eci_staging %s constituency=%r party=%r",
                        staging_key, cname_raw, party_raw,
                    )
                    continue

                mla, match_score = match
                staging.mark_eci_matched(conn, staging_key, mla.mla_id, score=match_score)

                # --- parse typed values ---
                assets_cr = _parse_rupees_to_crore(row["total_assets_raw"])
                liab_cr = _parse_rupees_to_crore(row["total_liabilities_raw"])
                criminal_cases = _parse_int(row["criminal_cases_raw"]) or 0
                age = _parse_int(row["age_raw"])

                payload = supabase_io.ECIUpdatePayload(
                    mla_id=mla.mla_id,
                    declared_assets_cr=assets_cr,
                    liabilities_cr=liab_cr,
                    criminal_cases=criminal_cases,
                    age=age,
                    education=row["education_raw"] or None,
                    source_url=row["source_url"],
                )

                # --- try to push extended fields (new columns) ---
                ext_data = self._build_extended_fields(row)

                n = supabase_io.update_mla_eci(supa, payload)
                if n > 0 and ext_data:
                    self._push_extended_fields(supa, mla.mla_id, ext_data)

                if n > 0:
                    updated += 1
                    pushed_keys.append(staging_key)
                else:
                    log.warning("update_mla_eci returned 0 for mla_id=%s", mla.mla_id)

            # Mark successfully pushed rows
            staging.mark_eci_pushed(conn, pushed_keys)

        finally:
            conn.close()

        log.info("match_and_push: %d mlas rows enriched", updated)
        return updated

    def _match_mla(
        self,
        cname_raw: str | None,
        party_raw: str | None,
        exact_index: dict[str, "supabase_io.MlaMatchRow"],
        party_index: dict[tuple[str, str], "supabase_io.MlaMatchRow"],
        candidate_names: list[str],
        mla_rows: list["supabase_io.MlaMatchRow"],
        process,
        fuzz,
    ) -> "tuple[supabase_io.MlaMatchRow, float] | None":
        """
        Try exact match first, then party-qualified exact match, then rapidfuzz
        WRatio fuzzy match on constituency name.
        Returns (MlaMatchRow, score) or None if no match meets fuzzy_threshold.
        """
        if not cname_raw:
            return None

        cname_key = cname_raw.lower().strip()
        party_key = (party_raw or "").upper().strip()

        # 1. Exact constituency name
        if cname_key in exact_index:
            return exact_index[cname_key], 100.0

        # 2. Exact (constituency, party) pair — handles disambiguation
        combo = (cname_key, party_key)
        if combo in party_index:
            return party_index[combo], 100.0

        # 3. Fuzzy match on constituency name
        result = process.extractOne(
            cname_raw,
            candidate_names,
            scorer=fuzz.WRatio,
            score_cutoff=self.fuzzy_threshold,
        )
        if result is None:
            return None

        best_name, score, idx = result
        matched_row = mla_rows[idx]
        log.info(
            "Fuzzy match: %r -> %r (score=%.1f, mla_id=%s)",
            cname_raw, best_name, score, matched_row.mla_id,
        )
        return matched_row, float(score)

    @staticmethod
    def _build_extended_fields(row) -> dict:
        """Build the extra columns that require a Supabase schema migration."""
        data: dict = {}
        serious_raw = row["criminal_cases_serious_raw"]
        if serious_raw is not None:
            try:
                data["criminal_cases_serious"] = int(serious_raw)
            except (ValueError, TypeError):
                pass
        eci_id = row["candidate_id_eci_raw"]
        if eci_id:
            data["candidate_id_eci"] = eci_id
        source = row["source_url"]
        if source:
            data["eci_source_url"] = source
        return data

    @staticmethod
    def _push_extended_fields(supa, mla_id: str, data: dict) -> None:
        """
        Attempt to push the extended (new-column) fields to Supabase.
        If the columns don't exist yet, the error is caught and logged — not raised.
        Run the migration SQL (shown in the module docstring) to enable this.
        """
        try:
            supa.table("mlas").update(data).eq("id", mla_id).execute()
        except Exception as exc:
            log.warning(
                "Extended field push failed for %s (columns may not exist yet): %s",
                mla_id, exc,
            )

    # ------------------------------------------------------------------
    # report()
    # ------------------------------------------------------------------

    async def report(self, run: AgentRunReport) -> None:
        """Append the run's outcome to the local agent_runs audit table."""
        await asyncio.to_thread(self._report_sync, run)

    def _report_sync(self, run: AgentRunReport) -> None:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            staging.insert_agent_run(conn, run)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    async def run(self) -> AgentRunReport:
        """
        Orchestrate fetch -> parse -> store -> match_and_push -> report.

        Any exception is caught and reported as a 'failed' run so the APScheduler
        orchestrator never crashes (Rule 7).  Always writes and returns a report.
        """
        started = datetime.now(timezone.utc)
        rows_written = 0
        status = "success"
        error_message: str | None = None

        try:
            pages = await self.fetch()
            candidate_pages = [p for p in pages if p.page_type is SourcePageType.ECI_CANDIDATE]
            ok_pages = [p for p in candidate_pages if p.http_status == 200]

            if not ok_pages:
                status = "failed"
                error_message = "no candidate pages fetched successfully"
            else:
                records = self.parse(ok_pages)
                rows_written = await self.store(records)

                if rows_written == 0:
                    status = "failed"
                    error_message = "0 records stored to eci_staging"
                else:
                    if len(ok_pages) < len(candidate_pages):
                        status = "partial"
                    # Enrich Supabase mlas table
                    pushed = await self.match_and_push()
                    log.info("Pushed %d ECI enrichments to Supabase mlas", pushed)

        except Exception as exc:  # noqa: BLE001 — agent must never crash the orchestrator
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


__all__ = ["ECIScraperAgent", "INDEX_URL", "USER_AGENT", "FUZZY_THRESHOLD"]


if __name__ == "__main__":  # python -m agents.eci_scraper [db_path] [--skip-push]
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = sys.argv[1:]
    db = next((a for a in args if not a.startswith("--")), "data/staging.db")
    skip_push = "--skip-push" in args

    async def _main() -> None:
        agent = ECIScraperAgent(db_path=db)
        if skip_push:
            # Fetch + parse + store only; skip Supabase step (useful for testing)
            pages = await agent.fetch()
            records = agent.parse(pages)
            n = await agent.store(records)
            print(f"Stored {n} raw ECI records to {db}")
            print(f"Sample (first 3):")
            for r in records[:3]:
                print(f"  {r.staging_key}  {r.constituency_name_raw!r}  "
                      f"{r.party_raw!r}  assets={r.total_assets_raw!r}")
        else:
            report = await agent.run()
            print(report.model_dump_json(indent=2))

    asyncio.run(_main())
