"""Per-season player totals -> data/raw/player_stats.csv

Source: the `#totals_stats` table on
.../leagues/NBA_<year>_totals.html, one page per season.

Run directly (`python -m scrapers.player_stats`) to scrape and write
data/raw/player_stats.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.config import DEFAULT_SEASON_YEARS
from scrapers.fetch import build_session, fetch_page
from scrapers.parse import href_id, parse_stat_table

logger = logging.getLogger(__name__)

TOTALS_URL = "https://www.basketball-reference.com/leagues/NBA_{year}_totals.html"
OUTPUT_PATH = Path("data/raw/player_stats.csv")


def player_stats_for_season(
    session: requests.Session, year: int
) -> list[dict[str, object]]:
    """Scrape one season's player-totals table into one dict per player."""
    html = fetch_page(session, TOTALS_URL.format(year=year))
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "table#totals_stats"):
        name_href = row.get("name_display_href")
        records.append(
            {
                "Year": year,
                "Rank": row.get("ranker"),
                "Player_Id": href_id(name_href) if name_href else None,
                "Age": row.get("age"),
                "Team": row.get("team_name_abbr"),
                "Position": row.get("pos"),
                "Games": row.get("games"),
                "Games Started": row.get("games_started"),
                "Minutes Played": row.get("mp"),
                "FG": row.get("fg"),
                "FGA": row.get("fga"),
                "FG%": row.get("fg_pct"),
                "3P": row.get("fg3"),
                "3PA": row.get("fg3a"),
                "3p%": row.get("fg3_pct"),
                "2P": row.get("fg2"),
                "2PA": row.get("fg2a"),
                "2P%": row.get("fg2_pct"),
                "eFG%": row.get("efg_pct"),
                "FT": row.get("ft"),
                "FTA": row.get("fta"),
                "FT%": row.get("ft_pct"),
                "ORB": row.get("orb"),
                "DRB": row.get("drb"),
                "TRB": row.get("trb"),
                "AST": row.get("ast"),
                "STL": row.get("stl"),
                "BLK": row.get("blk"),
                "TOV": row.get("tov"),
                "PF": row.get("pf"),
                "PTS": row.get("pts"),
                "Trp_Dbl": row.get("tpl_dbl"),
            }
        )
    return records


def scrape(
    session: requests.Session | None = None,
    season_years: range = DEFAULT_SEASON_YEARS,
) -> pd.DataFrame:
    """Scrape every season in `season_years` into one DataFrame."""
    session = session or build_session()
    all_rows: list[dict[str, object]] = []
    for year in tqdm(list(season_years), desc="player stats"):
        all_rows.extend(player_stats_for_season(session, year))
    return pd.DataFrame(all_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
