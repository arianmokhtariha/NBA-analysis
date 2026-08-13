"""Prove the cleaning pipeline is reproducible and referentially sound.

From the repository root::

    python -m cleaning.verify

It deletes ``data/processed`` outright, rebuilds it from ``data/raw``, and
then prints six things:

1. every expected file reappeared;
2. orphan foreign keys per fact table (all must be 0 for the PostgreSQL
   loader to run with foreign keys enforced instead of switched off);
3. duplicate primary keys per table (all must be 0);
4. every table against a minimum row count, which is the only check here
   that can catch an incomplete scrape - see :data:`MINIMUM_ROWS`;
5. every categorical column against the set of values it may hold - see
   :data:`VALUE_DOMAINS`;
6. the rows-in / rows-out / rows-dropped audit table with the reason for
   every drop.

A short list of spot checks on the specific bugs this pipeline fixes is
printed at the end.
"""

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    POSITION_SHORT_CODES,
    PROCESSED_DIR,
    RAW_DIR,
    read_table,
)
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

#: table -> column -> every value that column is allowed to hold.
#:
#: The checks above are structural: they ask whether the rows agree with each
#: other. None of them can see a value that is simply not a member of its
#: vocabulary, and a categorical column with a foreign value is internally
#: consistent right up until the database refuses it.
#:
#: That is not hypothetical. A scraper selector that missed put a player's
#: whole bio paragraph in his position cell, and the word "Forward" (the
#: source's spelling for a pre-1980 player) went straight into a two-character
#: column. Every check here passed. PostgreSQL then failed the load with a
#: column-width error naming neither the player nor the cause - and because
#: players is the parent of five foreign keys, six further tables failed after
#: it. Stating the vocabularies costs a few lines and moves that discovery
#: back to the step that can actually fix it.
#:
#: The position sets are imported, not retyped, so the vocabulary has exactly
#: one definition and this check cannot drift away from the cleaning code.
VALUE_DOMAINS: dict[str, dict[str, frozenset[str]]] = {
    "players": {
        "primary_position": POSITION_SHORT_CODES,
        "shoots": frozenset({"right", "left", "both"}),
    },
    "player_positions": {"position_code": POSITION_SHORT_CODES},
    "player_season_stats": {"position": POSITION_SHORT_CODES},
    "rosters": {
        "position_primary": POSITION_SHORT_CODES,
        "position_secondary": POSITION_SHORT_CODES,
    },
    "season_awards": {"league": frozenset({"NBA", "ABA", "BAA"})},
    "mvp_winners": {"league": frozenset({"NBA", "ABA", "BAA"})},
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


def check_value_domains(tables: dict[str, pd.DataFrame]) -> int:
    """Print any value outside its column's vocabulary; return the total.

    Missing values are not offences - most of these columns are legitimately
    NULL - so only values that are present and unrecognised are counted. The
    offending values are printed, because the whole point of running this
    check here rather than at load time is to name what went wrong.
    """
    print("\n5. VALUE DOMAINS (all must be 0)")
    print("-" * 70)
    total = 0
    for table_name, columns in VALUE_DOMAINS.items():
        for column, allowed in columns.items():
            values = tables[table_name][column].dropna().astype(str)
            offenders = values[~values.isin(allowed)]
            total += len(offenders)
            label = f"{table_name}.{column}"
            print(f"  {label:60s} {len(offenders):5d}")
            for value, count in offenders.value_counts().head(3).items():
                print(f"      not allowed: {value[:48]!r} x{count}")
    print(f"  total values outside their domain: {total}")
    return total


def _raw_bios() -> pd.DataFrame:
    """The raw bio file indexed by player id, ready for raw-vs-clean lookups."""
    raw = read_table(RAW_DIR / "player_bios.csv")
    raw["player_id"] = raw["player_id"].astype("string").str.strip().str.lower()
    return raw.dropna(subset=["player_id"]).drop_duplicates("player_id").set_index(
        "player_id"
    )


def spot_checks(tables: dict[str, pd.DataFrame]) -> None:
    """Show the concrete bugs this pipeline fixes, on real rows.

    Every example below is *found in the data*, never named in the code.
    The players that happen to illustrate a bug change with each scrape -
    naming them here made this section crash on the first re-scrape that
    dropped one of them.
    """
    print("\n7. SPOT CHECKS ON THE FIXED BUGS")
    print("-" * 70)
    players = tables["players"].set_index("player_id")
    raw_bios = _raw_bios()

    print("  mojibake repaired (raw -> cleaned):")
    shared = raw_bios.index.intersection(players.index)
    raw_names = raw_bios.loc[shared, "player_name"]
    clean_names = players.loc[shared, "player_name"]
    repaired = shared[(raw_names != clean_names).to_numpy()]
    print(f"    names changed by the repair: {len(repaired)}")
    for player_id in repaired[:3]:
        print(
            f"    {player_id:12s} {raw_names[player_id]!r} -> "
            f"{clean_names[player_id]!r}"
        )

    print("  position slots (the players with the most positions):")
    positions = tables["player_positions"]
    slot_counts = positions.groupby("player_id")["slot"].max()
    for player_id in slot_counts.nlargest(2).index:
        slots = positions.loc[positions["player_id"] == player_id]
        raw_value = (
            raw_bios.loc[player_id, "Position"]
            if player_id in raw_bios.index
            else None
        )
        print(f"    {player_id:12s} raw: {raw_value!r}")
        print(
            "                 slots: "
            + ", ".join(f"{row.slot}={row.position_code}" for row in slots.itertuples())
        )
    counts = positions["slot"].value_counts().sort_index()
    print(f"    rows per slot: {counts.to_dict()}")

    print("  shooting hand derived by one regex rule (no row indices):")
    # The interesting cells are the malformed ones ("Shoots: Right Left", or a
    # whole bio paragraph); a clean "Right" proves nothing.
    raw_shoots = raw_bios["Shoots"].astype("string").str.strip()
    messy = raw_shoots[~raw_shoots.isin(["Right", "Left"]) & raw_shoots.notna()]
    print(f"    malformed source cells: {len(messy)}")
    for player_id, raw_value in messy.head(3).items():
        value = (
            players.loc[player_id, "shoots"] if player_id in players.index else None
        )
        print(f"    {player_id:12s} {raw_value[:40]!r} -> {value!r}")
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
    stint_counts = stats.groupby(["season", "player_id"])["stint"].count()
    season, player_id = stint_counts.idxmax()
    traded = stats.loc[
        (stats["player_id"] == player_id) & (stats["season"] == season),
        ["season", "player_id", "stint", "is_primary", "team_id", "games_played",
         "points"],
    ]
    print(traded.to_string(index=False).replace("\n", "\n    "))

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
    # Players with no bio page of their own are the point of this check: they
    # are only known from a roster or an MVP listing, and they still get a row.
    named_without_bio = players.loc[
        ~players["has_bio"] & players["player_name"].notna()
    ]
    print(f"    named but never scraped a bio page: {len(named_without_bio)}")
    for player_id, row in named_without_bio.head(5).iterrows():
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
    bad_values = check_value_domains(tables)

    print("\n6. ROW COUNTS (rows in -> rows out, with the reason for drops)")
    print("-" * 70)
    print_report(build_all().reports)

    spot_checks(tables)

    print("\n" + "=" * 70)
    failures = missing + orphans + key_problems + undersized + bad_values
    verdict = "PASS" if failures == 0 else "FAIL"
    print(
        f"{verdict}: missing files={missing}, orphan foreign keys={orphans}, "
        f"primary-key problems={key_problems}, undersized tables={undersized}, "
        f"values outside their domain={bad_values}"
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
