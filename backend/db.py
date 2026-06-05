"""
Async Supabase client helper for the FastAPI backend.

The client is a process-wide singleton initialised once during app lifespan
(CONTEXT.md §9 Rule 6: no secrets in code — reads from .env only).

Usage in routes:
    db = get_client()
    resp = await db.table("mlas").select("*").execute()
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from supabase import AsyncClient, acreate_client

_client: AsyncClient | None = None


async def init_client() -> None:
    """Create and cache the Supabase async client. Call once at app startup."""
    global _client
    load_dotenv(override=True)
    raw_url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not raw_url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    # Strip /rest/v1 suffix if someone pasted the REST endpoint URL
    url = raw_url.strip().split("/rest/v1")[0].rstrip("/")
    _client = await acreate_client(url, key)


async def close_client() -> None:
    """Release the client reference on app shutdown."""
    global _client
    _client = None


def get_client() -> AsyncClient:
    """Return the cached async client. Raises if init_client() was not called."""
    if _client is None:
        raise RuntimeError("Supabase client is not initialised — call init_client() first")
    return _client
