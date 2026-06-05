"""
Tests for the Score Calculator Agent (CONTEXT.md §9 Rule 11).

Offline + deterministic: calculate_score() is a pure function; all tests run
without Supabase credentials. The ScoreCalculatorAgent I/O methods are tested
via a stub client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.score_calculator import (
    BASE_SCORE,
    OTHER_DEDUCTION_CAP,
    SCORE_VERSION,
    SERIOUS_DEDUCTION_CAP,
    ScoreCalculatorAgent,
    ScoreResult,
    calculate_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score(
    mla_id: str = "MLA-001",
    criminal_cases: int = 0,
    criminal_cases_serious: int = 0,
    declared_assets_cr: Decimal | None = None,
) -> ScoreResult:
    return calculate_score(mla_id, criminal_cases, criminal_cases_serious, declared_assets_cr)


# ---------------------------------------------------------------------------
# calculate_score — happy-path cases
# ---------------------------------------------------------------------------

def test_clean_mla_scores_base():
    r = _score(criminal_cases=0, criminal_cases_serious=0)
    assert r.score == BASE_SCORE


def test_one_serious_case():
    r = _score(criminal_cases=1, criminal_cases_serious=1)
    assert r.score == 45  # 60 - 15


def test_one_other_case():
    r = _score(criminal_cases=1, criminal_cases_serious=0)
    assert r.score == 55  # 60 - 5


def test_mixed_cases():
    r = _score(criminal_cases=3, criminal_cases_serious=1)
    # serious: 1 * -15 = -15 (no cap)
    # other:   2 * -5  = -10 (no cap)
    assert r.score == 35  # 60 - 25


# ---------------------------------------------------------------------------
# calculate_score — cap enforcement
# ---------------------------------------------------------------------------

def test_serious_cases_capped():
    # 3 * -15 = -45, but cap is -40
    r = _score(criminal_cases=3, criminal_cases_serious=3)
    assert r.score == 20  # 60 - 40
    assert r.breakdown["criminal_deduction"]["serious_deduction_applied"] == SERIOUS_DEDUCTION_CAP


def test_other_cases_capped():
    # 5 * -5 = -25, but cap is -20
    r = _score(criminal_cases=5, criminal_cases_serious=0)
    assert r.score == 40  # 60 - 20
    assert r.breakdown["criminal_deduction"]["other_deduction_applied"] == OTHER_DEDUCTION_CAP


def test_both_caps_applied():
    # serious: 10 cases → cap -40
    # other:   10 cases → cap -20
    # total deduction: -60 → final = max(0, 60-60) = 0
    r = _score(criminal_cases=20, criminal_cases_serious=10)
    assert r.score == 0


def test_score_never_below_zero():
    # Need both caps to hit zero: serious (-40) + other (-20) = -60 → 60-60=0
    r = _score(criminal_cases=1000, criminal_cases_serious=500)
    assert r.score == 0


def test_score_never_above_100():
    # No mechanism to boost above 60 in v0.1; just assert the clamp exists
    r = _score()
    assert r.score <= 100


# ---------------------------------------------------------------------------
# calculate_score — asset flag
# ---------------------------------------------------------------------------

def test_high_wealth_flag_set():
    r = _score(declared_assets_cr=Decimal("15"))
    assert r.breakdown["asset_flag"]["high_wealth_flag"] is True


def test_high_wealth_flag_not_set_below_threshold():
    r = _score(declared_assets_cr=Decimal("9.99"))
    assert r.breakdown["asset_flag"]["high_wealth_flag"] is False


def test_high_wealth_flag_not_set_exactly_at_threshold():
    # threshold is > 10, so exactly 10 is NOT flagged
    r = _score(declared_assets_cr=Decimal("10"))
    assert r.breakdown["asset_flag"]["high_wealth_flag"] is False


def test_asset_flag_no_score_deduction():
    r_with_assets = _score(declared_assets_cr=Decimal("50"))
    r_without_assets = _score(declared_assets_cr=None)
    assert r_with_assets.score == r_without_assets.score


def test_asset_none_no_flag():
    r = _score(declared_assets_cr=None)
    assert r.breakdown["asset_flag"]["high_wealth_flag"] is False
    assert r.breakdown["asset_flag"]["declared_assets_cr"] is None


# ---------------------------------------------------------------------------
# calculate_score — breakdown structure (receipts)
# ---------------------------------------------------------------------------

def test_breakdown_has_source():
    r = _score(criminal_cases=2, criminal_cases_serious=1)
    assert "source" in r.breakdown["criminal_deduction"]
    assert "myneta" in r.breakdown["criminal_deduction"]["source"].lower()


def test_breakdown_preserves_counts():
    r = _score(criminal_cases=5, criminal_cases_serious=2)
    cd = r.breakdown["criminal_deduction"]
    assert cd["serious_cases_count"] == 2
    assert cd["other_cases_count"] == 3


def test_breakdown_final_score_matches_result():
    r = _score(criminal_cases=2, criminal_cases_serious=1)
    assert r.breakdown["final_score"] == r.score


def test_score_version_set():
    r = _score()
    assert r.version == SCORE_VERSION


def test_calculated_at_is_utc():
    r = _score()
    assert r.calculated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# calculate_score — defensive clamping
# ---------------------------------------------------------------------------

def test_serious_clamped_to_total_when_data_drifts():
    # DB might have serious > total due to stale data; we clamp silently
    r = _score(criminal_cases=2, criminal_cases_serious=5)
    # After clamp: serious=2, other=0
    assert r.breakdown["criminal_deduction"]["serious_cases_count"] == 2
    assert r.breakdown["criminal_deduction"]["other_cases_count"] == 0


# ---------------------------------------------------------------------------
# ScoreCalculatorAgent.calculate — integration over the pure function
# ---------------------------------------------------------------------------

def _make_agent_with_stub_client() -> ScoreCalculatorAgent:
    agent = object.__new__(ScoreCalculatorAgent)
    agent._client = MagicMock()
    return agent


def test_agent_calculate_maps_rows():
    agent = _make_agent_with_stub_client()
    rows = [
        {"id": "MLA-001", "criminal_cases": 1, "criminal_cases_serious": 0, "declared_assets_cr": None},
        {"id": "MLA-002", "criminal_cases": 3, "criminal_cases_serious": 2, "declared_assets_cr": "12.5"},
    ]
    results = agent.calculate(rows)
    assert len(results) == 2
    assert results[0].mla_id == "MLA-001"
    assert results[0].score == 55  # 60 - 5
    assert results[1].mla_id == "MLA-002"
    assert results[1].score == 25  # 60 - 30(2 serious) - 5(1 other)
    assert results[1].breakdown["asset_flag"]["high_wealth_flag"] is True


def test_agent_calculate_handles_null_serious():
    agent = _make_agent_with_stub_client()
    rows = [{"id": "MLA-003", "criminal_cases": 2, "criminal_cases_serious": None, "declared_assets_cr": None}]
    results = agent.calculate(rows)
    assert results[0].score == 50  # 60 - 10 (2 other cases, no serious)


def test_agent_store_calls_update_per_result():
    agent = _make_agent_with_stub_client()
    mock_resp = MagicMock()
    mock_resp.data = [{"id": "MLA-001"}]
    agent._client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_resp

    results = [
        ScoreResult(
            mla_id="MLA-001",
            score=55,
            breakdown={"final_score": 55},
            version=SCORE_VERSION,
            calculated_at=datetime.now(timezone.utc),
        )
    ]
    count = agent.store(results)
    assert count == 1
    agent._client.table.assert_called_with("mlas")


def test_agent_store_empty_returns_zero():
    agent = _make_agent_with_stub_client()
    assert agent.store([]) == 0
