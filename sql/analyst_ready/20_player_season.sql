-- ============================================================================
-- analyst_ready.player_season — THE wide player-season fact table.
--
-- One join, written once. Box score, advanced metrics, bio, club and season
-- context in a single row, so an analysis starts from `select ... from
-- player_season where ...` instead of re-deriving the same five joins.
--
-- This table answers no question by itself. It is the enriched, de-duplicated
-- base that questions are asked OF — every filter, grouping and comparison
-- belongs in the query that asks, not here.
--
-- Grain: ONE ROW PER PLAYER PER SEASON, seasons 2018-19 through 2024-25
--        (3,884 rows).
--
-- How the grain is achieved: `player_season_stats` keeps every stint of a
-- traded player — a combined season total (stint 0, team_id 'tot') plus one row
-- per club. `is_primary` marks exactly the row to use for a per-player
-- question: the combined line where one exists, otherwise the player's only
-- line. Filtering on it here is what stops a traded player being counted twice
-- in every downstream mart. Anyone who genuinely needs the per-club splits
-- should go to `processed.player_season_stats` directly.
--
-- Two scales live side by side, and are NOT harmonised, because harmonising
-- them silently is how a chart ends up 100x wrong:
--   * shooting percentages (field_goal_pct, true_shooting_percentage, ...) are
--     0-1 fractions;
--   * advanced percentages (usage_percentage, assist_percentage, ...) are
--     0-100.
-- The column comments below say which is which. `effective_fg_pct` and
-- `true_shooting_percentage` can exceed 1.0 — they are weighted, not bounded.
--
-- Materialised as a table rather than a view: notebooks hit it repeatedly, and
-- the whole schema rebuilds in seconds anyway.
-- ============================================================================

create table analyst_ready.player_season as

-- The scrape's most recent season. Used only to roll the players table's
-- career "Experience" figure back to a per-season one, below. Read from the
-- data rather than hard-coded, so a future re-scrape does not silently break
-- the arithmetic.
with latest as (
    select max(season) as latest_season
    from processed.player_season_stats
)

