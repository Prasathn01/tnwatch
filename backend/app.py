"""
TNWatch FastAPI backend — Slice #1 (MLA Profiles & Performance).

Routes
------
GET /health            → HealthResponse
GET /mlas              → MLAListResponse  (filters: ?district=, ?party=)
GET /mlas/{id}         → MLADetail
GET /constituencies    → ConstituencyListResponse

Rules (CONTEXT.md §9)
-----
- Async throughout: every route is async def, every DB call is awaited.
- Typed responses: every route declares a response_model; no raw dicts.
- No secrets in code: DB credentials come from .env via db.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import close_client, get_client, init_client
from .models import (
    ConstituencyItem,
    ConstituencyListResponse,
    HealthResponse,
    MLADetail,
    MLAListItem,
    MLAListResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_client()
    yield
    await close_client()


app = FastAPI(
    title="TNWatch API",
    description="Civic accountability data for Tamil Nadu — MLAs, constituencies, performance.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness check. Also returns the current MLA count."""
    db = get_client()
    resp = await db.table("mlas").select("id", count="exact").execute()
    return HealthResponse(status="ok", mlas=resp.count or 0)


@app.get("/mlas", response_model=MLAListResponse)
async def list_mlas(
    district: str | None = Query(default=None, description="Filter by district name, e.g. Chennai"),
    party: str | None = Query(default=None, description="Filter by party name, e.g. DMK"),
) -> MLAListResponse:
    """
    List all MLAs. Optionally filter by district and/or party.

    Filtering by district requires a sub-query to resolve constituency IDs first;
    this avoids the fragility of PostgREST embedded-resource filter syntax.
    """
    db = get_client()

    constituency_ids: list[str] | None = None
    if district:
        c_resp = await db.table("constituencies").select("id").eq("district", district).execute()
        if not c_resp.data:
            return MLAListResponse(count=0, items=[])
        constituency_ids = [row["id"] for row in c_resp.data]

    q = db.table("mlas").select("id, name, party, constituency_id, constituencies(name)")
    if party:
        q = q.eq("party", party)
    if constituency_ids is not None:
        q = q.in_("constituency_id", constituency_ids)

    resp = await q.execute()
    items = [
        MLAListItem(
            id=row["id"],
            name=row["name"],
            party=row["party"],
            constituency_id=row["constituency_id"],
            constituency_name=(row.get("constituencies") or {}).get("name", ""),
        )
        for row in (resp.data or [])
    ]
    return MLAListResponse(count=len(items), items=items)


@app.get("/mlas/{mla_id}", response_model=MLADetail)
async def get_mla(mla_id: str) -> MLADetail:
    """Fetch a single MLA's full record including constituency name."""
    db = get_client()
    resp = await db.table("mlas").select("*, constituencies(name)").eq("id", mla_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail=f"MLA '{mla_id}' not found")
    row = dict(resp.data[0])
    constituency_name = (row.pop("constituencies", None) or {}).get("name", "")
    return MLADetail(**row, constituency_name=constituency_name)


@app.get("/constituencies", response_model=ConstituencyListResponse)
async def list_constituencies() -> ConstituencyListResponse:
    """List all 234 constituencies with their current filled/vacant status."""
    db = get_client()
    resp = await db.table("constituencies").select("*").order("number").execute()
    items = [ConstituencyItem(**row) for row in (resp.data or [])]
    return ConstituencyListResponse(count=len(items), items=items)
