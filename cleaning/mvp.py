"""Clean the two MVP award tables.

Outputs
-------
``data/processed/mvp_winners.csv``
    Every MVP since 1955-56, one row per season.
``data/processed/mvp_candidates.csv``
    The full MVP ballot (voting shares and season averages) for 2018-19
    through 2024-25.

The bootcamp brief calls this award the "Michael Jordan Trophy"; on
Basketball-Reference it is the NBA Most Valuable Player award.
"""

from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    BuildResult,
    TableReport,
    normalize_ids,
    normalize_text,
    read_source,
    to_season_end_year,
    write_table,
)

#: Ported verbatim from ``01_data_cleaning_anoosha.py``.
WINNERS_COLUMN_MAP: dict[str, str] = {
    "season": "season",
    "league": "league",
    "player_id": "player_id",
    "age": "age",
    "team_id": "team_id",
    "game": "games",
    "minutes played per game": "minutes_per_game",
    "points per game": "points_per_game",
    "total rebounds per game": "rebounds_per_game",
    "assists per game": "assists_per_game",
    "steals per game": "steals_per_game",
    "blocks per game": "blocks_per_game",
    "field goal percentage": "field_goal_pct",
    "3-point field goal percentage": "three_point_pct",
    "free throw percentage": "free_throw_pct",
    "win shares": "win_shares",
    "win shares per 48 minutes": "win_shares_per_48",
}

WINNERS_OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "league",
    "player_id",
    "team_id",
    "age",
    "games",
    "minutes_per_game",
    "points_per_game",
    "rebounds_per_game",
    "assists_per_game",
    "steals_per_game",
    "blocks_per_game",
    "field_goal_pct",
    "three_point_pct",
    "free_throw_pct",
    "win_shares",
    "win_shares_per_48",
)

#: Ported verbatim; ``year`` is additionally renamed to ``season`` so that
#: every fact table names the season column the same way.
CANDIDATES_COLUMN_MAP: dict[str, str] = {
    "year": "season",
    "player_id": "player_id",
    "first_place_vote": "first_place_votes",
    "pts won": "points_won",
    "pts max": "points_max",
    "fg%": "fg_pct",
    "3p%": "three_pct",
    "ft%": "ft_pct",
    "ws/48": "ws_per_48",
    "team": "team_id",
}

CANDIDATES_OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "player_id",
    "rank",
    "tie",
    "age",
    "team_id",
    "first_place_votes",
    "points_won",
    "points_max",
    "share",
    "games",
    "mp",
    "pts",
    "trb",
    "ast",
    "stl",
    "blk",
    "fg_pct",
    "three_pct",
    "ft_pct",
    "ws",
    "ws_per_48",
)


def build_mvp_winners(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean ``mvp_winners``: one row per season, keyed by season."""
    raw = read_source(raw_dir, "mvp_winners")
    rows_in = len(raw)

    winners = raw.copy()
    winners.columns = winners.columns.str.strip().str.lower()
    winners = winners.rename(columns=WINNERS_COLUMN_MAP)
    winners = normalize_text(winners)
    winners["season"] = to_season_end_year(winners["season"])
    winners["league"] = winners["league"].astype("string").str.upper()
    winners["player_id"] = normalize_ids(winners["player_id"])
    winners["team_id"] = normalize_ids(winners["team_id"])
    winners["age"] = pd.to_numeric(winners["age"], errors="coerce").astype("Int64")
    winners["games"] = pd.to_numeric(winners["games"], errors="coerce").astype("Int64")

    winners = (
        winners[list(WINNERS_OUTPUT_COLUMNS)]
        .sort_values("season")
        .reset_index(drop=True)
    )

    report = TableReport(
        table="mvp_winners",
        rows_in=rows_in,
        rows_out=len(winners),
        reason=(
            "no rows dropped; the 26 winners with no scraped bio page keep "
            "their rows because the player dimension covers them"
        ),
    )
    return BuildResult(tables={"mvp_winners": winners}, reports=[report])


def build_mvp_candidates(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean ``mvp_candidates``: the full ballot, keyed by season and player."""
    raw = read_source(raw_dir, "mvp_candidates", sheet_name="mvp_candidates")
    rows_in = len(raw)

    candidates = raw.copy()
    candidates.columns = candidates.columns.str.strip().str.lower()
    candidates = candidates.rename(columns=CANDIDATES_COLUMN_MAP)
    candidates = normalize_text(candidates)

    # The ballot rank carries a "T" suffix when players tied, e.g. "10T".
    rank_parts = (
        candidates["rank"].astype("string").str.upper().str.extract(r"(\d+)(T?)")
    )
    candidates["rank"] = pd.to_numeric(rank_parts[0], errors="coerce").astype("Int64")
    candidates["tie"] = rank_parts[1].fillna("") == "T"

    candidates["season"] = to_season_end_year(candidates["season"])
    candidates["player_id"] = normalize_ids(candidates["player_id"])
    candidates["team_id"] = normalize_ids(candidates["team_id"])
    for column in ("age", "first_place_votes", "points_won", "points_max", "games"):
        candidates[column] = pd.to_numeric(
            candidates[column], errors="coerce"
        ).astype("Int64")

    candidates = (
        candidates[list(CANDIDATES_OUTPUT_COLUMNS)]
        .sort_values(["season", "rank", "player_id"])
        .reset_index(drop=True)
    )

    report = TableReport(
        table="mvp_candidates",
        rows_in=rows_in,
        rows_out=len(candidates),
        reason="no rows dropped; 'year' renamed to 'season' for a uniform key",
    )
    return BuildResult(tables={"mvp_candidates": candidates}, reports=[report])


def build_mvp(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Build both MVP tables."""
    winners = build_mvp_winners(raw_dir)
    candidates = build_mvp_candidates(raw_dir)
    return BuildResult(
        tables={**winners.tables, **candidates.tables},
        reports=[*winners.reports, *candidates.reports],
    )


def main() -> None:
    """Build the MVP tables standalone and write them to ``data/processed``."""
    result = build_mvp()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
