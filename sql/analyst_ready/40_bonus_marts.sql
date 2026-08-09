-- ============================================================================
-- analyst_ready — the bonus analyses.
--
-- These are not on the assignment sheet. They are the extra questions the team
-- invented, and the brief awards points for them. Same rule as the question
-- marts: one relation per question, with the definitional choices written down.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- bonus_availability — "availability wins championships": how much of the
-- season does a player actually play?
--
-- Grain: one row per player per season, 2018-19 through 2024-25 (3,884 rows) —
--        the same grain as player_season, which is where the arithmetic lives.
--
-- Definitional choices:
--   * AVAILABILITY = games played / games his club played. 1.0 means he never
--     missed a game. It is a share of the schedule, not a share of minutes: a
--     player who appears for two minutes counts as available.
--   * DENOMINATOR — for a player who was traded there is no single club, so the
--     season's full schedule length is used instead (82 games normally, 75 in
--     2019-20 and 72 in 2020-21, both shortened by COVID). `games_basis` says
--     which denominator each row used; roughly 80 players a season are on the
--     league-schedule basis. Two rows in seven seasons come out a shade above
--     1.0 — Mikal Bridges played 83 games in 2022-23 and Buddy Hield 84 in
--     2023-24, which a traded player can do when his two clubs are at different
--     points in their schedules. Real data, left as it is.
--   * The MVP flags let the original comparison be rebuilt as it was. Note the
--     two groups OVERLAP — the MVP winner is also on the ballot at rank 1 — so
--     `is_mvp_candidate` and `is_mvp_winner` are kept as separate flags rather
--     than collapsed into one label. `mvp_group` is a convenience that assigns
--     each player-season to its highest honour, for charts that need exactly
--     one category per row.
--   * Every player-season is kept, not just the MVP ones, so the honoured
--     players can be compared against the league they came from.
-- ----------------------------------------------------------------------------
create table analyst_ready.bonus_availability as
select
    ps.season,
    ps.season_label,
    ps.player_id,
    ps.player_name,
    ps.team_id,
    ps.team_name,
    ps.is_multi_team_season,
    ps.games_played,
    ps.team_games,
    ps.games_basis,
    ps.availability,
    ps.minutes_played,
    ps.minutes_per_game,
    ps.points_rank,
    (mc.player_id is not null) as is_mvp_candidate,
    mc.rank                    as mvp_rank,
    (mw.player_id is not null) as is_mvp_winner,
    case
        when mw.player_id is not null then 'mvp_winner'
        when mc.player_id is not null then 'mvp_candidate'
        else 'other'
    end                        as mvp_group
from analyst_ready.player_season as ps
left join processed.mvp_candidates as mc
    on mc.season = ps.season
    and mc.player_id = ps.player_id
left join processed.mvp_winners as mw
    on mw.season = ps.season
    and mw.player_id = ps.player_id
    and mw.league = 'NBA';


-- ----------------------------------------------------------------------------
-- bonus_superstar_tax — does a player's efficiency fall as he is asked to do
-- more?
--
-- The idea: usage percentage is the share of his team's possessions a player
-- finishes, true shooting percentage is how efficiently he finishes them. If
-- carrying a bigger load costs accuracy, the two should trade off — and the
-- players who stay efficient at high usage are the genuinely elite ones.
--
-- Grain: one row per player per season. 70 rows — the top 10 scorers in each of
--        the seven seasons, all of whom clear the minutes floor.
--
-- Definitional choices:
--   * POPULATION = the season's top 10 scorers (points_rank <= 10) who played
--     at least 1,000 minutes, as in the original analysis. The minutes floor
--     keeps out small samples where a percentage swings wildly; at the top of
--     the scoring list nobody is actually excluded by it, but it is the stated
--     rule.
--   * SCALES — usage is stored 0-100 and true shooting 0-1. Plotting them on
--     one pair of axes needs them on the same scale, so a converted
--     `true_shooting_pct` (0-100) is provided alongside the raw fraction. Both
--     are kept: the conversion is visible rather than assumed. True shooting
--     can exceed 100 because it weights a three above a two.
-- ----------------------------------------------------------------------------
create table analyst_ready.bonus_superstar_tax as
select
    ps.season,
    ps.season_label,
    ps.player_id,
    ps.player_name,
    ps.team_id,
    ps.team_name,
    ps.position,
    ps.points_rank,
    ps.minutes_played,
    ps.points,
    ps.points_per_game,
    -- 0-100, as stored.
    ps.usage_percentage,
    -- 0-1, as stored.
    ps.true_shooting_percentage,
    -- The same figure on usage's scale, so the two can share an axis.
    round(ps.true_shooting_percentage * 100, 1) as true_shooting_pct,
    ps.player_efficiency_rate,
    ps.win_shares,
    ps.box_plus_minus
