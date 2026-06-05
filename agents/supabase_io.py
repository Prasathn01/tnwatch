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
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
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


@dataclass
class MlaMatchRow:
    """Lightweight row used by eci_scraper for fuzzy matching."""
    mla_id: str
    name: str
    party: str
    constituency_name: str


@dataclass
class ECIUpdatePayload:
    """Fields to write back into the `mlas` table from ECI/MyNeta data."""
    mla_id: str
    declared_assets_cr: Decimal | None
    liabilities_cr: Decimal | None
    criminal_cases: int
    age: int | None
    education: str | None
    source_url: str  # provenance (Rule 5)


def load_mlas_for_matching(client: "Client") -> list[MlaMatchRow]:
    """
    Return all current MLAs with their constituency names for fuzzy matching.
    The constituency name comes from the joined `constituencies` table so it
    matches the Wikipedia canonical spelling used in eci_scraper's match step.
    """
    resp = (
        client.table("mlas")
        .select("id, name, party, constituencies(name)")
        .execute()
    )
    rows: list[MlaMatchRow] = []
    for row in resp.data or []:
        cname = (row.get("constituencies") or {}).get("name") or ""
        rows.append(MlaMatchRow(
            mla_id=row["id"],
            name=row["name"],
            party=row["party"],
            constituency_name=cname,
        ))
    return rows


def update_mla_eci(client: "Client", payload: ECIUpdatePayload) -> int:
    """
    Update a single `mlas` row with ECI-sourced enrichment fields.
    Uses UPDATE (not upsert) — only enriches existing rows, never creates new ones.
    Returns 1 on success, 0 if the mla_id was not found.

    NOTE: `criminal_cases_serious` and `candidate_id_eci` are stored in eci_staging
    but require a schema migration before they can be pushed here:
        ALTER TABLE mlas ADD COLUMN criminal_cases_serious int DEFAULT 0;
        ALTER TABLE mlas ADD COLUMN candidate_id_eci text;
    Run that migration in Supabase SQL editor, then add them to the dict below.
    """
    data: dict = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    if payload.declared_assets_cr is not None:
        data["declared_assets_cr"] = str(payload.declared_assets_cr)
    if payload.liabilities_cr is not None:
        data["liabilities_cr"] = str(payload.liabilities_cr)
    # criminal_cases: always write (0 is a valid value)
    data["criminal_cases"] = payload.criminal_cases
    if payload.age is not None:
        data["age"] = payload.age
    if payload.education is not None:
        data["education"] = payload.education

    resp = client.table("mlas").update(data).eq("id", payload.mla_id).execute()
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
