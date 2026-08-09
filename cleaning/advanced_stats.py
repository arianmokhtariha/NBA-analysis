"""Clean the per-player, per-season advanced-metrics table.

Output: ``data/processed/player_advanced_stats.csv``.

Same two source quirks as the box-score table (League Average summary rows
and traded-player ``TOT`` rows), handled by the same shared helpers - which
is why the old pipeline's advanced file was exactly seven rows short of the
box-score file.

Columns that merely repeat the box-score table for the same key
(``age``, ``position``, ``games``, ``games_started``, ``minutes_played``)
are dropped: they were verified identical on all 5,025 shared rows, and the
two tables join on ``(season, player_id, stint)``. ``rank`` is dropped too -
it is the display order of the source web page, not a fact about the player.
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
    to_team_id,
    write_table,
)

ADVANCED_COLUMN_MAP: dict[str, str] = {
    "season": "season",
    "player_id": "player_id",
    "team": "team_id",
    "player_efficiency_rate": "player_efficiency_rate",
    "true_shooting_percentage": "true_shooting_percentage",
    "three_point_attempt_rate": "three_point_attempt_rate",
    "free_throw_attempt_rate": "free_throw_attempt_rate",
    "offensive_rebound_percentage": "offensive_rebound_percentage",
    "defensive_rebound_percentage": "defensive_rebound_percentage",
    "total_rebound_percentage": "total_rebound_percentage",
    "assist_percentage": "assist_percentage",
    "steal_percentage": "steal_percentage",
    "block_percentage": "block_percentage",
    "turnover_percentage": "turnover_percentage",
    "usage_percentage": "usage_percentage",
    "offensive_win_shares": "offensive_win_shares",
    "defensive_win_shares": "defensive_win_shares",
    "win_shares": "win_shares",
    "win_shares_per_48_minutes": "win_shares_per_48_minutes",
    "offensive_box_plus_minus": "offensive_box_plus_minus",
    "defensive_box_plus_minus": "defensive_box_plus_minus",
    "box_plus_minus": "box_plus_minus",
    "value_over_replacement_player": "value_over_replacement_player",
}

METRIC_COLUMNS: tuple[str, ...] = tuple(
    name
    for name in ADVANCED_COLUMN_MAP.values()
    if name not in {"season", "player_id", "team_id"}
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "player_id",
    "stint",
    "is_primary",
    "team_id",
    *METRIC_COLUMNS,
)


def build_player_advanced_stats(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean ``advanced_stats`` into ``player_advanced_stats``."""
    raw = read_source(raw_dir, "advanced_stats")
    rows_in = len(raw)

    advanced = raw.copy()
    advanced.columns = advanced.columns.str.strip().str.lower()
    advanced = advanced.rename(columns=ADVANCED_COLUMN_MAP)

    advanced, league_average_rows = drop_league_average_rows(advanced, "player_id")

    advanced = normalize_text(advanced, columns=["player_id", "team_id"])
    advanced["season"] = to_season_end_year(advanced["season"])
    advanced["player_id"] = normalize_ids(advanced["player_id"])
    # Folds every spelling of the combined "player was traded" line - blank,
    # "TOT", "2TM"/"3TM"/... - onto one id. See normalize.to_team_id.
    advanced["team_id"] = to_team_id(advanced["team_id"])

    advanced = add_stint_columns(advanced, "season", "player_id", "team_id")

    for column in METRIC_COLUMNS:
        advanced[column] = pd.to_numeric(advanced[column], errors="coerce")

    advanced = (
        advanced[list(OUTPUT_COLUMNS)]
        .sort_values(["season", "player_id", "stint"])
        .reset_index(drop=True)
    )

    report = TableReport(
        table="player_advanced_stats",
        rows_in=rows_in,
        rows_out=len(advanced),
        reason=(
            f"dropped {league_average_rows} 'League Average' summary rows "
            "(blank player_id, one per season); traded players keep both the "
            "season total (stint 0) and every per-team row"
        ),
    )
    return BuildResult(
        tables={"player_advanced_stats": advanced}, reports=[report]
    )


def main() -> None:
    """Build the table standalone and write it to ``data/processed``."""
    result = build_player_advanced_stats()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
