"""
Score Calculator Agent — computes performance_score for every MLA with ECI data.

For each MLA where criminal_cases IS NOT NULL, calculates a 0–100 score:

    base_score = 60
    criminal_deduction:
        serious IPC cases (murder/rape/fraud class): -15/case, cap -40
        other criminal cases: -5/case, cap -20
    asset_flag: True if declared_assets_cr > 10 crore (informational; no deduction in v0.1)
    final_score = clamp(0, 100, base_score + criminal_deduction)

Stores per-MLA: performance_score, score_breakdown (JSONB), score_version, score_calculated_at.
The breakdown is MANDATORY — the frontend displays each component with its source.
Never show a score without receipts.

Pre-conditions (run once in Supabase SQL editor before first run):
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS score_breakdown      jsonb;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS score_version        text;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS score_calculated_at  timestamptz;

Pipeline shape (CONTEXT.md §9 Rule 4): fetch() → calculate() → store() → report()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import supabase_io
from .models import AgentRunReport

log = logging.getLogger("tnwatch.score_calculator")

SCORE_VERSION = "v0.1"

BASE_SCORE = 60

SERIOUS_DEDUCTION_PER_CASE = -15
SERIOUS_DEDUCTION_CAP = -40   # never deduct more than 40 for serious cases

OTHER_DEDUCTION_PER_CASE = -5
OTHER_DEDUCTION_CAP = -20    # never deduct more than 20 for other cases

ASSET_HIGH_WEALTH_THRESHOLD_CR = Decimal("10")


# ---------------------------------------------------------------------------
# Pure scoring logic
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    mla_id: str
    score: int
    breakdown: dict[str, Any]
    version: str
    calculated_at: datetime


def calculate_score(
    mla_id: str,
    criminal_cases: int,
    criminal_cases_serious: int,
    declared_assets_cr: Decimal | None,
) -> ScoreResult:
    """
    Deterministic, pure scoring function. No I/O, no side effects.
    Returns a ScoreResult with the full breakdown so every number is traceable.

    criminal_cases_serious must be <= criminal_cases; if the DB has drift,
    we clamp it here rather than let the score go wrong silently.
    """
    criminal_cases_serious = min(criminal_cases_serious, criminal_cases)
    other_cases = criminal_cases - criminal_cases_serious

    serious_deduction = max(
        SERIOUS_DEDUCTION_CAP,
        criminal_cases_serious * SERIOUS_DEDUCTION_PER_CASE,
    )
    other_deduction = max(
        OTHER_DEDUCTION_CAP,
        other_cases * OTHER_DEDUCTION_PER_CASE,
    )
    total_criminal_deduction = serious_deduction + other_deduction

    final_score = max(0, min(100, BASE_SCORE + total_criminal_deduction))

    high_wealth_flag = (
        declared_assets_cr is not None
        and declared_assets_cr > ASSET_HIGH_WEALTH_THRESHOLD_CR
    )

    breakdown: dict[str, Any] = {
        "base_score": BASE_SCORE,
        "criminal_deduction": {
            "serious_cases_count": criminal_cases_serious,
            "serious_deduction_per_case": SERIOUS_DEDUCTION_PER_CASE,
            "serious_deduction_applied": serious_deduction,
            "other_cases_count": other_cases,
            "other_deduction_per_case": OTHER_DEDUCTION_PER_CASE,
            "other_deduction_applied": other_deduction,
            "total_criminal_deduction": total_criminal_deduction,
            "source": "ECI affidavit via MyNeta (myneta.info)",
        },
        "asset_flag": {
            "declared_assets_cr": str(declared_assets_cr) if declared_assets_cr is not None else None,
            "high_wealth_flag": high_wealth_flag,
            "threshold_cr": str(ASSET_HIGH_WEALTH_THRESHOLD_CR),
            "deduction": 0,
            "note": "Asset flag is informational only in v0.1; no score deduction applied",
        },
        "final_score": final_score,
    }

    return ScoreResult(
        mla_id=mla_id,
        score=final_score,
        breakdown=breakdown,
        version=SCORE_VERSION,
        calculated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ScoreCalculatorAgent:
    """
    Reads MLAs with criminal data from Supabase, calculates scores, writes back.
    Follows the fetch → calculate → store → report pipeline (CONTEXT.md §9 Rule 4).
    """

    def __init__(self) -> None:
        self._client = supabase_io.create_client()

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch(self) -> list[dict]:
        """Load all mlas rows where criminal_cases IS NOT NULL."""
        resp = (
            self._client.table("mlas")
            .select("id, criminal_cases, criminal_cases_serious, declared_assets_cr")
            .filter("criminal_cases", "not.is", "null")
            .execute()
        )
        rows = resp.data or []
        log.info("score_calculator: fetched %d eligible MLAs", len(rows))
        return rows

    # ------------------------------------------------------------------
    # calculate
    # ------------------------------------------------------------------

    def calculate(self, rows: list[dict]) -> list[ScoreResult]:
        """Calculate a ScoreResult for each fetched row. Pure; no I/O."""
        results: list[ScoreResult] = []
        for row in rows:
            mla_id: str = row["id"]
            criminal_cases = int(row.get("criminal_cases") or 0)
            criminal_cases_serious = int(row.get("criminal_cases_serious") or 0)
            raw_assets = row.get("declared_assets_cr")
            declared_assets_cr = Decimal(str(raw_assets)) if raw_assets is not None else None

            results.append(
                calculate_score(
                    mla_id=mla_id,
                    criminal_cases=criminal_cases,
                    criminal_cases_serious=criminal_cases_serious,
                    declared_assets_cr=declared_assets_cr,
                )
            )
        return results

    # ------------------------------------------------------------------
    # store
    # ------------------------------------------------------------------

    def store(self, results: list[ScoreResult]) -> int:
        """
        Write performance_score + breakdown back into mlas.
        Uses individual UPDATE calls (not upsert) — we only enrich existing rows,
        never create new ones (same discipline as update_mla_eci in supabase_io.py).
        Returns the total number of rows updated.
        """
        if not results:
            return 0
        count = 0
        for r in results:
            payload: dict[str, Any] = {
                "performance_score": r.score,
                "score_breakdown": r.breakdown,
                "score_version": r.version,
                "score_calculated_at": r.calculated_at.isoformat(),
                "last_updated": r.calculated_at.isoformat(),
            }
            resp = (
                self._client.table("mlas")
                .update(payload)
                .eq("id", r.mla_id)
                .execute()
            )
            count += len(resp.data or [])
        log.info("score_calculator: stored scores for %d MLAs", count)
        return count

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------

    def report(
        self,
        started_at: datetime,
        rows_written: int,
        error: str | None = None,
    ) -> None:
        """Write an agent_runs row to Supabase (Rule 4 audit trail)."""
        run = AgentRunReport(
            agent_name="score_calculator",
            status="success" if error is None else "failed",
            rows_written=rows_written,
            error_message=error,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )
        self._client.table("agent_runs").insert(run.model_dump(mode="json")).execute()

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    def run(self) -> AgentRunReport:
        """Top-level entry point: fetch → calculate → store → report."""
        started_at = datetime.now(timezone.utc)
        log.info("score_calculator: run started")
        try:
            rows = self.fetch()
            results = self.calculate(rows)
            rows_written = self.store(results)
            self.report(started_at, rows_written)
            return AgentRunReport(
                agent_name="score_calculator",
                status="success",
                rows_written=rows_written,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            log.exception("score_calculator: run failed — %s", exc)
            self.report(started_at, 0, error=str(exc))
            return AgentRunReport(
                agent_name="score_calculator",
                status="failed",
                rows_written=0,
                error_message=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ScoreCalculatorAgent()
    result = agent.run()
    print(f"status={result.status}  rows_written={result.rows_written}")
    if result.error_message:
        print(f"error: {result.error_message}")