select
    -- ── keys and context ────────────────────────────────────────────────
    box.season,
    ds.season_label,
    box.player_id,
    dp.player_name,
    box.team_id,
    dt.team_name,
    -- True when this row is a traded player's combined season line. The
    -- team_id is then the 'tot' pseudo-club, not a real franchise.
    dt.is_aggregate                                as is_multi_team_season,
    -- True when the player finished the season on the club that won the title.
    (box.team_id = ds.champion_team_id)            as is_on_champion_team,

    -- ── who the player was that season ──────────────────────────────────
    -- Age DURING this season, straight from the source page. This is the only
    -- correct age to use in a per-season comparison; a stored "current age"
    -- would give every season the same number and flatten exactly the
    -- differences these questions are testing.
    box.age,
    -- Position actually played this season, as the box-score page lists it.
    -- May differ from the bio page's primary_position, which is career-level.
    box.position,
    dp.primary_position,

    -- Basketball-Reference's display order on the season totals page. Verified
    -- against the data: it is the ranking by TOTAL POINTS SCORED, descending,
    -- with ties broken by the source's own order (the only disagreements with a
    -- recomputed points ranking are between players on identical point totals).
    -- It is a SCORING rank, not a league standing — this data has no wins
    -- column at all. Anything phrased "the top N players of the season" off
    -- this column means "the N highest scorers", and should say so.
    box.rank                                       as points_rank,

    -- ── season honours ──────────────────────────────────────────────────
    -- Facts about the player-season, carried here so an analysis does not have
    -- to re-join the two award tables. The winner is also on the ballot at
    -- rank 1, so the two flags deliberately overlap.
    (mc.player_id is not null)                     as is_mvp_candidate,
    mc.rank                                        as mvp_rank,
    mc.share                                       as mvp_vote_share,
    (mw.player_id is not null)                     as is_mvp_winner,

    -- ── playing time and availability ───────────────────────────────────
    box.games_played,
    box.games_started,
    box.minutes_played,
    -- Games the player's club played that season. For a traded player there is
    -- no single club, so the season's full schedule length is used instead;
    -- games_basis records which of the two applies.
    case
        when dt.is_aggregate then ds.scheduled_games
        else nullif(tss.games, 0)
    end                                            as team_games,
    case
        when dt.is_aggregate then 'league_schedule'
        else 'own_team'
    end                                            as games_basis,
    -- Share of his team's games the player appeared in: 1.0 = never missed one.
    -- It can sit a hair above 1.0 for a traded player, because his two clubs
    -- had played a different number of games at the moment of the trade — Mikal
    -- Bridges appeared in 83 of a possible 82 in 2022-23, Buddy Hield in 84.
    -- That is real, not a fault: two rows in seven seasons.
    round(
        box.games_played::numeric
        / nullif(
            case
                when dt.is_aggregate then ds.scheduled_games
                else nullif(tss.games, 0)
            end,
            0
        ),
        4
    )                                              as availability,

    -- ── box score, as season totals ─────────────────────────────────────
    box.points,
    box.total_rebounds,
    box.assists,
    box.steals,
    box.blocks,
    box.turnovers,
    box.triple_doubles,

    -- ── the same, per game (the form every chart wants) ─────────────────
    round(box.points::numeric        / box.games_played, 2) as points_per_game,
    round(box.total_rebounds::numeric / box.games_played, 2) as rebounds_per_game,
    round(box.assists::numeric       / box.games_played, 2) as assists_per_game,
    round(box.minutes_played::numeric / box.games_played, 2) as minutes_per_game,

    -- ── shooting: 0-1 fractions, NULL when nothing was attempted ────────
    box.field_goal_pct,
    box.three_point_pct,
    box.free_throw_pct,
    box.effective_fg_pct,

    -- ── advanced metrics ────────────────────────────────────────────────
    adv.player_efficiency_rate,
    -- 0-1 fraction, can exceed 1.0.
    adv.true_shooting_percentage,
    -- 0-100 from here down.
    adv.usage_percentage,
    adv.total_rebound_percentage,
    adv.assist_percentage,
    adv.steal_percentage,
    adv.block_percentage,
    adv.turnover_percentage,
    adv.win_shares,
    adv.win_shares_per_48_minutes,
    adv.offensive_box_plus_minus,
    adv.defensive_box_plus_minus,
    adv.box_plus_minus,
    adv.value_over_replacement_player,

    -- ── bio attributes (NULL for players with no scraped bio page) ──────
    dp.has_bio,
    dp.height_cm,
    dp.weight_kg,
    -- Centimetres per kilogram — a build/leanness ratio. ~2.2 for a guard,
    -- ~1.9 for a centre.
    dp.height_to_weight,
    dp.college,
    dp.draft_year,
    dp.draft_round,
    dp.draft_overall_pick,

    -- Career seasons of experience as of the scrape (the end of the most
    -- recent season in this data).
    dp.career_experience_seasons,
    -- Seasons of experience BEFORE this one — 0 means this was his rookie year,
    -- which is Basketball-Reference's own convention on the roster pages.
    -- Derived by rolling the career figure back by the number of seasons since.
    -- Checked against the champion rosters, which carry the real per-season
    -- figure: it agrees exactly for every player in 2023-24 and 2024-25 and for
    -- all 478 current-roster players. It drifts low for players who sat out a
    -- whole season earlier on, because the career figure counts seasons played,
    -- not calendar years. Trustworthy for recent seasons, indicative further
    -- back; the only mart that uses it (d2) stays inside the recent window.
    -- NULL for 603 of the 3,884 player-seasons: 291 players have a scraped bio
    -- page that simply omits the Experience field, and nothing is invented to
    -- fill it. None of them reach a top-15 scoring finish, so d2 loses nobody.
    (dp.career_experience_seasons - (l.latest_season - box.season) - 1)
                                                   as experience_seasons

from processed.player_season_stats as box
cross join latest as l
join processed.player_advanced_stats as adv
    on adv.season = box.season
    and adv.player_id = box.player_id
    and adv.stint = box.stint
join analyst_ready.dim_player as dp
    on dp.player_id = box.player_id
join analyst_ready.dim_team as dt
    on dt.team_id = box.team_id
join analyst_ready.dim_season as ds
    on ds.season = box.season
-- Left, not inner: the 'tot' pseudo-club has no team-season totals, and losing
-- every traded player would be a silent, sizeable sample change (~80 players a
-- season).
left join processed.team_season_stats as tss
    on tss.season = box.season
    and tss.team_id = box.team_id
-- Left: the vast majority of player-seasons receive no MVP vote.
left join processed.mvp_candidates as mc
    on mc.season = box.season
    and mc.player_id = box.player_id
left join processed.mvp_winners as mw
    on mw.season = box.season
    and mw.player_id = box.player_id
    and mw.league = 'NBA'
where box.is_primary;
