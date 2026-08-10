"""
PostgreSQL project bootstrapper.

Creates a PostgreSQL database, applies a directory of versioned .sql files
to it, and loads a set of CSV files into the resulting tables.

This is the slow half of the database workflow: it creates the `processed`
schema and loads every cleaned CSV into it. Run it when the data changes.
For everything downstream of `processed`, use rebuild.py instead — it is
far faster because it loads no data.

Reusable across projects: to retarget it, edit ONLY the CONFIG block below.
Nothing further down is project-specific.

Usage:
    python db_setup.py
"""

import csv
import io
import itertools
import sys
import threading
import time
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import extensions, sql

from db_config import DB_CONFIG, DB_CONFIG_INIT

_ROOT = Path(__file__).parent

# ============================================================
# CONFIG — the only block to edit per project
# ============================================================

# Every *.sql file in this directory is executed in filename order, each as
# a single batch, exactly as written. Number the files to control the order:
#   00_schema.sql, 10_indexes.sql, 20_views.sql
SCHEMA_DIR: Path = _ROOT / "sql" / "processed"

# {csv path relative to this file: target table}
# (Important) Order parent tables before child tables so foreign keys resolve.
# Table names may be schema-qualified, e.g. "raw.sales".
CSV_MAPPING: dict[str, str] = {
    # ── dimensions first: every fact below references these ──────────────
    "data/processed/teams.csv": "processed.teams",
    "data/processed/players.csv": "processed.players",
    "data/processed/seasons.csv": "processed.seasons",
    # ── children of the dimensions ───────────────────────────────────────
    "data/processed/player_positions.csv": "processed.player_positions",
    "data/processed/season_awards.csv": "processed.season_awards",
    # ── facts ────────────────────────────────────────────────────────────
    "data/processed/rosters.csv": "processed.rosters",
    "data/processed/player_season_stats.csv": "processed.player_season_stats",
    "data/processed/player_advanced_stats.csv": "processed.player_advanced_stats",
    "data/processed/team_season_stats.csv": "processed.team_season_stats",
    "data/processed/mvp_winners.csv": "processed.mvp_winners",
    "data/processed/mvp_candidates.csv": "processed.mvp_candidates",
}

# "stream" — pipe the CSV straight into Postgres and let Postgres parse it.
#            Values land byte-exact and memory stays flat on huge files.
# "pandas" — read into a DataFrame first. Only needed when the data has to
#            be inspected or transformed in Python before it lands.
LOAD_MODE: str = "stream"

# True  — drop the database and rebuild it from scratch.
# False — leave the database in place, just apply SCHEMA_DIR and reload CSVs.
RECREATE_DB: bool = True

# "null_token" is the text that means NULL in the source files. An empty
# string (the default) means an empty CSV field is NULL.
CSV_DIALECT: dict[str, str] = {
    "delimiter": ",",
    "encoding": "utf-8",
    "null_token": "",
}

# ============================================================
# ANSI COLOR HELPERS (no external deps)
# ============================================================

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"


def _c(text: object, *codes: str) -> str:
    """Wrap text with one or more ANSI codes and reset at the end."""
    return "".join(codes) + str(text) + RESET


# ============================================================
# SPINNER (pure threading, no external deps)
# ============================================================


class Spinner:
    """
    Context-manager spinner that animates on a single terminal line while a
    blocking operation runs, then replaces itself with a success / failure
    icon when complete.

    Usage:
        with Spinner("Creating table players"):
            do_slow_work()
        # success → ✅  Creating table players
        # error   → ❌  Creating table players  (failed)
    """

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    INTERVAL = 0.08  # seconds between frames

    def __init__(self, message: str, indent: int = 2) -> None:
        self.message = message
        self.indent = " " * indent
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            sys.stdout.write(
                f"\r{self.indent}{_c(frame, CYAN)}  {self.message}{_c('...', DIM)}"
            )
            sys.stdout.flush()
            time.sleep(self.INTERVAL)

    def start(self) -> "Spinner":
        self._thread.start()
        return self

    def stop(self, success: bool = True, suffix: str = "") -> None:
        self._stop.set()
        self._thread.join()
        icon = _c("✅", GREEN) if success else _c("❌", RED)
        tag = _c(f"  ({suffix})", DIM) if suffix else ""
        sys.stdout.write(f"\r{self.indent}{icon}  {self.message}{tag}\n")
        sys.stdout.flush()

    # ── context-manager protocol ─────────────────────────────────────────
    def __enter__(self) -> "Spinner":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        # exc_type is None when the block exits cleanly
        self.stop(success=(exc_type is None))
        # Do NOT suppress exceptions — let them propagate to the caller
        return False


