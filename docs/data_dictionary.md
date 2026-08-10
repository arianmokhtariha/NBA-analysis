# Data dictionary: the `analyst_ready` schema

This document covers the **13 relations** in the PostgreSQL `analyst_ready`
schema — the tables and views a notebook actually queries to answer one of
the project's questions. It does not repeat the underlying `processed`
schema (the cleaned Basketball-Reference data); that is fully documented in
[`schema.md`](schema.md), and every `analyst_ready` relation is ultimately
built from it — see `sql/analyst_ready/*.sql` for the exact SQL.

Built by `python rebuild.py`, which runs `sql/analyst_ready/*.sql` in order.
It is fast (seconds) and safe to re-run at any time: it never touches
`processed`, only rebuilds `analyst_ready` from scratch each time.

Column types and row counts below were read directly from the live database
(`information_schema.columns` and `count(*)` on each relation), then checked
against the SQL that creates them.

---

## Conventions that bite

These apply across the whole schema and are easy to trip over if you don't
know them going in.

1. **`season` is the ending year.** The 2023-24 season is stored as `2024`.
   Every table that has a `season` column follows this rule; `season_label`
   gives you the readable form (`'2023-24'`) when you need to print it.

2. **A player-season is already de-duplicated.** `player_season` — the base
   table every mart is built from — keeps exactly one row per player per
   season, even for a player who was traded mid-season. This corresponds to
   `is_primary = true` in the underlying `processed.player_season_stats`
   table: the combined season-total row where a trade happened, otherwise
   the player's only row. If you need the *per-club* rows for a traded
   player (`stint` 1, 2, ...), go to `processed.player_season_stats`
   directly — `analyst_ready` does not carry the split-by-team rows.

3. **Percentage scales are not consistent between columns.** Some
   percentages are stored as a 0-1 fraction (e.g. `field_goal_pct`,
   `true_shooting_percentage`), others as a 0-100 number (e.g.
   `usage_percentage`, the `avg_*_pct` columns in the draft-picks mart).
   This is inherited from the two different Basketball-Reference pages the
   numbers come from, and it is **not** harmonised — the column comments
   below say which scale each one uses. Plotting two percentage columns on
   one axis without checking this first is the most common way to get a
   chart that is silently wrong by a factor of 100.

4. **`effective_fg_pct` and `true_shooting_percentage` can exceed 1.0**
   (i.e. more than "100%"). Both are *weighted* efficiency measures — a
   three-pointer counts for more than a two-pointer — not a simple make/miss
   ratio, so there is no mathematical ceiling at 1.0. This is expected, not
   a data error.

5. **814 of the 1,989 players have no bio data.** `dim_player.has_bio` (and
   the same flag wherever it's carried downstream) is `false` for players
   who are referenced by a roster or an MVP award but were never scraped
   from their own bio page — so they have no height, weight, or draft
   information anywhere in this schema. Michael Jordan is one of them: his
   five MVP awards are on record, but every bio column for him is `NULL`.
   None of the 814 reach an MVP ballot or a top-50 scoring finish in the
   2019-20–2023-24 window this project studies, so the descriptive-stats
   marts (D1, D2) are not missing anyone's height because of this — but any
   query that filters or averages by height should check `has_bio` first.

6. **`points_rank` (called `rank` in `processed`) is a scoring rank, not a
   league standing.** Wherever this project defines "the top N players (or
   teams) of a season," it means ranked by total points scored — because
   that is the order Basketball-Reference's own season pages use, and
   because the underlying data has no wins/losses column at all. A
   statement like "team four factors that go with a stronger season" is
   really "... that go with scoring more," and should be presented that
   way.

---

## The 13 relations, at a glance

