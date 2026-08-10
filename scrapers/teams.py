"""Franchise list + franchise "About" box -> data/raw/teams.csv

Source pages:

- The season index (https://www.basketball-reference.com/leagues/)
  links to a team page for every season's champion, which is the only
  place '/teams/...' links appear on that page. `list_team_links` is
  also imported by `team_seasons.py` and `team_season_rosters.py`,
  which need the exact same links but treat them differently (this
  module collapses each link down to its franchise's own page; the
  other two use the season-specific link as-is).
- Each franchise's own page (.../teams/<ABBR>/) for its "About" box:
  founded date, arena, career seasons played, etc.

Run directly (`python -m scrapers.teams`) to scrape and write
data/raw/teams.csv.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page, normalize_url
from scrapers.parse import parse_meta_box, parse_seasons_summary

logger = logging.getLogger(__name__)

SEASON_INDEX_URL = "https://www.basketball-reference.com/leagues/"
OUTPUT_PATH = Path("data/raw/teams.csv")

TeamLink = dict[str, str]

_TEAM_HREF_PATTERN = re.compile(r"^/teams")
_SKIPPED_LINK_TEXT = {"F", "Teams"}


def list_team_links(
    session: requests.Session, url: str = SEASON_INDEX_URL
) -> list[TeamLink]:
    """Collect every '/teams/...' link on the season index page.

    Each link points at one season's champion, so the same franchise
    appears once per championship it has won (and franchises that
    changed names show up under each name they played under).
    """
    html = fetch_page(session, url)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[TeamLink] = []
    for anchor in soup.find_all("a", href=_TEAM_HREF_PATTERN):
        text = anchor.get_text(strip=True)
        if text in _SKIPPED_LINK_TEXT:
            continue
        links.append(
            {"team_name": text, "link": urljoin(normalize_url(url), anchor["href"])}
        )
    return links


def team_detail(
    session: requests.Session, team: TeamLink, seen: set[str]
) -> dict[str, object] | None:
    """Fetch one franchise's "About" box (founded date, arena, seasons
    played, etc).

    `team["link"]` may point at a specific season (it's a champion
    link from the index page), so this truncates it down to the
    franchise's own page (`/teams/<ABBR>/`) first. Returns None if
    that franchise was already visited via a different season's link.
    """
    parsed = urlparse(team["link"])
    base_path = "/".join(parsed.path.split("/")[:3])
    href = f"{parsed.scheme}://{parsed.netloc}{base_path}"
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

    title_span = meta.select_one("h1 span")
    result: dict[str, object] = {
        "link": href,
        "team_full_name": title_span.get_text(strip=True) if title_span else None,
    }

    for key, value in parse_meta_box(meta).items():
        if key == "team_name":
            result["team_names"] = value
            continue
        result[key] = value
        if key == "seasons":
            summary = parse_seasons_summary(str(value))
            result["seasons_count"] = summary["count"]
            result["seasons_range"] = summary["range"]

    return result


def scrape(
    session: requests.Session | None = None, max_teams: int | None = None
) -> pd.DataFrame:
    """Scrape every franchise's "About" box into one DataFrame.

    `max_teams` caps how many franchises are fetched - useful for a
    quick smoke test without hitting every franchise page on the site.
    """
    session = session or build_session()
    seen: set[str] = set()
    links = list_team_links(session)
    if max_teams is not None:
        links = links[:max_teams]

    details: list[dict[str, object]] = []
    for team in tqdm(links, desc="teams"):
        detail = team_detail(session, team, seen)
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
