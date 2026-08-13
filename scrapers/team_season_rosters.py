"""Per-team-season roster -> data/raw/team_season_rosters.csv

Source: the `#roster` table on each team-season page. Uses the
generic `parse.parse_stat_table` instead of the old per-cell
`td:nth-child(N)` selectors - this is the single biggest quality win
from the refactor (see `parse.py` docstring): one table, one call,
scalar values, instead of ~10 hand-written selectors per column that
each built a one-item list.

Which team-seasons get scraped is decided by
`teams.list_team_season_links`, not by whatever the season index page
happens to link. It used to be the latter, and the difference is not
cosmetic: the index links a team-season only for champions, so once
the in-progress season ended, this file collapsed from every team to
one champion per season, taking `player_bios` (which takes its player
ids from this file) down with it.

Run directly (`python -m scrapers.team_season_rosters`) to scrape and
write data/raw/team_season_rosters.csv.
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
from scrapers.teams import TeamLink, list_team_season_links

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/raw/team_season_rosters.csv")


def team_season_roster(
    session: requests.Session, team: TeamLink, seen: set[str]
) -> list[dict[str, object]]:
    """Scrape one team-season's roster table into one dict per player."""
    href = team["link"]
    if href in seen:
        return []
    seen.add(href)

    html = fetch_page(session, href)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("#info #meta")
    if meta is None:
        return []

    title_spans = meta.select("h1 > span")
    season = title_spans[0].get_text(strip=True) if title_spans else None
    team_full_name = (
        title_spans[1].get_text(strip=True) if len(title_spans) > 1 else None
    )
    team_id = href_id(href, segment=-2)

    roster: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "#roster"):
        player_href = row.get("player_href")
        roster.append(
            {
                "TeamName": team_full_name,
                "Season": season,
                "PlayerName": row.get("player"),
                "Player_id": href_id(player_href) if player_href else None,
                "Team_id": team_id,
                "Pos": row.get("pos"),
                "Ht": row.get("height"),
                "Wt": row.get("weight"),
                "Birth Date": row.get("birth_date"),
                "Birth": row.get("flag"),
                "Exp": row.get("years_experience"),
                "College": row.get("college"),
            }
        )
    return roster


def scrape(
    session: requests.Session | None = None,
    season_years: range = DEFAULT_SEASON_YEARS,
    include_champions: bool = True,
    max_teams: int | None = None,
) -> pd.DataFrame:
    """Scrape every team-season's roster into one DataFrame.

    Covers all teams of every season in `season_years` plus every
    champion in league history - see
    :func:`scrapers.teams.list_team_season_links`.
    """
    session = session or build_session()
    seen: set[str] = set()
    links = list_team_season_links(
        session, season_years=season_years, include_champions=include_champions
    )
    if max_teams is not None:
        links = links[:max_teams]

    all_rows: list[dict[str, object]] = []
    for team in tqdm(links, desc="team rosters"):
        all_rows.extend(team_season_roster(session, team, seen))
    return pd.DataFrame(all_rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
