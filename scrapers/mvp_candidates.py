"""Per-season MVP award ballot -> data/raw/mvp_candidates.csv

Source: the `#mvp` table on .../awards/awards_<year>.html, one page
per season - every player who received an MVP vote that season, not
just the winner (see `mvp_winners.py` for the historical winners
list).

Run directly (`python -m scrapers.mvp_candidates`) to scrape and write
data/raw/mvp_candidates.csv.
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

AWARDS_URL = "https://www.basketball-reference.com/awards/awards_{year}.html"
OUTPUT_PATH = Path("data/raw/mvp_candidates.csv")


def mvp_candidates_for_season(
    session: requests.Session, year: int
) -> list[dict[str, object]]:
    """Scrape one season's MVP ballot into one dict per candidate."""
    html = fetch_page(session, AWARDS_URL.format(year=year))
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "table#mvp"):
        player_href = row.get("player_href")
        records.append(
            {
                "Year": year,
                "Rank": row.get("rank"),
                "Player_Id": href_id(player_href) if player_href else None,
                "Age": row.get("age"),
                "Team": row.get("team_id"),
                "First_Place_Vote": row.get("votes_first"),
                "Pts Won": row.get("points_won"),
                "pts Max": row.get("points_max"),
                "Share": row.get("award_share"),
                "Games": row.get("g"),
                "MP": row.get("mp_per_g"),
                "PTS": row.get("pts_per_g"),
                "TRB": row.get("trb_per_g"),
                "AST": row.get("ast_per_g"),
                "STL": row.get("stl_per_g"),
                "BLK": row.get("blk_per_g"),
                "FG%": row.get("fg_pct"),
                "3P%": row.get("fg3_pct"),
                "FT%": row.get("ft_pct"),
                "WS": row.get("ws"),
                "WS/48": row.get("ws_per_48"),
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
    for year in tqdm(list(season_years), desc="mvp candidates"):
        all_rows.extend(mvp_candidates_for_season(session, year))
    return pd.DataFrame(all_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