| Relation | Kind | Rows | Grain — one row is... | Answers |
| --- | --- | ---: | --- | --- |
| `dim_player` | view | 1,989 | one player | (shared dimension) |
| `dim_team` | view | 75 | one franchise | (shared dimension) |
| `dim_season` | view | 80 | one season | (shared dimension) |
| `player_season` | table | 3,884 | one player-season, 2018-19 to 2024-25 | (shared base fact for every mart below) |
| `d1_height_sample` | table | 311 | one player, in one season, in one group | **D1** — height: MVP ballot vs. top-50 scorers |
| `d2_champion_vs_top15` | table | 68 | one player, in one season, in one group | **D2** — champion roster vs. top-15 scorers: height & experience |
| `d3_point_guard_candidates` | table | 13 | one point guard | **D3** — which point guard should the club buy? |
| `h1_agility` | table | 80 | one player, in one season | **H1** — has the "agility" of the top 20 players increased? |
| `h2_innate_ability` | table | 73 | one champion-roster player, in one season | **H2** — has champion teams' "innate ability" increased? |
| `bonus_availability` | table | 3,884 | one player-season | **Bonus** — how much of the season do MVP-calibre players actually play? |
| `bonus_superstar_tax` | table | 70 | one player-season | **Bonus** — does shooting efficiency fall as usage rises? |
| `bonus_team_four_factors` | table | 210 | one team-season | **Bonus** — Dean Oliver's "four factors," rebuilt from team totals |
| `bonus_draft_picks` | table | 188 | one player | **Bonus** — are picks 1-5 measurably better than picks 6-10? |

"D1-D3" are the three assigned descriptive-statistics questions; "H1-H2"
are the two assigned hypothesis tests. The four "Bonus" marts are additional
analyses the team chose to add, beyond what was assigned.

Every mart carries `has_bio`, `height_cm` or similar columns straight
through from `dim_player`/`player_season` rather than re-deriving them, so
joining marts back to each other on `player_id` and `season` is always
safe.

---

## Shared dimensions

### `dim_player` — one row per player (1,989 rows)

A view over `processed.players`, renamed for readability, plus one derived
column. Not itself an answer to a question — every mart below pulls a
player's bio attributes from here.

| Column | Type | Meaning |
| --- | --- | --- |
| `player_id` | varchar(12) | Basketball-Reference's player code (e.g. `jordami01`). |
| `player_name` | text | Player's name. |
| `has_bio` | boolean | See convention 5 above. `false` for 814 of 1,989 players; every column below is `NULL` for them. |
| `primary_position` | varchar(2) | Career-level position: `PG`/`SG`/`SF`/`PF`/`C`. |
| `shoots` | varchar(8) | `right`, `left`, or `both`. |
| `height_cm` | numeric(5,1) | Height in centimetres. |
| `weight_kg` | numeric(5,1) | Weight in kilograms. |
| `height_to_weight` | numeric | `height_cm ÷ weight_kg`, rounded to 4 decimals. This project's stand-in for "agility" (Hypothesis 1): a higher number means more height per kilogram, i.e. a leaner build. Roughly 2.2 for a guard, 1.9 for a centre. `NULL` if either half is missing. |
| `birth_date` | date | Date of birth. |
| `birth_year` | integer | Year of birth. |
| `college` | text | `NULL` for the 169 players (with a bio) who never attended one. |
| `career_experience_seasons` | integer | Total NBA seasons of experience **as of the scrape** — a career snapshot, not a per-season figure. For "how experienced was this player *during* season X," use `player_season.experience_seasons` instead. |
| `nba_debut_year` | integer | Year of first NBA game. |
| `draft_year` | integer | Draft class. |
| `draft_round` | integer | `NULL` for undrafted players. |
| `draft_overall_pick` | integer | Overall pick number. This defines "top-10 pick" in the bonus draft-picks mart. |
| `draft_team_name` | text | Drafting club, as free text (not a `team_id` key). |
| `career_games` | integer | Career games played, where the source records it. |
| `career_points_per_game` | numeric(5,1) | Career points **per game** (not a total). |
| `career_per` | numeric(5,1) | Career Player Efficiency Rating (PER) — a per-minute production score where 15.0 is league average. |
| `career_win_shares` | numeric(5,1) | Career total Win Shares — a cumulative estimate of wins the player has been worth. |

### `dim_team` — one row per franchise (75 rows)

A thin view over `processed.teams`.

| Column | Type | Meaning |
| --- | --- | --- |
| `team_id` | varchar(4) | Basketball-Reference's 3-letter club code, e.g. `bos`. |
| `team_name` | text | Club name as the source writes it. |
| `is_aggregate` | boolean | `true` only for `tot`, the pseudo-team used for a traded player's combined season line. **Not a real club** — exclude it before counting anything per franchise. |
| `has_detail` | boolean | `true` when the team has season-level stats on file (68 of 75 do). |

### `dim_season` — one row per season (80 rows, 1946-47 through 2025-26)

A view over `processed.seasons`, joined out to that season's NBA champion
and MVP.

