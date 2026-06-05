"""
Pytest tests for the TNWatch FastAPI backend.

All Supabase I/O is mocked so tests run without a live DB or .env file.
Each test configures the mock builder to return the exact data it needs,
then asserts on the JSON response.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resp(data: list[dict] | None = None, count: int | None = None) -> MagicMock:
    """Build a fake Supabase APIResponse."""
    r = MagicMock()
    r.data = data or []
    r.count = count
    return r


def _make_builder(response: MagicMock) -> MagicMock:
    """Return a mock PostgREST builder whose .execute() returns *response*."""
    b = MagicMock()
    b.select.return_value = b
    b.eq.return_value = b
    b.in_.return_value = b
    b.order.return_value = b
    b.execute = AsyncMock(return_value=response)
    return b


def _mock_client(builder: MagicMock) -> MagicMock:
    db = MagicMock()
    db.table.return_value = builder
    return db


# ---------------------------------------------------------------------------
# Fixture: async HTTP client with Supabase mocked out
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def ac():
    """
    Yield an httpx.AsyncClient pointed at the FastAPI app.
    The lifespan is bypassed (init_client / close_client are no-ops) so tests
    don't need a real Supabase connection.
    """
    with (
        patch("backend.db.init_client", new_callable=AsyncMock),
        patch("backend.db.close_client", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_ok(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[], count=229))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mlas"] == 229


@pytest.mark.asyncio
async def test_health_zero_mlas(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[], count=0))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json()["mlas"] == 0


# ---------------------------------------------------------------------------
# GET /mlas
# ---------------------------------------------------------------------------

_MLA_ROW: dict[str, Any] = {
    "id": "MLA-001",
    "name": "Test MLA",
    "party": "DMK",
    "constituency_id": "AC-001",
    "constituencies": {"name": "Harbour"},
}


@pytest.mark.asyncio
async def test_list_mlas_no_filter(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[_MLA_ROW]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/mlas")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["items"][0]["constituency_name"] == "Harbour"


@pytest.mark.asyncio
async def test_list_mlas_party_filter(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[_MLA_ROW]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/mlas?party=DMK")
    assert r.status_code == 200
    builder.eq.assert_called_with("party", "DMK")


@pytest.mark.asyncio
async def test_list_mlas_district_filter_no_constituencies(ac: AsyncClient) -> None:
    """When district matches no constituencies, return empty list immediately."""
    # First call (constituencies) returns empty, second call should not happen
    builder = _make_builder(_resp(data=[]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/mlas?district=Nonexistent")
    assert r.status_code == 200
    assert r.json() == {"count": 0, "items": []}


@pytest.mark.asyncio
async def test_list_mlas_district_filter_found(ac: AsyncClient) -> None:
    """District filter resolves constituency IDs then queries mlas."""
    db = MagicMock()

    const_builder = _make_builder(_resp(data=[{"id": "AC-001"}, {"id": "AC-002"}]))
    mla_builder = _make_builder(_resp(data=[_MLA_ROW]))

    call_count = 0

    def table_side_effect(name: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        return const_builder if name == "constituencies" else mla_builder

    db.table.side_effect = table_side_effect

    with patch("backend.app.get_client", return_value=db):
        r = await ac.get("/mlas?district=Chennai")
    assert r.status_code == 200
    assert r.json()["count"] == 1
    mla_builder.in_.assert_called_once_with("constituency_id", ["AC-001", "AC-002"])


# ---------------------------------------------------------------------------
# GET /mlas/{id}
# ---------------------------------------------------------------------------

_FULL_MLA_ROW: dict[str, Any] = {
    "id": "MLA-014",
    "name": "Full MLA",
    "party": "AIADMK",
    "constituency_id": "AC-014",
    "constituencies": {"name": "Villivakkam"},
    "alliance": None,
    "assembly_number": 17,
    "elected_year": 2026,
    "vote_margin": 5000,
    "vote_share_pct": "52.30",
    "age": 55,
    "education": "B.Sc",
    "profession": "Politician",
    "declared_assets_cr": "10.50",
    "liabilities_cr": "2.00",
    "criminal_cases": 0,
    "is_minister": False,
    "portfolio": None,
    "photo_url": None,
    "performance_score": None,
    "source_url": "https://en.wikipedia.org/wiki/Villivakkam",
    "last_updated": "2026-06-05T10:00:00+00:00",
}


@pytest.mark.asyncio
async def test_get_mla_found(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[_FULL_MLA_ROW]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/mlas/MLA-014")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "MLA-014"
    assert body["constituency_name"] == "Villivakkam"
    assert body["vote_share_pct"] == "52.30"


@pytest.mark.asyncio
async def test_get_mla_not_found(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/mlas/MLA-999")
    assert r.status_code == 404
    assert "MLA-999" in r.json()["detail"]


# ---------------------------------------------------------------------------
# GET /constituencies
# ---------------------------------------------------------------------------

_CONST_ROW: dict[str, Any] = {
    "id": "AC-001",
    "number": 1,
    "name": "Harbour",
    "district": "Chennai",
    "lok_sabha_seat": "Chennai South",
    "total_electors": 120000,
    "reserved": "GEN",
    "status": "filled",
    "created_at": "2026-06-04T00:00:00+00:00",
}


@pytest.mark.asyncio
async def test_list_constituencies(ac: AsyncClient) -> None:
    builder = _make_builder(_resp(data=[_CONST_ROW]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/constituencies")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == "AC-001"
    assert item["status"] == "filled"


@pytest.mark.asyncio
async def test_list_constituencies_vacant_status(ac: AsyncClient) -> None:
    vacant = {**_CONST_ROW, "id": "AC-100", "number": 100, "status": "vacant"}
    builder = _make_builder(_resp(data=[vacant]))
    with patch("backend.app.get_client", return_value=_mock_client(builder)):
        r = await ac.get("/constituencies")
    assert r.status_code == 200
    assert r.json()["items"][0]["status"] == "vacant"
