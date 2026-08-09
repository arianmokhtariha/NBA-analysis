"""NBA/ABA season-by-season summary -> data/raw/season_summaries.csv

Source: the `#stats` table on
https://www.basketball-reference.com/leagues/ - one row per season,
listing that season's champion, MVP, Rookie of the Year, and
statistical leaders.

This was the one page the old `Scraper.py` fetched with Selenium
(`seasons_details`, `way=2`), on the theory that the table needed a
real browser to render. It does not: a live check while writing this
module confirmed plain `requests` gets the fully-populated `#stats`
table back in the first response, no JavaScript execution required.
The only real wrinkle is that this particular table lists its `<tr>`
rows directly under `<table>` with no `<tbody>` wrapper at all - most
basketball-reference tables do have one - which Python's built-in
`html.parser` will not synthesize the way a browser (or `lxml`)
would. `parse.parse_stat_table` selects `tr` broadly for exactly this
reason, so it works on both layouts.

Because Selenium turned out to be unnecessary here (the only place it
was used anywhere in this project), `selenium` and `webdriver_manager`
have been dropped from environment.yml.

Run directly (`python -m scrapers.season_summaries`) to scrape and
write data/raw/season_summaries.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scrapers.fetch import build_session, fetch_page
from scrapers.parse import parse_stat_table

logger = logging.getLogger(__name__)

SEASON_INDEX_URL = "https://www.basketball-reference.com/leagues/"
OUTPUT_PATH = Path("data/raw/season_summaries.csv")


def scrape(session: requests.Session | None = None) -> pd.DataFrame:
    """Scrape the full season-by-season summary table into one DataFrame.

    Rows with no champion yet (the current, still-in-progress season)
    are skipped - the old code hardcoded a specific season string
    ("2025-26") for this, which would have gone stale the moment that
    season ended; checking for a missing champion instead works for
    whichever season is actually in progress at scrape time.
    """
    session = session or build_session()
    html = fetch_page(session, SEASON_INDEX_URL)
    if html is None:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, object]] = []
    for row in parse_stat_table(soup, "table#stats"):
        if row.get("champion") is None:
            continue
        records.append(
            {
                "Season Year": row.get("season"),
                "League": row.get("lg_id"),
                "Champion Name": row.get("champion"),
                "MVP": row.get("mvp"),
                "Rookie of the Year": row.get("roy"),
                "Most Points": row.get("pts_leader_name"),
                "Most Rebounds": row.get("trb_leader_name"),
                "Most Assists": row.get("ast_leader_name"),
                "Most Winshares": row.get("ws_leader_name"),
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
