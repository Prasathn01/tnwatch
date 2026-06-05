"""
Vote Scraper Agent — Tamil Nadu 2026 assembly election results.

Scrapes per-constituency vote data from results.eci.gov.in (primary) with
Wikipedia's 2026 TN election article as a fallback. Extracts the 7 vote fields
per constituency, fuzzy-matches to the `mlas` + `constituencies` tables, and
upserts into Supabase.

Shape: fetch() -> parse() -> store() -> report()  (CONTEXT.md §9 Rule 4)

ECI note: results.eci.gov.in blocks plain httpx (Akamai CDN 403). The ECI fetch
path uses Playwright (headless Chromium) to render the JS-driven site. The Wikipedia
fallback uses plain httpx and does not require Playwright.

Schema note — run this SQL in Supabase before the first production run if the
columns are missing (safe to re-run: IF NOT EXISTS):

    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS winning_votes  int;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS total_votes    int;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS runner_up_name text;
    ALTER TABLE mlas ADD COLUMN IF NOT EXISTS runner_up_votes int;

The four existing columns (name, vote_margin, vote_share_pct, elected_year) are
always written; the four new columns are written when present and silently skipped
via try/except on the Supabase response if the column doesn't exist yet.

Run (from tnwatch/ project root):
    .venv/Scripts/python.exe -m agents.vote_scraper
    .venv/Scripts/python.exe -m agents.vote_scraper --source wiki   # force Wikipedia
    .venv/Scripts/python.exe -m agents.vote_scraper --dry-run       # no DB writes
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag
from rapidfuzz import process as fuzz_process, fuzz

from .models import AgentRunReport
from .supabase_io import create_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_NAME = "vote_scraper"
ELECTED_YEAR = 2026
ASSEMBLY_NUMBER = 18  # 18th Tamil Nadu Legislative Assembly
TN_STATE_CODE = "S22"

UA = "TNWatch/0.1 (civic-accountability data; +https://github.com/tnwatch; contact prasathcodes@gmail.com)"
REQUEST_DELAY = 2.0   # seconds between constituency fetches (Rule 12)
FUZZY_THRESHOLD = 80  # minimum rapidfuzz score for constituency name match

ECI_BASE = "https://results.eci.gov.in"

# Candidate URL patterns tried in order; the probe reveals which works.
ECI_INDEX_URLS = [
    f"{ECI_BASE}/ResultGeneral/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/AcResult26/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/Result2026/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/ResultAC2026/PartywiseResult-{TN_STATE_CODE}.htm",
    f"{ECI_BASE}/",  # main index as last resort
]

# Wikipedia tries multiple title variants (capitalisation differs across edits)
WIKI_2026_URLS = [
    "https://en.wikipedia.org/wiki/2026_Tamil_Nadu_Legislative_Assembly_election",
    "https://en.wikipedia.org/wiki/Tamil_Nadu_Legislative_Assembly_election,_2026",
    "https://en.wikipedia.org/wiki/18th_Tamil_Nadu_Legislative_Assembly",
    "https://en.wikipedia.org/wiki/2026_Tamil_Nadu_legislative_assembly_election",
]

# Column headers that identify a candidate results table on ECI pages
ECI_CANDIDATE_HEADERS = re.compile(
    r"candidate|votes?\s*polled|total\s*votes?|%\s*of\s*votes?|party", re.I
)

# Normalise constituency name for fuzzy matching
_NOISE = re.compile(r"\([^)]*\)|assembly|constituency|ac\s*[-–]\s*\d+|\s+", re.I)

# Known name aliases: Wikipedia short form → DB canonical name (post-normalisation)
# Add entries whenever probe reveals a mismatch between the scrape source and the DB.
_CONSTITUENCY_ALIASES: dict[str, str] = {
    "r.k.nagar": "dr.radhakrishnannagar",   # Wikipedia "R.K. Nagar" → DB "Dr. Radhakrishnan Nagar"
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class VoteResult:
    """Vote data for one constituency — the 7 fields the task requires."""
    constituency_name: str          # as scraped (raw, pre-match)
    winning_candidate_name: str
    winning_votes: int
    total_votes: int
    vote_share: float               # percentage, e.g. 45.32
    runner_up_name: str
    runner_up_votes: int
    vote_margin: int                # winner - runner-up
    source_url: str
    # filled in by store() after constituency match
    constituency_id: str = ""
    mla_id: str = ""
    party: str = ""


@dataclass
class ParseState:
    """Running totals passed from parse() to store()."""
    results: list[VoteResult] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    source: str = ""                # "eci" or "wiki"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _make_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        follow_redirects=True,
        timeout=30.0,
    )


def _get(client: httpx.Client, url: str) -> tuple[int, str, str]:
    try:
        r = client.get(url)
        return r.status_code, str(r.url), r.text
    except Exception as exc:
        return 0, url, f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# ECI parsers
# ---------------------------------------------------------------------------

def _normalise_name(name: str) -> str:
    """Lower-case, strip noise tokens for fuzzy matching."""
    return _NOISE.sub("", name.lower()).strip()


def _parse_int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_float(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _find_candidate_table(soup: BeautifulSoup) -> Tag | None:
    """Return the first table whose headers look like a candidates result table."""
    for tbl in soup.select("table"):
        rows = tbl.select("tr")
        if not rows:
            continue
        header_text = " ".join(c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"]))
        if ECI_CANDIDATE_HEADERS.search(header_text):
            return tbl
    return None


def _resolve_col_index(header_cells: list[Tag], patterns: list[str]) -> int:
    """Return the column index matching the first of patterns (case-insensitive), -1 if none."""
    for i, cell in enumerate(header_cells):
        text = cell.get_text(" ", strip=True).lower()
        for pat in patterns:
            if re.search(pat, text, re.I):
                return i
    return -1


def _parse_constituency_page(url: str, html: str) -> tuple[str | None, list[dict]]:
    """
    Parse an ECI constituency result page.
    Returns (constituency_name, candidate_rows) where each row is a dict with
    keys: candidate_name, party, votes, vote_pct.
    """
    soup = BeautifulSoup(html, "lxml")

    # Constituency name is typically in the page title or an <h2>/<h3>
    title = ""
    for sel in ["h2", "h3", "h1", "title"]:
        node = soup.find(sel)
        if node:
            text = node.get_text(" ", strip=True)
            # ECI titles often look like "Constituency : Villivakkam" or just the name
            match = re.search(r"constituency\s*[:\-]\s*(.+)", text, re.I)
            title = match.group(1).strip() if match else text.strip()
            if title:
                break

    tbl = _find_candidate_table(soup)
    if not tbl:
        return title or None, []

    rows = tbl.select("tr")
    if not rows:
        return title or None, []

    # Detect columns from header row
    header_cells = rows[0].find_all(["th", "td"])
    col_name = _resolve_col_index(header_cells, [r"candidate", r"name"])
    col_party = _resolve_col_index(header_cells, [r"party"])
    col_votes = _resolve_col_index(header_cells, [r"total\s*votes?", r"votes?\s*polled", r"votes?"])
    col_pct = _resolve_col_index(header_cells, [r"%\s*of\s*votes?", r"vote\s*%", r"percent"])

    if col_votes < 0:
        return title or None, []

    candidates: list[dict] = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) <= col_votes:
            continue
        votes_val = _parse_int(cells[col_votes].get_text(" ", strip=True))
        if votes_val is None:
            continue
        candidate: dict = {
            "candidate_name": cells[col_name].get_text(" ", strip=True) if col_name >= 0 and col_name < len(cells) else "",
            "party": cells[col_party].get_text(" ", strip=True) if col_party >= 0 and col_party < len(cells) else "",
            "votes": votes_val,
            "vote_pct": _parse_float(cells[col_pct].get_text(" ", strip=True)) if col_pct >= 0 and col_pct < len(cells) else None,
        }
        if candidate["candidate_name"] and candidate["votes"] > 0:
            candidates.append(candidate)

    # Sort descending by votes to ensure winner is first
    candidates.sort(key=lambda c: c["votes"], reverse=True)
    return title or None, candidates


def _extract_vote_result_from_candidates(
    constituency_name: str,
    candidates: list[dict],
    total_votes: int,
    source_url: str,
) -> VoteResult | None:
    """Build a VoteResult from a sorted candidate list (winner first)."""
    if len(candidates) < 2:
        return None
    winner = candidates[0]
    runner_up = candidates[1]
    vote_share = winner.get("vote_pct") or (
        round(winner["votes"] / total_votes * 100, 2) if total_votes > 0 else 0.0
    )
    return VoteResult(
        constituency_name=constituency_name,
        winning_candidate_name=winner["candidate_name"],
        winning_votes=winner["votes"],
        total_votes=total_votes,
        vote_share=float(vote_share),
        runner_up_name=runner_up["candidate_name"],
        runner_up_votes=runner_up["votes"],
        vote_margin=winner["votes"] - runner_up["votes"],
        source_url=source_url,
        party=winner.get("party", ""),
    )


def _collect_ac_links_from_index(html: str, base_url: str) -> list[tuple[str, str]]:
    """
    Return (constituency_name, url) pairs from an ECI state index page.
    ECI index pages link each AC as: <a href="CandidatewiseResult-NNNN.htm">Name</a>
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[str, str]] = []
    ac_pattern = re.compile(r"candidateresult|CandidatewiseResult|acresult", re.I)
    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if ac_pattern.search(href):
            name = a.get_text(" ", strip=True)
            abs_url = urljoin(base_url, href)
            results.append((name, abs_url))
    # Also try table rows that embed AC links
    if not results:
        for tbl in soup.select("table"):
            for row in tbl.select("tr"):
                cells = row.find_all(["td", "th"])
                for cell in cells:
                    a = cell.find("a", href=True)
                    if a and ac_pattern.search(a["href"]):
                        name = a.get_text(" ", strip=True)
                        abs_url = urljoin(base_url, a["href"])
                        results.append((name, abs_url))
    return results


