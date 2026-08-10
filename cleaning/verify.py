"""Prove the cleaning pipeline is reproducible and referentially sound.

From the repository root::

    python -m cleaning.verify

It deletes ``data/processed`` outright, rebuilds it from ``data/raw``, and
then prints five things:

1. every expected file reappeared;
2. orphan foreign keys per fact table (all must be 0 for the PostgreSQL
   loader to run with foreign keys enforced instead of switched off);
3. duplicate primary keys per table (all must be 0);
4. every table against a minimum row count, which is the only check here
   that can catch an incomplete scrape - see :data:`MINIMUM_ROWS`;
5. the rows-in / rows-out / rows-dropped audit table with the reason for
   every drop.

A short list of spot checks on the specific bugs this pipeline fixes is
printed at the end.
"""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from cleaning.normalize import PROCESSED_DIR, RAW_DIR, read_table
from cleaning.run_all import build_all, print_report

EXPECTED_TABLES: tuple[str, ...] = (
    "mvp_candidates",
    "mvp_winners",
    "player_advanced_stats",
    "player_positions",
    "player_season_stats",
    "players",
    "rosters",
    "season_awards",
    "seasons",
    "team_season_stats",
    "teams",
)

#: table -> the fewest rows a healthy build should produce.
#:
#: Every other check here is structural: it asks whether the rows that
#: exist are consistent with each other. None of them notice a build that
#: is simply too small. A scrape that quietly returned 800 players instead
#: of 1381 still has no orphan keys and no duplicate keys - it is a
#: perfectly consistent, badly incomplete dataset, and it would pass.
#:
#: These are floors, not expected counts, set around 15% below the build
#: they were taken from. That asymmetry is deliberate: the data grows every
#: season, so growth must never raise an alarm, while a real shortfall
#: (pages skipped, a scraper stopping early, a season missing) shows up
#: immediately. They only need revisiting to make the check stricter.
MINIMUM_ROWS: dict[str, int] = {
    "mvp_candidates": 72,
    "mvp_winners": 59,
    "player_advanced_stats": 4271,
    "player_positions": 1396,
    "player_season_stats": 4271,
    "players": 1690,
    "rosters": 1592,
    "season_awards": 74,
    "seasons": 68,
    "team_season_stats": 1439,
    "teams": 63,
}

#: table -> primary key columns
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "players": ("player_id",),
    "player_positions": ("player_id", "slot"),
    "teams": ("team_id",),
    "seasons": ("season",),
    "season_awards": ("season", "league"),
    "team_season_stats": ("season", "team_id"),
    "player_season_stats": ("season", "player_id", "stint"),
    "player_advanced_stats": ("season", "player_id", "stint"),
    "rosters": ("season", "team_id", "player_id"),
    "mvp_winners": ("season",),
    "mvp_candidates": ("season", "player_id"),
}


@dataclass(frozen=True)
class ForeignKey:
    """One foreign-key constraint to check."""

    table: str
    column: str
    parent_table: str
    parent_column: str


FOREIGN_KEYS: tuple[ForeignKey, ...] = (
    ForeignKey("player_positions", "player_id", "players", "player_id"),
    ForeignKey("player_season_stats", "player_id", "players", "player_id"),
    ForeignKey("player_season_stats", "team_id", "teams", "team_id"),
    ForeignKey("player_season_stats", "season", "seasons", "season"),
    ForeignKey("player_advanced_stats", "player_id", "players", "player_id"),
    ForeignKey("player_advanced_stats", "team_id", "teams", "team_id"),
    ForeignKey("player_advanced_stats", "season", "seasons", "season"),
    ForeignKey("rosters", "player_id", "players", "player_id"),
    ForeignKey("rosters", "team_id", "teams", "team_id"),
    ForeignKey("rosters", "season", "seasons", "season"),
    ForeignKey("mvp_winners", "player_id", "players", "player_id"),
    ForeignKey("mvp_winners", "team_id", "teams", "team_id"),
    ForeignKey("mvp_winners", "season", "seasons", "season"),
    ForeignKey("mvp_candidates", "player_id", "players", "player_id"),
    ForeignKey("mvp_candidates", "team_id", "teams", "team_id"),
    ForeignKey("mvp_candidates", "season", "seasons", "season"),
    ForeignKey("team_season_stats", "team_id", "teams", "team_id"),
    ForeignKey("team_season_stats", "season", "seasons", "season"),
    ForeignKey("season_awards", "season", "seasons", "season"),
    ForeignKey("season_awards", "champion_team_id", "teams", "team_id"),
)

