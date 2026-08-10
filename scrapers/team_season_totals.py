"""Per-season team totals -> data/raw/team_season_totals.csv

Source: the `#totals-team` table on each season page
(.../leagues/NBA_<year>.html). Unlike `player_stats.py` /
`advanced_stats.py` / `mvp_candidates.py` (which only need seasons
2019-2026 for the Phase 3 analysis), this covers every season in
league history, so it discovers season links from the season index
page rather than building a fixed year range.

Run directly (`python -m scrapers.team_season_totals`) to scrape and
write data/raw/team_season_totals.csv.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page, normalize_url
from scrapers.parse import href_id, parse_stat_table

logger = logging.getLogger(__name__)

SEASON_INDEX_URL = "https://www.basketball-reference.com/leagues/"
OUTPUT_PATH = Path("data/raw/team_season_totals.csv")

SeasonLink = dict[str, str]

_SEASON_HREF_PATTERN = re.compile(r"^/leagues/NBA_[0-9]{4}\.html$")


def list_season_links(
    session: requests.Session, url: str = SEASON_INDEX_URL
) -> list[SeasonLink]:
    """Collect every season-page link ('/leagues/NBA_YYYY.html') from
    the season index page."""
    html = fetch_page(session, url)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[SeasonLink] = []
    for anchor in soup.find_all("a", href=_SEASON_HREF_PATTERN):
        text = anchor.get_text(strip=True)
        if text == "NBA":
            continue
        links.append(
            {"season": text, "link": urljoin(normalize_url(url), anchor["href"])}
        )
    return links


def season_team_totals(
    session: requests.Session, season: SeasonLink, seen: set[str]
) -> list[dict[str, object]]:
    """Scrape one season's team-totals table into one dict per team."""
    href = season["link"]
    if href in seen:
        return []
    seen.add(href)

    html = fetch_page(session, href)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "#totals-team"):
        team_href = row.get("team_href")
        records.append(
            {
                "Rk": row.get("ranker"),
                "Season": season["season"],
                "TeamName": row.get("team"),
                "TeamId": href_id(team_href, segment=-2) if team_href else None,
                "G": row.get("g"),
                "MP": row.get("mp"),
                "FG": row.get("fg"),
                "FGA": row.get("fga"),
                "FG%": row.get("fg_pct"),
                "3P": row.get("fg3"),
                "3PA": row.get("fg3a"),
                "3P%": row.get("fg3_pct"),
                "2P": row.get("fg2"),
                "2PA": row.get("fg2a"),
                "2P%": row.get("fg2_pct"),
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
            }
        )
    return records


def scrape(
    session: requests.Session | None = None, max_seasons: int | None = None
) -> pd.DataFrame:
    """Scrape every season's team totals into one DataFrame."""
    session = session or build_session()
    seen: set[str] = set()
    links = list_season_links(session)
    if max_seasons is not None:
        links = links[:max_seasons]

    all_rows: list[dict[str, object]] = []
    for season in tqdm(links, desc="team season totals"):
        all_rows.extend(season_team_totals(session, season, seen))
    return pd.DataFrame(all_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
