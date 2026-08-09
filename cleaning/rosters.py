"""Clean the team-season roster listings.

Output: ``data/processed/rosters.csv``.

What this table actually covers is worth knowing before using it: the
scrape collected the **champion team's roster for every season from 1946-47
onwards** (both the NBA and the ABA champion in the nine seasons the ABA
existed), plus the full 30-team rosters of the current 2025-26 season. It is
not a complete league-wide roster history.
"""

from pathlib import Path

import pandas as pd

from cleaning.normalize import (
    PROCESSED_DIR,
    RAW_DIR,
    BuildResult,
    TableReport,
    fix_mojibake_series,
    height_to_cm,
    normalize_ids,
    normalize_text,
    read_source,
    to_season_end_year,
    weight_to_kg,
    write_table,
)

ROSTER_COLUMN_MAP: dict[str, str] = {
    "teamname": "team_name",
    "season": "season",
    "playername": "player_name",
    "player_id": "player_id",
    "team_id": "team_id",
    "pos": "position",
    "ht": "height",
    "wt": "weight",
    "birth date": "birth_date",
    "birth": "birth_country",
    "exp": "experience_seasons",
    "college": "college",
}

OUTPUT_COLUMNS: tuple[str, ...] = (
    "season",
    "team_id",
    "player_id",
    "player_name",
    "roster_note",
    "position",
    "position_primary",
    "position_secondary",
    "height_cm",
    "weight_kg",
    "birth_date",
    "birth_country",
    "experience_seasons",
    "college",
)


def _prepare(raw_dir: Path) -> pd.DataFrame:
    """Read the roster file and apply the renames/season conversion."""
    rosters = read_source(raw_dir, "team_season_rosters").copy()
    rosters.columns = rosters.columns.str.strip().str.lower()
    rosters = rosters.rename(columns=ROSTER_COLUMN_MAP)
    rosters = normalize_text(rosters)
    rosters["season"] = to_season_end_year(rosters["season"])
    rosters["team_id"] = normalize_ids(rosters["team_id"])
    return rosters


def build_team_name_lookup(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Return ``(season, team_id, team_name)`` as listed on the roster pages.

    Two other tables need it: ``teams`` takes franchise names for the six ABA
    clubs that never appear in the team totals file, and ``season_awards``
    resolves its champion name to a real ``team_id`` through it.
    """
    rosters = _prepare(raw_dir)
    lookup = rosters[["season", "team_id", "team_name"]].dropna(
        subset=["team_id", "team_name"]
    )
    return lookup.drop_duplicates().reset_index(drop=True)


def build_rosters(raw_dir: Path = RAW_DIR) -> BuildResult:
    """Clean ``team_season_rosters`` into ``rosters``."""
    rosters = _prepare(raw_dir)
    rows_in = len(rosters)

    # Every team-season block on the source page ends with an empty trailing
    # row (a table footer the scraper picked up). It carries a team but no
    # player, so it cannot be a roster entry.
    empty_rows = int(rosters["player_id"].isna().sum())
    rosters = rosters.loc[rosters["player_id"].notna()].copy()

    rosters["player_id"] = normalize_ids(rosters["player_id"])
    rosters["player_name"] = fix_mojibake_series(rosters["player_name"])

    # Names carry a trailing annotation on the source page, e.g.
    # "Ulrich Chomche  (TW)" for a two-way contract. Keep it, but out of the
    # name so names can be matched.
    note = rosters["player_name"].astype("string").str.extract(r"\(([^)]*)\)\s*$")[0]
    rosters["roster_note"] = note
    rosters["player_name"] = (
        rosters["player_name"]
        .astype("string")
        .str.replace(r"\s*\([^)]*\)\s*$", "", regex=True)
        .str.strip()
    )

    position = rosters["position"].astype("string")
    split = position.str.split("-", expand=True)
    rosters["position_primary"] = split[0].str.strip()
    rosters["position_secondary"] = (
        split[1].str.strip() if split.shape[1] > 1 else pd.NA
    )

    rosters["height_cm"] = height_to_cm(rosters["height"])
    rosters["weight_kg"] = weight_to_kg(rosters["weight"])
    rosters["birth_date"] = pd.to_datetime(
        rosters["birth_date"].astype("string"),
        format="%B %d, %Y",
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")
    # "us US" -> "US": the flag code repeated as an ISO country code.
    rosters["birth_country"] = (
        rosters["birth_country"].astype("string").str.split().str[-1].str.upper()
    )
    # "R" marks a rookie, i.e. zero completed seasons.
    rosters["experience_seasons"] = pd.to_numeric(
        rosters["experience_seasons"].astype("string").str.strip().replace("R", "0"),
        errors="coerce",
    ).astype("Int64")

    rosters = (
        rosters[list(OUTPUT_COLUMNS)]
        .sort_values(["season", "team_id", "player_id"])
        .reset_index(drop=True)
    )

    report = TableReport(
        table="rosters",
        rows_in=rows_in,
        rows_out=len(rosters),
        reason=(
            f"dropped {empty_rows} empty trailing rows (team present, no "
            "player_id) - table-footer artefacts of the scrape"
        ),
    )
    return BuildResult(tables={"rosters": rosters}, reports=[report])


def main() -> None:
    """Build the table standalone and write it to ``data/processed``."""
    result = build_rosters()
    for name, table in result.tables.items():
        write_table(table, PROCESSED_DIR / f"{name}.csv")
    for report in result.reports:
        print(report)


if __name__ == "__main__":
    main()