| Column | Type | Meaning |
| --- | --- | --- |
| `season` | integer | Ending year — `2025` means the 2024-25 season. |
| `season_label` | varchar(8) | Readable form, `'2024-25'`. |
| `start_year` | integer | Always `season - 1`. |
| `champion_team_id` | varchar(4) | That season's **NBA** champion. `NULL` for a handful of very early seasons with no recorded champion. |
| `champion_team_name` | text | Same, as a name. |
| `mvp_player_id` | varchar(12) | That season's MVP. `NULL` before the award existed (pre-1955-56) or for a season not yet decided. |
| `mvp_player_name` | text | Same, as a name. |
| `scheduled_games` | integer | The longest regular-season schedule any team played that year — 82 in a normal season, 72 in 2020-21 and 75 in 2019-20 (both COVID-shortened). `NULL` for the not-yet-played 2025-26 season. |
| `has_been_played` | boolean | `true` once `scheduled_games` is known. |

---

## `player_season` — the shared base fact (3,884 rows)

**Grain: one row per player per season, seasons 2018-19 through 2024-25.**
Not itself the answer to a question — it is the single wide table every
mart below is a filter or aggregate of. It already resolves the
traded-player duplication described in convention 2 above: a player traded
mid-season appears once, with his combined season line.

**Keys and context**

| Column | Type | Meaning |
| --- | --- | --- |
| `season`, `season_label` | integer, varchar(8) | See convention 1. |
| `player_id`, `player_name` | varchar(12), text | |
| `team_id`, `team_name` | varchar(4), text | The player's club that season, or `tot` (see `is_multi_team_season`). |
| `is_multi_team_season` | boolean | `true` when this is a traded player's combined line (`team_id = 'tot'`). |
| `is_on_champion_team` | boolean | `true` when the player finished the season on that year's NBA champion. |

**Who the player was that season**

| Column | Type | Meaning |
| --- | --- | --- |
| `age` | integer | Age **during** that season — not a current age. This is what makes a fair past-vs-recent comparison possible. |
| `position` | varchar(2) | Position actually played that season (box-score page). |
| `primary_position` | varchar(2) | Career-level position (bio page) — may differ from `position`. |
| `points_rank` | integer | Scoring-volume rank that season (see convention 6). This is how the project defines "top 15," "top 20," "top 50" throughout. |

**Playing time and availability**

| Column | Type | Meaning |
| --- | --- | --- |
| `games_played`, `games_started`, `minutes_played` | integer | Season totals. |
| `team_games` | integer | Games the player's club played that season; for a traded player, the league's full schedule length instead (see `games_basis`). |
| `games_basis` | text | `'own_team'` or `'league_schedule'` — which denominator `team_games` uses. |
| `availability` | numeric | `games_played ÷ team_games`, rounded to 4 decimals. `1.0` = never missed a game. Two rows across the whole window sit a shade above 1.0 (Mikal Bridges, 2022-23; Buddy Hield, 2023-24) — both were traded between clubs that had played a different number of games at that point, which is genuine, not an error. |

**Box score (season totals) and per-game**

| Column | Type | Meaning |
| --- | --- | --- |
| `points`, `total_rebounds`, `assists`, `steals`, `blocks`, `turnovers`, `triple_doubles` | integer | Season totals. |
| `points_per_game`, `rebounds_per_game`, `assists_per_game`, `minutes_per_game` | numeric | Same, divided by `games_played`, rounded to 2 decimals. |

**Shooting — 0-1 fractions**

| Column | Type | Meaning |
| --- | --- | --- |
| `field_goal_pct`, `three_point_pct`, `free_throw_pct` | numeric(5,3) | `NULL` when the player attempted none of that shot type, not `0`. |
| `effective_fg_pct` | numeric(5,3) | Field-goal % weighted for a three being worth more than a two. **Can exceed 1.0** (convention 4). |

**Advanced metrics** — the `*_percentage` columns are **0-100**, everything else is as noted

