"""Clean the per-player, per-season box-score table.

Output: ``data/processed/player_season_stats.csv``.

Two source quirks drive everything here:

* the last row of every season is Basketball-Reference's *League Average*
  line, which has no player behind it and is removed;
* a player who was traded mid-season gets one combined row (team ``TOT``)
  plus one row per team. All of them are kept and labelled with ``stint`` /
  ``is_primary`` instead of the old behaviour of deleting the per-team rows.
"""

from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    TOTAL_TEAM_ID,
    BuildResult,
    TableReport,
    add_stint_columns,
    drop_league_average_rows,
    normalize_ids,
    normalize_text,
    read_source,
    to_season_end_year,
    write_table,
)

#: Ported verbatim from ``01_data_cleaning_anoosha.py``.
PLAYER_STATS_COLUMN_MAP: dict[str, str] = {
    "year": "season",
    "rank": "rank",
    "player_id": "player_id",
    "age": "age",
    "team": "team_id",
    "position": "position",
    "games": "games_played",
    "games started": "games_started",
    "minutes played": "minutes_played",
    "fg": "field_goals_made",
    "fga": "field_goals_attempted",
    "fg%": "field_goal_pct",
    "3p": "three_pointers_made",
    "3pa": "three_pointers_attempted",
    "3p%": "three_point_pct",
    "2p": "two_pointers_made",
    "2pa": "two_pointers_attempted",
    "2p%": "two_point_pct",
    "efg%": "effective_fg_pct",
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
    "trp_dbl": "triple_doubles",
}

COUNT_COLUMNS: tuple[str, ...] = (
    "rank",
    "age",
    "games_played",
    "games_started",
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
    "triple_doubles",
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "player_id",
    "stint",
    "is_primary",
    "team_id",
    "rank",
    "age",
    "position",
    "games_played",
    "games_started",
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
    "effective_fg_pct",
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
    "triple_doubles",
)


def build_player_season_stats(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean ``player_stats`` into ``player_season_stats``."""
    raw = read_source(raw_dir, "player_stats")
    rows_in = len(raw)

    stats = raw.copy()
    stats.columns = stats.columns.str.strip().str.lower()
    stats = stats.rename(columns=PLAYER_STATS_COLUMN_MAP)

    stats, league_average_rows = drop_league_average_rows(stats, "player_id")

    stats = normalize_text(stats, columns=["player_id", "team_id", "position"])
    stats["season"] = to_season_end_year(stats["season"])
    stats["player_id"] = normalize_ids(stats["player_id"])
    # A blank team means Basketball-Reference's combined "TOT" line for a
    # player who changed team during the season.
    stats["team_id"] = normalize_ids(stats["team_id"]).fillna(TOTAL_TEAM_ID)

    stats = add_stint_columns(stats, "season", "player_id", "team_id")

    for column in COUNT_COLUMNS:
        stats[column] = pd.to_numeric(stats[column], errors="coerce").astype("Int64")

    stats = (
        stats[list(OUTPUT_COLUMNS)]
        .sort_values(["season", "rank", "player_id", "stint"])
        .reset_index(drop=True)
    )

    report = TableReport(
        table="player_season_stats",
        rows_in=rows_in,
        rows_out=len(stats),
        reason=(
            f"dropped {league_average_rows} 'League Average' summary rows "
            "(blank player_id, one per season); traded players keep both the "
            "season total (stint 0) and every per-team row"
        ),
    )
    return BuildResult(tables={"player_season_stats": stats}, reports=[report])


def main() -> None:
    """Build the table standalone and write it to ``data/processed``."""
    result = build_player_season_stats()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
