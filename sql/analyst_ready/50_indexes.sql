-- ============================================================================
-- analyst_ready — keys and indexes.
--
-- Two jobs, in this order:
--
-- 1. DECLARE EACH MART'S GRAIN AS A PRIMARY KEY. Every mart above states its
--    grain in a comment ("one row per player per season"). A primary key turns
--    that sentence into something the database checks: if a join ever starts
--    duplicating rows — the classic way a traded player's stints leak into an
--    average — the rebuild fails here instead of quietly reporting a wrong
--    number. These keys are the cheapest regression test in the project.
--
-- 2. INDEX WHAT THE NOTEBOOKS FILTER ON. The marts are small (the largest is
--    3,884 rows) so PostgreSQL will often scan them regardless; these exist to
--    keep the common filters fast and, just as usefully, to record which
--    columns the analysis actually slices by.
--
-- Naming: pk_ for the grain key, ix_ for a secondary index, both prefixed with
-- the relation name so they read unambiguously in \d output.
--
-- Views (dim_player, dim_team, dim_season) are not indexable. They resolve to
-- the indexes on `processed`.
-- ============================================================================


-- ── player_season — the wide fact everything else is built from ──────────────
-- One row per player per season: the whole point of the is_primary filter.
alter table analyst_ready.player_season
    add constraint pk_player_season primary key (season, player_id);

-- "This player's career" — the second most common access path after the key.
create index ix_player_season_player
    on analyst_ready.player_season (player_id);

-- "The season's leading scorers", which is how D1, D2, H1 and the superstar-tax
-- mart all define their populations.
create index ix_player_season_points_rank
    on analyst_ready.player_season (season, points_rank);

-- "Everyone who played for this club that season."
create index ix_player_season_team
    on analyst_ready.player_season (team_id, season);


-- ── D1 — height: MVP ballot vs top-50 scorers ────────────────────────────────
-- A player can legitimately appear in both groups, so group_label is part of
-- the key; he can never appear twice within one group.
alter table analyst_ready.d1_height_sample
    add constraint pk_d1_height_sample primary key (group_label, season, player_id);

create index ix_d1_height_sample_group
    on analyst_ready.d1_height_sample (group_label);


-- ── D2 — champion squad vs the season's top 15 ───────────────────────────────
alter table analyst_ready.d2_champion_vs_top15
    add constraint pk_d2_champion_vs_top15
    primary key (group_label, season, player_id);

create index ix_d2_champion_vs_top15_group
    on analyst_ready.d2_champion_vs_top15 (group_label);


-- ── D3 — the point-guard shortlist ───────────────────────────────────────────
-- One row per player: the count of ballot appearances is already aggregated.
alter table analyst_ready.d3_point_guard_candidates
    add constraint pk_d3_point_guard_candidates primary key (player_id);

-- The list is almost always read in recommendation order.
create index ix_d3_point_guard_candidates_rank
    on analyst_ready.d3_point_guard_candidates (recommendation_rank);


-- ── H1 — agility of the top 20, recent vs past ───────────────────────────────
-- No group_label in the key: the two periods are different seasons, so a
-- player-season belongs to exactly one of them.
alter table analyst_ready.h1_agility
    add constraint pk_h1_agility primary key (season, player_id);

create index ix_h1_agility_group
    on analyst_ready.h1_agility (group_label);


-- ── H2 — innate ability of champion squads, recent vs past ───────────────────
alter table analyst_ready.h2_innate_ability
    add constraint pk_h2_innate_ability primary key (season, player_id);

create index ix_h2_innate_ability_group
    on analyst_ready.h2_innate_ability (group_label);


-- ── Bonus — availability ─────────────────────────────────────────────────────
alter table analyst_ready.bonus_availability
    add constraint pk_bonus_availability primary key (season, player_id);

-- The comparison the analysis makes is between honour groups.
create index ix_bonus_availability_mvp_group
    on analyst_ready.bonus_availability (mvp_group);

-- "This player's availability history", which is the roster-trend chart.
create index ix_bonus_availability_player
    on analyst_ready.bonus_availability (player_id);


-- ── Bonus — superstar tax ────────────────────────────────────────────────────
alter table analyst_ready.bonus_superstar_tax
    add constraint pk_bonus_superstar_tax primary key (season, player_id);

-- The chart is faceted one panel per player.
create index ix_bonus_superstar_tax_player
    on analyst_ready.bonus_superstar_tax (player_id);


-- ── Bonus — team four factors ────────────────────────────────────────────────
alter table analyst_ready.bonus_team_four_factors
    add constraint pk_bonus_team_four_factors primary key (season, team_id);

create index ix_bonus_team_four_factors_season
    on analyst_ready.bonus_team_four_factors (season);


-- ── Bonus — draft-pick trade targets ─────────────────────────────────────────
alter table analyst_ready.bonus_draft_picks
    add constraint pk_bonus_draft_picks primary key (player_id);

-- The whole question is picks 1-5 against picks 6-10.
create index ix_bonus_draft_picks_group
    on analyst_ready.bonus_draft_picks (pick_group);

create index ix_bonus_draft_picks_overall_pick
    on analyst_ready.bonus_draft_picks (draft_overall_pick);