from analyst_ready.player_season as ps
where ps.points_rank <= 10
  and ps.minutes_played >= 1000;


-- ----------------------------------------------------------------------------
-- bonus_team_four_factors — which parts of a team's game go with a stronger
-- season?
--
-- Dean Oliver's "four factors" — shooting, turnovers, rebounding, free throws —
-- rebuilt from team season totals, because the source gives raw counts only.
--
-- Grain: one team-season. 210 rows — 30 clubs x seasons 2018-19..2024-25.
--
-- Definitional choices:
--   * FORMULAS, as the original analysis wrote them:
--       effective FG%      = (FGM + 0.5 x 3PM) / FGA
--       possessions        = FGA - ORB + TOV + 0.44 x FTA
--       turnover %         = TOV / possessions
--       offensive rebound% = ORB / (FGA - FGM)     [own misses only]
--       free-throw rate    = FTA / FGA
--     Kept at full precision rather than truncated to whole percents as the
--     original did — truncation loses about half a point per team for nothing.
--   * `points_rank` IS NOT A LEAGUE STANDING. It is the source page's ordering
--     of the season, which is by total points scored. This data has no wins
--     column, so any "what drives performance" statement made from it is really
--     "what goes with scoring more", and must be presented that way. The column
--     is named for what it is, not for what one might wish it were.
--   * SEASONS — the original looked at 2023-24 and 2024-25. This mart carries
--     the whole 2018-19..2024-25 window the rest of the project uses, so the
--     original two-season comparison is one filter away and a longer view is
--     available for free. The unplayed 2025-26 rows (games = 0) are excluded:
--     every formula above would divide by zero.
-- ----------------------------------------------------------------------------
create table analyst_ready.bonus_team_four_factors as
select
    tss.season,
    ds.season_label,
    tss.team_id,
    dt.team_name,
    tss.rank                                       as points_rank,
    (tss.team_id = ds.champion_team_id)            as is_champion,
    tss.games,
    tss.points,
    round(tss.points::numeric / tss.games, 1)      as points_per_game,
    round(
        (tss.field_goals_made + 0.5 * tss.three_pointers_made)::numeric
        / tss.field_goals_attempted * 100,
        2
    )                                              as effective_fg_pct,
    round(
        tss.field_goals_attempted
        - tss.offensive_rebounds
        + tss.turnovers
        + 0.44 * tss.free_throws_attempted,
        1
    )                                              as estimated_possessions,
    round(
        tss.turnovers::numeric
        / (
            tss.field_goals_attempted
            - tss.offensive_rebounds
            + tss.turnovers
            + 0.44 * tss.free_throws_attempted
        ) * 100,
        2
    )                                              as turnover_pct,
    round(
        tss.offensive_rebounds::numeric
        / nullif(tss.field_goals_attempted - tss.field_goals_made, 0) * 100,
        2
    )                                              as offensive_rebound_pct,
    round(
        tss.free_throws_attempted::numeric
        / tss.field_goals_attempted * 100,
        2
    )                                              as free_throw_rate
from processed.team_season_stats as tss
join analyst_ready.dim_team as dt
    on dt.team_id = tss.team_id
join analyst_ready.dim_season as ds
    on ds.season = tss.season
where tss.season between 2019 and 2025
  and tss.games > 0;


