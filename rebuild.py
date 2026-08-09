"""
PostgreSQL derived-schema rebuilder.

Rebuilds schemas that are *derived* from an existing base schema, by running
directories of numbered .sql files in order. Loads no data, and never touches
the base schema.

Companion to db_setup.py, which does the slow half of the job (create the
database, apply its schema, load the CSVs). This script does the fast half —
everything downstream of that — so iterating on a marts layer costs seconds
instead of a full reload.

Reusable across projects: to retarget it, edit ONLY the CONFIG block below.
Nothing further down is project-specific.

Usage:
    python rebuild.py
"""

import itertools
import sys
import threading
import time
from pathlib import Path

import psycopg2
from psycopg2 import extensions, sql

from db_config import DB_CONFIG

_ROOT = Path(__file__).parent

# ============================================================
# CONFIG — the only block to edit per project
# ============================================================

# Root of the SQL tree. Each build target below points at a sub-directory.
SQL_ROOT: Path = _ROOT / "sql"

# Schemas to build, in list order. Each entry is (schema name, directory).
# Every *.sql file directly inside the directory runs in filename order, each
# as a single batch, exactly as written. Number the files to control the order:
#   00_schema.sql, 10_dimensions.sql, 20_facts.sql
# The glob is non-recursive, matching db_setup.py — sub-directories are ignored.
BUILD_TARGETS: list[tuple[str, Path]] = [
    ("analyst_ready", SQL_ROOT / "analyst_ready"),
]

# The base schema every target is built FROM. It must already exist and hold
# tables before anything runs; if it does not, this script stops and tells you
# to run db_setup.py first, rather than failing later with an opaque SQL error.
REQUIRED_SCHEMA: str = "processed"

# Schemas this script must never drop. The base schema belongs here: this
# script reads from it and never writes to it. The guard runs before any
# destructive statement, so a typo in BUILD_TARGETS aborts harmlessly.
PROTECTED_SCHEMAS: set[str] = {
    "processed",
    "public",
    "pg_catalog",
    "pg_toast",
    "information_schema",
}

# True  — drop each target schema and rebuild it from nothing.
#         This is what makes re-running safe: the result is identical every
#         time, so the .sql files never need IF NOT EXISTS / DROP guards and
#         stay readable as plain business logic.
# False — run the .sql files against whatever is already there. Only useful
#         when a target is expensive to rebuild and the files are written to
#         be individually idempotent.
DROP_TARGET_SCHEMA: bool = True

# Ask before dropping. Left False by default because every target is derived
# and gets rebuilt in the same run, so a drop destroys nothing that this
# script does not immediately recreate. Set True if a target ever holds
# state that is not reproducible from the base schema.
CONFIRM_BEFORE_DROP: bool = False

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
# GUARDS
# ============================================================


def check_targets_allowed(
    targets: list[tuple[str, Path]],
    protected: set[str],
) -> None:
    """
    Refuse to run if any build target is a protected schema.

    This is what structurally enforces "never touch the base schema" — a typo
    in BUILD_TARGETS stops the run here, before any DROP is issued, rather
    than destroying data that took a full load to produce.
    """
    offenders = [name for name, _ in targets if name in protected]
    if offenders:
        _print_box(
            "✖  REFUSING TO RUN",
            [
                "",
                "These build targets are protected schemas:",
                "",
                *[f"  - {name}" for name in offenders],
                "",
                "This script builds derived schemas only.",
                "Remove them from BUILD_TARGETS — or from",
                "PROTECTED_SCHEMAS if you really mean it.",
            ],
            RED,
        )
        print()
        sys.exit(1)


