"""
THROWAWAY PROBE — inspect ECI results.eci.gov.in structure before building vote_scraper.

Fetches the TN 2026 results index, walks links, and prints page/table structure so
vote_scraper.py can be built with exact selectors. Also probes the Wikipedia cross-
reference page for 2026 TN election results.

Run (from tnwatch/ project root):
    .venv/Scripts/python.exe scripts/probe_eci_results.py
    .venv/Scripts/python.exe scripts/probe_eci_results.py eci       # ECI only
    .venv/Scripts/python.exe scripts/probe_eci_results.py wiki      # Wikipedia only
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

UA = "TNWatch/0.1 (civic-data probe; +https://github.com/tnwatch; contact prasathcodes@gmail.com)"
TIMEOUT = 30.0

# ECI state code for Tamil Nadu
TN_STATE_CODE = "S22"

# Candidate URL patterns to try (ECI restructures each cycle)
ECI_BASE = "https://results.eci.gov.in"
ECI_CANDIDATE_URLS = [
    f"{ECI_BASE}/",
    f"{ECI_BASE}/ResultGeneral/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/AcResult26/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/Result2026/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/ResultAC2026/PartywiseResult-{TN_STATE_CODE}.htm",
]

# Try multiple capitalisation variants — Wikipedia article titles vary
WIKI_2026_TN_URLS = [
    "https://en.wikipedia.org/wiki/2026_Tamil_Nadu_Legislative_Assembly_election",
    "https://en.wikipedia.org/wiki/Tamil_Nadu_Legislative_Assembly_election,_2026",
    "https://en.wikipedia.org/wiki/18th_Tamil_Nadu_Legislative_Assembly",
    "https://en.wikipedia.org/wiki/2026_Tamil_Nadu_legislative_assembly_election",
]

# Keywords used to detect TN-related links
TN_KEYWORDS = re.compile(r"tamil\s*nadu|tn\b|S22", re.I)


def get(url: str, client: httpx.Client) -> tuple[int, str, str]:
    try:
        r = client.get(url, follow_redirects=True, timeout=TIMEOUT)
        return r.status_code, str(r.url), r.text
    except Exception as exc:
        return 0, url, f"ERROR: {exc}"


def print_separator(label: str = "") -> None:
    if label:
        print(f"\n{'='*100}")
        print(f"  {label}")
        print("=" * 100)
    else:
        print("-" * 80)


def summarise_tables(soup: BeautifulSoup, max_tables: int = 10) -> None:
    tables = soup.select("table")
    print(f"  total <table> elements: {len(tables)}")
    for i, tbl in enumerate(tables[:max_tables]):
        rows = tbl.select("tr")
        headers = [c.get_text(" ", strip=True)[:40] for c in rows[0].find_all(["th", "td"])] if rows else []
        data_rows = [r for r in rows if r.find("td")]
        print(f"    table #{i}: {len(rows)} rows ({len(data_rows)} data rows)  headers={headers[:8]}")
        for r in data_rows[:3]:
            cells = [c.get_text(" ", strip=True)[:35] for c in r.find_all(["td", "th"])[:8]]
            print(f"      row: {cells}")


def summarise_links(soup: BeautifulSoup, base_url: str, pattern: re.Pattern | None = None, max_links: int = 30) -> list[str]:
    """Return links whose text/href match pattern (or all if None)."""
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]
        abs_href = urljoin(base_url, href)
        if pattern and not (pattern.search(text) or pattern.search(href)):
            continue
        found.append(abs_href)
        if len(found) <= max_links:
            print(f"    [{text[:50]!r}] -> {abs_href}")
    return found


def probe_eci_main(client: httpx.Client) -> None:
    """Probe the ECI results index for Tamil Nadu links."""
    print_separator("ECI — main index: " + ECI_BASE)
    status, final_url, html = get(ECI_BASE, client)
    print(f"  status={status}  final_url={final_url}  bytes={len(html)}")
    if status == 0:
        print(f"  {html}")  # error message
        return
    soup = BeautifulSoup(html, "lxml")
    print(f"  <title>: {soup.title and soup.title.get_text(strip=True)}")

    # Print all links mentioning Tamil Nadu
    print(f"\n  Tamil Nadu / TN / S22 links:")
    tn_links = summarise_links(soup, final_url, pattern=TN_KEYWORDS)

    # Also print any links that look like constituency/party result pages
    result_pattern = re.compile(r"partywiseresu|candidateresult|acresult|result", re.I)
    print(f"\n  Result-looking links (first 20):")
    result_links = summarise_links(soup, final_url, pattern=result_pattern, max_links=20)

    # Print visible text blurbs (elections listed)
    print(f"\n  Page text excerpt (first 2000 chars):")
    print(f"  {soup.get_text(' ', strip=True)[:2000]}")

    # Probe each candidate URL
    print_separator("ECI — probing candidate URLs")
    for url in ECI_CANDIDATE_URLS:
        status, final, html = get(url, client)
        s = BeautifulSoup(html, "lxml") if status == 200 else None
        title = s.title and s.title.get_text(strip=True) if s else ""
        print(f"  {status}  {url}")
        print(f"         final={final}  title={title!r}  bytes={len(html)}")
        if s:
            tables = s.select("table")
            rows = sum(len(t.select("tr")) for t in tables)
            print(f"         tables={len(tables)}  total_rows={rows}")


def probe_eci_state_page(client: httpx.Client, state_url: str) -> None:
    """Deep-dive a TN state results page."""
    print_separator(f"ECI — state page: {state_url}")
    status, final_url, html = get(state_url, client)
    print(f"  status={status}  bytes={len(html)}")
    if status != 200:
        print(f"  {html[:300]}")
        return
    soup = BeautifulSoup(html, "lxml")
    print(f"  <title>: {soup.title and soup.title.get_text(strip=True)}")

    # Table structure
    summarise_tables(soup, max_tables=5)

    # Constituency result links
    print(f"\n  Constituency result links (first 30):")
    ac_pattern = re.compile(r"candidateresult|acresult|AC=|ac=", re.I)
    ac_links = summarise_links(soup, final_url, pattern=ac_pattern)
    if ac_links:
        # Probe first constituency page as a sample
        print(f"\n  Sample constituency page: {ac_links[0]}")
        probe_constituency_page(client, ac_links[0])


def probe_constituency_page(client: httpx.Client, url: str) -> None:
    """Print the structure of a single constituency result page."""
    status, final_url, html = get(url, client)
    print(f"  status={status}  bytes={len(html)}")
    if status != 200:
        return
    soup = BeautifulSoup(html, "lxml")
    print(f"  <title>: {soup.title and soup.title.get_text(strip=True)}")
    summarise_tables(soup, max_tables=3)

    # Check for JSON-LD or embedded JSON (ECI sometimes embeds result data)
    scripts = soup.find_all("script", type="application/json")
    for sc in scripts[:3]:
        txt = sc.string or ""
        if txt.strip():
            print(f"  JSON script tag ({len(txt)} bytes): {txt[:400]}")

    # Check for XHR-friendly endpoints embedded in JS
    inline_scripts = soup.find_all("script", src=False)
    for sc in inline_scripts[:5]:
        txt = sc.string or ""
        if "url" in txt.lower() or "api" in txt.lower() or "json" in txt.lower():
            print(f"  Interesting inline script ({len(txt)} bytes): {txt[:300]}")


def probe_eci_api(client: httpx.Client) -> None:
    """Try common ECI API / JSON endpoints for TN 2026 results."""
    print_separator("ECI — JSON / API endpoint probes")
    api_candidates = [
        f"{ECI_BASE}/Result2026/ResultData-S22.json",
        f"{ECI_BASE}/ResultGeneral/ResultData-S22.json",
        f"{ECI_BASE}/AcResult26/ResultData-S22.json",
        f"{ECI_BASE}/ResultData-S22.json",
        f"https://cdn.eci.gov.in/2026/tn/results.json",
        f"https://cdn.eci.gov.in/results/S22/AC.json",
    ]
    for url in api_candidates:
        status, final, body = get(url, client)
        snippet = body[:200].replace("\n", " ").strip()
        print(f"  {status}  {url}")
        print(f"         {snippet}")
        if status == 200 and body.strip().startswith(("{", "[")):
            try:
                data = json.loads(body)
                print(f"         VALID JSON: type={type(data).__name__}  len={len(data) if hasattr(data, '__len__') else 'N/A'}")
            except Exception:
                pass


def probe_wikipedia(client: httpx.Client) -> None:
    """
    Probe Wikipedia 2026 TN election article.
    Specifically targets the 'Results by constituency' table (h3#Results_by_constituency)
    and prints its column layout plus sample rows so vote_scraper selectors can be
    verified without re-probing.
    """
    html = ""
    final_url = ""
    for wiki_url in WIKI_2026_TN_URLS:
        status, final_url, html = get(wiki_url, client)
        print_separator(f"Wikipedia — {wiki_url}")
        print(f"  status={status}  final_url={final_url}  bytes={len(html)}")
        if status == 200 and len(html) > 10_000:
            break
    if not html or len(html) < 10_000:
        print("  All Wikipedia variants failed — article may not exist yet.")
        return
    soup = BeautifulSoup(html, "lxml")
    print(f"  <title>: {soup.title and soup.title.get_text(strip=True)}")

    # --- Show all tables with 5+ data rows (sorted by size) ---
    all_tables = sorted(
        [(t, len([r for r in t.find_all("tr") if r.find("td")])) for t in soup.find_all("table")],
        key=lambda x: -x[1],
    )
    print(f"\n  All tables ({len(all_tables)} total), top 8 by data rows:")
    for tbl, nrows in all_tables[:8]:
        node = tbl.find_previous(["h2", "h3", "h4"])
        htxt = node.get_text(strip=True)[:55] if node else "?"
        first_tr = tbl.find("tr")
        hcells = [c.get_text(" ", strip=True)[:40] for c in (first_tr.find_all(["th", "td"]) if first_tr else [])[:8]]
        print(f"    {nrows:3d} rows under {htxt!r}")
        print(f"         headers: {hcells}")

    # --- Deep-dive: Results by constituency table ---
    print_separator("Wikipedia — Results by constituency table (deep dive)")
    heading = soup.find(id="Results_by_constituency")
    if not heading:
        # Also try text-search for the heading
        for h in soup.find_all(["h2", "h3", "h4"]):
            if "results by constituency" in h.get_text(strip=True).lower():
                heading = h
                break
    if not heading:
        print("  ERROR: 'Results by constituency' heading not found")
        return

    tbl = heading.find_next("table")
    if not tbl:
        print("  ERROR: no table found after heading")
        return

    all_rows = tbl.find_all("tr")
    data_rows = [r for r in all_rows if r.find("td")]
    print(f"  Table: {len(all_rows)} total rows, {len(data_rows)} data rows")

    print("\n  Header rows:")
    for i, row in enumerate(all_rows):
        if row.find("td"):
            break
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        print(f"    Header row {i}: {len(cells)} cells")
        for j, c in enumerate(cells):
            rs = c.get("rowspan", 1)
            cs = c.get("colspan", 1)
            print(f"      [{j}] rs={rs} cs={cs}  {c.get_text(' ', strip=True)[:50]!r}")

    print(f"\n  First 5 data rows:")
    for i, row in enumerate(data_rows[:5]):
        cells = row.find_all(["td", "th"])
        cell_texts = [c.get_text(" ", strip=True)[:35] for c in cells]
        print(f"    Row {i} ({len(cells)} cells): {cell_texts}")

    print("\n  Last 3 data rows:")
    for i, row in enumerate(data_rows[-3:]):
        cells = row.find_all(["td", "th"])
        cell_texts = [c.get_text(" ", strip=True)[:35] for c in cells]
        print(f"    Row {len(data_rows)-3+i} ({len(cells)} cells): {cell_texts}")


def main() -> int:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(headers=headers, follow_redirects=True, timeout=TIMEOUT) as client:
        if mode in ("all", "eci"):
            probe_eci_main(client)
            probe_eci_api(client)
            # If any TN state page was found, probe it
            for url in ECI_CANDIDATE_URLS[1:]:  # skip bare root
                status, final, _ = get(url, client)
                if status == 200:
                    probe_eci_state_page(client, final)
                    break

        if mode in ("all", "wiki"):
            probe_wikipedia(client)

    print("\n" + "=" * 100)
    print("PROBE COMPLETE — check output above before building vote_scraper.py")
    print("Key things to identify:")
    print("  1. Exact ECI URL pattern for TN 2026 assembly results index page")
    print("  2. How constituency pages are linked (AC number in URL? separate param?)")
    print("  3. Table structure: are candidates listed with votes in <td> columns?")
    print("  4. Whether ECI needs Playwright (JS-rendered) or plain httpx suffices")
    print("  5. Wikipedia fallback: does the 2026 article have constituency-level tables?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
