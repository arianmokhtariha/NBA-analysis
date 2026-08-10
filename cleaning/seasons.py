"""Build the season dimension and the season award summary.

Outputs
-------
``data/processed/seasons.csv``
    One row per season referenced anywhere in the database (1947-2026), so
    that every fact table's ``season`` column has something to point at.
``data/processed/season_awards.csv``
    The league summary line per season and league: champion, Rookie of the
    Year and the season leaders.

Two deliberate changes from the old ``season_stats.csv``:

* the ``mvp`` column is gone. It held an abbreviated display name
  (``"n. jokić"``) that cannot be joined to anything, and the structured
  ``mvp_winners`` table already carries the same fact with a real
  ``player_id``.
* ``champion_name`` (a name pointing at a non-key column) is replaced by
  ``champion_team_id``, resolved against the team dimension.

The remaining award columns stay as free text on purpose: the source only
gives an abbreviated name, which is display material, not a key.
"""

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    BuildResult,
    TableReport,
    fix_mojibake_series,
    normalize_ids,
    normalize_text,
    read_source,
    to_season_end_year,
    to_season_label,
    write_table,
)
from cleaning.rosters import build_team_name_lookup

#: Ported verbatim from ``01_data_cleaning_anoosha.py``.
SEASON_COLUMN_MAP: dict[str, str] = {
    "season year": "season",
    "league": "league",
    "champion name": "champion_name",
    "mvp": "mvp",
    "rookie of the year": "rookie_of_the_year",
    "most points": "most_points",
    "most rebounds": "most_rebounds",
    "most assists": "most_assists",
    "most winshares": "most_winshares",
}

AWARD_OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "league",
    "champion_team_id",
    "rookie_of_the_year",
    "most_points",
    "most_rebounds",
    "most_assists",
    "most_winshares",
)


def build_seasons(
    raw_dir: Path = RAW_DIR,
    referenced_seasons: Iterable[int] | None = None,
    champion_lookup: pd.DataFrame | None = None,
) -> BuildResult:
    """Build ``seasons`` and ``season_awards``.

    Parameters
    ----------
    raw_dir:
        Folder holding the immutable scraped files.
    referenced_seasons:
        Every ``season`` used by a fact table. The dimension is their union
        with the award summary, which is what lets rosters keep their full
        1947-2026 history instead of being cut back to the award years.
    champion_lookup:
        ``(season, team_id, team_name)``. The champion is stored by name in
        the source, and a bare name is ambiguous across franchise history
        ("Indiana Pacers" is both the ABA ``ina`` and the NBA ``ind``), so
        the merge is done on season *and* name, which is unique.
    """
    raw = read_source(raw_dir, "season_summaries", sheet_name="seasons_table")
    rows_in = len(raw)

    awards = raw.copy()
    awards.columns = awards.columns.str.strip().str.lower()
    awards = awards.rename(columns=SEASON_COLUMN_MAP)
    awards = normalize_text(awards)
    for column in ("champion_name", "rookie_of_the_year", "most_points",
                   "most_rebounds", "most_assists", "most_winshares"):
        awards[column] = fix_mojibake_series(awards[column])
    awards["season"] = to_season_end_year(awards["season"])
    awards["league"] = awards["league"].astype("string").str.upper()

    if champion_lookup is None:
        champion_lookup = build_team_name_lookup(raw_dir)
    lookup = (
        champion_lookup.rename(
            columns={"team_name": "champion_name", "team_id": "champion_team_id"}
        )[["season", "champion_name", "champion_team_id"]]
        .drop_duplicates()
    )
    awards = awards.merge(lookup, on=["season", "champion_name"], how="left")
    awards["champion_team_id"] = normalize_ids(awards["champion_team_id"])

    unresolved = int(awards["champion_team_id"].isna().sum())
    awards = (
        awards[list(AWARD_OUTPUT_COLUMNS)]
        .sort_values(["season", "league"])
        .reset_index(drop=True)
    )

    seasons = _build_dimension(awards, referenced_seasons)

    reports = [
        TableReport(
            table="season_awards",
            rows_in=rows_in,
            rows_out=len(awards),
            reason=(
                "no rows dropped; 'mvp' column removed as unjoinable free "
                "text (see mvp_winners), champion_name replaced by "
                f"champion_team_id ({unresolved} unresolved)"
            ),
        ),
        TableReport(
            table="seasons",
            rows_in=len(awards),
            rows_out=len(seasons),
            reason=(
                "one row per season referenced anywhere, so roster and team "
                "history before the award years keeps a valid foreign key"
            ),
        ),
    ]
    return BuildResult(
        tables={"seasons": seasons, "season_awards": awards}, reports=reports
    )


def _build_dimension(
    awards: pd.DataFrame, referenced_seasons: Iterable[int] | None
) -> pd.DataFrame:
    """Assemble the complete season lookup."""
    universe = {int(value) for value in awards["season"].dropna()}
    if referenced_seasons is not None:
        universe |= {int(value) for value in referenced_seasons if pd.notna(value)}

    seasons = pd.DataFrame({"season": sorted(universe)})
    seasons["season_label"] = to_season_label(seasons["season"])
    seasons["start_year"] = seasons["season"] - 1
    seasons["has_awards"] = seasons["season"].isin(set(awards["season"]))
    return seasons


def main() -> None:
    """Build the season tables standalone and write them to ``data/processed``."""
    result = build_seasons()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
