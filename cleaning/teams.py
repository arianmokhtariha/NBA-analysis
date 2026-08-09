"""Build the team dimension and the team-season totals fact table.

Outputs
-------
``data/processed/teams.csv``
    One row per team code referenced anywhere in the database, including the
    six ABA clubs that only ever show up in old rosters and the pseudo-team
    ``tot``.
``data/processed/team_season_stats.csv``
    Season totals per franchise, for the full history the source provides.
"""

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    TOTAL_TEAM_ID,
    TOTAL_TEAM_NAME,
    BuildResult,
    TableReport,
    normalize_ids,
    normalize_text,
    read_source,
    to_season_end_year,
    write_table,
)
from cleaning.rosters import build_team_name_lookup

#: Ported verbatim from ``01_data_cleaning_anoosha.py``.
TEAM_COLUMN_MAP: dict[str, str] = {
    "rk": "rank",
    "season": "season",
    "teamname": "team_name",
    "teamid": "team_id",
    "g": "games",
    "mp": "minutes_played",
    "fg": "field_goals_made",
    "fga": "field_goals_attempted",
    "fg%": "field_goal_pct",
    "3p": "three_pointers_made",
    "3pa": "three_pointers_attempted",
    "3p%": "three_point_pct",
    "2p": "two_pointers_made",
    "2pa": "two_pointers_attempted",
    "2p%": "two_point_pct",
    "ft": "free_throws_made",
    "fta": "free_throws_attempted",
    "ft%": "free_throw_pct",
    "orb": "offensive_rebounds",
    "drb": "defensive_rebounds",
    "trb": "total_rebounds",
    "ast": "assists",
    "stl": "steals",
    "blk": "blocks",
    "tov": "turnovers",
    "pf": "personal_fouls",
    "pts": "points",
}

COUNT_COLUMNS: tuple[str, ...] = (
    "rank",
    "games",
    "minutes_played",
    "field_goals_made",
    "field_goals_attempted",
    "three_pointers_made",
    "three_pointers_attempted",
    "two_pointers_made",
    "two_pointers_attempted",
    "free_throws_made",
    "free_throws_attempted",
    "offensive_rebounds",
    "defensive_rebounds",
    "total_rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "personal_fouls",
    "points",
)

SEASON_OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "team_id",
    "rank",
    "games",
    "minutes_played",
    "field_goals_made",
    "field_goals_attempted",
    "field_goal_pct",
    "three_pointers_made",
    "three_pointers_attempted",
    "three_point_pct",
    "two_pointers_made",
    "two_pointers_attempted",
    "two_point_pct",
    "free_throws_made",
    "free_throws_attempted",
    "free_throw_pct",
    "offensive_rebounds",
    "defensive_rebounds",
    "total_rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "personal_fouls",
    "points",
)


def build_teams(
    raw_dir: Path = RAW_DIR,
    referenced_team_ids: Iterable[str] | None = None,
    roster_team_names: pd.DataFrame | None = None,
) -> BuildResult:
    """Build ``team_season_stats`` and the complete ``teams`` dimension.

    Parameters
    ----------
    raw_dir:
        Folder holding the immutable scraped files.
    referenced_team_ids:
        Every ``team_id`` used by a fact table. Together with the totals file
        this makes the dimension complete, so no fact row is left orphaned.
    roster_team_names:
        ``(season, team_id, team_name)`` from :mod:`cleaning.rosters`; the
        only place the ABA franchise names appear.
    """
    raw = read_source(raw_dir, "team_season_totals")
    rows_in = len(raw)

    totals = raw.copy()
    totals.columns = totals.columns.str.strip().str.lower()
    totals = totals.rename(columns=TEAM_COLUMN_MAP)
    totals = normalize_text(totals)

    # The scrape kept the blank separator rows that sit between the season
    # blocks on the source page: no team, no numbers.
    blank_rows = int(totals["team_id"].isna().sum())
    totals = totals.loc[totals["team_id"].notna()].copy()

    totals["season"] = to_season_end_year(totals["season"])
    totals["team_id"] = normalize_ids(totals["team_id"])
    for column in COUNT_COLUMNS:
        totals[column] = pd.to_numeric(totals[column], errors="coerce").astype("Int64")

    season_stats = (
        totals[list(SEASON_OUTPUT_COLUMNS)]
        .sort_values(["season", "team_id"])
        .reset_index(drop=True)
    )

    teams = _build_dimension(totals, referenced_team_ids, roster_team_names)

    reports = [
        TableReport(
            table="team_season_stats",
            rows_in=rows_in,
            rows_out=len(season_stats),
            reason=(
                f"dropped {blank_rows} blank separator rows (no team, no "
                "numbers); all seasons kept, including the not-yet-played "
                "2025-26 rows where games = 0"
            ),
        ),
        TableReport(
            table="teams",
            rows_in=totals["team_id"].nunique(),
            rows_out=len(teams),
            reason=(
                "one row per team code referenced anywhere: totals file, plus "
                "ABA clubs known only from rosters, plus the 'tot' pseudo-team"
            ),
        ),
    ]
    return BuildResult(
        tables={"teams": teams, "team_season_stats": season_stats}, reports=reports
    )


def _build_dimension(
    totals: pd.DataFrame,
    referenced_team_ids: Iterable[str] | None,
    roster_team_names: pd.DataFrame | None,
) -> pd.DataFrame:
    """Assemble the complete team lookup from every available name source."""
    detail_ids = set(totals["team_id"].dropna())

    names = (
        totals.dropna(subset=["team_name"])
        .sort_values("season")
        .drop_duplicates("team_id", keep="last")
        .set_index("team_id")["team_name"]
    )

    roster_names: pd.Series = pd.Series(dtype="string")
    if roster_team_names is not None and len(roster_team_names):
        roster_names = (
            roster_team_names.dropna(subset=["team_name"])
            .sort_values("season")
            .drop_duplicates("team_id", keep="last")
            .set_index("team_id")["team_name"]
        )

    universe = set(detail_ids) | set(roster_names.index) | {TOTAL_TEAM_ID}
    if referenced_team_ids is not None:
        universe |= {
            str(value).strip().lower()
            for value in referenced_team_ids
            if isinstance(value, str) and str(value).strip()
        }

    teams = pd.DataFrame({"team_id": sorted(universe)})
    teams["team_name"] = (
        teams["team_id"]
        .map(names)
        .astype("string")
        .combine_first(teams["team_id"].map(roster_names).astype("string"))
    )
    # "tot" is Basketball-Reference's row for a player's combined season
    # across every team he played for - a real key in the fact tables, so it
    # needs a real dimension row, flagged so analyses can exclude it.
    teams.loc[teams["team_id"] == TOTAL_TEAM_ID, "team_name"] = TOTAL_TEAM_NAME
    teams["is_aggregate"] = teams["team_id"] == TOTAL_TEAM_ID
    teams["has_detail"] = teams["team_id"].isin(detail_ids)
    return teams.sort_values("team_id").reset_index(drop=True)


def main() -> None:
    """Build the team tables standalone and write them to ``data/processed``."""
    result = build_teams(roster_team_names=build_team_name_lookup())
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
