"""Career stat summary -> data/raw/player_career_stats.csv

Source: the summary box at the top of each player's own page
(.../players/<first-letter>/<id>.html) - the same page `player_bios`
reads. Because both tables come from one page, `player_bios` imports
the parser below and writes both files from a single fetch, which is
why this file is not a separate step in `run_all`. Running this module
directly re-fetches every page, and is only worth doing to refresh
career stats without touching bios.

Nothing in the old codebase produced this table. `Scraper.players()`
came closest but scraped a single hardcoded player id, so the committed
`player_career_stats.csv` could not be regenerated at all - it was the
one input the pipeline could not rebuild from scratch.

Two of the column names below are wrong, and are kept anyway. "Career
Total Rebound Percentage" and "Career Assists Percentage" hold rebounds
and assists *per game*, not percentages, and "Career Points" is points
per game rather than a career total. The names come from the original
bootcamp scrape and flow through `cleaning/players.py` into the
database, so renaming them here alone would quietly break that chain.
See docs/data_dictionary.md, where the real meaning is documented.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page

logger = logging.getLogger(__name__)

PLAYER_URL = "https://www.basketball-reference.com/players/{first_letter}/{id}.html"
ROSTERS_PATH = Path("data/raw/team_season_rosters.csv")
OUTPUT_PATH = Path("data/raw/player_career_stats.csv")

#: Abbreviation shown in the summary box -> output column name.
#: The output names are the ones `cleaning/players.py` expects; see the
#: module docstring on why two of them are misnomers.
CAREER_STAT_COLUMNS: dict[str, str] = {
    "G": "Career Games",
    "PTS": "Career Points",
    "TRB": "Career Total Rebound Percentage",
    "AST": "Career Assists Percentage",
    "FG%": "Career Field Goal Percentage",
    "FG3%": "Career 3pt Field Goal Percentage",
    "FT%": "Career Free Throw Percentage",
    "eFG%": "Career Effective Field Goal Percentage",
    "PER": "Career Player Efficiency Rating",
    "WS": "Career Win Shares",
}

#: Text of the header cell marking the career column.
_CAREER_HEADER = "career"


def _leaf_blocks(pullout: Tag) -> list[Tag]:
    """Return the innermost divs of the summary box - one per statistic.

    The box nests stat blocks inside grouping divs, so a naive scan sees
    each value twice: once on the leaf and once concatenated onto its
    parent. Keeping only divs that contain no further div avoids that.
    """
    return [div for div in pullout.select("div") if div.find("div") is None]


def _career_column_index(blocks: list[Tag]) -> int:
    """Find which value column holds career figures.

    The box shows the current season alongside the career line, and the
    header row names both. Reading the index off that header means a
    player whose page shows only one column (a rookie mid-debut-season,
    or a retired player) still lands on the right value instead of
    silently taking the wrong one.
    """
    for block in blocks:
        label = block.find("span")
        if label is None or label.get_text(strip=True).lower() != "summary":
            continue
        headers = [p.get_text(strip=True).lower() for p in block.select("p")]
        if _CAREER_HEADER in headers:
            return headers.index(_CAREER_HEADER)
    return -1  # no header found: fall back to the last column


def parse_career_stats(soup: BeautifulSoup) -> dict[str, str]:
    """Pull the career column out of a player page's summary box.

    Returns the stats found, keyed by output column name. Statistics the
    page does not show for this player are simply absent, which becomes
    an empty cell in the CSV rather than a fabricated zero.
    """
    pullout = soup.select_one(".stats_pullout")
    if pullout is None:
        return {}

    blocks = _leaf_blocks(pullout)
    career_index = _career_column_index(blocks)

    stats: dict[str, str] = {}
    for block in blocks:
        label_tag = block.find("span")
        if label_tag is None:
            continue
        column = CAREER_STAT_COLUMNS.get(label_tag.get_text(strip=True))
        if column is None:
            continue
        values = [p.get_text(strip=True) for p in block.select("p")]
        if not values:
            continue
        # A player with fewer columns than the header promises still has
        # his career figure last, so clamp rather than index blindly.
        index = career_index if -1 < career_index < len(values) else len(values) - 1
        value = values[index]
        if value and value != "-":
            stats[column] = value
    return stats


def career_stats(
    session: requests.Session, player_id: str
) -> dict[str, object] | None:
    """Fetch one player's page and return his career summary row."""
    url = PLAYER_URL.format(first_letter=player_id[0], id=player_id)
    html = fetch_page(session, url)
    if html is None:
        return None

    soup = BeautifulSoup(html, "html.parser")
    stats = parse_career_stats(soup)
    if not stats:
        return None

    name_tag = soup.select_one("#info #meta h1 span")
    return {
        "player_id": player_id,
        "player_name": name_tag.get_text(strip=True) if name_tag else None,
        **stats,
    }


def _player_ids_from_rosters(path: Path = ROSTERS_PATH) -> list[str]:
    """Default player-id universe: everyone seen on a scraped roster."""
    frame = pd.read_csv(path, usecols=["Player_id"])
    return sorted(frame["Player_id"].dropna().unique().tolist())


def scrape(
    session: requests.Session | None = None,
    player_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Scrape a career summary for every id in `player_ids`.

    Prefer `player_bios.main()`, which produces this table and the bio
    table from the same set of page fetches.
    """
    session = session or build_session()
    ids = player_ids if player_ids is not None else []

    rows: list[dict[str, object]] = []
    for player_id in tqdm(ids, desc="career stats"):
        row = career_stats(session, player_id)
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows)


def main(player_ids: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    ids = player_ids if player_ids is not None else _player_ids_from_rosters()
    frame = scrape(player_ids=ids)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(frame), OUTPUT_PATH)


if __name__ == "__main__":
    main()
