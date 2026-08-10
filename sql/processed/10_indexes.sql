-- ============================================================================
-- processed — indexes beyond the primary keys.
--
-- Each primary key already gives a free index on its own columns, in order.
-- So (season, player_id, stint) covers lookups by season, and by season plus
-- player, and nothing more. Everything below fills a gap that leaves.
--
-- Two kinds of gap are worth filling here:
--
--   1. Foreign-key columns. PostgreSQL indexes the parent side of a foreign
--      key automatically but NOT the child side, so "every row that points at
--      this team" has no index unless one is made. Those are the joins this
--      project runs constantly.
--
--   2. The is_primary filter. Almost every player-level question starts with
--      `where is_primary` to collapse traded players back to one row per
--      season. A partial index stores only those 3,884 rows.
--
-- Honest note on size: the biggest table here is 5,025 rows, so PostgreSQL
-- will often read the whole table anyway and ignore these. They are cheap,
-- they keep foreign-key maintenance fast, and they document which columns the
-- analysis actually joins on.
-- ============================================================================

-- ── players ─────────────────────────────────────────────────────────────
-- "Find me a Point Guard" is a stated requirement of the analysis.
create index ix_players_primary_position
    on processed.players (primary_position);

-- ── player_positions ────────────────────────────────────────────────────
-- The PK covers player_id; this covers the other direction, "who plays C".
create index ix_player_positions_position_code
    on processed.player_positions (position_code);

-- ── season_awards ───────────────────────────────────────────────────────
-- "Which seasons did this team win?" — the champion lookup.
create index ix_season_awards_champion_team
    on processed.season_awards (champion_team_id);

-- ── rosters ─────────────────────────────────────────────────────────────
-- PK is (season, team_id, player_id), so player-first lookups need their own.
create index ix_rosters_player
    on processed.rosters (player_id);

create index ix_rosters_team_season
    on processed.rosters (team_id, season);

-- ── player_season_stats ─────────────────────────────────────────────────
create index ix_player_season_stats_player
    on processed.player_season_stats (player_id);

create index ix_player_season_stats_team_season
    on processed.player_season_stats (team_id, season);

-- One row per player-season: the shape nearly every question wants.
create index ix_player_season_stats_primary
    on processed.player_season_stats (season, player_id)
    where is_primary;

-- ── player_advanced_stats ───────────────────────────────────────────────
create index ix_player_advanced_stats_player
    on processed.player_advanced_stats (player_id);

create index ix_player_advanced_stats_team_season
    on processed.player_advanced_stats (team_id, season);

create index ix_player_advanced_stats_primary
    on processed.player_advanced_stats (season, player_id)
    where is_primary;

-- ── team_season_stats ───────────────────────────────────────────────────
-- PK is (season, team_id); this serves "this franchise across all seasons".
create index ix_team_season_stats_team
    on processed.team_season_stats (team_id);

-- ── mvp_winners ─────────────────────────────────────────────────────────
-- "How many MVPs does this player have?" is the Michael Jordan Trophy count
-- the analysis ranks players by.
create index ix_mvp_winners_player
    on processed.mvp_winners (player_id);

create index ix_mvp_winners_team
    on processed.mvp_winners (team_id);

-- ── mvp_candidates ──────────────────────────────────────────────────────
create index ix_mvp_candidates_player
    on processed.mvp_candidates (player_id);

create index ix_mvp_candidates_team
    on processed.mvp_candidates (team_id);
