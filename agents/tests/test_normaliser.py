"""
Tests for the Normaliser Agent (CONTEXT.md §9 Rule 11).

Offline + deterministic: cleaning rules are pure functions; store() runs against a
stub Supabase client and a temp SQLite DB, so nothing hits the network.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents import staging
from agents.mla_scraper import MEMBERS_URL, MLAScraperAgent
from agents.models import FetchedPage, RawMLARecord, SourcePageType
from agents.normaliser import (
    NormaliserAgent,
    clean_name,
    derive_constituency_id,
    derive_vacant_ids,
    map_party,
)

FIXTURES = Path(__file__).parent / "fixtures"
MEMBERS_FIXTURE = FIXTURES / "members_table.html"
ALL_SEAT_IDS = {f"AC-{n:03d}" for n in range(1, 235)}


def _raw(**kw) -> RawMLARecord:
    base = dict(
        constituency_number_raw="14",
        mla_name_raw="S. Raja",
        party_raw="DMK",
        alliance_raw="DMK+",
        source_url=MEMBERS_URL,
        source_page_type=SourcePageType.MEMBERS_LIST,
        scraped_at=datetime.now(timezone.utc),
        staging_key="members_list:AC-014",
    )
    base.update(kw)
    return RawMLARecord(**base)


# --- cleaning rules -------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Thiru S. Raja[a]", "S. Raja"),
        ("Dr. M. K.  Stalin", "M. K. Stalin"),
        ("Tmt.\xa0Geetha *", "Geetha"),
        ("  P.\tSathyabama †", "P. Sathyabama"),
        ("ARUNKUMAR", "Arunkumar"),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Indian National Congress", "INC"),
        ("CPM", "CPI(M)"),
        ("CPI(M)", "CPI(M)"),
        ("Independent", "IND"),
        ("DMK", "DMK"),
    ],
)
def test_map_party_canonicalises(raw, expected):
    assert map_party(raw) == expected


def test_map_party_unmapped_passes_through_with_warning(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        assert map_party("ZZZ Party") == "ZZZ Party"  # not in map -> as-is
    assert any("Unmapped party" in r.message for r in caplog.records)


def test_derive_constituency_id():
    assert derive_constituency_id("14") == "AC-014"
    assert derive_constituency_id(" 7 ") == "AC-007"
    with pytest.raises(ValueError):
        derive_constituency_id("not-a-number")


# --- parse / validation ---------------------------------------------------------

def test_parse_happy_path():
    result = NormaliserAgent(db_path=":memory:").parse([_raw()])
    assert len(result.clean) == 1
    rec = result.clean[0]
    assert rec.id == "MLA-014"
    assert rec.constituency_id == "AC-014"
    assert rec.name == "S. Raja"
    assert rec.party == "DMK"
    assert rec.alliance == "DMK+"
    assert rec.source_url == MEMBERS_URL
    assert result.consumed_keys == ["members_list:AC-014"]
    assert result.skipped == []


def test_parse_skips_unparseable_constituency_number():
    result = NormaliserAgent(db_path=":memory:").parse(
        [_raw(constituency_number_raw="N/A", staging_key="members_list:bad")]
    )
    assert result.clean == []
    assert result.skipped and "unparseable" in result.skipped[0][1]


def test_parse_skips_blank_source_url():
    # source_url is required + non-empty in the model; whitespace must fail validation.
    result = NormaliserAgent(db_path=":memory:").parse([_raw(source_url="   ")])
    assert result.clean == []
    assert result.skipped and "validation" in result.skipped[0][1]


# --- vacancy derivation ---------------------------------------------------------

def test_derive_vacant_ids():
    staged = ALL_SEAT_IDS - {"AC-035", "AC-101", "AC-103", "AC-141", "AC-225"}
    assert derive_vacant_ids(ALL_SEAT_IDS, staged) == ["AC-035", "AC-101", "AC-103", "AC-141", "AC-225"]


def test_integration_from_scraper_output_yields_229_and_5_vacant():
    page = FetchedPage(
        url=MEMBERS_URL, page_type=SourcePageType.MEMBERS_LIST,
        html=MEMBERS_FIXTURE.read_text(encoding="utf-8"),
        fetched_at=datetime.now(timezone.utc), http_status=200,
    )
    raw = MLAScraperAgent(db_path=":memory:").parse([page])
    result = NormaliserAgent(db_path=":memory:").parse(raw)
    assert len(result.clean) == 229
    assert result.skipped == []
    staged = {r.constituency_id for r in result.clean}
    assert derive_vacant_ids(ALL_SEAT_IDS, staged) == ["AC-035", "AC-101", "AC-103", "AC-141", "AC-225"]


# --- store() against a stub Supabase client ------------------------------------

class _StubResp:
    def __init__(self, data):
        self.data = data


class _StubQuery:
    def __init__(self, table):
        self._table = table
        self._payload = None
        self._filter_ids = None

    def upsert(self, payload):
        self._payload = payload
        self._table.upserted.extend(payload)
        return self

    def update(self, values):
        self._values = values
        return self

    def in_(self, _col, ids):
        self._filter_ids = ids
        self._table.status_updates.append((self._values["status"], list(ids)))
        return self

    def execute(self):
        if self._payload is not None:
            return _StubResp(self._payload)
        return _StubResp([{"id": i} for i in (self._filter_ids or [])])


class _StubTable:
    def __init__(self):
        self.upserted = []
        self.status_updates = []

    def __call__(self, _name):
        return _StubQuery(self)


class _StubClient:
    def __init__(self):
        self._mlas = _StubTable()
        self._const = _StubTable()

    def table(self, name):
        return (self._mlas if name == "mlas" else self._const).__call__(name)


async def test_store_pushes_marks_and_flips(tmp_path):
    # seed file with all 234 ids
    seed = tmp_path / "constituencies.json"
    import json
    seed.write_text(json.dumps([{"id": i} for i in sorted(ALL_SEAT_IDS)]), encoding="utf-8")

    # stage 229 sitting MLAs from the scraper fixture
    db = str(tmp_path / "staging.db")
    page = FetchedPage(
        url=MEMBERS_URL, page_type=SourcePageType.MEMBERS_LIST,
        html=MEMBERS_FIXTURE.read_text(encoding="utf-8"),
        fetched_at=datetime.now(timezone.utc), http_status=200,
    )
    scraper = MLAScraperAgent(db_path=db)
    await scraper.store(scraper.parse([page]))

    stub = _StubClient()
    agent = NormaliserAgent(db_path=db, client=stub, constituencies_json=str(seed))
    result = agent.parse(await agent.fetch())
    counts = await agent.store(result)

    assert counts.upserted == 229
    assert counts.vacant == 5
    assert counts.consumed == 229
    assert counts.vacant_ids == ["AC-035", "AC-101", "AC-103", "AC-141", "AC-225"]

    # staging rows now consumed -> a second fetch sees nothing pending
    assert await agent.fetch() == []

    conn = staging.connect(db)
    try:
        pending = conn.execute("SELECT COUNT(*) n FROM staging_mla_raw WHERE normalised = 0").fetchone()["n"]
    finally:
        conn.close()
    assert pending == 0
