"""
Tests for the MLA Scraper Agent (CONTEXT.md §9 Rule 11: tests alongside code).

Offline + deterministic: parses a saved HTML fixture of the real Wikipedia
members table (agents/tests/fixtures/members_table.html), so the test never hits
the network and pins the vacant-seat / duplicate-seat behaviour found via the probe.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents import staging
from agents.mla_scraper import MLAScraperAgent, MEMBERS_URL
from agents.models import FetchedPage, SourcePageType

FIXTURES = Path(__file__).parent / "fixtures"
MEMBERS_FIXTURE = FIXTURES / "members_table.html"
CONSTITUENCIES_FIXTURE = FIXTURES / "constituencies_table.html"

# From the probe: 234 seats, 5 currently vacant (resigned), 1 seat (167) listed
# twice for a party switch -> 229 currently-sitting MLAs staged.
EXPECTED_SITTING = 229
VACANT_SEATS = {35, 101, 103, 141, 225}


def _page() -> FetchedPage:
    return FetchedPage(
        url=MEMBERS_URL,
        page_type=SourcePageType.MEMBERS_LIST,
        html=MEMBERS_FIXTURE.read_text(encoding="utf-8"),
        fetched_at=datetime.now(timezone.utc),
        http_status=200,
    )


@pytest.fixture
def records():
    return MLAScraperAgent(db_path=":memory:").parse([_page()])


def test_parses_one_row_per_sitting_seat(records):
    numbers = [int(r.constituency_number_raw) for r in records]
    assert len(records) == EXPECTED_SITTING
    assert len(set(numbers)) == len(numbers), "constituency numbers must be unique"
    assert min(numbers) == 1 and max(numbers) == 234


def test_vacant_seats_are_skipped(records):
    staged = {int(r.constituency_number_raw) for r in records}
    assert VACANT_SEATS.isdisjoint(staged), "currently-vacant seats must not be staged"
    assert all("vacant" not in (r.mla_name_raw or "").lower() for r in records)


def test_duplicate_seat_keeps_most_current_row(records):
    # Mannargudi (167): AMMK row then IND row after expulsion -> keep IND.
    seat_167 = next(r for r in records if r.constituency_number_raw == "167")
    assert seat_167.party_raw == "IND"


def test_known_row_is_correct(records):
    seat_1 = next(r for r in records if r.constituency_number_raw == "1")
    assert seat_1.constituency_name_raw == "Gummidipoondi"
    assert seat_1.mla_name_raw == "S. Vijayakumar"
    assert seat_1.party_raw == "TVK"
    assert seat_1.alliance_raw == "TVK+"
    assert seat_1.district_raw == "Tiruvallur"  # carried via rowspan from grid expansion
    assert seat_1.staging_key == "members_list:AC-001"
    assert seat_1.source_url == MEMBERS_URL


def test_selects_members_table_not_council_of_ministers():
    # Guards the live bug: the Council of Ministers table also has
    # constituency/name/party headers and appears earlier on the page.
    from agents.mla_scraper import MEMBERS_TABLE_HEADERS
    from agents.wikitable import cell_text, find_wikitable, table_to_grid

    html = """
    <table class="wikitable"><tr><th>Sr. No.</th><th>Name</th><th>Constituency</th>
      <th>Designation</th><th>Party</th></tr>
      <tr><td>1</td><td>Some Minister</td><td>Perambur</td><td>CM</td><td>TVK</td></tr></table>
    <table class="wikitable"><tr><th>District</th><th>No.</th><th>Constituency</th>
      <th>Name</th><th>Party</th><th>Alliance</th><th>Remarks</th></tr>
      <tr><td>Chennai</td><td>7</td><td>Maduravoyal</td><td>P. Charan</td>
      <td>TVK</td><td>TVK+</td><td></td></tr></table>
    """
    table = find_wikitable(html, contains_headers=MEMBERS_TABLE_HEADERS)
    headers = [cell_text(c).lower() for c in table_to_grid(table)[0]]
    assert "alliance" in headers and "remarks" in headers
    assert "designation" not in headers


def test_every_record_is_sourced(records):
    # Rule 5: no source, no store.
    assert all(r.source_url for r in records)
    assert all(r.staging_key.startswith("members_list:AC-") for r in records)


async def test_store_is_idempotent(tmp_path, records):
    db = str(tmp_path / "staging.db")
    agent = MLAScraperAgent(db_path=db)

    first = await agent.store(records)
    second = await agent.store(records)  # re-run must not duplicate (Rule 8)
    assert first == len(records)
    assert second == len(records)

    conn = staging.connect(db)
    try:
        total = conn.execute("SELECT COUNT(*) AS n FROM staging_mla_raw").fetchone()["n"]
    finally:
        conn.close()
    assert total == len(records)


async def test_report_writes_agent_run(tmp_path):
    db = str(tmp_path / "staging.db")
    agent = MLAScraperAgent(db_path=db)
    # parse+store from fixture, then report a synthetic run
    await agent.store(agent.parse([_page()]))

    from agents.models import AgentRunReport

    await agent.report(
        AgentRunReport(
            agent_name=agent.AGENT_NAME,
            status="success",
            rows_written=EXPECTED_SITTING,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
    )
    conn = staging.connect(db)
    try:
        row = conn.execute(
            "SELECT agent_name, status, rows_written FROM agent_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row["agent_name"] == "mla_scraper"
    assert row["status"] == "success"
    assert row["rows_written"] == EXPECTED_SITTING


# --- seed script (constituencies) sanity, same grid machinery ---

def _load_seed_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_constituencies.py"
    spec = importlib.util.spec_from_file_location("seed_constituencies", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_parses_234_constituencies():
    seed = _load_seed_module()
    rows = seed.parse_constituencies(CONSTITUENCIES_FIXTURE.read_text(encoding="utf-8"))
    assert len(rows) == 234
    ids = {r.id for r in rows}
    assert "AC-001" in ids and "AC-234" in ids
    first = next(r for r in rows if r.number == 1)
    assert first.name == "Gummidipoondi"
    assert first.district == "Thiruvallur"
    assert first.total_electors and first.total_electors > 0
    assert {r.reserved for r in rows} <= {"GEN", "SC", "ST"}
