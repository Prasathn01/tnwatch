"""
Pydantic v2 response models for the TNWatch FastAPI layer (CONTEXT.md §9 Rule 1).

These are READ-side contracts (what the API returns to clients). The write-side
contracts (what agents produce) live in agents/models.py.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    mlas: int


class MLAListItem(BaseModel):
    """Slim MLA record returned by GET /mlas."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    party: str
    constituency_id: str
    constituency_name: str


class MLAListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    items: list[MLAListItem]


class MLADetail(BaseModel):
    """Full MLA record returned by GET /mlas/{id}."""

    model_config = ConfigDict(extra="forbid")

    id: str
    constituency_id: str
    constituency_name: str
    name: str
    party: str
    alliance: str | None = None
    assembly_number: int = 17
    elected_year: int | None = None
    vote_margin: int | None = None
    vote_share: Decimal | None = None
    age: int | None = None
    education: str | None = None
    profession: str | None = None
    total_assets: Decimal | None = None
    total_liabilities: Decimal | None = None
    criminal_cases: int = 0
    criminal_cases_serious: int | None = None
    is_minister: bool = False
    portfolio: str | None = None
    photo_url: str | None = None
    performance_score: Decimal | None = None
    score_breakdown: dict | None = None
    source_url: str | None = None
    last_updated: str | None = None  # ISO timestamp string from Supabase


class ConstituencyItem(BaseModel):
    """One constituency row returned by GET /constituencies."""

    # extra="ignore" because Supabase also returns created_at which the API doesn't expose
    model_config = ConfigDict(extra="ignore")

    id: str
    number: int
    name: str
    district: str
    lok_sabha_seat: str | None = None
    total_electors: int | None = None
    reserved: str
    status: str  # 'filled' | 'vacant'


class ConstituencyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    items: list[ConstituencyItem]
