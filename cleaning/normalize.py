"""Shared helpers used by every cleaning module.

Anything that more than one table needs lives here, so a rule is written
once and applied identically everywhere. Several helpers encode facts about
Basketball-Reference (the data source) rather than generic data cleaning;
those are called out in the docstrings.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Project paths
# --------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
RAW_DIR: Path = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR: Path = PROJECT_ROOT / "data" / "processed"

#: Basketball-Reference writes a player's combined line for a season in which
#: he was traded under the pseudo-team "TOT" (total). It is not a franchise,
#: so it gets its own dimension row instead of being silently dropped.
TOTAL_TEAM_ID: str = "tot"
TOTAL_TEAM_NAME: str = "Multiple Teams (season total)"

#: Basketball-Reference spells positions out on the player bio page but uses
#: two-letter codes on the season tables. This maps one vocabulary onto the
#: other so both can be joined.
POSITION_CODES: dict[str, str] = {
    "point guard": "PG",
    "shooting guard": "SG",
    "small forward": "SF",
    "power forward": "PF",
    "center": "C",
}

MONTH_NUMBERS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_INCHES_PER_FOOT_CM: float = 30.48
_INCH_CM: float = 2.54
_POUND_KG: float = 0.45359237


# --------------------------------------------------------------------------
# Reporting containers
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TableReport:
    """One row of the rows-in / rows-out / rows-dropped audit table."""

    table: str
    rows_in: int
    rows_out: int
    reason: str

    @property
    def rows_dropped(self) -> int:
        """Rows removed between the raw input and the written output."""
        return self.rows_in - self.rows_out


@dataclass(frozen=True)
class BuildResult:
    """What every ``build_*`` function returns: tables plus an audit trail."""

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    reports: list[TableReport] = field(default_factory=list)


# --------------------------------------------------------------------------
# Input / output
# --------------------------------------------------------------------------
def read_table(path: Path, sheet_name: str | None = None) -> pd.DataFrame:
    """Read a table from disk, picking the reader from the file extension.

    ``.xlsx`` / ``.xls`` go through ``pd.read_excel`` (first sheet unless
    ``sheet_name`` is given), everything else through ``pd.read_csv``.
    """
    if path.suffix.lower() in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, sheet_name=sheet_name if sheet_name else 0)
        # read_excel returns a dict only when sheet_name is a list/None-for-all,
        # which we never do; the cast keeps the return type honest.
        if isinstance(frame, dict):  # pragma: no cover - defensive
            frame = next(iter(frame.values()))
        return frame
    return pd.read_csv(path)


def read_source(
    raw_dir: Path, stem: str, sheet_name: str | None = None
) -> pd.DataFrame:
    """Read ``<stem>`` from ``raw_dir`` whatever extension it was saved with.

    A CSV wins over a workbook when both exist, so a freshly re-scraped
    ``<stem>.csv`` can be dropped next to the old ``.xlsx`` and be picked up
    without touching any code.
    """
    for suffix in (".csv", ".xlsx", ".xls"):
        candidate = raw_dir / f"{stem}{suffix}"
        if candidate.exists():
            return read_table(candidate, sheet_name=sheet_name)
    raise FileNotFoundError(f"No .csv/.xlsx source named {stem!r} in {raw_dir}")


def write_table(frame: pd.DataFrame, path: Path) -> None:
    """Write a processed table as UTF-8 CSV with stable, platform-free newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