| Column | Type | Meaning |
| --- | --- | --- |
| `player_efficiency_rate` | numeric(5,1) | PER — per-minute production; 15.0 is league average. |
| `true_shooting_percentage` | numeric(5,3) | TS% — shooting efficiency counting 2s, 3s and free throws. A 0-1 fraction; **can exceed 1.0**. |
| `usage_percentage` | numeric(5,1) | USG% — share of team possessions the player used while on court, 0-100. |
| `total_rebound_percentage`, `assist_percentage`, `steal_percentage`, `block_percentage` | numeric(5,1) | Share of the available rebounds/assists/steals/blocks the player collected, 0-100. |
| `turnover_percentage` | numeric(5,1) | Turnovers per 100 plays the player used. |
| `win_shares` | numeric(5,1) | Estimated wins the player was worth that season. |
| `win_shares_per_48_minutes` | numeric(5,3) | Win Shares normalised for playing time. |
| `offensive_box_plus_minus`, `defensive_box_plus_minus`, `box_plus_minus` | numeric(5,1) | Points per 100 possessions above a league-average player — offence, defence, and combined. |
| `value_over_replacement_player` | numeric(5,1) | VORP — total contribution above a bench-level ("replacement") player, over the season. |

**Bio attributes — `NULL` for the 814 players with `has_bio = false`**

| Column | Type | Meaning |
| --- | --- | --- |
| `has_bio`, `height_cm`, `weight_kg`, `height_to_weight` | | As in `dim_player`. |
| `college`, `draft_year`, `draft_round`, `draft_overall_pick` | | As in `dim_player`. |
| `career_experience_seasons` | integer | Career snapshot, as in `dim_player` — not per-season. |
| `experience_seasons` | integer | Seasons of experience **before** this one; `0` = rookie year. Rolled back from the career figure. `NULL` for 603 of the 3,884 rows, where the bio page never recorded an experience figure at all — nothing is invented to fill it. |

---

## D1 — `d1_height_sample`: height on the MVP ballot vs. the top 50 scorers

**Grain: one row per player, per season, per group. 311 rows** — 61 MVP
ballot places plus 5 seasons × 50 scorers, seasons 2019-20 through 2023-24.
A player can legitimately appear once in each group (most MVP candidates
are also top-50 scorers); never twice within one group.

| Column | Type | Meaning |
| --- | --- | --- |
| `group_label` | text | `'mvp_candidates'` or `'top_50'`. |
| `season`, `season_label` | integer, varchar(8) | |
| `player_id`, `player_name` | varchar(12), text | |
| `height_cm`, `weight_kg` | numeric(5,1) | |
| `has_bio` | boolean | All 311 rows here have a height — none of the 814 bio-less players reach this list. |
| `position` | varchar(2) | |
| `mvp_rank` | integer | Ballot position, for `mvp_candidates` rows. `NULL` on `top_50` rows for a player who wasn't also on the ballot that year. |
| `points_rank` | integer | Scoring rank that season. |
| `points_per_game` | numeric | |

---

## D2 — `d2_champion_vs_top15`: champion roster vs. top-15 scorers

**Grain: one row per player, per season, per group. 68 rows** — 19+19
champion-roster players and 15+15 top scorers, across the two most recent
seasons with a champion (2023-24 and 2024-25).

| Column | Type | Meaning |
| --- | --- | --- |
| `group_label` | text | `'champion_team'` or `'top_15'`. |
| `season`, `season_label` | integer, varchar(8) | |
| `team_id`, `team_name` | varchar(4), text | The champion, for `champion_team` rows; the player's own club, for `top_15` rows. |
| `player_id`, `player_name` | varchar(12), text | |
| `height_cm` | numeric(5,1) | All 68 rows have one. |
| `has_bio` | boolean | |
| `experience_seasons` | integer | Seasons before this one. |
| `experience_source` | text | `'roster_page'` (the authoritative per-season figure, used for `champion_team` rows) or `'career_rolled_back'` (derived, used for `top_15` rows). The two methods agree exactly wherever they overlap, which is what licenses comparing them. |
| `age` | integer | During that season. |
| `position` | varchar(2) | |
| `games_played` | integer | |
| `points_rank` | integer | |

---

## D3 — `d3_point_guard_candidates`: the point-guard shortlist

**Grain: one row per point guard. 13 rows** — every point guard who
received at least one MVP vote, seasons 2019-20 through 2023-24, ranked as
a buy recommendation.

| Column | Type | Meaning |
| --- | --- | --- |
| `player_id`, `player_name` | varchar(12), text | |
| `mvp_appearances` | bigint | Number of seasons this player appeared on the MVP ballot **while listed at PG**. This is the club's stated "ability metric." |
| `avg_mvp_rank` | numeric | Mean ballot position across those seasons (lower is better), rounded to 2 decimals — the tie-breaker. |
| `best_mvp_rank` | integer | Best single-season ballot position. |
| `first_season`, `last_season` | integer | |
| `seasons_listed` | text | Comma-separated season labels the player appeared in. |
| `avg_points_per_game`, `avg_assists_per_game` | numeric | Averaged across the qualifying seasons. |
| `most_recent_team_name` | text | Club he was with in the most recent qualifying season — context, not part of the ranking. |
| `recommendation_rank` | bigint | `1` = top recommendation. Ordered by `mvp_appearances` (desc), then `avg_mvp_rank` (asc), then name. |
| `is_recommended` | boolean | `true` for the top 3 — the club asked for three names. |