def _total_votes_from_page(soup: BeautifulSoup) -> int:
    """Try to extract total valid votes from an ECI constituency page."""
    # ECI often has a summary row at the bottom: "Total" with summed votes
    for tbl in soup.select("table"):
        rows = tbl.select("tr")
        for row in reversed(rows):
            text = row.get_text(" ", strip=True).lower()
            if "total" in text:
                # grab the largest number in this row as total
                nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{4,}", text)]
                if nums:
                    return max(nums)
    return 0


# ---------------------------------------------------------------------------
# ECI fetch strategy — Playwright (ECI blocks plain httpx via Akamai CDN 403)
# ---------------------------------------------------------------------------

async def _playwright_get_html(page, url: str, wait_selector: str | None = None) -> tuple[str, str]:
    """
    Navigate Playwright page to url, optionally wait for a CSS selector,
    return (final_url, html).
    """
    try:
        await page.goto(url, wait_until="networkidle", timeout=30_000)
        if wait_selector:
            await page.wait_for_selector(wait_selector, timeout=10_000)
    except Exception:
        pass  # best-effort; grab whatever rendered
    return page.url, await page.content()


async def fetch_eci_playwright() -> ParseState:
    """
    Use Playwright headless Chromium to bypass Akamai CDN 403.
    Navigates the ECI index page, collects AC links, then visits each
    constituency page with REQUEST_DELAY seconds between requests.
    """
    from playwright.async_api import async_playwright

    state = ParseState(source="eci")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=UA,
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = await ctx.new_page()

        # Find a working ECI index page
        index_html = ""
        index_base = ""
        for idx_url in ECI_INDEX_URLS:
            final_url, html = await _playwright_get_html(page, idx_url)
            if "Access Denied" not in html and len(html) > 1000:
                index_html = html
                index_base = final_url
                print(f"  [ECI] index OK via Playwright: {final_url} ({len(html)} bytes)")
                break
            print(f"  [ECI] blocked/empty: {idx_url}")

        if not index_html:
            state.parse_errors.append(
                "ECI index: all URLs blocked or empty — election results may not be published yet"
            )
            await browser.close()
            return state

        ac_links = _collect_ac_links_from_index(index_html, index_base)
        print(f"  [ECI] found {len(ac_links)} constituency links")

        if not ac_links:
            state.parse_errors.append(
                "ECI index: no constituency links found — the index page may use a "
                "JS framework that needs additional wait selectors; inspect with probe"
            )
            await browser.close()
            return state

        for i, (ac_name, ac_url) in enumerate(ac_links):
            await asyncio.sleep(REQUEST_DELAY)
            final_url, html = await _playwright_get_html(page, ac_url)
            soup = BeautifulSoup(html, "lxml")
            total_votes = _total_votes_from_page(soup)
            con_name, candidates = _parse_constituency_page(final_url, html)
            display_name = con_name or ac_name

            result = _extract_vote_result_from_candidates(
                display_name,
                candidates,
                total_votes or sum(c["votes"] for c in candidates),
                final_url,
            )
            if result:
                state.results.append(result)
                if (i + 1) % 20 == 0:
                    print(f"  [ECI] parsed {i+1}/{len(ac_links)} constituencies...")
            else:
                state.parse_errors.append(f"parse failed: {display_name} ({ac_url})")

        await browser.close()

    return state


