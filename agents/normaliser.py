"""
Normaliser Agent — Slice #1 staging -> Supabase.

Reads pending raw rows from SQLite `staging_mla_raw`, cleans/types them into
validated MLACleanRecords, and upserts into the Supabase `mlas` table. Also derives
currently-vacant seats (seeded constituencies − staged seats) and flips their
`constituencies.status` to 'vacant', then marks consumed staging rows.

Shape per CONTEXT.md §9 Rule 4: fetch() -> parse() -> store() -> report(), where
fetch() reads staging (not the web) and parse() does the normalise + validate.

Base-profile normalisation is purely deterministic string work (no Ollama/Gemini):
the constituency link is already known (the staged constituency number), so there
is no fuzzy matching here — that belongs to the ECI/PRS enrichment agents, which
arrive with external names and must match them back to these MLAs.

Cleaning rules (locked):
  name:  strip footnote markers ([a], *, †) -> collapse whitespace (incl. \\xa0,
         tabs) -> strip honorifics -> title-case.
  party: strip markers/whitespace -> map via PARTY_MAP (unmapped -> pass through
         as-is + WARNING; never crash, never skip).
  constituency_id / id: f"AC-{n:03d}" / f"MLA-{n:03d}" from the constituency
         number; a non-integer number is the one unrecoverable error -> skip + log.
  source_url: carried verbatim; empty -> validation failure (enforced in the model).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from . import staging, supabase_io
from .models import AgentRunReport, MLACleanRecord, RawMLARecord

log = logging.getLogger("tnwatch.normaliser")

# --- cleaning rules -------------------------------------------------------------

_FOOTNOTE_RE = re.compile(r"\[[a-z]\]")        # wiki footnote markers like [a], [b]
_SYMBOL_MARKERS = ("*", "†", "‡")
_WS_RE = re.compile(r"\s+")

# honorifics stripped from names (compared lower-cased, trailing '.' removed)
HONORIFICS = {
    "thiru", "tmt", "thirumathi", "dr", "adv", "er", "prof", "capt", "col",
}

# canonical party codes. Unmapped raw values pass through as-is (+ WARNING); the
# map grows as the scraper surfaces new values. A miss is a log event, never a crash.
PARTY_MAP = {
    "TVK": "TVK",
    "Tamilaga Vettri Kazhagam": "TVK",
    "DMK": "DMK",
    "Dravida Munnetra Kazhagam": "DMK",
    "AIADMK": "AIADMK",
    "All India Anna Dravida Munnetra Kazhagam": "AIADMK",
    "BJP": "BJP",
    "Bharatiya Janata Party": "BJP",
    "INC": "INC",
    "Indian National Congress": "INC",
    "PMK": "PMK",
    "Pattali Makkal Katchi": "PMK",
    "DMDK": "DMDK",
    "VCK": "VCK",
    "Viduthalai Chiruthaigal Katchi": "VCK",
    "IUML": "IUML",
    "Indian Union Muslim League": "IUML",
    "AMMK": "AMMK",
    "NTK": "NTK",
    "Naam Tamilar Katchi": "NTK",
    "CPI": "CPI",
    "CPI(M)": "CPI(M)",
    "CPM": "CPI(M)",          # normalise to one canonical form
    "IND": "IND",
    "Independent": "IND",
}


def _strip_markers(text: str) -> str:
    text = _FOOTNOTE_RE.sub("", text)
    for sym in _SYMBOL_MARKERS:
        text = text.replace(sym, "")
    return text


def _collapse_ws(text: str) -> str:
    return _WS_RE.sub(" ", text.replace("\xa0", " ")).strip()


_PAREN_JUNK_RE = re.compile(r"\s*\(.*")  # strips "(Tvk?" style party/footnote leakage


def clean_name(raw: str | None) -> str:
    """Footnotes -> whitespace -> honorifics -> title-case -> strip trailing parentheticals."""
    s = _collapse_ws(_strip_markers(raw or ""))
    tokens = s.split(" ") if s else []
    while tokens and tokens[0].rstrip(".").lower() in HONORIFICS:
        tokens.pop(0)
    name = " ".join(tokens).strip().title()
    return _PAREN_JUNK_RE.sub("", name).strip()


def map_party(raw: str | None) -> str:
    """Map a raw party value to its canonical code; unmapped values pass through (+WARNING)."""
    key = _collapse_ws(_strip_markers(raw or ""))
    if key in PARTY_MAP:
        return PARTY_MAP[key]
    if key:
        log.warning("Unmapped party value %r - passing through as-is; add it to PARTY_MAP", key)
    return key


def clean_alliance(raw: str | None) -> str | None:
    """Alliances (e.g. 'TVK+') are already canonical on Wikipedia — just de-noise."""
    cleaned = _collapse_ws(_strip_markers(raw or ""))
    return cleaned or None


def derive_constituency_id(number_raw: str | None) -> str:
    """f'AC-{n:03d}' from the constituency number. Raises ValueError if not an int."""
    return f"AC-{int(str(number_raw).strip()):03d}"


def derive_vacant_ids(seed_ids: set[str], staged_ids: set[str]) -> list[str]:
    """Seeded constituencies with no staged member row = currently-vacant seats."""
    return sorted(seed_ids - staged_ids)


# --- result containers ----------------------------------------------------------

@dataclass
class NormaliseResult:
    clean: list[MLACleanRecord] = field(default_factory=list)
    consumed_keys: list[str] = field(default_factory=list)        # staging rows successfully normalised
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (staging_key, reason)


@dataclass
class StoreCounts:
    upserted: int = 0
    vacant: int = 0
    consumed: int = 0
    vacant_ids: list[str] = field(default_factory=list)


# --- agent ----------------------------------------------------------------------

class NormaliserAgent:
    """Cleans staged MLA rows and pushes them to Supabase `mlas`."""

    AGENT_NAME = "normaliser"

    def __init__(self, db_path: str, client=None, constituencies_json: str = "data/constituencies.json") -> None:
        """
        Args:
            db_path: local SQLite staging DB.
            client: optional Supabase client (injected in tests; built from .env if None).
            constituencies_json: seed file used to derive the full set of 234 seat ids.
        """
        self.db_path = db_path
        self._client = client
        self.constituencies_json = constituencies_json

    async def fetch(self) -> list[RawMLARecord]:
        """Read pending (normalised = 0) rows from staging into RawMLARecords."""
        return await asyncio.to_thread(self._fetch_sync)

    def parse(self, raw_records: list[RawMLARecord]) -> NormaliseResult:
        """
        Normalise + validate each raw row into an MLACleanRecord. A non-integer
        constituency number, or any Pydantic validation error, skips that row with
        a logged reason (never raised); everything else is collected for store().
        """
        result = NormaliseResult()
        for r in raw_records:
            try:
                cid = derive_constituency_id(r.constituency_number_raw)
                mla_id = f"MLA-{int(str(r.constituency_number_raw).strip()):03d}"
            except (TypeError, ValueError):
                reason = f"unparseable constituency_number_raw={r.constituency_number_raw!r}"
                log.error("Skipping %s: %s", r.staging_key, reason)
                result.skipped.append((r.staging_key, reason))
                continue
            try:
                record = MLACleanRecord(
                    id=mla_id,
                    constituency_id=cid,
                    name=clean_name(r.mla_name_raw),
                    party=map_party(r.party_raw),
                    alliance=clean_alliance(r.alliance_raw),
                    source_url=r.source_url,
                )
            except ValidationError as exc:
                reason = f"validation: {exc.errors(include_url=False)[:1]}"
                log.error("Skipping %s: %s", r.staging_key, reason)
                result.skipped.append((r.staging_key, reason))
                continue
            result.clean.append(record)
            result.consumed_keys.append(r.staging_key)
        return result

    async def store(self, result: NormaliseResult) -> StoreCounts:
        """Push clean rows to Supabase, flip vacant seats, mark staging consumed."""
        return await asyncio.to_thread(self._store_sync, result)

    async def report(self, run: AgentRunReport) -> None:
        """Append the run to the local agent_runs audit table."""
        await asyncio.to_thread(self._report_sync, run)

    async def run(self) -> AgentRunReport:
        """fetch -> parse -> store -> report, wrapped so failures never crash the orchestrator."""
        started = datetime.now(timezone.utc)
        rows_written = 0
        status = "success"
        error_message: str | None = None
        try:
            raw = await self.fetch()
            result = self.parse(raw)
            counts = await self.store(result)
            rows_written = counts.upserted
            if result.skipped:
                status = "partial"
                error_message = f"{len(result.skipped)} row(s) skipped; first: {result.skipped[0]}"
            if raw and counts.upserted == 0:
                status = "failed"
                error_message = "fetched rows but upserted 0 to mlas"
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

    async def preview(self) -> tuple[NormaliseResult, list[str]]:
        """Read-only dry run: fetch + parse + derive vacant seats, writing nothing."""
        raw = await self.fetch()
        result = self.parse(raw)
        conn = staging.connect(self.db_path)
        try:
            staged = staging.staged_seat_ids(conn)
        finally:
            conn.close()
        vacant = derive_vacant_ids(self._seed_ids(), staged)
        return result, vacant

    # --- sync helpers (run via asyncio.to_thread) ---

    def _fetch_sync(self) -> list[RawMLARecord]:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            rows = conn.execute(
                "SELECT constituency_number_raw, constituency_name_raw, district_raw, mla_name_raw,"
                " mla_wiki_url, party_raw, alliance_raw, remarks_raw, source_url, source_page_type,"
                " scraped_at, staging_key FROM staging_mla_raw WHERE normalised = 0"
            ).fetchall()
        finally:
            conn.close()
        return [
            RawMLARecord(
                constituency_number_raw=row["constituency_number_raw"],
                constituency_name_raw=row["constituency_name_raw"],
                district_raw=row["district_raw"],
                mla_name_raw=row["mla_name_raw"],
                mla_wiki_url=row["mla_wiki_url"],
                party_raw=row["party_raw"],
                alliance_raw=row["alliance_raw"],
                remarks_raw=row["remarks_raw"],
                source_url=row["source_url"],
                source_page_type=row["source_page_type"],
                scraped_at=datetime.fromisoformat(row["scraped_at"]),
                staging_key=row["staging_key"],
            )
            for row in rows
        ]

    def _store_sync(self, result: NormaliseResult) -> StoreCounts:
        client = self._client or supabase_io.create_client()
        upserted = supabase_io.upsert_mlas(client, result.clean)
        conn = staging.connect(self.db_path)
        try:
            staged = staging.staged_seat_ids(conn)
            vacant_ids = derive_vacant_ids(self._seed_ids(), staged)
            vacant = supabase_io.set_constituency_status(client, vacant_ids, "vacant")
            # Guard: if we computed vacant seats but Supabase updated 0 rows, the
            # constituencies table probably wasn't seeded yet — surface this rather
            # than silently succeeding with stale status='filled' rows in prod.
            if vacant_ids and vacant == 0:
                log.warning(
                    "set_constituency_status computed %d vacant IDs %s but updated 0 rows "
                    "— constituencies table may not be seeded yet; re-run normaliser after seeding.",
                    len(vacant_ids), vacant_ids,
                )
            consumed = supabase_io.mark_staging_consumed(conn, result.consumed_keys)
        finally:
            conn.close()
        return StoreCounts(upserted=upserted, vacant=vacant, consumed=consumed, vacant_ids=vacant_ids)

    def _report_sync(self, run: AgentRunReport) -> None:
        conn = staging.connect(self.db_path)
        try:
            staging.init_staging_db(conn)
            staging.insert_agent_run(conn, run)
        finally:
            conn.close()

    def _seed_ids(self) -> set[str]:
        path = Path(self.constituencies_json)
        if not path.is_absolute():
            path = Path.cwd() / path
        data = json.loads(path.read_text(encoding="utf-8"))
        return {row["id"] for row in data}


__all__ = ["NormaliserAgent", "clean_name", "map_party", "derive_constituency_id", "PARTY_MAP"]


if __name__ == "__main__":  # python -m agents.normaliser [db_path] [--dry-run]
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    db = args[0] if args else "data/staging.db"
    dry_run = "--dry-run" in sys.argv

    async def _main() -> None:
        agent = NormaliserAgent(db_path=db)
        if dry_run:
            result, vacant = await agent.preview()
            print(f"\n[DRY RUN] {len(result.clean)} clean MLAs, {len(result.skipped)} skipped, "
                  f"{len(vacant)} vacant seats\n")
            for rec in result.clean[:10]:
                print(f"  {rec.id} {rec.constituency_id} | {rec.name:28} | {rec.party:8} | {rec.alliance}")
            if result.skipped:
                print("\n  SKIPPED:")
                for key, reason in result.skipped:
                    print(f"    {key}: {reason}")
            print(f"\n  vacant seats ({len(vacant)}): {vacant}")
        else:
            report = await agent.run()
            print(report.model_dump_json(indent=2))

    asyncio.run(_main())
