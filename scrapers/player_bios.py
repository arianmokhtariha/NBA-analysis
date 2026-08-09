"""Player bio + draft fields -> data/raw/player_bios.csv

Source: each player's own page (.../players/<first-letter>/<id>.html).

This ports the bio-box parsing from `archive/Player_Scraper.py`
(`Get_Players`), which is the only place in the old codebase that
extracted Draft / Draft Team / Draft Pick / NBA Debut - fields
`Scraper.players()` never scraped at all. The archived version located
these fields with page-wide anchor searches and hardcoded list
indices (e.g. "the 3rd link on the whole page whose href contains
'draft'"), which breaks the moment an unrelated draft-related link
appears earlier on the page. This rewrite locates the same fields
robustly instead: by finding the `<strong>` label the value sits next
to, scoped to that one paragraph. The archived script also carried a
hardcoded live browser cookie header - dropped entirely; it was
specific to one logged-in session and not needed to read public pages.

`Scraper.players()` is intentionally not ported: it scraped a
*single hardcoded player id* (a bug called out in the refactor plan).
This module instead takes a list of player ids - by default, every id
already seen on a scraped roster (data/raw/team_season_rosters.csv).

Its career-stat half *is* reproduced, by `player_career_stats.py`. That
table reads the summary box on this same page, so this module parses
both out of one fetch and writes both files. Scraping them separately
would double an already hour-long run for no benefit, which is why
`run_all` lists only this step.

Run directly (`python -m scrapers.player_bios`) to scrape and write
both data/raw/player_bios.csv and data/raw/player_career_stats.csv.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from tqdm import tqdm

from scrapers.fetch import build_session, fetch_page
from scrapers.parse import to_snake_case
from scrapers.player_career_stats import parse_career_stats
from scrapers.player_career_stats import OUTPUT_PATH as CAREER_OUTPUT_PATH

logger = logging.getLogger(__name__)

PLAYER_URL = "https://www.basketball-reference.com/players/{first_letter}/{id}.html"
ROSTERS_PATH = Path("data/raw/team_season_rosters.csv")
OUTPUT_PATH = Path("data/raw/player_bios.csv")


def _label_value_pairs(meta: Tag) -> dict[str, str]:
    """Walk every `<strong>` label inside the meta box and capture the
    text that follows it, up to the next `<strong>` (or the end of its
    paragraph).

    Player bio paragraphs sometimes pack two labeled fields into one
    `<p>` (e.g. "Position: ... ▪ Shoots: ..."), so this reads label by
    label rather than assuming one label per paragraph the way
    `parse.parse_meta_box` does for team/season pages.
    """
    pairs: dict[str, str] = {}
    for strong in meta.select("p > strong"):
        label = to_snake_case(strong.get_text(strip=True))
        if not label:
            continue

        pieces: list[str] = []
        for sibling in strong.next_siblings:
            if isinstance(sibling, Tag) and sibling.name == "strong":
                break
            if isinstance(sibling, NavigableString):
                text = str(sibling)
            else:
                text = sibling.get_text(" ", strip=True)
            text = text.strip()
            if text and text != "▪":  # the "▪" bullet separator
                pieces.append(text)

        value = re.sub(r"\s+", " ", " ".join(pieces)).strip(" ;:\n\t,▪")
        if value:
            pairs[label] = value
    return pairs


def _paragraph_for_label(meta: Tag, label: str) -> Tag | None:
    """Return the `<p>` whose top-level `<strong>` label matches `label`
    (already snake_cased), e.g. "draft" or "nba_debut"."""
    for strong in meta.select("p > strong"):
        if to_snake_case(strong.get_text(strip=True)) == label:
            return strong.find_parent("p")
    return None


def _height_weight(meta: Tag) -> tuple[str | None, str | None]:
    """Height/Weight sit in an unlabeled paragraph shaped like
    "<span>6-6</span>, <span>195lb</span> (198cm, 88kg)" - no `<strong>`
    label to key off, so this matches by shape instead of position.
    """
    for p in meta.select("p"):
        spans = p.select("span")
        if len(spans) >= 2 and re.fullmatch(
            r"\d-\d{1,2}", spans[0].get_text(strip=True)
        ):
            height = spans[0].get_text(strip=True)
            weight = spans[1].get_text(strip=True).replace("lb", "")
            return height, weight
    return None, None


def _draft_fields(meta: Tag) -> tuple[str | None, str | None, str | None]:
    """Extract (Draft Team, Draft Pick, Draft) from the "Draft:"
    paragraph, e.g.:

        Draft: <a>Charlotte Hornets</a>, 1st round (11th pick, 11th
        overall), <a>2018 NBA Draft</a>

    Undrafted players have no such paragraph, in which case all three
    come back as None.
    """
    draft_p = _paragraph_for_label(meta, "draft")
    if draft_p is None:
        return None, None, None

    links = draft_p.select("a")
    draft_team = links[0].get_text(strip=True) if links else None
    draft = links[-1].get_text(strip=True) if links else None

    # The draft-position text (e.g. "1st round (11th pick, 11th
    # overall)") sits as loose text between the two links - i.e. it's
    # the direct NavigableString children of the paragraph, which
    # excludes both the <strong> label and the <a> tags' own text.
    loose_text = " ".join(
        str(child) for child in draft_p.contents if isinstance(child, NavigableString)
    )
    draft_pick = re.sub(r"\s+", " ", loose_text).strip(" ,:\n\t") or None

    return draft_team, draft_pick, draft


def parse_bio(soup: BeautifulSoup, player_id: str) -> dict[str, object] | None:
    """Read one player's bio box: name, position, measurements, birth
    info, college, draft info, and NBA experience.

    Takes an already-parsed page rather than fetching one, so the same
    download can also be handed to `parse_career_stats`.
    """
    meta = soup.select_one("#info #meta")
    if meta is None:
        return None

    name_span = meta.select_one("h1 span")
    labels = _label_value_pairs(meta)

    # "Point Guard and Shooting Guard" -> "Point Guard, Shooting Guard".
    position_raw = labels.get("position", "")
    positions = [p.strip() for p in re.split(r",|\band\b", position_raw) if p.strip()]

    height, weight = _height_weight(meta)

    birthmonth = birthday = None
    birthday_link = meta.select_one('a[href*="birthdays"]')
    if birthday_link is not None:
        parts = birthday_link.get_text(strip=True).split()
        if len(parts) == 2:
            birthmonth, birthday = parts

    birthyear_link = meta.select_one('a[href*="birthyears"]')
    birthyear = birthyear_link.get_text(strip=True) if birthyear_link else None

    college_link = meta.select_one('a[href*="colleges"]')
    college = college_link.get_text(strip=True) if college_link else None

    draft_team, draft_pick, draft = _draft_fields(meta)

    debut_p = _paragraph_for_label(meta, "nba_debut")
    nba_debut = None
    if debut_p is not None:
        debut_link = debut_p.select_one("a")
        nba_debut = debut_link.get_text(strip=True) if debut_link else None

    experience_raw = labels.get("experience")
    experience: int | str | None = experience_raw
    if experience_raw is not None:
        match = re.match(r"(\d+)", experience_raw)
        if match:
            experience = int(match.group(1))

    return {
        "player_id": player_id,
        "player_name": name_span.get_text(strip=True) if name_span else None,
        "Position": ", ".join(positions) if positions else None,
        "Shoots": labels.get("shoots"),
        "Height": height,
        "Weight": weight,
        "Birthday": birthday,
        "Birthmonth": birthmonth,
        "Birthyear": birthyear,
        "College": college,
        "Draft": draft,
        "Draft Team": draft_team,
        "Draf Pick": draft_pick,
        "Experience": experience,
        "NBA Debut": nba_debut,
    }


def player_page(
    session: requests.Session, player_id: str
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Fetch one player's page once and read both tables out of it.

    Returns (bio row, career-stats row); either may be None if that part
    of the page is missing.
    """
    url = PLAYER_URL.format(first_letter=player_id[0], id=player_id)
    html = fetch_page(session, url)
    if html is None:
        return None, None

    soup = BeautifulSoup(html, "html.parser")
    bio = parse_bio(soup, player_id)

    stats = parse_career_stats(soup)
    career: dict[str, object] | None = None
    if stats:
        career = {
            "player_id": player_id,
            "player_name": bio["player_name"] if bio else None,
            # Seasons played is read off the bio box, not the summary
            # box, so it is carried across rather than parsed twice.
            "Experience": bio.get("Experience") if bio else None,
            **stats,
        }
    return bio, career