# ============================================================
# TERMINAL OUTPUT
# ============================================================

_BOX_WIDTH = 52


def _print_header(title: str) -> None:
    """Print a bold section header with a surrounding box."""
    bar = "═" * _BOX_WIDTH
    print()
    print(_c(f"╔{bar}╗", BOLD, CYAN))
    print(_c(f"║  {title:<{_BOX_WIDTH - 2}}║", BOLD, CYAN))
    print(_c(f"╚{bar}╝", BOLD, CYAN))
    print()


def _print_box(title: str, body: list[str], color: str) -> None:
    """
    Print a titled, boxed message block in the given ANSI colour.

    Padding is computed with len(), so every character placed inside the box
    must span the same number of terminal cells as code points. ⚠ ℹ ✔ ✖ are
    safe; ✅ ❌ are not (one code point, two cells) — they belong on the
    unpadded spinner lines instead.
    """
    inner = _BOX_WIDTH - 2
    bar = "═" * _BOX_WIDTH
    print(_c(f"  ╔{bar}╗", BOLD, color))
    print(_c(f"  ║  {title:<{inner}}║", BOLD, color))
    if body:
        print(_c(f"  ╠{bar}╣", BOLD, color))
        for line in body:
            print(_c(f"  ║  {line:<{inner}}║", color))
    print(_c(f"  ╚{bar}╝", BOLD, color))


def _print_section(label: str) -> None:
    """Print a dimmed step sub-header."""
    print(_c(f"\n  ── {label} {'─' * max(0, 46 - len(label))}", DIM))


# ============================================================
# DATABASE LIFECYCLE
# ============================================================


def _database_exists(db_name: str, config_init: dict[str, str]) -> bool:
    """Return True if the target database already exists in the cluster."""
    conn = psycopg2.connect(**config_init)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name])
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conn.close()