def fetch_eci(client: httpx.Client) -> ParseState:
    """Sync wrapper — runs the Playwright coroutine in a new event loop."""
    return asyncio.run(fetch_eci_playwright())


# ---------------------------------------------------------------------------
# Wikipedia fallback parser
# ---------------------------------------------------------------------------

def _find_results_constituency_table(soup: BeautifulSoup) -> Tag | None:
    """
    Locate the 'Results by constituency' table in the Wikipedia TN election article.

    Primary: find the <h3 id="Results_by_constituency"> heading then the next <table>.
    Fallback: scan all tables for one with 200+ data rows whose first header row
    contains 'Winner' and 'Runner Up'.
    """
    heading = soup.find(id="Results_by_constituency")
    if heading:
        tbl = heading.find_next("table")
        if tbl:
            return tbl

    # Fallback: look for the table by header content
    for tbl in soup.find_all("table"):
        first_row = tbl.find("tr")
        if not first_row:
            continue
        header_text = first_row.get_text(" ", strip=True).lower()
        if "winner" in header_text and "runner" in header_text:
            data_rows = [r for r in tbl.find_all("tr") if r.find("td")]
            if len(data_rows) >= 200:
                return tbl
    return None


def fetch_wikipedia(client: httpx.Client) -> ParseState:
    """
    Scrape Wikipedia's 2026 TN election article — specifically the
    'Results by constituency' table (h3#Results_by_constituency).

    Probed column layout (confirmed 2026-06-05):
      Row with 14 cells (district rowspan first row of district block):
        [0]=district  [1]=no  [2]=constituency
        [3]=winner_name  [4]=winner_img  [5]=winner_party
        [6]=winner_votes  [7]=winner_share%
        [8]=runner_name  [9]=runner_img  [10]=runner_party
        [11]=runner_votes  [12]=runner_share%  [13]=margin
      Row with 13 cells (district absent — same rowspan block):
        same layout shifted left by 1 (no district cell)

    total_votes is derived: winner_votes * 100 / winner_share (rounded).
    """
    state = ParseState(source="wiki")
    html = ""
    final_url = ""
    for wiki_url in WIKI_2026_URLS:
        status, final_url, html = _get(client, wiki_url)
        if status == 200 and len(html) > 10_000:
            print(f"  [Wiki] {status} {final_url} ({len(html)} bytes)")
            break
        print(f"  [Wiki] {status} {wiki_url}")
    else:
        state.parse_errors.append(
            "Wikipedia: all URL variants returned non-200 or empty — "
            f"article may not exist yet; check {WIKI_2026_URLS[0]}"
        )
        return state

    soup = BeautifulSoup(html, "lxml")
    tbl = _find_results_constituency_table(soup)

    if not tbl:
        state.parse_errors.append(
            "Wikipedia: 'Results by constituency' table not found — "
            "article structure may have changed; re-run probe"
        )
        return state

    data_rows = [row for row in tbl.find_all("tr") if row.find("td")]
    print(f"  [Wiki] results table: {len(data_rows)} data rows")

    for row in data_rows:
        cells = row.find_all(["td", "th"])
        n = len(cells)

        # Determine offset: 14+ cells means district cell is present
        off = 1 if n >= 14 else 0

        # Need at least offset + 13 cells (margin is last)
        if n < off + 13:
            state.parse_errors.append(
                f"skipped row with {n} cells (expected 13 or 14): "
                f"{[c.get_text(' ', strip=True)[:20] for c in cells[:4]]}"
            )
            continue

        def _c(idx: int) -> str:
            return cells[off + idx].get_text(" ", strip=True) if (off + idx) < len(cells) else ""

        con_name = _c(1)           # constituency name (index 1 after offset)
        winner_name = _c(2)        # winner candidate
        # _c(3) = winner party img — skip
        winner_party = _c(4)       # winner party abbreviation
        winner_votes = _parse_int(_c(5)) or 0
        vote_share = _parse_float(_c(6)) or 0.0
        runner_name = _c(7)        # runner-up candidate
        # _c(8) = runner party img — skip
        runner_party = _c(9)       # runner-up party abbreviation
        runner_votes = _parse_int(_c(10)) or 0
        # _c(11) = runner share% — we don't need it
        vote_margin = _parse_int(_c(12)) or 0

        if not con_name or not winner_name or winner_votes <= 0:
            continue

        # Derive total_votes from winner's vote share
        if vote_share > 0:
            total_votes = round(winner_votes * 100 / vote_share)
        else:
            total_votes = winner_votes + runner_votes  # lower bound

        state.results.append(VoteResult(
            constituency_name=con_name,
            winning_candidate_name=winner_name,
            winning_votes=winner_votes,
            total_votes=total_votes,
            vote_share=vote_share,
            runner_up_name=runner_name,
            runner_up_votes=runner_votes,
            vote_margin=vote_margin,
            source_url=final_url,
            party=winner_party,
        ))

    print(f"  [Wiki] extracted {len(state.results)} constituency results")
    return state


