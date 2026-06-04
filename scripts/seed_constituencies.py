"""
Seed the 234 Tamil Nadu assembly constituencies (BUILD_PLAN.md Week 1).

Scrapes the Wikipedia constituencies list ONCE, validates each row as a
Constituency model, and writes data/constituencies.json — the canonical seed that
is loaded into the Supabase `constituencies` table. The MLA scraper assumes these
rows already exist and links to them by id; this script deliberately does NOT
touch the `mlas` table (clean separation, per ruling #3).

Usage:
    python scripts/seed_constituencies.py                 # write data/constituencies.json
    python scripts/seed_constituencies.py --html FILE     # parse a saved fixture instead
    python scripts/seed_constituencies.py --load          # also upsert into Supabase (needs .env)

Run from the repo root so `import agents...` resolves.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agents.models import Constituency  # noqa: E402
from agents.wikitable import cell_text, find_wikitable, resolve_columns, table_to_grid  # noqa: E402

SOURCE_URL = "https://en.wikipedia.org/wiki/List_of_constituencies_of_the_Tamil_Nadu_Legislative_Assembly"
USER_AGENT = "TNWatch/0.1 (civic-accountability data; contact prasathcodes@gmail.com)"
OUTPUT_PATH = REPO_ROOT / "data" / "constituencies.json"

TABLE_HEADERS = ["constituency", "reserved", "electors"]
COLUMN_SPEC = {
    "number": ["#"],
    "name": ["constituency"],         # exact match beats "lok sabha constituency", etc.
    "reserved": ["reserved"],
    "electors": ["electors"],
    "district": ["district"],
    "lok_sabha": ["lok sabha constituency", "lok sabha"],
}

RESERVED_MAP = {"-": "GEN", "": "GEN", "gen": "GEN", "general": "GEN", "sc": "SC", "st": "ST"}


def fetch_html() -> str:
    resp = httpx.get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.text


def parse_constituencies(html: str) -> list[Constituency]:
    """Parse the constituencies list table into validated Constituency models."""
    table = find_wikitable(html, contains_headers=TABLE_HEADERS)
    grid = table_to_grid(table)
    cols = resolve_columns(grid[0], COLUMN_SPEC)
    out: list[Constituency] = []
    for row in grid[1:]:
        number_txt = cell_text(row[cols["number"]])
        if not number_txt.isdigit():
            continue
        number = int(number_txt)
        out.append(
            Constituency(
                id=f"AC-{number:03d}",
                number=number,
                name=cell_text(row[cols["name"]]),
                district=cell_text(row[cols["district"]]),
                lok_sabha_seat=cell_text(row[cols["lok_sabha"]]) or None,
                total_electors=_to_int(cell_text(row[cols["electors"]])),
                reserved=_normalise_reserved(cell_text(row[cols["reserved"]])),
            )
        )
    return out


def _to_int(text: str) -> int | None:
    digits = text.replace(",", "").strip()
    return int(digits) if digits.isdigit() else None


def _normalise_reserved(text: str) -> str:
    return RESERVED_MAP.get(text.strip().lower(), "GEN")


def write_json(rows: list[Constituency], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [r.model_dump() for r in sorted(rows, key=lambda c: c.number)]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed TN constituencies from Wikipedia.")
    parser.add_argument("--html", help="parse a saved HTML file instead of fetching live")
    parser.add_argument("--load", action="store_true", help="also upsert into Supabase (needs .env creds)")
    args = parser.parse_args()

    html = Path(args.html).read_text(encoding="utf-8") if args.html else fetch_html()
    rows = parse_constituencies(html)
    write_json(rows, OUTPUT_PATH)

    print(f"Parsed {len(rows)} constituencies -> {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    if len(rows) != 234:
        print(f"  WARNING: expected 234 constituencies, got {len(rows)} — check the source layout.")
    reserved_counts: dict[str, int] = {}
    for r in rows:
        reserved_counts[r.reserved] = reserved_counts.get(r.reserved, 0) + 1
    print(f"  reservation split: {reserved_counts}")
    print(f"  sample: {rows[0].model_dump()}")

    if args.load:
        _load_to_supabase(rows)
    return 0


def _load_to_supabase(rows: list[Constituency]) -> None:
    """Upsert seed rows into Supabase. Optional path — only runs with --load."""
    try:
        import os

        from dotenv import load_dotenv
        from supabase import create_client
    except ImportError:
        print("  --load needs `supabase` and `python-dotenv` installed; skipping.")
        return
    load_dotenv(REPO_ROOT / ".env")
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        print("  SUPABASE_URL / SUPABASE_SERVICE_KEY missing in .env; skipping load.")
        return
    client = create_client(url, key)
    client.table("constituencies").upsert([r.model_dump() for r in rows]).execute()
    print(f"  upserted {len(rows)} rows into Supabase constituencies.")


if __name__ == "__main__":
    raise SystemExit(main())
