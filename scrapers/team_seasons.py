"""Per-team-season "About" box -> data/raw/team_seasons.csv

Source: each team-season page (.../teams/<ABBR>/<YEAR>.html), reusing
the same links `teams.py` discovers on the season index page - but
unlike `teams.team_detail`, this does NOT truncate the link down to
the franchise page, since the season (e.g. "2024-25") and that
season's record/coach/arena info only exist on the season-specific
page.

Run directly (`python -m scrapers.team_seasons`) to scrape and write
data/raw/team_seasons.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page
from scrapers.parse import parse_meta_box
from scrapers.teams import TeamLink, list_team_links

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/raw/team_seasons.csv")


def team_season_detail(
    session: requests.Session, team: TeamLink, seen: set[str]
) -> dict[str, object] | None:
    """Fetch one team-season's "About" box: record, coach, arena, etc."""
    href = team["link"]
    if href in seen:
        return None
    seen.add(href)

    html = fetch_page(session, href)
    if html is None:
        return {"link": href}

    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("#info > #meta")
    if meta is None:
        return {"link": href}

    # The h1 on a team-season page has two spans: season, then team
    # name (a third, "Roster and Stats", is a page-section label we
    # don't need). Guarded with a length check in case a page ever
    # omits one - better a None field than a crashed scrape.
    title_spans = meta.select("h1 > span")
    result: dict[str, object] = {
        "link": href,
        "season": title_spans[0].get_text(strip=True) if title_spans else None,
        "team_full_name": (
            title_spans[1].get_text(strip=True) if len(title_spans) > 1 else None
        ),
    }

    for key, value in parse_meta_box(meta).items():
        if "_playoffs" in key:
            continue
        result[key] = value

    return result


def scrape(
    session: requests.Session | None = None, max_teams: int | None = None
) -> pd.DataFrame:
    """Scrape every team-season's "About" box into one DataFrame."""
    session = session or build_session()
    seen: set[str] = set()
    links = list_team_links(session)
    if max_teams is not None:
        links = links[:max_teams]

    details: list[dict[str, object]] = []
    for team in tqdm(links, desc="team seasons"):
        detail = team_season_detail(session, team, seen)
        if detail is not None:
            details.append(detail)
    return pd.DataFrame(details)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    df = scrape()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(df), OUTPUT_PATH)


if __name__ == "__main__":
    main()