# ---------------------------------------------------------------------------
# Store — fuzzy match + Supabase upsert
# ---------------------------------------------------------------------------

def _load_constituency_map(sb_client) -> dict[str, tuple[str, str]]:
    """
    Returns {normalised_name: (constituency_id, mla_id)} for all constituencies
    that have an MLA row. Queries mlas JOIN constituencies by constituency_id.
    """
    resp = (
        sb_client.table("constituencies")
        .select("id, name")
        .execute()
    )
    constituency_rows = resp.data or []

    resp2 = (
        sb_client.table("mlas")
        .select("id, constituency_id")
        .execute()
    )
    mla_rows = resp2.data or []
    mla_by_cid: dict[str, str] = {r["constituency_id"]: r["id"] for r in mla_rows}

    mapping: dict[str, tuple[str, str]] = {}
    for row in constituency_rows:
        norm = _normalise_name(row["name"])
        mla_id = mla_by_cid.get(row["id"], "")
        mapping[norm] = (row["id"], mla_id)
    return mapping


def _fuzzy_match(raw_name: str, mapping: dict[str, tuple[str, str]]) -> tuple[str, str, int]:
    """
    Fuzzy-match raw_name against the normalised constituency name map.
    Applies _CONSTITUENCY_ALIASES before fuzzy scoring to handle known name mismatches.
    Returns (constituency_id, mla_id, score). Empty strings + score=0 if no match.
    """
    norm = _normalise_name(raw_name)
    norm = _CONSTITUENCY_ALIASES.get(norm, norm)  # apply alias before fuzzy
    keys = list(mapping.keys())
    match = fuzz_process.extractOne(norm, keys, scorer=fuzz.WRatio, score_cutoff=FUZZY_THRESHOLD)
    if not match:
        return "", "", 0
    matched_key, score, _ = match
    cid, mid = mapping[matched_key]
    return cid, mid, score