def _repair_once(text: str) -> str | None:
    """One Latin-1 -> UTF-8 round trip, or None if the text cannot survive it."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def fix_mojibake(value: str, max_passes: int = 3) -> str:
    """Repair text that was decoded as Latin-1 after being encoded as UTF-8.

    ``"Nikola JokiÄ\\x87"`` is what you get when UTF-8 bytes are read as
    Latin-1; encoding back to Latin-1 and decoding as UTF-8 restores
    ``"Nikola Jokić"``. Text that is already correct cannot survive the
    round-trip (it raises), so it is returned untouched - the function is
    safe to run twice.

    Non-breaking spaces need care, and the order below is load-bearing.
    A ``\\xa0`` is valid Latin-1 but is not a valid UTF-8 *start* byte, so
    a stray one - such as the ``\\xa0\\xa0(TW)`` two-way-contract marker on
    ``David Jones García`` - makes the decode of the whole string fail and
    the name comes back still mangled. Dropping them up front looks like
    the fix, but ``\\xa0`` is *also* the second byte of characters that are
    themselves mangled: ``Š`` is UTF-8 ``C5 A0``, so pre-stripping destroys
    ``Dario Šarić``. Hence: always try the string as written first, and
    only retry without the non-breaking spaces if that attempt fails.

    The repair repeats until the text stops changing, so text mangled more
    than once still comes out clean. Correct text fails on the first pass
    and exits, so repetition cannot over-correct it.
    """
    if not isinstance(value, str):
        return value
    text = value
    for _ in range(max_passes):
        repaired = _repair_once(text)
        if repaired is None:
            without_nbsp = text.replace("\xa0", " ")
            repaired = (
                _repair_once(without_nbsp) if without_nbsp != text else None
            )
        if repaired is None or repaired == text:
            break
        text = repaired
    return unicodedata.normalize("NFC", text)


def fix_mojibake_series(values: pd.Series) -> pd.Series:
    """Apply :func:`fix_mojibake` to every non-missing value of a Series."""
    return values.map(fix_mojibake, na_action="ignore")


def normalize_text(
    frame: pd.DataFrame, columns: Sequence[str] | None = None
) -> pd.DataFrame:
    """Trim and collapse whitespace in text columns (case is left alone).

    Scraped cells routinely carry newlines and doubled spaces from the HTML.
    Casing is deliberately preserved: identifiers are lower-cased explicitly
    with :func:`normalize_ids`, while human-readable names keep their real
    spelling.
    """
    result = frame.copy()
    targets = (
        list(columns)
        if columns is not None
        else [
            column
            for column in result.columns
            if pd.api.types.is_string_dtype(result[column])
            or result[column].dtype == object
        ]
    )
    for column in targets:
        cleaned = (
            result[column]
            .astype("string")
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
        )
        result[column] = cleaned.replace("", pd.NA)
    return result


def normalize_ids(values: pd.Series) -> pd.Series:
    """Lower-case and trim an identifier column so joins never miss on case.

    Basketball-Reference writes team codes upper-case on some pages
    (``OKC``) and lower-case in the player URLs; the database uses one form.
    """
    return values.astype("string").str.strip().str.lower()


#: How the source marks a traded player's combined season line. It has used
#: a blank cell and the literal "TOT" in the past, and now writes the team
#: count instead - "2TM", "3TM", "4TM". All of them mean the same thing.
_SEASON_TOTAL_TEAM = re.compile(r"^\d+tm$")


def to_team_id(values: pd.Series) -> pd.Series:
    """Normalise a team column, folding every "season total" spelling into
    :data:`TOTAL_TEAM_ID`.

    A traded player gets one combined row plus one row per team. The source
    has changed how it labels that combined row at least twice: it used to
    leave the cell blank, and now writes ``"2TM"``/``"3TM"``/``"4TM"``.
    Recognising only one spelling is quietly dangerous rather than loudly
    broken - the combined row stops being detected, so
    :func:`add_stint_columns` marks a player's *first partial stint* as his
    season line, and every traded player's totals come out too low. Matching
    the count pattern as well means a future "5TM" needs no code change.
    """
    ids = normalize_ids(values)
    is_total = (
        ids.isna()
        | (ids == TOTAL_TEAM_ID)
        | ids.str.fullmatch(_SEASON_TOTAL_TEAM).fillna(False)
    )
    return ids.mask(is_total, TOTAL_TEAM_ID)


# --------------------------------------------------------------------------
# Unit and season conversions (ported verbatim from the original script)
# --------------------------------------------------------------------------
def to_season_end_year(values: pd.Series) -> pd.Series:
    """Convert a Basketball-Reference season label to its ending year.

    ``"2024-25"`` -> ``2025``. A column that already holds the ending year as
    a number is passed straight through, so the helper is safe to apply to
    either style of source column.
    """
    if pd.api.types.is_numeric_dtype(values):
        return values.astype("Int64")
    labels = values.astype("string").str.strip()
    start_year = labels.str.split("-", expand=True)[0].astype("Int64")
    return start_year + 1


def to_season_label(end_years: pd.Series) -> pd.Series:
    """Inverse of :func:`to_season_end_year`: ``2025`` -> ``"2024-25"``."""
    end = end_years.astype("Int64")
    start = end - 1
    return (
        start.astype("string")
        + "-"
        + end.astype("string").str.slice(-2)
    )


def height_to_cm(values: pd.Series) -> pd.Series:
    """Convert Basketball-Reference heights (``"6-5"`` = 6ft 5in) to centimetres."""
    parts = values.astype("string").str.strip().str.split("-", expand=True)
    feet = pd.to_numeric(parts[0], errors="coerce")
    inches = pd.to_numeric(parts[1], errors="coerce") if parts.shape[1] > 1 else 0.0
    return (feet * _INCHES_PER_FOOT_CM + inches * _INCH_CM).round(1)


def weight_to_kg(values: pd.Series) -> pd.Series:
    """Convert weights in pounds to kilograms using the exact conversion factor."""
    return (pd.to_numeric(values, errors="coerce") * _POUND_KG).round(1)


# --------------------------------------------------------------------------
# Position helpers
# --------------------------------------------------------------------------
def split_positions(value: str) -> list[str]:
    """Split a bio position string into real positions, dropping empty slots.

    The scraped string sometimes contains an empty comma-separated token,
    e.g. Paul George is ``"Small Forward, Power Forward, , Shooting Guard"``.
    Splitting into fixed slots without removing that token pushes his third
    position into the fourth slot, which is why the empty tokens are dropped
    *before* anything is numbered.
    """
    if not isinstance(value, str):
        return []
    tokens = (token.strip() for token in value.split(","))
    return [token for token in tokens if token]


def position_code(name: str) -> str:
    """Map a spelled-out position to its two-letter code, or pass it through."""
    if not isinstance(name, str):
        return name
    return POSITION_CODES.get(name.strip().lower(), name.strip())


def parse_shooting_hand(value: str) -> str | None:
    """Derive the shooting hand from the raw ``Shoots`` cell.

    The scraper occasionally captured the label and both hands
    (``"\\n  Shoots:\\n  \\nRight Left"`` for genuinely both-handed players)
    or, on one profile, an entire bio paragraph where the selector missed.
    One rule covers all of it: look for the words *Right* and *Left*.
    Both present -> ``"both"``, exactly one -> that hand, neither -> missing.
    """
    if not isinstance(value, str):
        return None
    has_right = re.search(r"\bright\b", value, flags=re.IGNORECASE) is not None
    has_left = re.search(r"\bleft\b", value, flags=re.IGNORECASE) is not None
    if has_right and has_left:
        return "both"
    if has_right:
        return "right"
    if has_left:
        return "left"
    return None


# --------------------------------------------------------------------------
# Row-level rules shared by the per-season player tables
# --------------------------------------------------------------------------
def drop_league_average_rows(
    frame: pd.DataFrame, player_id_column: str
) -> tuple[pd.DataFrame, int]:
    """Remove Basketball-Reference's "League Average" summary line.

    Every season table ends with a league-average row. It has no player URL,
    so its ``player_id`` is blank while a few percentage columns are filled.
    Left in place it becomes a fake player once missing values are filled,
    so it is removed before anything else touches the frame.

    Returns the trimmed frame and how many rows were removed.
    """
    ids = frame[player_id_column].astype("string").str.strip()
    keep = ids.notna() & (ids != "")
    return frame.loc[keep].copy(), int((~keep).sum())


def add_stint_columns(
    frame: pd.DataFrame,
    season_column: str,
    player_column: str,
    team_column: str,
) -> pd.DataFrame:
    """Label a traded player's season-total row and his per-team rows.

    Basketball-Reference gives a traded player one combined row (team
    ``"tot"``) plus one row per team he played for. All of them are real and
    all are kept:

    * ``stint`` - ``0`` on the combined season-total row, ``1..n`` on the
      per-team rows in the order the source lists them. A player who stayed
      put has a single row with ``stint = 1``.
    * ``is_primary`` - ``True`` on exactly one row per player-season: the
      combined row when there is one, otherwise the player's only row.
      Filtering on it gives one row per player per season without throwing
      the per-team detail away.
    """
    result = frame.copy()
    is_total = result[team_column] == TOTAL_TEAM_ID
    keys = [season_column, player_column]

    per_team_order = (
        result.loc[~is_total].groupby(keys, dropna=False).cumcount() + 1
    )
    result["stint"] = (
        per_team_order.reindex(result.index).fillna(0).astype("int64")
    )

    has_total = is_total.groupby([result[key] for key in keys]).transform("any")
    result["is_primary"] = is_total | (~has_total & (result["stint"] == 1))
    return result