def check_base_schema(schema_name: str, config: dict[str, str]) -> int:
    """
    Verify the base schema exists and holds tables. Returns the table count.

    Failing here with a clear message beats letting every .sql file fail on a
    missing relation.
    """
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            """,
            [schema_name],
        )
        row = cursor.fetchone()
        count = int(row[0]) if row else 0
    finally:
        cursor.close()
        conn.close()

    if count == 0:
        _print_box(
            "✖  BASE SCHEMA NOT READY",
            [
                "",
                f"Schema : {schema_name}",
                "",
                "It is missing or holds no tables, so there is",
                "nothing to build from.",
                "",
                "Run db_setup.py first to create and load it.",
            ],
            RED,
        )
        print()
        sys.exit(1)

    return count


def confirm_drop(targets: list[tuple[str, Path]]) -> None:
    """
    Describe what is about to be dropped and wait for confirmation.

    Runs BEFORE any destructive statement, so answering 'no' leaves every
    schema untouched — there is nothing to roll back.
    """
    _print_box(
        "⚠  These schemas will be dropped and rebuilt",
        ["", *[f"  - {name}" for name, _ in targets], ""],
        YELLOW,
    )
    print()
    try:
        answer = input(_c("  Proceed? [yes / no]  → ", BOLD)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "no"
    print()

    if answer not in ("yes", "y"):
        print(_c("  ✖  Aborted. No changes were made.", BOLD, RED))
        print()
        sys.exit(0)


# ============================================================
# SQL FILES
# ============================================================


def _sql_files(sql_dir: Path) -> list[Path]:
    """
    Return the top-level .sql files in sql_dir, sorted by filename.

    The glob is deliberately non-recursive, matching db_setup.py: a
    sub-directory belongs to a different build target, not this one.
    """
    if sql_dir.is_file():
        raise NotADirectoryError(
            f"Build targets must point at a directory of .sql files, but this "
            f"points at a single file:\n    {sql_dir}\n  Use its folder "
            f"instead:\n    {sql_dir.parent}"
        )
    if not sql_dir.is_dir():
        raise FileNotFoundError(f"SQL directory not found: {sql_dir}")
    files = sorted(sql_dir.glob("*.sql"))
    if not files:
        raise FileNotFoundError(
            f"No .sql files directly inside {sql_dir} "
            f"(sub-directories are not searched)"
        )
    return files


def _list_objects(cursor: extensions.cursor, schema_name: str) -> list[tuple[str, str]]:
    """
    Return (object name, kind) for everything in a schema, read from the
    catalog — so what gets printed is what the database really contains
    rather than what the .sql files intended to create.
    """
    cursor.execute(
        """
        SELECT c.relname,
               CASE c.relkind
                   WHEN 'r' THEN 'table'
                   WHEN 'v' THEN 'view'
                   WHEN 'm' THEN 'materialized view'
                   WHEN 'f' THEN 'foreign table'
                   WHEN 'p' THEN 'partitioned table'
                   ELSE c.relkind::text
               END
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s
          AND c.relkind IN ('r', 'v', 'm', 'f', 'p')
        ORDER BY 1
        """,
        [schema_name],
    )
    return [(row[0], row[1]) for row in cursor.fetchall()]


# ============================================================
# BUILD
# ============================================================


def build_schema(
    schema_name: str,
    sql_dir: Path,
    config: dict[str, str],
    drop_first: bool,
) -> None:
    """
    Build one schema from its directory of .sql files, in a single transaction.

    Everything runs inside one transaction and commits at the end, so a
    failure anywhere rolls the whole target back to exactly how it was. There
    is no half-built schema to clean up, which is what makes this safe to run
    as often as you like.
    """
    files = _sql_files(sql_dir)
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    try:
        if drop_first:
            with Spinner(f"Dropping schema {_c(schema_name, BOLD, WHITE)}"):
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )

        for path in files:
            with Spinner(f"Running   {_c(path.name, BOLD, WHITE)}"):
                # No parameters are passed, so psycopg2 performs no
                # interpolation and a literal '%' in the SQL is safe.
                cursor.execute(path.read_text(encoding="utf-8"))

        conn.commit()

        print()
        objects = _list_objects(cursor, schema_name)
        for name, kind in objects:
            label = f"{schema_name}.{name}"
            print(
                f"  {_c('✅', GREEN)}  Built  {_c(f'{label:<38}', BOLD, WHITE)}"
                f"{_c(kind, DIM)}"
            )
        if not objects:
            print(f"  {_c('⚠', YELLOW)}  Schema is empty — did the .sql files run?")

    except Exception as exc:
        conn.rollback()
        print(_c(f"\n  ❌ Build failed for '{schema_name}': {exc}", RED))
        print(_c("     Rolled back — the schema is unchanged.", DIM))
        raise
    finally:
        cursor.close()
        conn.close()


# ============================================================
# ENTRY POINT
# ============================================================


def run_rebuild() -> None:
    """Rebuild every configured derived schema from the base schema."""
    _print_header("SCHEMA REBUILD")

    # Guard first: refuse protected targets before anything destructive runs.
    check_targets_allowed(BUILD_TARGETS, PROTECTED_SCHEMAS)

    _print_section("Step 1 — Check base schema")
    with Spinner(f"Checking  {_c(REQUIRED_SCHEMA, BOLD, WHITE)}"):
        table_count = check_base_schema(REQUIRED_SCHEMA, DB_CONFIG)
    print(
        f"  {_c('ℹ', CYAN)}  {REQUIRED_SCHEMA} holds "
        f"{_c(table_count, BOLD, WHITE)} tables — reading only, never written."
    )

    if DROP_TARGET_SCHEMA and CONFIRM_BEFORE_DROP:
        print()
        confirm_drop(BUILD_TARGETS)

    step = itertools.count(2)
    for schema_name, sql_dir in BUILD_TARGETS:
        _print_section(f"Step {next(step)} — Build {schema_name}")
        build_schema(schema_name, sql_dir, DB_CONFIG, DROP_TARGET_SCHEMA)

    print()
    _print_box("✔  Rebuild complete.", [], GREEN)
    print()


if __name__ == "__main__":
    run_rebuild()