#: Foreign keys spanning several columns at once, as
#: (table, columns, parent table, parent columns).
#:
#: The advanced metrics and the box score are two halves of the same
#: player-season, scraped from two different pages by two different
#: modules - each with its own season range. Those ranges have drifted
#: apart before. The database enforces this join, so a row of advanced
#: stats for a season the box scores do not cover will stop the load; this
#: check finds it here instead, in seconds.
COMPOSITE_FOREIGN_KEYS: tuple[
    tuple[str, tuple[str, ...], str, tuple[str, ...]], ...
] = (
    (
        "player_advanced_stats",
        ("season", "player_id", "stint"),
        "player_season_stats",
        ("season", "player_id", "stint"),
    ),
)


def rebuild(raw_dir: Path = RAW_DIR, out_dir: Path = PROCESSED_DIR) -> list[str]:
    """Delete the processed folder and regenerate it from the raw inputs."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    from cleaning.run_all import main as run_all_main

    run_all_main(raw_dir=raw_dir, out_dir=out_dir)
    return sorted(path.name for path in out_dir.glob("*.csv"))


def load_processed(out_dir: Path = PROCESSED_DIR) -> dict[str, pd.DataFrame]:
    """Read every processed CSV back from disk."""
    return {
        path.stem: read_table(path) for path in sorted(out_dir.glob("*.csv"))
    }


def check_files(written: list[str]) -> int:
    """Print which expected files reappeared; return the number missing."""
    print("\n1. REGENERATION FROM SCRATCH")
    print("-" * 70)
    missing = [
        name for name in EXPECTED_TABLES if f"{name}.csv" not in written
    ]
    unexpected = [
        name for name in written if Path(name).stem not in EXPECTED_TABLES
    ]
    for name in EXPECTED_TABLES:
        status = "missing" if f"{name}.csv" in missing else "ok"
        print(f"  {name + '.csv':32s} {status}")
    if unexpected:
        print(f"  unexpected files: {unexpected}")
    print(f"  files expected: {len(EXPECTED_TABLES)}, missing: {len(missing)}")
    return len(missing)


def check_foreign_keys(tables: dict[str, pd.DataFrame]) -> int:
    """Print the orphan count for every foreign key; return the total."""
    print("\n2. ORPHAN FOREIGN KEYS (all must be 0)")
    print("-" * 70)
    total = 0
    for key in FOREIGN_KEYS:
        child = tables[key.table]
        parent_values = set(tables[key.parent_table][key.parent_column].dropna())
        values = child[key.column].dropna()
        orphans = int((~values.isin(parent_values)).sum())
        total += orphans
        label = f"{key.table}.{key.column} -> {key.parent_table}"
        print(f"  {label:60s} {orphans:5d}")

    for table, columns, parent_table, parent_columns in COMPOSITE_FOREIGN_KEYS:
        child_keys = tables[table][list(columns)].dropna()
        parent_keys = set(
            tables[parent_table][list(parent_columns)]
            .dropna()
            .itertuples(index=False, name=None)
        )
        orphans = sum(
            1
            for row in child_keys.itertuples(index=False, name=None)
            if row not in parent_keys
        )
        total += orphans
        label = f"{table}({', '.join(columns)}) -> {parent_table}"
        print(f"  {label:60s} {orphans:5d}")

    print(f"  total orphans: {total}")
    return total


def check_primary_keys(tables: dict[str, pd.DataFrame]) -> int:
    """Print duplicate-key counts for every table; return the total."""
    print("\n3. DUPLICATE PRIMARY KEYS (all must be 0)")
    print("-" * 70)
    total = 0
    for table_name, key_columns in PRIMARY_KEYS.items():
        table = tables[table_name]
        duplicates = int(table.duplicated(list(key_columns)).sum())
        nulls = int(table[list(key_columns)].isna().any(axis=1).sum())
        total += duplicates + nulls
        label = f"{table_name} ({', '.join(key_columns)})"
        print(f"  {label:60s} dup={duplicates:4d} null={nulls:4d}")
    print(f"  total key problems: {total}")
    return total


def check_row_volume(tables: dict[str, pd.DataFrame]) -> int:
    """Print each table's size against its floor; return the number too small.

    Catches the one failure the other checks cannot see: a build that is
    internally consistent but incomplete. See :data:`MINIMUM_ROWS`.
    """
    print("\n4. ROW VOLUME (each table against its minimum)")
    print("-" * 70)
    short = 0
    for table_name, floor in MINIMUM_ROWS.items():
        rows = len(tables[table_name])
        ok = rows >= floor
        short += 0 if ok else 1
        marker = "ok" if ok else "TOO FEW"
        change = f"{rows - floor:+d} vs floor"
        print(f"  {table_name:26s} {rows:6d}  (min {floor:6d}, "
              f"{change:>16s})  {marker}")
    if short:
        print(f"  {short} table(s) below the floor - the source data is "
              f"probably incomplete, not the code")
    else:
        print("  every table is at or above its minimum")
    return short


def spot_checks(tables: dict[str, pd.DataFrame]) -> None:
    """Show the concrete bugs this pipeline fixes, on real rows."""
    print("\n5. SPOT CHECKS ON THE FIXED BUGS")
    print("-" * 70)
    players = tables["players"].set_index("player_id")

    print("  mojibake repaired (raw -> cleaned):")
    raw_bios = read_table(RAW_DIR / "player_bios.csv").set_index("player_id")
    for player_id in ("jokicni01", "doncilu01", "schrode01"):
        raw_name = raw_bios.loc[player_id, "player_name"]
        clean_name = players.loc[player_id, "player_name"]
        print(f"    {player_id:12s} {raw_name!r} -> {clean_name!r}")

    print("  position slots (Paul George: 3 real positions, no empty slot):")
    positions = tables["player_positions"]
    george = positions.loc[positions["player_id"] == "georgpa01"]
    print(f"    raw: {raw_bios.loc['georgpa01', 'Position']!r}")
    print(
        "    slots: "
        + ", ".join(
            f"{row.slot}={row.position_code}" for row in george.itertuples()
        )
    )
    counts = positions["slot"].value_counts().sort_index()
    print(f"    rows per slot: {counts.to_dict()}")

    print("  shooting hand derived by one regex rule (no row indices):")
    for player_id in ("plumlma01", "thomptr01", "vildolu01"):
        value = players.loc[player_id, "shoots"]
        print(f"    {player_id:12s} -> {value!r}")
    print(f"    distribution: {tables['players']['shoots'].value_counts().to_dict()}")

    print("  'tot' handled as two different things:")
    teams = tables["teams"]
    tot_row = teams.loc[teams["team_id"] == "tot"]
    print(f"    teams row: {tot_row.to_dict('records')}")
    stats = tables["player_season_stats"]
    total_rows = stats.loc[stats["team_id"] == "tot"]
    print(
        f"    player_season_stats rows with team_id='tot': {len(total_rows)} "
        f"(all stint 0: {bool((total_rows['stint'] == 0).all())})"
    )
    print(
        f"    rows with player_id='tot': "
        f"{int((stats['player_id'] == 'tot').sum())} (League Average rows removed)"
    )

    print("  traded players keep every stint:")
    harris = stats.loc[
        (stats["player_id"] == "harrito02") & (stats["season"] == 2019),
        ["season", "player_id", "stint", "is_primary", "team_id", "games_played",
         "points"],
    ]
    print(harris.to_string(index=False).replace("\n", "\n    "))

    print("  one row per player-season is still available via is_primary:")
    for name in ("player_season_stats", "player_advanced_stats"):
        table = tables[name]
        primary = table.loc[table["is_primary"]]
        unique = len(primary.drop_duplicates(["season", "player_id"]))
        print(
            f"    {name:22s} rows={len(table)} is_primary={len(primary)} "
            f"unique(season,player)={unique}"
        )

    print("  dimensions are complete, so no history was dropped:")
    print(
        f"    players={len(tables['players'])} "
        f"(has_bio={int(tables['players']['has_bio'].sum())}, "
        f"named={int(tables['players']['player_name'].notna().sum())})"
    )
    for player_id in ("jordami01", "abdulka01", "birdla01", "johnsma02",
                      "chambwi01"):
        row = players.loc[player_id]
        print(f"    {player_id:12s} {row['player_name']!r} has_bio={row['has_bio']}")
    print(
        f"    teams={len(tables['teams'])} "
        f"(has_detail={int(tables['teams']['has_detail'].sum())})"
    )
    aba = tables["teams"].loc[~tables["teams"]["has_detail"]]
    print(f"    teams without season totals: {aba['team_id'].tolist()}")
    seasons = tables["seasons"]
    print(
        f"    seasons={len(seasons)} range={seasons['season'].min()}-"
        f"{seasons['season'].max()} with_awards={int(seasons['has_awards'].sum())}"
    )


def main() -> int:
    """Rebuild, verify, and return a process exit code (0 = everything passed)."""
    written = rebuild()
    missing = check_files(written)
    tables = load_processed()
    orphans = check_foreign_keys(tables)
    key_problems = check_primary_keys(tables)
    undersized = check_row_volume(tables)

    print("\n5. ROW COUNTS (rows in -> rows out, with the reason for drops)")
    print("-" * 70)
    print_report(build_all().reports)

    spot_checks(tables)

    print("\n" + "=" * 70)
    failures = missing + orphans + key_problems + undersized
    verdict = "PASS" if failures == 0 else "FAIL"
    print(
        f"{verdict}: missing files={missing}, orphan foreign keys={orphans}, "
        f"primary-key problems={key_problems}, undersized tables={undersized}"
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
