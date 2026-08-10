"""Per-season player advanced stats -> data/raw/advanced_stats.csv

Source: the `#advanced` table on
.../leagues/NBA_<year>_advanced.html, one page per season.

Run directly (`python -m scrapers.advanced_stats`) to scrape and write
data/raw/advanced_stats.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page
from scrapers.parse import href_id, parse_stat_table

logger = logging.getLogger(__name__)

DEFAULT_SEASON_YEARS: range = range(2019, 2027)

ADVANCED_URL = "https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html"
OUTPUT_PATH = Path("data/raw/advanced_stats.csv")


def advanced_stats_for_season(
    session: requests.Session, year: int
) -> list[dict[str, object]]:
    """Scrape one season's advanced-stats table into one dict per player."""
    html = fetch_page(session, ADVANCED_URL.format(year=year))
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "table#advanced"):
        name_href = row.get("name_display_href")
        records.append(
            {
                "Season": year,
                "Rank": row.get("ranker"),
                "Player_id": href_id(name_href) if name_href else None,
                "Age": row.get("age"),
                "Team": row.get("team_name_abbr"),
                "Position": row.get("pos"),
                "Games": row.get("games"),
                "Games_started": row.get("games_started"),
                "Minute_Played": row.get("mp"),
                "Player_Efficiency_Rate": row.get("per"),
                "True_Shooting_Percentage": row.get("ts_pct"),
                "Three_Point_Attempt_Rate": row.get("fg3a_per_fga_pct"),
                "Free_Throw_Attempt_Rate": row.get("fta_per_fga_pct"),
                "Offensive_Rebound_Percentage": row.get("orb_pct"),
                "Defensive_Rebound_Percentage": row.get("drb_pct"),
                "Total_Rebound_Percentage": row.get("trb_pct"),
                "Assist_Percentage": row.get("ast_pct"),
                "Steal_Percentage": row.get("stl_pct"),
                "Block_Percentage": row.get("blk_pct"),
                "Turnover_Percentage": row.get("tov_pct"),
                "Usage_Percentage": row.get("usg_pct"),
                "Offensive_Win_Shares": row.get("ows"),
                "Defensive_Win_Shares": row.get("dws"),
                "Win_Shares": row.get("ws"),
                "Win_Shares_Per_48_Minutes": row.get("ws_per_48"),
                "Offensive_Box_Plus_Minus": row.get("obpm"),
                "Defensive_Box_Plus_Minus": row.get("dbpm"),
                "Box_Plus_Minus": row.get("bpm"),
                "Value_over_Replacement_Player": row.get("vorp"),
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
    for year in tqdm(list(season_years), desc="advanced stats"):
        all_rows.extend(advanced_stats_for_season(session, year))
    return pd.DataFrame(all_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