def store(results: list[VoteResult], dry_run: bool = False) -> tuple[int, int, list[str]]:
    """
    Match results to Supabase rows and upsert vote data into `mlas`.
    Returns (rows_upserted, unmatched_count, error_messages).
    """
    if not results:
        return 0, 0, ["no results to store"]

    errors: list[str] = []
    sb_client = create_client()
    constituency_map = _load_constituency_map(sb_client)
    print(f"  [store] loaded {len(constituency_map)} constituencies from Supabase")

    payloads: list[dict] = []
    unmatched: list[str] = []

    for r in results:
        cid, mid, score = _fuzzy_match(r.constituency_name, constituency_map)
        if not cid:
            unmatched.append(r.constituency_name)
            errors.append(f"no match for constituency {r.constituency_name!r}")
            continue
        if not mid:
            # No MLA row yet — build a new MLA id from constituency id
            # e.g. AC-014 -> MLA-014
            mid = "MLA-" + cid.split("-")[1]

        r.constituency_id = cid
        r.mla_id = mid

        payload: dict = {
            "id": mid,
            "constituency_id": cid,
            "name": r.winning_candidate_name,
            "party": r.party or "Unknown",
            "assembly_number": ASSEMBLY_NUMBER,
            "elected_year": ELECTED_YEAR,
            "vote_margin": r.vote_margin,
            "vote_share_pct": round(r.vote_share, 2),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            # Extended columns (need ALTER TABLE above if not present)
            "winning_votes": r.winning_votes,
            "total_votes": r.total_votes,
            "runner_up_name": r.runner_up_name,
            "runner_up_votes": r.runner_up_votes,
        }
        payloads.append(payload)

    if not payloads:
        return 0, len(unmatched), errors

    if dry_run:
        print(f"  [dry-run] would upsert {len(payloads)} rows (skipping DB write)")
        for p in payloads[:5]:
            print(f"    {p}")
        return len(payloads), len(unmatched), errors

    # Try upsert with extended columns; fall back to core columns if they fail
    try:
        resp = sb_client.table("mlas").upsert(payloads, on_conflict="id").execute()
        rows_written = len(resp.data or [])
    except Exception as exc:
        errors.append(f"upsert with extended columns failed: {exc} — retrying with core columns only")
        # Retry with only the columns the schema is guaranteed to have
        core_keys = {"id", "constituency_id", "name", "party", "assembly_number",
                     "elected_year", "vote_margin", "vote_share_pct", "last_updated"}
        core_payloads = [{k: v for k, v in p.items() if k in core_keys} for p in payloads]
        try:
            resp = sb_client.table("mlas").upsert(core_payloads, on_conflict="id").execute()
            rows_written = len(resp.data or [])
            errors.append("stored core columns only — run ALTER TABLE to add extended columns")
        except Exception as exc2:
            errors.append(f"core-column upsert also failed: {exc2}")
            rows_written = 0

    return rows_written, len(unmatched), errors


