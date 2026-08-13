"""Build the player dimension and its position child table.

Outputs
-------
``data/processed/players.csv``
    One row per player *referenced anywhere in the database*, not just per
    player we managed to scrape a bio page for. Michael Jordan appears in the
    all-time MVP list and in old championship rosters but has no bio row; he
    still gets a ``players`` row (with ``has_bio = False`` and empty bio
    attributes) so the foreign keys pointing at him are real.
``data/processed/player_positions.csv``
    ``(player_id, slot, position)`` - the normalised replacement for the old
    ``position_1 ... position_6`` repeating group.
"""

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    MONTH_NUMBERS,
    PROCESSED_DIR,
    RAW_DIR,
    BuildResult,
    TableReport,
    fix_mojibake_series,
    height_to_cm,
    normalize_ids,
    normalize_text,
    parse_shooting_hand,
    position_code,
    read_source,
    split_positions,
    weight_to_kg,
    write_table,
)

#: Career columns of ``player_career_stats``; ported verbatim from the
#: original cleaning script.
CAREER_COLUMN_MAP: dict[str, str] = {
    "career games": "career_games",
    "career points": "career_points",
    "career total rebound percentage": "career_total_rebound_pct",
    "career assists percentage": "career_assists_pct",
    "career field goal percentage": "career_field_goal_pct",
    "career 3pt field goal percentage": "career_three_point_pct",
    "career free throw percentage": "career_free_throw_pct",
    "career effective field goal percentage": "career_effective_fg_pct",
    "career player efficiency rating": "career_per",
    "career win shares": "career_win_shares",
}

#: Career percentage columns arrive as text and use "-" for "not applicable".
CAREER_NUMERIC_COLUMNS: tuple[str, ...] = tuple(CAREER_COLUMN_MAP.values())

PLAYER_COLUMNS: tuple[str, ...] = (
    "player_id",
    "player_name",
    "has_bio",
    "primary_position",
    "shoots",
    "height_cm",
    "weight_kg",
    "birth_year",
    "birth_month",
    "birth_day",
    "birth_date",
    "college",
    "experience_seasons",
    "nba_debut_date",
    "nba_debut_year",
    "draft_year",
    "draft_team_name",
    "draft_round",
    "draft_round_pick",
    "draft_overall_pick",
    *CAREER_NUMERIC_COLUMNS,
)


