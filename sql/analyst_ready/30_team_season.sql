-- ============================================================================
-- analyst_ready.team_season — the team-side counterpart to player_season.
--
-- One row per club per season, with the derived rate statistics that team
-- analysis normally starts by computing. Raw counts alone are not comparable
-- between clubs or eras: a team that plays fast attempts more of everything,
-- so the shares and per-possession rates below are what an actual comparison
-- needs.
--
-- Grain: ONE ROW PER TEAM PER SEASON, 1949-50 through the latest season.
--
-- Like player_season, this answers no question by itself. Nothing is filtered
-- to a window, so the full history is available and a question narrows it.
--
-- WHAT IS NULL, AND WHY. Two cases, both honest rather than filled:
--   * The league did not record the statistic in that era — no three-point
--     data before 1979-80, no offensive rebounds, steals or blocks before
--     1973-74. Any feature needing a missing input is NULL for those seasons.
--   * The season has not been played (games = 0). Every rate is NULL rather
--     than a division by zero, and `has_been_played` marks the rows.
--
-- The 'tot' pseudo-club never appears: it has no team-season totals to
-- aggregate, so it drops out at the inner join.
-- ============================================================================

create table analyst_ready.team_season as
select
    -- ── keys and context ────────────────────────────────────────────────
    tss.season,
    ds.season_label,
    tss.team_id,
    dt.team_name,
    (tss.team_id = ds.champion_team_id)            as is_champion,
    -- Basketball-Reference's display rank within the season, which is the
    -- ordering by TOTAL POINTS SCORED. It is NOT a league standing — this
    -- data carries no wins or losses at all.
    tss.rank                                       as points_rank,
    (tss.games > 0)                                as has_been_played,

    -- ── raw season totals, carried straight through ─────────────────────
    tss.games,
    tss.minutes_played,
    tss.points,
    tss.field_goals_made,
    tss.field_goals_attempted,
    tss.three_pointers_made,
    tss.three_pointers_attempted,
    tss.two_pointers_made,
    tss.two_pointers_attempted,
    tss.free_throws_made,
    tss.free_throws_attempted,
    tss.offensive_rebounds,
    tss.defensive_rebounds,
    tss.total_rebounds,
    tss.assists,
    tss.steals,
    tss.blocks,
    tss.turnovers,
    tss.personal_fouls,

    -- ── shooting percentages, as the source gives them (0-1 fractions) ──
    tss.field_goal_pct,
    tss.three_point_pct,
    tss.two_point_pct,
    tss.free_throw_pct,

    -- ── per-game rates ──────────────────────────────────────────────────
    round(tss.points::numeric / nullif(tss.games, 0), 1) as points_per_game,
    round(tss.total_rebounds::numeric / nullif(tss.games, 0), 1)
                                                   as rebounds_per_game,
    round(tss.assists::numeric / nullif(tss.games, 0), 1)
                                                   as assists_per_game,
    round(tss.turnovers::numeric / nullif(tss.games, 0), 1)
                                                   as turnovers_per_game,

    -- ── possessions ─────────────────────────────────────────────────────
    -- The standard approximation, since the source publishes no possession
    -- count. The 0.44 coefficient is the accepted estimate of how many free
    -- throw attempts actually end a possession — an and-one, or the first of
    -- two, does not.
    round(
        tss.field_goals_attempted
        - tss.offensive_rebounds
        + tss.turnovers
        + 0.44 * tss.free_throws_attempted,
        1
    )                                              as estimated_possessions,
    -- Possessions per game: the usual proxy for how fast a club plays.
    round(
        (
            tss.field_goals_attempted
            - tss.offensive_rebounds
            + tss.turnovers
            + 0.44 * tss.free_throws_attempted
        ) / nullif(tss.games, 0),
        1
    )                                              as possessions_per_game,
    -- Points per 100 possessions — the era-neutral way to say "good offence".
    -- A fast team scores more points without being more efficient; this is
    -- what separates the two.
    round(
        tss.points::numeric
        / nullif(
            tss.field_goals_attempted
            - tss.offensive_rebounds
            + tss.turnovers
            + 0.44 * tss.free_throws_attempted,
            0
        ) * 100,
        2
    )                                              as offensive_rating,

    -- ── Dean Oliver's four factors ──────────────────────────────────────
    -- The four things a team controls that decide games, in his order of
    -- importance: shoot well, keep the ball, rebound your own misses, get to
    -- the line. All on a 0-100 scale.
    --
    -- 1. SHOOTING — field goal percentage crediting a made three as 1.5
    --    makes, because it is worth 1.5 times as much.
    round(
        (tss.field_goals_made + 0.5 * tss.three_pointers_made)::numeric
        / nullif(tss.field_goals_attempted, 0) * 100,
        2
    )                                              as effective_fg_pct,
    -- 2. BALL SECURITY — turnovers per 100 possessions. LOWER IS BETTER;
    --    this is the one factor whose direction is inverted.
    round(
        tss.turnovers::numeric
        / nullif(
            tss.field_goals_attempted
            - tss.offensive_rebounds
            + tss.turnovers
            + 0.44 * tss.free_throws_attempted,
            0
        ) * 100,
        2
    )                                              as turnover_pct,
    -- 3. REBOUNDING — the share of the team's OWN missed shots it recovered.
    --    Each one is a fresh possession the opponent never got.
    round(
        tss.offensive_rebounds::numeric
        / nullif(tss.field_goals_attempted - tss.field_goals_made, 0) * 100,
        2
    )                                              as offensive_rebound_pct,
    -- 4. FREE THROWS — attempts per 100 field-goal attempts. A proxy for how
    --    hard the club attacks the basket, since that is what draws fouls.
    round(
        tss.free_throws_attempted::numeric
        / nullif(tss.field_goals_attempted, 0) * 100,
        2
    )                                              as free_throw_rate,

    -- ── shot profile ────────────────────────────────────────────────────
    -- Share of shots taken from three. The single clearest number for the
    -- league's tactical shift since the mid-2010s.
    round(
        tss.three_pointers_attempted::numeric
        / nullif(tss.field_goals_attempted, 0) * 100,
        2
    )                                              as three_point_attempt_rate,
    -- Share of made field goals that came off a pass.
    round(
        tss.assists::numeric / nullif(tss.field_goals_made, 0) * 100,
        2
    )                                              as assisted_fg_pct

from processed.team_season_stats as tss
join analyst_ready.dim_team as dt
    on dt.team_id = tss.team_id
join analyst_ready.dim_season as ds
    on ds.season = tss.season;
