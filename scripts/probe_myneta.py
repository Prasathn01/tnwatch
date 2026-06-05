"""
THROWAWAY PROBE — inspect MyNeta TN2026 HTML structure before building parser.

Per CONTEXT.md Build Loop: probe first, inspect output, THEN write the real agent.
This script only READS public pages and prints to stdout. Not part of the pipeline.

Run: .venv/Scripts/python.exe scripts/probe_myneta.py
     .venv/Scripts/python.exe scripts/probe_myneta.py --candidate 5   # probe a specific id
"""

from __future__ import annotations

import re
import sys

import httpx
from bs4 import BeautifulSoup, Tag

UA = "TNWatch/0.1 (civic-data probe; +https://github.com/Prasathn01/tnwatch; contact prasathcodes@gmail.com)"
BASE = "https://myneta.info/TamilNadu2026"
INDEX_URL = f"{BASE}/"
HEADERS = {"User-Agent": UA}


# ---------------------------------------------------------------------------
# fetch helpers
# ---------------------------------------------------------------------------

def fetch(url: str) -> tuple[int, str]:
    r = httpx.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    return r.status_code, r.text


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# index page probe
# ---------------------------------------------------------------------------

def probe_index() -> list[str]:
    """Print index table structure; return list of candidate URLs found."""
    print("=" * 80)
    print(f"INDEX PAGE  {INDEX_URL}")
    status, html = fetch(INDEX_URL)
    print(f"  HTTP {status}  bytes={len(html)}")
    if status != 200:
        print("  !! non-200, aborting")
        return []

    s = soup(html)

    # --- all tables ---
    tables = s.find_all("table")
    print(f"  total <table> elements: {len(tables)}")
    for i, t in enumerate(tables):
        if not isinstance(t, Tag):
            continue
        rows = t.find_all("tr")
        body_rows = [r for r in rows if r.find("td")]
        ths = [th.get_text(" ", strip=True)[:30] for th in (rows[0].find_all("th") if rows else [])]
        print(f"\n  TABLE #{i}  rows={len(body_rows)}  headers={ths}")
        for row in body_rows[:3]:
            cells = row.find_all(["td", "th"])
            vals = [c.get_text(" ", strip=True)[:35] for c in cells[:10]]
            print(f"    {vals}")

    # --- candidate links ---
    links = s.find_all("a", href=re.compile(r"candidate\.php\?candidate_id=\d+"))
    print(f"\n  candidate links found: {len(links)}")
    urls = list(dict.fromkeys(
        f"{BASE}/{a['href']}" for a in links if isinstance(a, Tag)
    ))
    print(f"  unique candidate URLs: {len(urls)}")
    for u in urls[:5]:
        print(f"    {u}")
    return urls


# ---------------------------------------------------------------------------
# candidate page probe
# ---------------------------------------------------------------------------

def probe_candidate(url: str) -> None:
    print("\n" + "=" * 80)
    print(f"CANDIDATE PAGE  {url}")
    status, html = fetch(url)
    print(f"  HTTP {status}  bytes={len(html)}")
    if status != 200:
        print("  !! non-200, skipping")
        return

    s = soup(html)

    # --- page title ---
    title = s.find("title")
    print(f"  <title>: {title.get_text(strip=True) if title else '(none)'}")

    # --- headings ---
    for tag in ["h1", "h2", "h3", "h4"]:
        for h in s.find_all(tag):
            print(f"  <{tag}>: {h.get_text(' ', strip=True)[:80]}")

    # --- all tables ---
    tables = s.find_all("table")
    print(f"\n  total <table> elements: {len(tables)}")
    for i, t in enumerate(tables):
        if not isinstance(t, Tag):
            continue
        rows = t.find_all("tr")
        body_rows = [r for r in rows if r.find("td")]
        ths = [th.get_text(" ", strip=True)[:30] for th in (rows[0].find_all("th") if rows else [])]
        print(f"\n  TABLE #{i}  rows={len(body_rows)}  headers={ths}")
        for row in body_rows[:8]:
            cells = row.find_all(["td", "th"])
            vals = [c.get_text(" ", strip=True)[:50] for c in cells[:4]]
            print(f"    {vals}")

    # --- paragraphs (criminal case text often lives here) ---
    print("\n  <p> tags (first 15):")
    for p in s.find_all("p")[:15]:
        txt = p.get_text(" ", strip=True)
        if txt:
            print(f"    {txt[:100]}")

    # --- links (look for affidavit / ECI PDF links) ---
    print("\n  <a> tags containing 'affidavit' or 'eci' or 'pdf' (case-insensitive):")
    for a in s.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        if re.search(r"affidavit|eci|\.pdf", href, re.I) or re.search(r"affidavit|eci", text, re.I):
            print(f"    text={text[:40]!r}  href={href[:80]!r}")

    # --- key patterns via regex on full text ---
    text = s.get_text(" ")
    print("\n  KEY VALUE PATTERNS in page text:")
    patterns = {
        "total_assets":     r"Total\s+Assets[^\d]{0,20}(Rs\.?\s*[\d,]+)",
        "total_liab":       r"Total\s+Liabilit\w+[^\d]{0,20}(Rs\.?\s*[\d,]+)",
        "criminal_cases":   r"Criminal\s+Cases?[^\d]{0,20}(\d+)",
        "age":              r"\bAge[^\d]{0,10}(\d{2,3})\b",
        "education":        r"Education[^\w]{0,10}([\w ]+?)(?:\n|<|$)",
        "eci_id":           r"(?:Affidavit|ECI|S/No\.?)[^\w]{0,10}([A-Z]\d{4,}|\d{6,})",
    }
    for label, pat in patterns.items():
        m = re.search(pat, text, re.I | re.DOTALL)
        print(f"    {label:20s}: {m.group(0)[:80].strip()!r}" if m else f"    {label:20s}: NOT FOUND")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    # Parse --candidate N flag
    candidate_id: str | None = None
    args = sys.argv[1:]
    if "--candidate" in args:
        idx = args.index("--candidate")
        if idx + 1 < len(args):
            candidate_id = args[idx + 1]

    # Step 1: probe index
    candidate_urls = probe_index()

    # Step 2: probe one candidate page
    if candidate_id:
        url = f"{BASE}/candidate.php?candidate_id={candidate_id}"
    elif candidate_urls:
        url = candidate_urls[0]
    else:
        # fallback: try candidate_id=1
        url = f"{BASE}/candidate.php?candidate_id=1"

    probe_candidate(url)

    # Step 3: probe a second candidate (different party/profile) for structural variance
    if len(candidate_urls) > 5:
        print("\n[Probing a second candidate for structural variance]")
        probe_candidate(candidate_urls[5])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
