"""Historical MVP winners -> data/raw/mvp_winners.csv

Source: the `#mvp_NBA` table on https://www.basketball-reference.com/
awards/mvp.html - one row per season, the actual winner only (see
`mvp_candidates.py` for the full per-season ballot). This is one page
covering the league's whole history, so there is no year range to
loop over.

This replaces the old `Scraper.mvps()` method, which looped
`for i in range(70)` (a magic number - it happened to be roughly how
many seasons existed when that line was written) and re-queried the
DOM by position for every field. Here the table is parsed once via
`parse.parse_stat_table` and the row count follows automatically from
however many seasons actually exist.

Run directly (`python -m scrapers.mvp_winners`) to scrape and write
data/raw/mvp_winners.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.fetch import build_session, fetch_page
from scrapers.parse import href_id, parse_stat_table

logger = logging.getLogger(__name__)

MVP_INDEX_URL = "https://www.basketball-reference.com/awards/mvp.html"
OUTPUT_PATH = Path("data/raw/mvp_winners.csv")


def scrape(session: requests.Session | None = None) -> pd.DataFrame:
    """Scrape the full historical MVP-winners table into one DataFrame."""
    session = session or build_session()
    html = fetch_page(session, MVP_INDEX_URL)
    if html is None:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "table#mvp_NBA"):
        player_href = row.get("player_href")
        records.append(
            {
                "Season": row.get("season"),
                "League": row.get("lg_id"),
                "Player_id": href_id(player_href) if player_href else None,
                "Age": row.get("age"),
                "Team_id": row.get("team_id"),
                "Game": row.get("g"),
                "Minutes Played Per Game": row.get("mp_per_g"),
                "Points Per Game": row.get("pts_per_g"),
                "Total Rebounds Per Game": row.get("trb_per_g"),
                "Assists Per Game": row.get("ast_per_g"),
                "Steals Per Game": row.get("stl_per_g"),
                "Blocks Per Game": row.get("blk_per_g"),
                "Field Goal Percentage": row.get("fg_pct"),
                "3-Point Field Goal Percentage": row.get("fg3_pct"),
                "Free Throw Percentage": row.get("ft_pct"),
                "Win Shares": row.get("ws"),
                "Win Shares Per 48 Minutes": row.get("ws_per_48"),
            }
        )
    return pd.DataFrame(records)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