---

## H1 — `h1_agility`: has the top 20's agility increased?

**Grain: one row per player, per season. 80 rows** — the 20 highest scorers
in each of four seasons.

| Column | Type | Meaning |
| --- | --- | --- |
| `group_label` | text | `'past'` (2020-21, 2021-22) or `'recent'` (2022-23, 2023-24) — the two periods the hypothesis compares. |
| `season`, `season_label` | integer, varchar(8) | |
| `player_id`, `player_name` | varchar(12), text | |
| `has_bio` | boolean | All 80 rows have both height and weight. |
| `points_rank` | integer | `<= 20` by construction. |
| `position` | varchar(2) | |
| `height_cm`, `weight_kg` | numeric(5,1) | |
| `agility` | numeric | `height_cm ÷ weight_kg`, rounded to 4 decimals — the hypothesis's own definition of "agility." Higher means leaner (more height per kilogram). |
| `age` | integer | |

---

## H2 — `h2_innate_ability`: has champion rosters' innate ability increased?

**Grain: one row per champion-roster player, per season. 73 rows** — the
four most recent champion rosters (Golden State 2021-22, Denver 2022-23,
Boston 2023-24, Oklahoma City 2024-25).

| Column | Type | Meaning |
| --- | --- | --- |
| `group_label` | text | `'past'` (2021-22, 2022-23) or `'recent'` (2023-24, 2024-25). |
| `season`, `season_label` | integer, varchar(8) | |
| `team_id`, `team_name` | varchar(4), text | The champion that season. |
| `player_id`, `player_name` | varchar(12), text | |
| `experience_seasons` | integer | Seasons before this one, from the roster page. |
| `age` | integer | During that season. |
| `innate_ability` | numeric | `experience_seasons ÷ age`, rounded to 4 decimals — the hypothesis's definition. Rewards a player who reached the league young and stayed: a 22-year-old with 4 seasons behind him scores 0.18; a 34-year-old with 12 scores 0.35. |
| `position`, `games_played`, `minutes_played`, `height_cm` | | Context columns; height is not part of this hypothesis. |

---

## Bonus — `bonus_availability`: how much of the season do MVP-calibre players play?

**Grain: one row per player-season. 3,884 rows** — every player-season in
the window, not only MVP-honoured ones, so the honoured players can be
compared against the league they came from.

| Column | Type | Meaning |
| --- | --- | --- |
| `season`, `season_label`, `player_id`, `player_name`, `team_id`, `team_name` | | As in `player_season`. |
| `is_multi_team_season` | boolean | |
| `games_played`, `team_games`, `games_basis`, `availability` | | As in `player_season`. |
| `minutes_played`, `minutes_per_game` | | |
| `points_rank` | integer | |
| `is_mvp_candidate` | boolean | On the MVP ballot that season. |
| `mvp_rank` | integer | Ballot position, where applicable. |
| `is_mvp_winner` | boolean | Won MVP that season. |
| `mvp_group` | text | `'mvp_winner'`, `'mvp_candidate'`, or `'other'` — one label per row (the winner is also a candidate, so this picks the higher honour), for charts that need exactly one category. |

---

## Bonus — `bonus_superstar_tax`: does efficiency fall as usage rises?

**Grain: one row per player-season. 70 rows** — the top 10 scorers in each
of the 7 seasons, all with at least 1,000 minutes played.

| Column | Type | Meaning |
| --- | --- | --- |
| `season`, `season_label`, `player_id`, `player_name`, `team_id`, `team_name`, `position` | | |
| `points_rank` | integer | `<= 10` by construction. |
| `minutes_played`, `points`, `points_per_game` | | |
| `usage_percentage` | numeric(5,1) | 0-100, as stored. |
| `true_shooting_percentage` | numeric(5,3) | 0-1 fraction, as stored; can exceed 1.0. |
| `true_shooting_pct` | numeric | The same figure × 100, rounded to 1 decimal, so it can share a chart axis with `usage_percentage`. Both are kept so the conversion is visible rather than assumed. |
| `player_efficiency_rate`, `win_shares`, `box_plus_minus` | | |

