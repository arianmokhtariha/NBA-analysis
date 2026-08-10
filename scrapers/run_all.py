"""Run every scraper in dependency order.

`player_bios` depends on `team_season_rosters` having already run (it
reads player ids from data/raw/team_season_rosters.csv by default), so
it's kept last. Every other step is independent.

It is also by far the longest step: one page per player, several
hundred to over a thousand of them, throttled a few seconds apart. The
other nine steps together are a couple of hundred requests. If a run
has to be split, split it there.

`player_bios` writes *two* files - player_bios.csv and
player_career_stats.csv - because both come from the same player page
and one fetch fills both. That is why there is no separate
`player_career_stats` step here; running `scrapers.player_career_stats`
directly would re-download every page for data this step already has.

Usage (always from the repo root, so the `scrapers` package resolves):

    conda run -n analyst_313 python -m scrapers.run_all
    conda run -n analyst_313 python -m scrapers.run_all \
        --only player_stats,advanced_stats
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable

from scrapers import (
    advanced_stats,
    mvp_candidates,
    mvp_winners,
    player_bios,
    player_stats,
    season_summaries,
    team_season_rosters,
    team_season_totals,
    team_seasons,
    teams,
)

logger = logging.getLogger(__name__)

STEPS: dict[str, Callable[[], None]] = {
    "teams": teams.main,
    "team_seasons": team_seasons.main,
    "team_season_rosters": team_season_rosters.main,
    "team_season_totals": team_season_totals.main,
    "player_stats": player_stats.main,
    "advanced_stats": advanced_stats.main,
    "mvp_candidates": mvp_candidates.main,
    "mvp_winners": mvp_winners.main,
    "season_summaries": season_summaries.main,
    "player_bios": player_bios.main,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "Comma-separated subset of steps to run, e.g. "
            "'player_stats,advanced_stats'. Default: run everything, "
            f"in this order: {', '.join(STEPS)}."
        ),
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()

    steps = list(STEPS)
    if args.only:
        requested = [name.strip() for name in args.only.split(",")]
        unknown = [name for name in requested if name not in STEPS]
        if unknown:
            raise SystemExit(f"Unknown step(s): {unknown}. Valid: {list(STEPS)}")
        steps = requested

    for name in steps:
        logger.info("=== %s ===", name)
        STEPS[name]()


if __name__ == "__main__":
    main()
