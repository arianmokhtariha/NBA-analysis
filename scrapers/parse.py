"""HTML parsing helpers shared by every scraper module.

Basketball-Reference's stat tables are consistent enough that one
generic parser (:func:`parse_stat_table`) can read almost all of them:
every data cell carries a `data-stat="..."` attribute naming its
column, so we walk the rows and pull cells out by that attribute
instead of hand-writing one CSS selector per column per table (the
pattern the old `Scraper.py` used - roughly 500 lines of copy-pasted
`td:nth-child(N)` selectors, one clause per column per row, rebuilt
from scratch for every table).

A second family of pages (team/season "About" boxes, `id="meta"`)
uses a different layout: `<p><strong>Label:</strong> value</p>`
pairs. :func:`parse_meta_box` handles those.
"""

from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup, NavigableString, Tag

# Row classes basketball-reference uses to mark header / separator
# rows that are not real data. These show up inside <tbody> too - long
# tables repeat the column header every ~20 rows - so filtering by
# class is more reliable than assuming a <thead>/<tbody> split exists
# at all (the season-index table has neither: its rows sit directly
# under <table>, and Python's built-in html.parser, unlike a browser
# or lxml, will not invent a <tbody> that was never in the source).
_HEADER_ROW_CLASSES = {"thead", "over_header"}


class SeasonsSummary(TypedDict):
    """Parsed form of a franchise page's "Seasons: N (YYYY-YY, ...)" line."""

    raw: str
    count: int | None
    range: str | None


def to_snake_case(label: str) -> str:
    """Turn a page label like "Draft Position:" into "draft_position"."""
    label = label.strip().rstrip(":")
    label = re.sub(r"[^\w]+", "_", label)
    label = re.sub(r"__+", "_", label)
    return label.strip("_").lower()


def try_int(value: str) -> int | str:
    """Coerce a purely-numeric string (commas allowed) to `int`.

    Anything that isn't a plain integer (dates, percentages, names,
    "N/A", ...) is returned unchanged.
    """
    stripped = value.replace(",", "").strip()
    if re.fullmatch(r"\d+", stripped):
        return int(stripped)
    return value


def parse_seasons_summary(value: str) -> SeasonsSummary:
    """Parse a franchise "Seasons" meta line, e.g. "77 (1949-50 to 2025-26)"."""
    parts = [p.strip() for p in value.split(";") if p.strip()]
    result: SeasonsSummary = {"raw": value, "count": None, "range": None}
    if not parts:
        return result

    match = re.match(r"^(\d+)$", parts[0])
    if match:
        result["count"] = int(match.group(1))
        if len(parts) > 1:
            result["range"] = parts[1]
    elif len(parts) == 1 and re.search(r"\d{4}", parts[0]):
        result["range"] = parts[0]
    return result


def parse_meta_box(meta: Tag) -> dict[str, str | int]:
    """Parse the '<p><strong>Label:</strong> value</p>' pairs found in a
    basketball-reference '#meta' info box (used on team and season
    pages) into a `{snake_case_label: value}` dict, with purely
    numeric values coerced to `int`.

    Only the *first* `<strong>` in each `<p>` is treated as a label -
    matching how these boxes are laid out in practice (one label per
    paragraph on team/season pages; player-page bio boxes, which
    sometimes pack two labels into one paragraph, are handled
    separately in `player_bios.py`).
    """
    result: dict[str, str | int] = {}
    for p in meta.select("p"):
        strong = p.find("strong")
        if strong is None:
            continue
        key = to_snake_case(strong.get_text(strip=True))

        pieces: list[str] = []
        for sibling in strong.next_siblings:
            if isinstance(sibling, NavigableString):
                text = str(sibling)
            else:
                text = sibling.get_text(separator=" ", strip=True)
            if text and text != "\n":
                pieces.append(text)

        raw_value = re.sub(r"\s+", " ", " ".join(pieces)).strip()
        value = raw_value.strip(" ;:\n\t,")
        result[key] = try_int(value)
    return result


def parse_stat_table(
    soup: BeautifulSoup, table_selector: str
) -> list[dict[str, str | None]]:
    """Parse a basketball-reference 'data-stat' table into row dicts.

    Every data cell in these tables carries `data-stat="column_name"`.
    This walks every `<tr>` in the table, skips header/separator rows,
    and returns one dict per data row keyed by `data-stat` name.

    A row is treated as a header, not data, if either:

    - its class is one of `_HEADER_ROW_CLASSES` (how long tables mark
      a column header repeated every ~20 rows), or
    - any of its cells carries `scope="col"` (how a table's single
      leading header row is marked; data rows use `scope="row"` on
      their row-header cell instead). Not every header row gets a
      "thead" class - the short `#roster` table's header row has none
      - so this second check catches what the class check alone would
      miss.

    When a cell's value is a link (a player name, team name, season,
    ...), the link's own text is used as the cell value - matching
    what the original hand-written selectors did (`td[...] a`) - and
    the href is additionally captured under `f"{data_stat}_href"` so
    callers can derive ids without re-selecting the row. This also
    quietly avoids picking up trailing decorations basketball-
    reference appends outside the link, e.g. the "*" after a
    playoff-team name or the "(2143)" after a stat leader's name.
    """
    table = soup.select_one(table_selector)
    if table is None:
        return []

    rows: list[dict[str, str | None]] = []
    for tr in table.select("tr"):
        row_classes = set(tr.get("class") or [])
        if row_classes & _HEADER_ROW_CLASSES:
            continue

        cells = tr.select("th[data-stat], td[data-stat]")
        if not cells:
            continue
        if any(cell.get("scope") == "col" for cell in cells):
            continue

        row: dict[str, str | None] = {}
        for cell in cells:
            stat_name = cell["data-stat"]
            link = cell.find("a")
            if link is not None:
                row[stat_name] = link.get_text(" ", strip=True) or None
                href = link.get("href")
                if href:
                    row[f"{stat_name}_href"] = href
            else:
                row[stat_name] = cell.get_text(" ", strip=True) or None
        rows.append(row)
    return rows


def href_id(href: str, segment: int = -1) -> str:
    """Pull an id token out of a basketball-reference relative link.

    `segment` indexes the URL's path parts from the end, mirroring how
    ids are positioned differently depending on the link type:

    >>> href_id("/players/c/carlsbr01.html")
    'carlsbr01'
    >>> href_id("/teams/OKC/2025.html", segment=-2)
    'OKC'
    """
    path = href.split("?", 1)[0]
    parts = [p for p in path.split("/") if p]
    return parts[segment].split(".")[0]
