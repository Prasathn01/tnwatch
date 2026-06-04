"""
Wikipedia table helpers.

Wikipedia `wikitable`s lean heavily on `rowspan`/`colspan` (e.g. a District cell
that spans 6 member rows, or a Party column rendered as a colour-swatch cell plus
a name cell). Parsing by raw cell position is therefore fragile. These helpers
expand a table into a dense grid where every logical (row, col) is filled, and
resolve logical columns from the header text so a column-order change on Wikipedia
does not silently break parsing (CONTEXT.md §9 Rule 7: resilient scrapers).

Pure functions, no I/O — safe to unit-test against saved HTML fixtures.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

Grid = list[list[Tag | None]]


def table_to_grid(table: Tag) -> Grid:
    """
    Expand an HTML table into a rectangular grid of cell Tags, propagating
    `rowspan` and `colspan` so every covered position points at its source cell.

    Returns a list of rows; each row is a list of `Tag | None` of uniform width.
    A position is `None` only if the source HTML is genuinely ragged.
    """
    body = table.find("tbody") or table
    rows = body.find_all("tr", recursive=False)

    grid: list[dict[int, Tag]] = []

    def ensure(r: int) -> None:
        while len(grid) <= r:
            grid.append({})

    for r, tr in enumerate(rows):
        ensure(r)
        col = 0
        for cell in tr.find_all(["td", "th"], recursive=False):
            # skip columns already occupied by a rowspan coming from above
            while col in grid[r]:
                col += 1
            rowspan = _int_attr(cell, "rowspan")
            colspan = _int_attr(cell, "colspan")
            for dc in range(colspan):
                for dr in range(rowspan):
                    ensure(r + dr)
                    grid[r + dr][col + dc] = cell
            col += colspan

    width = max((max(rowdict) + 1 for rowdict in grid if rowdict), default=0)
    return [[rowdict.get(c) for c in range(width)] for rowdict in grid]


def cell_text(cell: Tag | None) -> str:
    """Whitespace-collapsed text of a cell ('' for None)."""
    return cell.get_text(" ", strip=True) if cell is not None else ""


def cell_link(cell: Tag | None) -> str | None:
    """href of the first <a> in a cell, or None (skips citation/footnote anchors)."""
    if cell is None:
        return None
    for a in cell.find_all("a"):
        href = a.get("href", "")
        if href and not href.startswith("#"):
            return href
    return None


def resolve_columns(header_row: list[Tag | None], wanted: dict[str, list[str]]) -> dict[str, int]:
    """
    Map logical field names to grid column indices using header text.

    `wanted` maps a logical field to a list of accepted header needles
    (case-insensitive). An EXACT header match wins over a substring match — this
    disambiguates pages with several similar headers (e.g. "Constituency" vs
    "Lok Sabha constituency" vs "Constituency Map"). Among matches of the same
    kind the LAST column index is returned, because a colspan group's value cell
    (e.g. Party = [colour-swatch, name]) follows its swatch cell.

    Raises KeyError listing any fields whose header could not be found, so a
    Wikipedia layout change fails loudly at parse time rather than silently
    mislabelling data.
    """
    texts = [cell_text(c).lower() for c in header_row]
    resolved: dict[str, int] = {}
    for field, needles in wanted.items():
        needles_l = [n.lower() for n in needles]
        exact = [i for i, t in enumerate(texts) if t in needles_l]
        substr = [i for i, t in enumerate(texts) if any(n in t for n in needles_l)]
        chosen = exact or substr
        if chosen:
            resolved[field] = chosen[-1]
    missing = [f for f in wanted if f not in resolved]
    if missing:
        raise KeyError(f"Could not locate header column(s) {missing} in headers {texts}")
    return resolved


def find_wikitable(html: str, *, contains_headers: list[str]) -> Tag:
    """
    Return the first `table.wikitable` whose header row contains all the given
    header substrings (case-insensitive). Lets an agent target the right table by
    its columns instead of a brittle positional index.

    Raises LookupError if no table matches.
    """
    soup = BeautifulSoup(html, "lxml")
    needles = [h.lower() for h in contains_headers]
    for table in soup.select("table.wikitable"):
        grid = table_to_grid(table)
        if not grid:
            continue
        header_text = " ".join(cell_text(c).lower() for c in grid[0])
        if all(n in header_text for n in needles):
            return table
    raise LookupError(f"No wikitable with headers containing {contains_headers}")


def _int_attr(cell: Tag, name: str) -> int:
    raw = cell.get(name)
    try:
        value = int(raw)
        return value if value > 0 else 1
    except (TypeError, ValueError):
        return 1
