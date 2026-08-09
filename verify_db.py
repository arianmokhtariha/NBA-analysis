"""
Check that the loaded `processed` schema matches the CSVs it came from and
that its constraints are real.

Run after db_setup.py:

    python verify_db.py

The checks are structural rather than a list of expected numbers, so this
keeps working after a re-scrape changes the row counts. It fails loudly
(exit code 1) if anything is wrong, so it can gate a rebuild.
"""

import csv
import sys
from pathlib import Path

import psycopg2

from db_config import DB_CONFIG

_ROOT = Path(__file__).parent
PROCESSED_DIR: Path = _ROOT / "data" / "processed"
SCHEMA: str = "processed"

# Every fact column that must resolve to a dimension, as
# (table, column, referenced table, referenced column).
REFERENCES: list[tuple[str, str, str, str]] = [
    ("rosters", "player_id", "players", "player_id"),
    ("rosters", "team_id", "teams", "team_id"),
    ("rosters", "season", "seasons", "season"),
    ("player_season_stats", "player_id", "players", "player_id"),
    ("player_season_stats", "team_id", "teams", "team_id"),
    ("player_season_stats", "season", "seasons", "season"),
    ("player_advanced_stats", "player_id", "players", "player_id"),
    ("player_advanced_stats", "season", "seasons", "season"),
    ("team_season_stats", "team_id", "teams", "team_id"),
    ("team_season_stats", "season", "seasons", "season"),
    ("mvp_winners", "player_id", "players", "player_id"),
    ("mvp_winners", "team_id", "teams", "team_id"),
    ("mvp_candidates", "player_id", "players", "player_id"),
    ("player_positions", "player_id", "players", "player_id"),
    ("season_awards", "champion_team_id", "teams", "team_id"),
]

_failures: list[str] = []


def _fail(message: str) -> None:
    _failures.append(message)


def _csv_row_count(path: Path) -> int:
    """Count data rows in a CSV, excluding the header.

    Uses the csv module rather than counting newlines, because several
    columns (player names, roster notes) contain quoted embedded newlines.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1


def check_row_counts(cursor: psycopg2.extensions.cursor) -> None:
    """Every table must hold exactly as many rows as its source CSV."""
    print("\n1. row counts, database vs source CSV")
    for path in sorted(PROCESSED_DIR.glob("*.csv")):
        table = path.stem
        expected = _csv_row_count(path)
        cursor.execute(f"SELECT count(*) FROM {SCHEMA}.{table}")
        actual = int(cursor.fetchone()[0])
        ok = actual == expected
        if not ok:
            _fail(f"{table}: {actual} rows loaded, {expected} in the CSV")
        print(f"   {'ok ' if ok else 'BAD'} {table:<24} {actual:>5}")


def check_constraints(cursor: psycopg2.extensions.cursor) -> None:
    """Constraints must exist AND be validated - a NOT VALID key proves nothing."""
    print("\n2. constraints defined and validated")
    cursor.execute(
        """
        SELECT contype, count(*), count(*) FILTER (WHERE convalidated)
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = %s AND contype IN ('p', 'f', 'c', 'u')
        GROUP BY contype
        ORDER BY contype
        """,
        [SCHEMA],
    )
    labels = {"p": "primary key", "f": "foreign key", "c": "check", "u": "unique"}
    seen: dict[str, int] = {}
    for contype, total, validated in cursor.fetchall():
        seen[contype] = int(total)
        if total != validated:
            _fail(f"{labels[contype]}: {total - validated} not validated")
        print(f"   {'ok ' if total == validated else 'BAD'} "
              f"{labels[contype]:<14} {total:>3} defined, {validated:>3} validated")

    if not seen.get("f"):
        _fail("no foreign keys defined at all")
    if not seen.get("p"):
        _fail("no primary keys defined at all")


def check_no_orphans(cursor: psycopg2.extensions.cursor) -> None:
    """
    Belt and braces: query for orphans directly.

    The foreign keys above should make this impossible, which is exactly why
    it is worth asserting - it catches a constraint that was quietly dropped.
    """
    print("\n3. orphan foreign keys (all must be 0)")
    total = 0
    for table, column, parent, parent_column in REFERENCES:
        cursor.execute(
            f"""
            SELECT count(*) FROM {SCHEMA}.{table} child
            WHERE child.{column} IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM {SCHEMA}.{parent} p
                  WHERE p.{parent_column} = child.{column}
              )
            """
        )
        orphans = int(cursor.fetchone()[0])
        total += orphans
        if orphans:
            _fail(f"{table}.{column} has {orphans} orphan values")
            print(f"   BAD {table}.{column:<20} {orphans}")
    print(f"   ok  all {len(REFERENCES)} relationships resolve"
          if total == 0 else f"   BAD {total} orphan values in total")


def check_primary_season_view(cursor: psycopg2.extensions.cursor) -> None:
    """
    The stint design must still yield one row per player-season.

    Traded players have a season-total row (stint 0) plus one row per team.
    Analysis that wants the old one-row-per-player-season shape filters on
    is_primary, so that filter has to be exactly unique or every downstream
    average is silently wrong.
    """
    print("\n4. is_primary gives exactly one row per player-season")
    for table in ("player_season_stats", "player_advanced_stats"):
        cursor.execute(
            f"""
            SELECT count(*), count(DISTINCT (season, player_id))
            FROM {SCHEMA}.{table} WHERE is_primary
            """
        )
        rows, distinct = (int(v) for v in cursor.fetchone())
        ok = rows == distinct
        if not ok:
            _fail(f"{table}: {rows - distinct} duplicate player-seasons in is_primary")
        print(f"   {'ok ' if ok else 'BAD'} {table:<24} {rows} rows, {distinct} distinct")


def check_constraints_bite(connection: psycopg2.extensions.connection) -> None:
    """
    Try to write data that must be rejected.

    Counting constraints proves they are declared; only a rejected write
    proves they are doing anything. Every statement is rolled back.
    """
    print("\n5. constraints actually reject bad writes")
    attempts = [
        (
            "roster row for a player who does not exist",
            f"INSERT INTO {SCHEMA}.rosters (season, player_id, team_id) "
            "VALUES (2024, 'nobody99', 'okc')",
        ),
        (
            "deleting a team that facts still reference",
            f"DELETE FROM {SCHEMA}.teams WHERE team_id = 'tot'",
        ),
    ]
    for label, statement in attempts:
        cursor = connection.cursor()
        try:
            cursor.execute(statement)
            _fail(f"{label}: was ACCEPTED, constraint is missing")
            print(f"   BAD {label:<44} accepted")
        except psycopg2.Error as exc:
            name = getattr(exc.diag, "constraint_name", None) or "a constraint"
            print(f"   ok  {label:<44} rejected by {name}")
        finally:
            connection.rollback()
            cursor.close()


def main() -> None:
    connection = psycopg2.connect(**DB_CONFIG)
    cursor = connection.cursor()
    print(f"Verifying schema '{SCHEMA}' in database "
          f"'{DB_CONFIG['dbname']}' at {DB_CONFIG['host']}")
    try:
        check_row_counts(cursor)
        check_constraints(cursor)
        check_no_orphans(cursor)
        check_primary_season_view(cursor)
    finally:
        cursor.close()
    check_constraints_bite(connection)
    connection.close()

    print()
    if _failures:
        print(f"FAIL - {len(_failures)} problem(s):")
        for message in _failures:
            print(f"  - {message}")
        sys.exit(1)
    print("PASS - row counts match, every constraint is validated, "
          "no orphans, and bad writes are rejected.")


if __name__ == "__main__":
    main()
