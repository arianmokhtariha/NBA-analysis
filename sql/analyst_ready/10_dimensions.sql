-- ============================================================================
-- analyst_ready — conformed dimensions
--
-- Three small views that answer "who / which club / which year" in one agreed
-- shape, so no mart has to re-derive them. They are views rather than tables
-- because each is a thin rename-and-tidy over `processed`: cheap to evaluate,
-- and nothing downstream hits them in a loop.
--
-- Nothing here filters rows out. Filtering belongs to the question, not to the
-- dimension.
--
-- Reminder on the one convention that trips people up: `season` is the season's
-- ENDING year. The 2023-24 season is 2024.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- dim_player — one row per player, with the bio attributes analysis actually
-- uses.
--
-- Grain: one row per player_id (1,989 rows).
--
-- Why `has_bio` is carried rather than filtered on: only 1,175 of the 1,989
-- players were scraped with a bio page. The other 814 are real players that
-- rosters, box scores and MVP awards refer to — they simply have no height,
-- weight or draft data. Dropping them here would silently shrink the sample of
-- every mart built on top. Each mart decides for itself, and says so.
--
-- `career_experience_seasons` is Basketball-Reference's "Experience" figure as
-- it stood when the bio page was scraped — i.e. counted THROUGH the most recent
-- season in this data. It is not a per-season value. Where a mart needs
-- "experience during season X", it uses the per-season figure instead; see
-- player_season.experience_seasons.
-- ----------------------------------------------------------------------------
create view analyst_ready.dim_player as
select
    p.player_id,
    p.player_name,
    p.has_bio,
    p.primary_position,
    p.shoots,
    p.height_cm,
    p.weight_kg,
    -- Height divided by weight: the project's chosen proxy for "agility".
    -- NULL whenever either half is missing, which is the honest answer.
    round(p.height_cm / nullif(p.weight_kg, 0), 4) as height_to_weight,
    p.birth_date,
    p.birth_year,
    p.college,
    p.experience_seasons as career_experience_seasons,
    p.nba_debut_year,
    p.draft_year,
    p.draft_round,
    p.draft_overall_pick,
    p.draft_team_name,
    p.career_games,
    p.career_points as career_points_per_game,
    p.career_per,
    p.career_win_shares
from processed.players as p;


-- ----------------------------------------------------------------------------
-- dim_team — one row per franchise (or franchise era).
--
-- Grain: one row per team_id (75 rows).
--
-- `is_aggregate` is true for exactly one row, `tot`. That is not a club: it is
-- Basketball-Reference's combined line for a player who was traded mid-season.
-- Anything counted per franchise must exclude it.
-- ----------------------------------------------------------------------------
create view analyst_ready.dim_team as
select
    t.team_id,
    t.team_name,
    t.is_aggregate,
    t.has_detail
from processed.teams as t;


-- ----------------------------------------------------------------------------
-- dim_season — one row per season, with the two season-level facts the
-- questions keep asking for: who won the title, and who won MVP.
--
-- Grain: one row per season (80 rows, 1946-47 through 2025-26).
--
-- Definitional choices:
--   * CHAMPION = the NBA champion. Nine seasons in the 1967-76 window also have
--     an ABA champion; `season_awards` keys on (season, league) for exactly that
--     reason. Every question in this project is about the NBA, so the ABA row is
--     left out here rather than duplicating the season.
--   * SCHEDULED_GAMES = the largest number of games any team played that
--     season. It is the natural denominator for "how much of the season was a
--     player available for" when the player's own club is unknown (a traded
--     player's combined line has no club). It is 82 in a normal season, 72 in
--     2020-21 and 75 in 2019-20 — both shortened by COVID. NULL for 2025-26,
--     which has not been played.
-- ----------------------------------------------------------------------------
create view analyst_ready.dim_season as
select
    s.season,
    s.season_label,
    s.start_year,
    sa.champion_team_id,
    ct.team_name as champion_team_name,
    mw.player_id as mvp_player_id,
    mp.player_name as mvp_player_name,
    sg.scheduled_games,
    (sg.scheduled_games is not null) as has_been_played
from processed.seasons as s
left join processed.season_awards as sa
    on sa.season = s.season
    and sa.league = 'NBA'
left join processed.teams as ct
    on ct.team_id = sa.champion_team_id
left join processed.mvp_winners as mw
    on mw.season = s.season
    and mw.league = 'NBA'
left join processed.players as mp
    on mp.player_id = mw.player_id
left join lateral (
    select max(tss.games) as scheduled_games
    from processed.team_season_stats as tss
    where tss.season = s.season
      and tss.games > 0
) as sg on true;