---

## Bonus — `bonus_team_four_factors`: Dean Oliver's four factors

**Grain: one team-season. 210 rows** — 30 clubs × seasons 2018-19 through
2024-25 (the unplayed 2025-26 season is excluded because the formulas below
would divide by zero).

| Column | Type | Meaning |
| --- | --- | --- |
| `season`, `season_label`, `team_id`, `team_name` | | |
| `points_rank` | integer | Scoring rank that season — **not a league standing** (convention 6). |
| `is_champion` | boolean | `true` for that season's NBA champion. |
| `games`, `points`, `points_per_game` | | |
| `effective_fg_pct` | numeric | `(FGM + 0.5 × 3PM) ÷ FGA × 100` — field-goal % crediting a three-pointer as 1.5 makes. |
| `estimated_possessions` | numeric | `FGA − ORB + TOV + 0.44 × FTA` — the standard approximation of possessions played, since the source gives no direct possession count. |
| `turnover_pct` | numeric | Turnovers per 100 estimated possessions. |
| `offensive_rebound_pct` | numeric | Share of the **team's own missed shots** recovered (`ORB ÷ (FGA − FGM) × 100`). |
| `free_throw_rate` | numeric | Free-throw attempts per 100 field-goal attempts — a proxy for how often the team draws fouls. |

---

## Bonus — `bonus_draft_picks`: are picks 1-5 better than picks 6-10?

**Grain: one row per player. 188 rows** — every player drafted 1st-10th
overall (by bio-page record) with at least one season of stats in this
database, 2018-19 through 2024-25. Undrafted players and picks outside the
top 10 are out of scope by construction; players with no scraped bio page
have no draft data and cannot be assessed. "Career" figures here mean
**totalled or averaged only over the seasons in this database**, not a full
career — `seasons_played` should always be read alongside them.

| Column | Type | Meaning |
| --- | --- | --- |
| `player_id`, `player_name` | varchar(12), text | |
| `draft_year`, `draft_overall_pick` | integer | |
| `pick_group` | text | `'picks_1_5'` or `'picks_6_10'` — the comparison this analysis tests. |
| `is_top5_pick` | boolean | Same split, as a flag. |
| `primary_position`, `height_cm`, `weight_kg` | | Career-level bio attributes. |
| `latest_age` | integer | Age in the player's most recent season in the data — the database stores no single "current age." |
| `latest_season`, `latest_team_name` | | |
| `career_experience_seasons` | integer | `NULL` for 49 of the 188, whose bio pages omit the field; no tier below depends on it. |
| `seasons_played`, `first_season` | | Seasons actually present in this database. |
| `triple_doubles` | bigint | Summed across those seasons. |
| `avg_player_efficiency_rate` | numeric | PER, averaged across seasons, rounded to 2 decimals. |
| `total_win_shares` | numeric | Summed across seasons. |
| `avg_total_rebound_pct`, `avg_assist_pct`, `avg_steal_pct`, `avg_block_pct`, `avg_usage_pct` | numeric | All 0-100, averaged across seasons. |
| `total_offensive_bpm`, `total_defensive_bpm` | numeric | Summed across seasons. `total_defensive_bpm` is the column the picks-1-5-vs-6-10 defensive comparison is run on — positive means points prevented above an average player, so higher is better. |
| `total_vorp` | numeric | Summed VORP across seasons. |
| `avg_points_per_game` | numeric | |
| `per_tier` | text | `'not_a_starter'` (avg PER ≤ 20), `'all-star_candidate'` (20-25), or `'mvp_candidate'` (> 25). |
| `vorp_tier` | text | `'high_vorp'` (total VORP ≥ 20) or `'low_vorp'`. |
| `defense_tier` | text | `'great'` (positive `total_defensive_bpm`), `'decent'` (zero), or `'bad'` (negative). Note the direction: a *positive* defensive box plus/minus is the good outcome. |
| `age_group` | text | `'30-40'` (`latest_age >= 30`) or `'20-30'`. |

---

*Generated against the live `nba_analysis` database. If this document and
the SQL in `sql/analyst_ready/` ever disagree, the SQL is what shipped —
see the comment above each `create table` statement there for the full
reasoning behind every definitional choice summarised here.*
