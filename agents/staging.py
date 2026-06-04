"""
Local SQLite staging DB — the "dirty data" landing zone (CONTEXT.md §5).

The scraper writes raw rows here first; the Normaliser later reads pending rows,
cleans them, and pushes to Supabase. `agent_runs` is mirrored locally too so an
agent's report() is runnable end-to-end before Supabase creds are wired (in
production report() targets the Supabase `agent_runs` table).

sqlite3 is synchronous; the agent calls these via asyncio.to_thread so the async
event loop is never blocked (CONTEXT.md §9 Rule 2).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .models import AgentRunReport, RawMLARecord

STAGING_MLA_RAW_DDL = """
CREATE TABLE IF NOT EXISTS staging_mla_raw (
    staging_key             TEXT PRIMARY KEY,   -- 'members_list:AC-014' (idempotency key)
    constituency_number_raw TEXT,
    constituency_name_raw   TEXT,
    district_raw            TEXT,
    mla_name_raw            TEXT,
    mla_wiki_url            TEXT,
    party_raw               TEXT,
    alliance_raw            TEXT,
    remarks_raw             TEXT,
    source_url              TEXT NOT NULL,       -- Rule 5
    source_page_type        TEXT NOT NULL,
    scraped_at              TEXT NOT NULL,       -- ISO-8601
    normalised              INTEGER NOT NULL DEFAULT 0  -- 0=pending, 1=consumed by Normaliser
);
"""

STAGING_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_staging_mla_raw_pending ON staging_mla_raw (normalised);"
)

AGENT_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name    TEXT NOT NULL,
    status        TEXT NOT NULL,                 -- success|partial|failed
    rows_written  INTEGER DEFAULT 0,
    error_message TEXT,
    started_at    TEXT,
    finished_at   TEXT
);
"""

_UPSERT_SQL = """
INSERT INTO staging_mla_raw (
    staging_key, constituency_number_raw, constituency_name_raw, district_raw,
    mla_name_raw, mla_wiki_url, party_raw, alliance_raw, remarks_raw,
    source_url, source_page_type, scraped_at, normalised
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
ON CONFLICT(staging_key) DO UPDATE SET
    constituency_number_raw = excluded.constituency_number_raw,
    constituency_name_raw   = excluded.constituency_name_raw,
    district_raw            = excluded.district_raw,
    mla_name_raw            = excluded.mla_name_raw,
    mla_wiki_url            = excluded.mla_wiki_url,
    party_raw               = excluded.party_raw,
    alliance_raw            = excluded.alliance_raw,
    remarks_raw             = excluded.remarks_raw,
    source_url              = excluded.source_url,
    source_page_type        = excluded.source_page_type,
    scraped_at              = excluded.scraped_at,
    normalised              = 0;                  -- re-staged rows become pending again
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row access by column name and FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_staging_db(conn: sqlite3.Connection) -> None:
    """Create staging tables if absent. Idempotent."""
    conn.execute(STAGING_MLA_RAW_DDL)
    conn.execute(STAGING_INDEX_DDL)
    conn.execute(AGENT_RUNS_DDL)
    conn.commit()


def upsert_raw_mla(conn: sqlite3.Connection, records: Iterable[RawMLARecord]) -> int:
    """
    Idempotent upsert of raw records keyed on staging_key (Rule 8): re-running the
    scraper refreshes rows in place, never duplicates. Returns rows written.
    """
    params = [
        (
            r.staging_key, r.constituency_number_raw, r.constituency_name_raw, r.district_raw,
            r.mla_name_raw, r.mla_wiki_url, r.party_raw, r.alliance_raw, r.remarks_raw,
            r.source_url, r.source_page_type.value, r.scraped_at.isoformat(),
        )
        for r in records
    ]
    cur = conn.executemany(_UPSERT_SQL, params)
    conn.commit()
    return cur.rowcount if cur.rowcount != -1 else len(params)


def insert_agent_run(conn: sqlite3.Connection, report: AgentRunReport) -> None:
    """Append one row to the local agent_runs audit table (CONTEXT.md §6)."""
    conn.execute(
        "INSERT INTO agent_runs (agent_name, status, rows_written, error_message, started_at, finished_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            report.agent_name, report.status, report.rows_written, report.error_message,
            report.started_at.isoformat(),
            report.finished_at.isoformat() if report.finished_at else None,
        ),
    )
    conn.commit()
