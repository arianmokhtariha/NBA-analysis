"""Franchise list + franchise "About" box -> data/raw/teams.csv

Source pages:

- The season index (https://www.basketball-reference.com/leagues/) for
  the franchise list, via `list_team_links`, which takes every
  '/teams/...' link on the page and this module then collapses down to
  each franchise's own page.
- Each franchise's own page (.../teams/<ABBR>/) for its "About" box:
  founded date, arena, career seasons played, etc.

This module also owns the link-discovery helpers the two team-season
scrapers share, because *which* team-seasons exist is a question about
teams, not about rosters:

- `list_team_links` - every '/teams/...' link on the index page, loose
  and undated. Only this module wants that.
- `list_champion_links` - one team-season per title ever won, read from
  the index table's Champion column.
- `list_season_team_links` - every team that played a given season,
  read from that season's own page.
- `list_team_season_links` - the union used by `team_season_rosters`
  and `team_seasons`.

The distinction is load-bearing. The index page carries a season-
specific team link *only* for champions, so a scraper that walked its
links got one team per season the moment no season was in progress.

Run directly (`python -m scrapers.teams`) to scrape and write
data/raw/teams.csv.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from scrapers.config import DEFAULT_SEASON_YEARS
from scrapers.fetch import build_session, fetch_page, normalize_url
from scrapers.parse import parse_meta_box, parse_seasons_summary, parse_stat_table

logger = logging.getLogger(__name__)

SEASON_INDEX_URL = "https://www.basketball-reference.com/leagues/"
SEASON_URL = "https://www.basketball-reference.com/leagues/NBA_{year}.html"
OUTPUT_PATH = Path("data/raw/teams.csv")

TeamLink = dict[str, str]

_TEAM_HREF_PATTERN = re.compile(r"^/teams")
_SKIPPED_LINK_TEXT = {"F", "Teams"}


def list_team_links(
    session: requests.Session, url: str = SEASON_INDEX_URL
) -> list[TeamLink]:
    """Collect every '/teams/...' link on the season index page.

    A deliberately loose mix of three different things: one dated link
    per champion (from the table's Champion column), one dated link per
    team of the *current* season (from the site-wide nav block), and
    undated franchise links. Only the franchise scrape wants that mix,
    because it collapses every link to its franchise page anyway.

    Anything needing real team-seasons wants
    :func:`list_champion_links` or :func:`list_season_team_links`.
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


def list_champion_links(
    session: requests.Session, url: str = SEASON_INDEX_URL
) -> list[TeamLink]:
    """Every league champion's team-season page, one per title ever won.

    Read from the Champion column of the season index table, not from
    the page's '/teams/...' links at large: the site's navigation block
    links all 30 teams of the *current* season on every page, and those
    are champions of nothing. `list_team_links` deliberately keeps that
    looser behaviour because the franchise scrape wants those links.
    """
    html = fetch_page(session, url)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[TeamLink] = []
    for row in parse_stat_table(soup, "table#stats"):
        href = row.get("champion_href")
        if not href:  # the in-progress season has no champion yet
            continue
        links.append(
            {
                "team_name": row.get("champion") or "",
                "link": urljoin(normalize_url(url), href),
            }
        )
    return links


def list_season_team_links(session: requests.Session, year: int) -> list[TeamLink]:
    """Every team that played in `year`, read off that season's own page.

    The year is pinned into the href pattern deliberately. Every page on
    the site carries a navigation block linking all 30 teams of the
    *current* season, so an unpinned '/teams/XXX/YYYY.html' match would
    silently add 30 wrong-season links to every season scraped.

    Each team is linked several times per page (standings, then each
    summary table), so links are deduplicated on the URL.
    """
    url = SEASON_URL.format(year=year)
    html = fetch_page(session, url)
    if html is None:
        return []

    soup = BeautifulSoup(html, "html.parser")
    pattern = re.compile(rf"^/teams/[A-Z]{{3}}/{year}\.html$")
    links: dict[str, TeamLink] = {}
    for anchor in soup.find_all("a", href=pattern):
        href = urljoin(normalize_url(url), anchor["href"])
        if href not in links:
            links[href] = {"team_name": anchor.get_text(strip=True), "link": href}
    return list(links.values())


def list_team_season_links(
    session: requests.Session,
    season_years: Iterable[int] = DEFAULT_SEASON_YEARS,
    include_champions: bool = True,
) -> list[TeamLink]:
    """Every team-season page worth scraping, from two sources.

    1. **All teams of every season in `season_years`** - the seasons the
       analysis actually covers, so a player's height and experience can
       be joined to any player in those seasons, not just to a champion.
    2. **Every champion in league history** (`include_champions`), which
       costs one extra page load and keeps two things the season pages
       cannot give: the title history back to 1947, and the ABA
       champions, whose seasons live on separate ABA pages entirely.

    Deduplicated on URL, so a champion inside `season_years` is fetched
    once, not twice.
    """
    links: dict[str, TeamLink] = {}
    for year in season_years:
        for link in list_season_team_links(session, year):
            links.setdefault(link["link"], link)
    if include_champions:
        for link in list_champion_links(session):
            links.setdefault(link["link"], link)
    return list(links.values())


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