def confirm_reset(
    db_name: str,
    config_init: dict[str, str],
    recreate: bool,
) -> None:
    """
    Describe exactly what is about to happen and wait for confirmation.

    Rollback guarantee: this runs BEFORE any destructive operation, so
    answering 'no' leaves the database completely untouched — there is
    nothing to roll back.
    """
    exists = _database_exists(db_name, config_init)

    if recreate and exists:
        _print_box(
            "⚠  WARNING — DESTRUCTIVE OPERATION",
            [
                "",
                f"Database : {db_name}",
                "",
                "This database WILL BE PERMANENTLY DELETED and",
                "rebuilt from scratch. ALL existing data is lost.",
            ],
            YELLOW,
        )
    elif exists:
        _print_box(
            "ℹ  APPLY TO EXISTING DATABASE",
            [
                "",
                f"Database : {db_name}",
                "",
                "The database is kept. Schema files and CSV loads",
                "will be applied on top of what is already there.",
            ],
            CYAN,
        )
    else:
        _print_box(
            "ℹ  FIRST-TIME SETUP",
            [
                "",
                f"Database : {db_name}",
                "",
                "No existing database was found.",
                "A fresh database will be created.",
            ],
            CYAN,
        )

    print()

    try:
        answer = input(_c("  Proceed? [yes / no]  → ", BOLD)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        # Non-interactive environment or Ctrl-C — treat as 'no'
        answer = "no"

    print()

    if answer in ("yes", "y"):
        print(_c("  ✔  Confirmed. Starting setup...", BOLD, GREEN))
        print()
    else:
        # Nothing has been modified yet, so exiting here is a complete and
        # safe rollback of the entire operation.
        print(_c("  ✖  Aborted. No changes were made.", BOLD, RED))
        print()
        sys.exit(0)


def drop_database(db_name: str, config_init: dict[str, str]) -> None:
    """Drop the database if it exists, disconnecting any active sessions."""
    with Spinner(f"Dropping database '{db_name}'"):
        conn = psycopg2.connect(**config_init)
        conn.autocommit = True
        cursor = conn.cursor()
        try:
            # Terminate active connections first — without this, DROP
            # DATABASE fails whenever any session is still connected.
            cursor.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid()
                """,
                [db_name],
            )
            cursor.execute(
                sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name))
            )
        finally:
            cursor.close()
            conn.close()


def create_database(db_name: str, config_init: dict[str, str]) -> None:
    """Create the database, leaving it alone if it already exists."""
    with Spinner(f"Creating database '{db_name}'"):
        conn = psycopg2.connect(**config_init)
        conn.autocommit = True
        cursor = conn.cursor()
        try:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
            )
        except psycopg2.errors.DuplicateDatabase:
            pass  # already exists — spinner will still show ✅
        finally:
            cursor.close()
            conn.close()


# ============================================================
# SCHEMA
# ============================================================


def _schema_files(schema_dir: Path) -> list[Path]:
    """
    Return the top-level .sql files in schema_dir, sorted by filename.

    The glob is deliberately non-recursive. Sub-directories hold SQL that
    runs later in a pipeline (staging, marts, tests) rather than bootstrap
    DDL, so they are left alone.
    """
    if schema_dir.is_file():
        raise NotADirectoryError(
            f"SCHEMA_DIR must be a directory of .sql files, but points at a "
            f"single file:\n    {schema_dir}\n  Use its folder instead:\n"
            f"    {schema_dir.parent}"
        )
    if not schema_dir.is_dir():
        raise FileNotFoundError(f"Schema directory not found: {schema_dir}")
    files = sorted(schema_dir.glob("*.sql"))
    if not files:
        raise FileNotFoundError(
            f"No .sql files directly inside {schema_dir} "
            f"(sub-directories are not searched)"
        )
    return files


def _list_tables(cursor: extensions.cursor) -> list[str]:
    """Return every user table in the database, schema-qualified."""
    cursor.execute(
        """
        SELECT table_schema || '.' || table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY 1
        """
    )
    return [row[0] for row in cursor.fetchall()]


def apply_schema(schema_dir: Path, config: dict[str, str]) -> None:
    """
    Execute every .sql file in schema_dir, in filename order, as one batch
    per file — verbatim, with no parsing.

    Running the files as written is what guarantees that everything in them
    actually executes. Extracting statements with a regex silently drops
    whatever the pattern does not match (CREATE INDEX, CREATE VIEW,
    schema-qualified names), with no error to reveal the omission.

    The result is then read back from the catalog, so what gets printed is
    what the database really contains rather than what was intended.
    """
    files = _schema_files(schema_dir)
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    try:
        for path in files:
            with Spinner(f"Applying  {_c(path.name, BOLD, WHITE)}"):
                # No parameters are passed, so psycopg2 performs no
                # interpolation and a literal '%' in the SQL is safe.
                cursor.execute(path.read_text(encoding="utf-8"))
                conn.commit()

        print()
        for name in _list_tables(cursor):
            print(f"  {_c('✅', GREEN)}  Table ready  {_c(name, BOLD, WHITE)}")

    except Exception as exc:
        conn.rollback()
        print(_c(f"\n  ❌ Schema step failed: {exc}", RED))
        raise
    finally:
        cursor.close()
        conn.close()


# ============================================================
# DATA LOADING
# ============================================================


def _quote_literal(value: str) -> str:
    """Render a Python string as a single-quoted SQL literal."""
    return "'" + value.replace("'", "''") + "'"


def _quote_columns(columns: list[str]) -> str:
    """Render column names as a quoted, comma-separated identifier list."""
    return ", ".join('"' + col.strip().replace('"', '""') + '"' for col in columns)


def _load_stream(
    csv_path: Path,
    table_name: str,
    cursor: extensions.cursor,
    dialect: dict[str, str],
) -> int:
    """
    Pipe the CSV file straight into Postgres and let Postgres parse it.

    Nothing passes through pandas, so values reach the table exactly as
    written in the file and memory use stays flat regardless of file size.
    This also sidesteps the float-upcast problem described in
    _restore_integer_columns entirely — it simply cannot arise here.

    Column names are taken from the CSV header, so the file's column order
    does not have to match the table's.
    """
    with csv_path.open("r", encoding=dialect["encoding"], newline="") as handle:
        header = next(csv.reader([handle.readline()], delimiter=dialect["delimiter"]))
        handle.seek(0)  # rewind so COPY's HEADER option consumes the header
        # table_name comes from CSV_MAPPING (trusted config) and may be
        # schema-qualified, so it is inlined rather than quoted as one
        # identifier — sql.Identifier would turn raw.sales into "raw.sales".
        cursor.copy_expert(
            f"COPY {table_name} ({_quote_columns(header)}) FROM STDIN WITH ("
            f"FORMAT csv, HEADER true, "
            f"DELIMITER {_quote_literal(dialect['delimiter'])}, "
            f"NULL {_quote_literal(dialect['null_token'])})",
            handle,
        )
    return cursor.rowcount


def _restore_integer_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Undo pandas' float upcast on integer columns that contain nulls.

    pandas' int64 dtype cannot represent a missing value, so read_csv has no
    choice but to store any integer column containing nulls as float64 —
    186 silently becomes 186.0, and Postgres then rejects the text "186.0"
    for an integer column.

    Where every non-null value in a float column is whole, the column was an
    integer to begin with and is restored to the nullable Int64 dtype.
    Columns holding genuine decimals fail that test, stay float, and keep
    full precision — which is why this is preferred over blanket-rounding
    every float with to_csv(float_format='%.0f').
    """
    for column in frame.select_dtypes(include=["float32", "float64"]).columns:
        non_null = frame[column].dropna()
        if not non_null.empty and (non_null % 1 == 0).all():
            frame[column] = frame[column].astype("Int64")
    return frame


def _load_pandas(
    csv_path: Path,
    table_name: str,
    cursor: extensions.cursor,
    dialect: dict[str, str],
) -> int:
    """
    Read the CSV into a DataFrame, then COPY that in as CSV text.

    Only worth using when the data has to be touched in Python before it
    lands; otherwise prefer _load_stream. CSV is used as the wire format
    (rather than tab-separated text) because pandas quotes embedded
    delimiters, quotes and newlines correctly for it — a tab-separated
    export would corrupt any value containing a tab or a backslash.

    NULLs travel as an unquoted \\N, which CSV format treats as NULL only
    when unquoted, so genuine empty strings survive as empty strings.
    """
    na_values = [dialect["null_token"]] if dialect["null_token"] else None
    frame = pd.read_csv(
        csv_path,
        delimiter=dialect["delimiter"],
        encoding=dialect["encoding"],
        na_values=na_values,
    )
    frame = _restore_integer_columns(frame)
    buffer = io.StringIO(frame.to_csv(index=False, header=False, na_rep="\\N"))
    cursor.copy_expert(
        f"COPY {table_name} ({_quote_columns(list(frame.columns))}) "
        f"FROM STDIN WITH (FORMAT csv, NULL '\\N')",
        buffer,
    )
    return len(frame)


def load_csv_to_table(
    csv_path: Path,
    table_name: str,
    config: dict[str, str],
    load_mode: str,
    dialect: dict[str, str],
) -> None:
    """Load one CSV into one table, with a live spinner and a row count."""
    loaders = {"stream": _load_stream, "pandas": _load_pandas}
    if load_mode not in loaders:
        raise ValueError(
            f"LOAD_MODE must be one of {sorted(loaders)}, got {load_mode!r}"
        )

    if not csv_path.exists():
        print(f"  {_c('⚠', YELLOW)}  Not found — skipping: {_c(csv_path, DIM)}")
        return
    if csv_path.stat().st_size == 0:
        print(f"  {_c('⚠', YELLOW)}  Empty — skipping: {_c(csv_path.name, DIM)}")
        return

    conn = psycopg2.connect(**config)
    cursor = conn.cursor()
    spinner = Spinner(f"Loading  {_c(f'{table_name:<32}', BOLD, WHITE)}").start()

    try:
        rows = loaders[load_mode](csv_path, table_name, cursor, dialect)
        conn.commit()
        spinner.stop(success=True, suffix=f"{rows:,} rows")
    except Exception as exc:
        conn.rollback()
        spinner.stop(success=False, suffix="failed")
        print(_c(f"     → {exc}", RED))
        raise
    finally:
        cursor.close()
        conn.close()


def load_all_csvs(
    csv_mapping: dict[str, str],
    config: dict[str, str],
    load_mode: str,
    dialect: dict[str, str],
) -> None:
    """Load every CSV in the mapping, in the order it is declared."""
    for rel_path, table_name in csv_mapping.items():
        load_csv_to_table(_ROOT / rel_path, table_name, config, load_mode, dialect)


# ============================================================
# ENTRY POINT
# ============================================================


def run_setup() -> None:
    """Create the database, apply the schema files, and load the CSVs."""
    _print_header("DATABASE SETUP")
    db_name = DB_CONFIG["dbname"]

    # Guard: describe the operation and require explicit confirmation. This
    # runs before anything destructive, so 'no' guarantees zero changes.
    confirm_reset(db_name, DB_CONFIG_INIT, RECREATE_DB)

    step = itertools.count(1)

    if RECREATE_DB:
        _print_section(f"Step {next(step)} — Drop existing database")
        drop_database(db_name, DB_CONFIG_INIT)

    _print_section(f"Step {next(step)} — Create database")
    create_database(db_name, DB_CONFIG_INIT)

    _print_section(f"Step {next(step)} — Apply schema")
    apply_schema(SCHEMA_DIR, DB_CONFIG)

    _print_section(f"Step {next(step)} — Load data ({LOAD_MODE})")
    if CSV_MAPPING:
        print()
        load_all_csvs(CSV_MAPPING, DB_CONFIG, LOAD_MODE, CSV_DIALECT)
    else:
        print(f"  {_c('ℹ', CYAN)}  Nothing to load (CSV_MAPPING is empty).")

    print()
    _print_box("✔  Setup complete — database is ready.", [], GREEN)
    print()


if __name__ == "__main__":
    run_setup()