def _clean_college(values: pd.Series) -> pd.Series:
    """Repair the college column.

    The scraper joined multi-word colleges with a comma (``"Arizona,State"``)
    and wrote the literal header word ``"Colleges"`` for players who never
    attended one.
    """
    cleaned = (
        values.astype("string")
        .str.replace(",", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )
    return cleaned.mask(cleaned.isin(["Colleges", "College", ""]), pd.NA)


def _birth_frame(bios: pd.DataFrame) -> pd.DataFrame:
    """Split the birth date into year / month / day plus a real ISO date.

    The original script turned this into a hard-coded ``age = 2025 - birthyear``.
    Age is a moving target, so only the birth date is stored; per-season age
    already lives in ``player_season_stats.age``.
    """
    month = (
        bios["birthmonth"].astype("string").str.strip().str.lower().map(MONTH_NUMBERS)
    )
    frame = pd.DataFrame(
        {
            "birth_year": pd.to_numeric(bios["birthyear"], errors="coerce").astype(
                "Int64"
            ),
            "birth_month": month.astype("Int64"),
            "birth_day": pd.to_numeric(bios["birthday"], errors="coerce").astype(
                "Int64"
            ),
        },
        index=bios.index,
    )
    # A handful of old players have no birth date on their bio page at all.
    # ``to_datetime`` cannot assemble a date from columns holding NA, so only
    # the rows with all three parts are assembled; the rest stay empty.
    complete = frame.notna().all(axis=1)
    birth_date = pd.Series(pd.NA, index=frame.index, dtype="string")
    if complete.any():
        parsed = pd.to_datetime(
            frame.loc[complete]
            .rename(
                columns={
                    "birth_year": "year",
                    "birth_month": "month",
                    "birth_day": "day",
                }
            )
            .astype("int64"),
            errors="coerce",
        )
        birth_date.loc[complete] = parsed.dt.strftime("%Y-%m-%d")
    frame["birth_date"] = birth_date
    return frame


def _draft_frame(bios: pd.DataFrame) -> pd.DataFrame:
    """Parse the draft columns into year, round and pick numbers.

    ``Draft`` looks like ``"2009 NBA Draft"`` and ``Draf Pick`` (the source
    misspells it) like ``" 1st round (3rd pick 3rd overall)"``.
    """
    pick = bios["draf pick"].astype("string")
    round_pick = pick.str.extract(r"\((\d+)[^0-9]+(\d+)")
    return pd.DataFrame(
        {
            "draft_year": bios["draft"]
            .astype("string")
            .str.extract(r"(\d{4})")[0]
            .astype("Int64"),
            "draft_team_name": bios["draft team"].astype("string"),
            "draft_round": pick.str.extract(r"(\d+)(?:st|nd|rd|th)\s+round")[0].astype(
                "Int64"
            ),
            "draft_round_pick": round_pick[0].astype("Int64"),
            "draft_overall_pick": round_pick[1].astype("Int64"),
        },
        index=bios.index,
    )


def _position_table(bios: pd.DataFrame) -> pd.DataFrame:
    """Explode the bio position string into one row per player and slot.

    Both output columns are ``not null`` in the database, so a name without a
    code is skipped rather than written as a hole. :func:`split_positions`
    already returns only recognised names, which leaves this as a guard: it
    keeps the two functions independently correct instead of making this one
    silently depend on the other's filtering.
    """
    records: list[dict[str, object]] = []
    for player_id, raw_positions in zip(bios["player_id"], bios["position"]):
        slot = 0
        for name in split_positions(raw_positions):
            code = position_code(name)
            if code is None:
                continue
            slot += 1
            records.append(
                {
                    "player_id": player_id,
                    "slot": slot,
                    "position": name,
                    "position_code": code,
                }
            )
    return pd.DataFrame.from_records(
        records, columns=["player_id", "slot", "position", "position_code"]
    )


def build_players(
    raw_dir: Path = RAW_DIR,
    referenced_player_ids: Iterable[str] | None = None,
    name_fallback: pd.DataFrame | None = None,
) -> BuildResult:
    """Build ``players`` and ``player_positions``.

    Parameters
    ----------
    raw_dir:
        Folder holding the immutable scraped files.
    referenced_player_ids:
        Every ``player_id`` used by a fact table. The dimension is the union
        of these and the bio file, which is what makes the foreign keys hold
        without dropping a single fact row.
    name_fallback:
        Optional ``(player_id, player_name)`` frame - used to name players who
        have no bio page (roster listings supply most historical names).
    """
    bios_raw = read_source(raw_dir, "player_bios")
    rows_in = len(bios_raw)

    bios = bios_raw.copy()
    bios.columns = bios.columns.str.strip().str.lower()

    # The shooting hand is read from the untouched cell: for two players the
    # scraper captured "Shoots: Right Left" and for one it captured a whole
    # bio paragraph, and all three are handled by the same rule.
    shoots = bios["shoots"].map(parse_shooting_hand, na_action="ignore")

    bios = normalize_text(bios)
    bios["player_id"] = normalize_ids(bios["player_id"])
    bios["player_name"] = fix_mojibake_series(bios["player_name"])

    positions = _position_table(bios)
    primary = (
        positions.loc[positions["slot"] == 1, ["player_id", "position_code"]]
        .rename(columns={"position_code": "primary_position"})
    )

    debut = pd.to_datetime(
        bios["nba debut"].astype("string").str.strip(),
        format="%B %d, %Y",
        errors="coerce",
    )

    bio_frame = pd.DataFrame(
        {
            "player_id": bios["player_id"],
            "player_name": bios["player_name"],
            "shoots": shoots.astype("string"),
            "height_cm": height_to_cm(bios["height"]),
            "weight_kg": weight_to_kg(bios["weight"]),
            "college": _clean_college(bios["college"]),
            "experience_seasons": pd.to_numeric(
                bios["experience"], errors="coerce"
            ).astype("Int64"),
            "nba_debut_date": debut.dt.strftime("%Y-%m-%d"),
            "nba_debut_year": debut.dt.year.astype("Int64"),
        }
    )
    bio_frame = pd.concat(
        [bio_frame, _birth_frame(bios), _draft_frame(bios)], axis=1
    )
    bio_frame = bio_frame.merge(primary, on="player_id", how="left")

    career = _career_frame(raw_dir)
    bio_frame = bio_frame.merge(career, on="player_id", how="left")

    # Basketball-Reference lists experience on both the bio page and the
    # career-stats page; the bio value wins and the career page fills gaps.
    bio_frame["experience_seasons"] = bio_frame["experience_seasons"].combine_first(
        bio_frame.pop("career_experience_seasons")
    )

    universe = set(bio_frame["player_id"])
    if referenced_player_ids is not None:
        universe |= {
            str(value).strip().lower()
            for value in referenced_player_ids
            if isinstance(value, str) and str(value).strip()
        }

    players = pd.DataFrame({"player_id": sorted(universe)}).merge(
        bio_frame, on="player_id", how="left"
    )
    players["has_bio"] = players["player_id"].isin(set(bio_frame["player_id"]))

    if name_fallback is not None and len(name_fallback):
        lookup = (
            name_fallback.dropna(subset=["player_name"])
            .drop_duplicates("player_id")
            .set_index("player_id")["player_name"]
        )
        players["player_name"] = players["player_name"].combine_first(
            players["player_id"].map(lookup).astype("string")
        )

    players = players[list(PLAYER_COLUMNS)].sort_values("player_id").reset_index(
        drop=True
    )
    positions = positions.sort_values(["player_id", "slot"]).reset_index(drop=True)

    reports = [
        TableReport(
            table="players",
            rows_in=rows_in,
            rows_out=len(players),
            reason=(
                f"no rows dropped; {len(players) - rows_in} id-only rows added for "
                "players referenced by rosters/MVP tables but never scraped "
                "(has_bio = False)"
            ),
        ),
        TableReport(
            table="player_positions",
            rows_in=rows_in,
            rows_out=len(positions),
            reason="one row per player and position slot (empty slots dropped)",
        ),
    ]
    return BuildResult(
        tables={"players": players, "player_positions": positions}, reports=reports
    )


def _career_frame(raw_dir: Path) -> pd.DataFrame:
    """Read career efficiency stats and keep only the career-level columns.

    The per-``last season`` columns of this file are deliberately left out:
    they are a snapshot of whichever season was most recent when the page was
    scraped and are fully reproducible from ``player_season_stats``.
    """
    career_raw = read_source(raw_dir, "player_career_stats")
    career = career_raw.copy()
    career.columns = career.columns.str.strip().str.lower()
    career = career.rename(columns=CAREER_COLUMN_MAP)
    career["player_id"] = normalize_ids(career["player_id"])

    keep = ["player_id", *CAREER_NUMERIC_COLUMNS, "experience"]
    career = career[keep].rename(
        columns={"experience": "career_experience_seasons"}
    )
    for column in CAREER_NUMERIC_COLUMNS:
        career[column] = pd.to_numeric(
            career[column].astype("string").str.strip().replace("-", pd.NA),
            errors="coerce",
        )
    career["career_experience_seasons"] = pd.to_numeric(
        career["career_experience_seasons"], errors="coerce"
    ).astype("Int64")
    return career.drop_duplicates("player_id")


def main() -> None:
    """Build the player tables standalone and write them to ``data/processed``."""
    result = build_players()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
