"""Settings shared by every scraper.

The season window lived as three identical copies of ``range(2019, 2027)``
in ``player_stats``, ``advanced_stats`` and ``mvp_candidates``. Widening
the analysis meant editing each one and hoping none was missed - and the
roster scraper needs the same window, which would have made four. It is
one constant here instead; every module imports it, so the name still
resolves as e.g. ``player_stats.DEFAULT_SEASON_YEARS``.
"""

from __future__ import annotations

#: Seasons the Phase 3 analysis covers, keyed the way basketball-reference
#: keys them: by the calendar year a season *ends* in. So 2019 is the
#: 2018-19 season and the range stops at 2026, the 2025-26 season.
DEFAULT_SEASON_YEARS: range = range(2019, 2027)
