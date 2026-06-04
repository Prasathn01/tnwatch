"""
THROWAWAY PROBE — inspect Wikipedia table structure before building parsers.

Per scripts/README.md and CONTEXT.md "when stuck": when a source's structure is
unknown, probe first, inspect output, THEN write the real agent. This script is
NOT part of the pipeline and can be deleted once mla_scraper.py and
seed_constituencies.py are built. It only READS public pages and prints to stdout.

Run: .venv/Scripts/python.exe scripts/probe_wikipedia.py
"""

from __future__ import annotations

import sys

import httpx
from bs4 import BeautifulSoup

UA = "TNWatch/0.1 (civic-data probe; +https://github.com/tnwatch; contact prasathcodes@gmail.com)"

PAGES = {
    "17th_assembly": "https://en.wikipedia.org/wiki/17th_Tamil_Nadu_Assembly",
    "constituencies_list": "https://en.wikipedia.org/wiki/List_of_constituencies_of_the_Tamil_Nadu_Legislative_Assembly",
    "2026_election": "https://en.wikipedia.org/wiki/2026_Tamil_Nadu_Legislative_Assembly_election",
}


def fetch(url: str) -> tuple[int, str, str]:
    r = httpx.get(url, headers={"User-Agent": UA}, follow_redirects=True, timeout=30)
    return r.status_code, str(r.url), r.text


def nearest_heading(table) -> str:
    """Walk backwards to find the section heading this table sits under."""
    node = table
    for _ in range(60):
        node = node.find_previous(["h2", "h3", "h4"])
        if node is None:
            return "(no heading found)"
        span = node.find("span", class_="mw-headline")
        return (span.get_text(strip=True) if span else node.get_text(strip=True))
    return "(no heading found)"


def summarise_page(label: str, url: str) -> None:
    print("=" * 100)
    print(f"PAGE [{label}] {url}")
    status, final_url, html = fetch(url)
    print(f"  status={status}  final_url={final_url}  bytes={len(html)}")
    if status != 200:
        print("  !! non-200, skipping")
        return
    soup = BeautifulSoup(html, "lxml")
    tables = soup.select("table.wikitable")
    print(f"  wikitable count: {len(tables)}")
    for i, table in enumerate(tables):
        heading = nearest_heading(table)
        # header cells
        header_cells = table.select("tr th")
        headers = [c.get_text(" ", strip=True) for c in header_cells[:12]]
        rows = table.select("tr")
        body_rows = [r for r in rows if r.find("td")]
        print("-" * 100)
        print(f"  TABLE #{i}  under heading: {heading!r}")
        print(f"    classes={table.get('class')}  data_rows={len(body_rows)}")
        print(f"    header cells (first 12): {headers}")
        # show first 3 body rows, first 8 cells each
        for r in body_rows[:3]:
            cells = r.find_all(["td", "th"], recursive=False)
            txt = [c.get_text(" ", strip=True)[:40] for c in cells[:8]]
            print(f"      row: {txt}")


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for label, url in PAGES.items():
        if only and only != label:
            continue
        try:
            summarise_page(label, url)
        except Exception as e:  # probe: never crash, just report
            print(f"  ERROR on {label}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