def player_bio(
    session: requests.Session, player_id: str
) -> dict[str, object] | None:
    """Fetch and parse one player's bio box."""
    bio, _ = player_page(session, player_id)
    return bio


def _player_ids_from_rosters(path: Path = ROSTERS_PATH) -> list[str]:
    """Default player-id universe: everyone who has appeared on an
    already-scraped team roster."""
    df = pd.read_csv(path, usecols=["Player_id"])
    return sorted(df["Player_id"].dropna().unique().tolist())


def scrape_pages(
    session: requests.Session | None = None,
    player_ids: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scrape every id once, returning (bios, career stats).

    One pass over the player pages fills both tables; scraping them
    separately would double the request count for identical data.
    """
    session = session or build_session()
    ids = player_ids if player_ids is not None else []

    bios: list[dict[str, object]] = []
    careers: list[dict[str, object]] = []
    for player_id in tqdm(ids, desc="player pages"):
        bio, career = player_page(session, player_id)
        if bio is not None:
            bios.append(bio)
        if career is not None:
            careers.append(career)
    return pd.DataFrame(bios), pd.DataFrame(careers)


def scrape(
    session: requests.Session | None = None,
    player_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Scrape a bio for every id in `player_ids` into one DataFrame."""
    bios, _ = scrape_pages(session=session, player_ids=player_ids)
    return bios


def main(player_ids: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    ids = player_ids if player_ids is not None else _player_ids_from_rosters()
    bios, careers = scrape_pages(player_ids=ids)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    bios.to_csv(OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(bios), OUTPUT_PATH)

    CAREER_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    careers.to_csv(CAREER_OUTPUT_PATH, index=False)
    logger.info("Wrote %d rows to %s", len(careers), CAREER_OUTPUT_PATH)


if __name__ == "__main__":
    main()