-- ----------------------------------------------------------------------------
-- bonus_draft_picks — which early draft picks are worth trading for?
--
-- The scenario: the club cannot realistically land the first overall pick, so
-- it wants to buy a player who was one. That pool is too small, so the search
-- widens to the top 10 picks — and the question becomes whether picks 1-5 are
-- measurably better than picks 6-10.
--
-- Grain: one row per player. 188 rows — every top-10 pick with at least one
--        season in the 2018-19..2024-25 window.
--
-- Definitional choices:
--   * POPULATION = players whose bio page records an overall draft pick of 10
--     or better. Undrafted players and later picks are out of scope by
--     construction; players with no scraped bio page have no draft data at all
--     and cannot be assessed. All 188 who qualify have at least one season of
--     statistics, so nothing is lost at the join.
--   * CAREER TOTALS HERE MEAN "over the seasons in this database", 2018-19
--     onwards — not a full career. A 20-year veteran and a 4-year pro are both
--     summed over the same window, which is why `seasons_played` is carried:
--     the totals must be read next to it. Rates (PER, rebound %, ...) are
--     averaged across seasons; counting stats (win shares, VORP, box plus/minus)
--     are summed, as in the original analysis.
--   * AGE = the player's age in his most recent season in the data. The
--     database deliberately stores no single "current age" — an age is only
--     meaningful attached to a season.
--   * `career_experience_seasons` is carried for context only and is NULL for
--     49 of the 188, whose bio pages omit the field. No tier depends on it, so
--     no player drops out of the comparison because of it.
--   * TIERS, from the original analysis:
--       pick_group   picks 1-5 vs picks 6-10 — the comparison being tested
--       per_tier     average PER <= 20 not_a_starter, 20-25 all-star_candidate,
--                    above 25 mvp_candidate
--       vorp_tier    total VORP >= 20 is high_vorp
--       age_group    30 and over is '30-40', otherwise '20-30'
--   * DEFENCE TIER IS DELIBERATELY NOT A COPY OF THE ORIGINAL. The original
--     labelled a NEGATIVE defensive box plus/minus 'great' and a positive one
--     'bad', which is backwards: defensive BPM measures points prevented per
--     100 possessions relative to an average player, so higher is better. That
--     is a sign error, not a definitional choice, and reproducing it would put
--     the worst defenders at the top of a recommendation list. Corrected here:
--     positive is 'great', zero 'decent', negative 'bad'.
-- ----------------------------------------------------------------------------
create table analyst_ready.bonus_draft_picks as
with career as (
    select
        ps.player_id,
        max(ps.player_name)                            as player_name,
        count(*)                                       as seasons_played,
        min(ps.season)                                 as first_season,
        max(ps.season)                                 as last_season,
        sum(ps.triple_doubles)                         as triple_doubles,
        round(avg(ps.player_efficiency_rate), 2)       as avg_player_efficiency_rate,
        round(sum(ps.win_shares), 1)                   as total_win_shares,
        round(avg(ps.total_rebound_percentage), 2)     as avg_total_rebound_pct,
        round(avg(ps.assist_percentage), 2)            as avg_assist_pct,
        round(avg(ps.steal_percentage), 2)             as avg_steal_pct,
        round(avg(ps.block_percentage), 2)             as avg_block_pct,
        round(avg(ps.usage_percentage), 2)             as avg_usage_pct,
        round(sum(ps.offensive_box_plus_minus), 1)     as total_offensive_bpm,
        round(sum(ps.defensive_box_plus_minus), 1)     as total_defensive_bpm,
        round(sum(ps.value_over_replacement_player), 1) as total_vorp,
        round(avg(ps.points_per_game), 2)              as avg_points_per_game
    from analyst_ready.player_season as ps
    group by ps.player_id
),
latest_age as (
    select distinct on (ps.player_id)
        ps.player_id,
        ps.age,
        ps.season as age_season,
        ps.team_id,
        ps.team_name
    from analyst_ready.player_season as ps
    order by ps.player_id, ps.season desc
)
select
    c.player_id,
    c.player_name,
    dp.draft_year,
    dp.draft_overall_pick,
    case
        when dp.draft_overall_pick <= 5 then 'picks_1_5'
        else 'picks_6_10'
    end                                     as pick_group,
    (dp.draft_overall_pick <= 5)            as is_top5_pick,
    dp.primary_position,
    dp.height_cm,
    dp.weight_kg,
    la.age                                  as latest_age,
    la.age_season                           as latest_season,
    la.team_name                            as latest_team_name,
    dp.career_experience_seasons,
    c.seasons_played,
    c.first_season,
    c.triple_doubles,
    c.avg_player_efficiency_rate,
    c.total_win_shares,
    c.avg_total_rebound_pct,
    c.avg_assist_pct,
    c.avg_steal_pct,
    c.avg_block_pct,
    c.avg_usage_pct,
    c.total_offensive_bpm,
    c.total_defensive_bpm,
    c.total_vorp,
    c.avg_points_per_game,
    case
        when c.avg_player_efficiency_rate <= 20 then 'not_a_starter'
        when c.avg_player_efficiency_rate <= 25 then 'all-star_candidate'
        else 'mvp_candidate'
    end                                     as per_tier,
    case
        when c.total_vorp >= 20 then 'high_vorp'
        else 'low_vorp'
    end                                     as vorp_tier,
    case
        when c.total_defensive_bpm > 0 then 'great'
        when c.total_defensive_bpm = 0 then 'decent'
        else 'bad'
    end                                     as defense_tier,
    case
        when la.age >= 30 then '30-40'
        else '20-30'
    end                                     as age_group
from career as c
join latest_age as la
    on la.player_id = c.player_id
join analyst_ready.dim_player as dp
    on dp.player_id = c.player_id
where dp.draft_overall_pick <= 10;
