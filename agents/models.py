"""
Pydantic v2 data contracts for Slice #1 (CONTEXT.md §9 Rule 1: no loose dicts).

Three layers, deliberately separated:
- RawMLARecord     dirty scraped text -> SQLite staging (untyped values, all str)
- MLACleanRecord   validated row matching the `mlas` table (Normaliser emits this)
- Constituency     validated row matching the `constituencies` table (seed script)

The scraper produces RawMLARecord only. MLACleanRecord/Constituency are the
downstream/seed contracts, defined here so both ends agree on the shape.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourcePageType(str, Enum):
    """Which kind of Wikipedia page a raw row came from."""

    MEMBERS_LIST = "members_list"            # 17th_Tamil_Nadu_Assembly members table
    CONSTITUENCY_PAGE = "constituency_page"  # per-constituency article (v2 enrichment)


class FetchedPage(BaseModel):
    """Raw output of an agent's fetch(): one downloaded page + provenance."""

    model_config = ConfigDict(extra="forbid")

    url: str
    page_type: SourcePageType
    html: str
    fetched_at: datetime
    http_status: int


class RawMLARecord(BaseModel):
    """
    One scraped member row as it came off Wikipedia — UNTRUSTED, UNPARSED.
    Every value field is str|None on purpose: numbers keep commas, names keep
    honorifics, party keeps wiki-link text. Typing/cleaning is the Normaliser's
    job, never the scraper's. This is the contract for the `staging_mla_raw` table.
    """

    model_config = ConfigDict(extra="forbid")

    # extracted text (all raw)
    constituency_number_raw: str | None = None
    constituency_name_raw: str | None = None
    district_raw: str | None = None
    mla_name_raw: str | None = None
    mla_wiki_url: str | None = None          # link to the member's wiki page (None for redlinks)
    party_raw: str | None = None
    alliance_raw: str | None = None
    remarks_raw: str | None = None           # defection/resignation notes; informs is_current

    # provenance (mandatory — Rule 5)
    source_url: str = Field(..., description="Exact Wikipedia URL this row came from")
    source_page_type: SourcePageType
    scraped_at: datetime

    # stable natural key for idempotent upsert (Rule 8): 'members_list:AC-014'
    staging_key: str


class MLACleanRecord(BaseModel):
    """
    Validated MLA row matching the `mlas` table (CONTEXT.md §6). The Normaliser
    emits this and the Validator enforces it before push to Supabase. The scraper
    only fills Wikipedia-derivable fields; ECI/PRS/scorer fields stay None/default.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^MLA-\d{3}$")
    constituency_id: str = Field(..., pattern=r"^AC-\d{3}$")
    name: str = Field(..., min_length=1)

    # Wikipedia-derivable
    party: str = Field(..., min_length=1)     # scraped, never hardcoded
    alliance: str | None = None
    assembly_number: int = 17
    elected_year: int | None = None
    vote_margin: int | None = None
    vote_share_pct: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)

    # enriched by later agents — None/default for now
    age: int | None = None
    education: str | None = None
    profession: str | None = None
    declared_assets_cr: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    liabilities_cr: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    criminal_cases: int = 0
    is_minister: bool = False
    portfolio: str | None = None
    photo_url: str | None = None
    performance_score: Decimal | None = Field(default=None, max_digits=5, decimal_places=1)

    # provenance for the base profile (Rule 5; mlas.source_url added this slice)
    source_url: str = Field(..., min_length=1)

    @field_validator("vote_share_pct")
    @classmethod
    def _share_in_range(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and not (Decimal(0) <= v <= Decimal(100)):
            raise ValueError("vote_share_pct must be between 0 and 100")
        return v

    @field_validator("source_url")
    @classmethod
    def _source_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_url must be a non-empty URL (Rule 5: no source, no store)")
        return v


class Constituency(BaseModel):
    """
    Validated row matching the `constituencies` table (CONTEXT.md §6). Produced by
    scripts/seed_constituencies.py from the Wikipedia constituencies list — loaded
    ONCE; the MLA scraper assumes these rows already exist and links to them.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=r"^AC-\d{3}$")
    number: int = Field(..., ge=1, le=234)
    name: str = Field(..., min_length=1)
    district: str = Field(..., min_length=1)
    lok_sabha_seat: str | None = None
    total_electors: int | None = Field(default=None, ge=0)
    reserved: str = "GEN"
    status: str = "filled"  # 'filled' | 'vacant'; vacancy is set later by the Normaliser

    @field_validator("reserved")
    @classmethod
    def _known_reservation(cls, v: str) -> str:
        if v not in {"GEN", "SC", "ST"}:
            raise ValueError(f"reserved must be GEN|SC|ST, got {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in {"filled", "vacant"}:
            raise ValueError(f"status must be filled|vacant, got {v!r}")
        return v


class AgentRunReport(BaseModel):
    """In-memory mirror of one `agent_runs` row (CONTEXT.md §6)."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    status: str  # 'success' | 'partial' | 'failed'
    rows_written: int = 0
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in {"success", "partial", "failed"}:
            raise ValueError(f"status must be success|partial|failed, got {v!r}")
        return v
