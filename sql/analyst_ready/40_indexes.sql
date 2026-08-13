-- ============================================================================
-- analyst_ready — keys and indexes.
--
-- Two jobs, in this order:
--
-- 1. DECLARE EACH TABLE'S GRAIN AS A PRIMARY KEY. Every table above states its
--    grain in a comment ("one row per player per season"). A primary key turns
--    that sentence into something the database checks: if a join ever starts
--    duplicating rows — the classic way a traded player's stints leak into an
--    average — the rebuild fails here instead of quietly reporting a wrong
--    number. These keys are the cheapest regression test in the project.
--
-- 2. INDEX THE COMMON ACCESS PATHS. These tables are small, so PostgreSQL will
--    often scan them regardless; the indexes exist to keep the usual filters
--    fast and to record which columns analysis actually slices by.
--
-- Naming: pk_ for the grain key, ix_ for a secondary index, both prefixed with
-- the relation name so they read unambiguously in \d output.
--
-- Views (dim_player, dim_team, dim_season) are not indexable. They resolve to
-- the indexes on `processed`.
-- ============================================================================


-- ── player_season ────────────────────────────────────────────────────────────
-- One row per player per season: the whole point of the is_primary filter.
alter table analyst_ready.player_season
    add constraint pk_player_season primary key (season, player_id);

-- "This player's career" — the second most common access path after the key.
create index ix_player_season_player
    on analyst_ready.player_season (player_id);

-- "The season's leading scorers", the usual way a population gets defined.
create index ix_player_season_points_rank
    on analyst_ready.player_season (season, points_rank);

-- "Everyone who played for this club that season."
create index ix_player_season_team
    on analyst_ready.player_season (team_id, season);

-- "Everyone who drew an MVP vote", which is a small slice of a big table and
-- therefore worth a partial index.
create index ix_player_season_mvp_candidate
    on analyst_ready.player_season (season, mvp_rank)
    where is_mvp_candidate;

-- Position filters are common and selective enough to be worth an index.
create index ix_player_season_position
    on analyst_ready.player_season (season, position);


-- ── team_season ──────────────────────────────────────────────────────────────
alter table analyst_ready.team_season
    add constraint pk_team_season primary key (season, team_id);

-- "This franchise over time."
create index ix_team_season_team
    on analyst_ready.team_season (team_id);

-- Champions are a frequent comparison group and a rare one — a partial index
-- stores only the handful of rows that qualify.
create index ix_team_season_champion
    on analyst_ready.team_season (season)
    where is_champion;
