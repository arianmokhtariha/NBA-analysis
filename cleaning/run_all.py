"""Run the whole cleaning pipeline: ``data/raw`` -> ``data/processed``.

From the repository root::

    python -m cleaning.run_all

Order matters. The fact tables are cleaned first; the dimensions
(``players``, ``teams``, ``seasons``) are then built from the union of every
key those facts refer to. That is what makes the exported CSVs loadable into
PostgreSQL with foreign keys switched on: a dimension can never be missing a
key that a fact uses, and no fact row has to be deleted to make it so.
"""

import textwrap
from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd

from cleaning.advanced_stats import build_player_advanced_stats
from cleaning.mvp import build_mvp
from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    BuildResult,
    TableReport,
    write_table,
)
from cleaning.player_stats import build_player_season_stats
from cleaning.players import build_players
from cleaning.rosters import build_rosters, build_team_name_lookup
from cleaning.seasons import build_seasons
from cleaning.teams import build_teams


def _collect_values(
    tables: Mapping[str, pd.DataFrame], column: str, sources: Iterable[str]
) -> set[str]:
    """Gather every non-missing value of ``column`` across the named tables."""
    values: set[str] = set()
    for name in sources:
        table = tables.get(name)
        if table is not None and column in table.columns:
            values |= set(table[column].dropna().tolist())
    return values


def build_all(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean every table and return them together with the audit trail."""
    tables: dict[str, pd.DataFrame] = {}
    reports: list[TableReport] = []

    for result in (
        build_player_season_stats(raw_dir),
        build_player_advanced_stats(raw_dir),
        build_rosters(raw_dir),
        build_mvp(raw_dir),
    ):
        tables.update(result.tables)
        reports.extend(result.reports)

    fact_tables = (
        "player_season_stats",
        "player_advanced_stats",
        "rosters",
        "mvp_winners",
        "mvp_candidates",
    )

    team_result = build_teams(
        raw_dir,
        referenced_team_ids=_collect_values(tables, "team_id", fact_tables),
        roster_team_names=build_team_name_lookup(raw_dir),
    )
    tables.update(team_result.tables)
    reports.extend(team_result.reports)

    season_sources = (*fact_tables, "team_season_stats")
    season_result = build_seasons(
        raw_dir,
        referenced_seasons=_collect_seasons(tables, season_sources),
        champion_lookup=build_team_name_lookup(raw_dir),
    )
    tables.update(season_result.tables)
    reports.extend(season_result.reports)

    player_result = build_players(
        raw_dir,
        referenced_player_ids=_collect_values(tables, "player_id", fact_tables),
        name_fallback=tables["rosters"][["player_id", "player_name"]],
    )
    tables.update(player_result.tables)
    reports.extend(player_result.reports)

    return BuildResult(tables=tables, reports=reports)


def _collect_seasons(
    tables: Mapping[str, pd.DataFrame], sources: Iterable[str]
) -> set[int]:
    """Gather every season referenced by the given tables."""
    seasons: set[int] = set()
    for name in sources:
        table = tables.get(name)
        if table is not None and "season" in table.columns:
            seasons |= {int(value) for value in table["season"].dropna()}
    return seasons


def print_report(reports: Iterable[TableReport]) -> None:
    """Print the rows-in / rows-out / rows-dropped audit table."""
    rows = list(reports)
    header = (
        f"{'table':24s} {'rows in':>9s} {'rows out':>9s} {'dropped':>8s} "
        f"{'added':>6s}"
    )
    print(header)
    print("-" * len(header))
    for report in sorted(rows, key=lambda item: item.table):
        dropped = max(report.rows_dropped, 0)
        added = max(-report.rows_dropped, 0)
        print(
            f"{report.table:24s} {report.rows_in:9d} {report.rows_out:9d} "
            f"{dropped:8d} {added:6d}"
        )
        for line in textwrap.wrap(report.reason, width=76):
            print(f"    {line}")
    print("-" * len(header))
    print(f"{len(rows)} tables written")


def main(raw_dir: Path = RAW_DIR, out_dir: Path = PROCESSED_DIR) -> None:
    """Clean everything and write the processed CSVs."""
    result = build_all(raw_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in sorted(result.tables.items()):
        write_table(table, out_dir / f"{name}.csv")
    print(f"wrote {len(result.tables)} tables to {out_dir}\n")
    print_report(result.reports)


if __name__ == "__main__":
    main()
