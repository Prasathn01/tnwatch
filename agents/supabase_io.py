"""
Supabase I/O for the Normaliser — isolates ALL of store()'s side effects.

Kept deliberately thin (v1 = exactly these four functions) so store() reads as a
short sequence of calls whose return counts feed report(). `mark_staging_consumed`
lives here even though it writes to SQLite, not Supabase: the module's job is to
own every write store() makes, in one place.

Note on `mark_staging_consumed`: the design sketch typed it as
`row_ids: list[int]`, but `staging_mla_raw` is keyed on `staging_key` (TEXT), so
this takes `staging_keys: list[str]` — marking by the stable natural key is safer
than SQLite's mutable rowid.
"""

from __future__ import annotations

import os
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from supabase import Client

    from .models import MLACleanRecord


def create_client() -> "Client":
    """
    Build a Supabase client from `.env` (SUPABASE_URL + SUPABASE_SERVICE_KEY).
    The service-role key is server-side only and bypasses RLS. The URL is
    normalised (a stray `/rest/v1` or trailing slash is stripped) so a pasted
    REST endpoint still works.
    """
    from dotenv import load_dotenv
    from supabase import create_client as _create_client

    load_dotenv(override=True)
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    base = url.strip().split("/rest/v1")[0].rstrip("/")
    return _create_client(base, key)


def upsert_mlas(client: "Client", records: list["MLACleanRecord"]) -> int:
    """Idempotent upsert into `mlas` (keyed on PK `id`). Returns rows upserted."""
    if not records:
        return 0
    payload = [r.model_dump(mode="json") for r in records]
    resp = client.table("mlas").upsert(payload).execute()
    return len(resp.data or [])


def set_constituency_status(client: "Client", ids: list[str], status: str) -> int:
    """Set `constituencies.status` for the given ids. Returns rows updated."""
    if not ids:
        return 0
    resp = client.table("constituencies").update({"status": status}).in_("id", ids).execute()
    return len(resp.data or [])


def mark_staging_consumed(conn: sqlite3.Connection, staging_keys: list[str]) -> int:
    """Set `normalised = 1` for the given staged rows (SQLite). Returns rows marked."""
    if not staging_keys:
        return 0
    placeholders = ",".join("?" for _ in staging_keys)
    cur = conn.execute(
        f"UPDATE staging_mla_raw SET normalised = 1 WHERE staging_key IN ({placeholders})",
        staging_keys,
    )
    conn.commit()
    return cur.rowcount