# ---------------------------------------------------------------------------
# Report helper
# ---------------------------------------------------------------------------

def _write_report(report: AgentRunReport, dry_run: bool) -> None:
    if dry_run:
        print(f"  [dry-run] report: {report.model_dump_json(indent=2)}")
        return
    try:
        sb_client = create_client()
        payload = {
            "agent_name": report.agent_name,
            "status": report.status,
            "rows_written": report.rows_written,
            "error_message": report.error_message,
            "started_at": report.started_at.isoformat() if report.started_at else None,
            "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        }
        sb_client.table("agent_runs").insert(payload).execute()
    except Exception as exc:
        print(f"  [report] failed to write agent_runs: {exc}")


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

class VoteScraperAgent:
    """
    Scrapes 2026 TN assembly vote data from ECI (primary) or Wikipedia (fallback),
    matches constituencies, and upserts into Supabase mlas table.
    """

    AGENT_NAME = AGENT_NAME

    def __init__(
        self,
        source: Literal["auto", "eci", "wiki"] = "auto",
        dry_run: bool = False,
        request_delay: float = REQUEST_DELAY,
    ) -> None:
        self.source = source
        self.dry_run = dry_run
        self.request_delay = request_delay

    def fetch(self) -> ParseState:
        with _make_client() as client:
            if self.source == "wiki":
                return fetch_wikipedia(client)
            # ECI requires Playwright (plain httpx returns 403 from Akamai CDN)
            state = fetch_eci(client)   # client unused internally; kept for signature symmetry
            if len(state.results) < 10 and self.source == "auto":
                print(f"  [auto] ECI yielded {len(state.results)} results — falling back to Wikipedia")
                wiki_state = fetch_wikipedia(client)
                if len(wiki_state.results) > len(state.results):
                    return wiki_state
            return state

    def parse(self, state: ParseState) -> list[VoteResult]:
        """Validate parsed results: drop entries with missing critical fields."""
        valid: list[VoteResult] = []
        for r in state.results:
            if not r.winning_candidate_name:
                state.parse_errors.append(f"no winner name for {r.constituency_name!r}")
                continue
            if r.winning_votes <= 0:
                state.parse_errors.append(f"zero winning votes for {r.constituency_name!r}")
                continue
            if r.vote_margin < 0:
                r.vote_margin = 0  # clamp; shouldn't happen in clean data
            valid.append(r)
        return valid

    def run(self) -> AgentRunReport:
        started = datetime.now(timezone.utc)
        rows_written = 0
        status = "success"
        all_errors: list[str] = []

        try:
            state = self.fetch()
            all_errors.extend(state.parse_errors)

            valid_results = self.parse(state)
            print(f"  [run] {len(valid_results)} valid results from {state.source}")

            if not valid_results:
                status = "failed"
                all_errors.append("0 valid results after fetch+parse")
            else:
                rows_written, unmatched, store_errors = store(valid_results, dry_run=self.dry_run)
                all_errors.extend(store_errors)
                print(f"  [run] upserted={rows_written}  unmatched={unmatched}  errors={len(store_errors)}")
                if rows_written == 0:
                    status = "failed"
                elif unmatched > 5 or len(store_errors) > 10:
                    status = "partial"

        except Exception as exc:
            status = "failed"
            all_errors.append(f"{type(exc).__name__}: {exc}")

        error_message = "; ".join(all_errors[:10]) if all_errors else None
        report = AgentRunReport(
            agent_name=self.AGENT_NAME,
            status=status,
            rows_written=rows_written,
            error_message=error_message,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
        _write_report(report, dry_run=self.dry_run)
        return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vote scraper for TN 2026 assembly results")
    parser.add_argument("--source", choices=["auto", "eci", "wiki"], default="auto",
                        help="Data source (default: auto — ECI with Wikipedia fallback)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and parse but skip all DB writes")
    args = parser.parse_args()

    agent = VoteScraperAgent(source=args.source, dry_run=args.dry_run)
    result = agent.run()
    print(result.model_dump_json(indent=2))
    sys.exit(0 if result.status == "success" else 1)
