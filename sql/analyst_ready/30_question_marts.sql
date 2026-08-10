-- ============================================================================
-- analyst_ready — one relation per assigned question.
--
-- Each mart is the single canonical answer-set for one deliverable: it carries
-- the grouping column, the measured column, and enough context to label a
-- chart, so a notebook can plot or test straight off it with no further
-- reshaping. The definitional choices behind each are written above it.
--
-- Naming: d1..d3 are the descriptive-statistics questions, h1..h2 the
-- hypothesis tests.
--
-- On the "Michael Jordan Trophy list": the brief's name for the NBA MVP award.
-- Two tables record it. `mvp_winners` holds the single winner per season since
-- 1955-56; `mvp_candidates` holds everyone who received a vote, but only for
-- 2018-19 onwards. Every question here is scoped to 2019-20 or later and asks
-- about a *list* of players rather than a single winner, so `mvp_candidates` —
-- the ballot — is the list meant. The winner appears on it at rank 1.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- d1_height_sample — D1: are MVP-calibre players taller than high scorers?
--
-- "Produce the height distribution of players on the Michael Jordan Trophy list
--  compared with the top 50 players of the season, seasons 2019-20 through
--  2023-24."
--
-- Grain: one row per player per season per group. 311 rows —
--        61 MVP ballot places + 5 seasons x 50 scorers.
--
-- Definitional choices:
--   * SEASONS 2020-2024 as ending years = the 2019-20 through 2023-24 seasons.
--   * "TOP 50 PLAYERS OF THE SEASON" = the 50 highest scorers, i.e.
--     points_rank <= 50. The source page's display order is exactly that
--     ranking (see player_season.points_rank), and it is what the original
--     analysis used. It is a scoring-volume definition, not an all-round one —
--     worth stating out loud when presenting the result.
--   * The two groups OVERLAP by design: most MVP candidates are also top-50
--     scorers, so roughly 60 players appear once in each group. The question
--     asks to compare two named populations, not to partition the league, and
--     the original analysis did the same. A player appearing twice is one row
--     per group, never two rows within a group.
--
-- Height coverage: no row is dropped for a missing height. 814 of the 1,989
-- players in the database have no scraped bio page and therefore no height, but
-- none of them reach an MVP ballot or a top-50 scoring finish in this window —
-- all 311 rows here carry a height. `has_bio` is kept so that stays visible if
-- the data is ever re-scraped.
-- ----------------------------------------------------------------------------
create table analyst_ready.d1_height_sample as
select
    'mvp_candidates'::text as group_label,
    ps.season,
    ps.season_label,
    ps.player_id,
    ps.player_name,
    ps.height_cm,
    ps.weight_kg,
    ps.has_bio,
    ps.position,
    mc.rank               as mvp_rank,
    ps.points_rank,
    ps.points_per_game
from processed.mvp_candidates as mc
join analyst_ready.player_season as ps
    on ps.season = mc.season
    and ps.player_id = mc.player_id
where mc.season between 2020 and 2024

union all

select
    'top_50'::text        as group_label,
    ps.season,
    ps.season_label,
    ps.player_id,
    ps.player_name,
    ps.height_cm,
    ps.weight_kg,
    ps.has_bio,
    ps.position,
    mc.rank               as mvp_rank,
    ps.points_rank,
    ps.points_per_game
from analyst_ready.player_season as ps
left join processed.mvp_candidates as mc
    on mc.season = ps.season
    and mc.player_id = ps.player_id
where ps.season between 2020 and 2024
  and ps.points_rank <= 50;


-- ----------------------------------------------------------------------------
-- d2_champion_vs_top15 — D2: how do title-winning squads differ from the
-- season's individual stars, in height and in experience?
--
-- "Compare the distribution of experience of active players on the champion
--  team, and their height, over the last two seasons, with the experience and
--  height distribution of the top 15 players of that season."
--
-- Grain: one row per player per season per group. 68 rows —
--        19 + 19 champions, 15 + 15 top scorers.
--
-- Definitional choices:
--   * "LAST TWO SEASONS" = 2023-24 and 2024-25 (stored as 2024 and 2025), the
--     two most recent seasons with a champion. Boston, then Oklahoma City.
--   * "ACTIVE PLAYERS" = players on the champion's roster who actually appeared
--     in a game that season, i.e. who have a box-score row. In practice this
--     removes nobody: all 38 roster players played. The filter is written
--     anyway because it is the definition, and a future season may differ.
--   * "TOP 15 PLAYERS OF THAT SEASON" = the 15 highest scorers, the same
--     scoring-volume reading as D1.
--   * EXPERIENCE means seasons played BEFORE the season in question, so a
--     rookie is 0. For the champions it comes from the roster page, which
--     states it per season and is the authoritative figure. The top-15 group is
--     not on those roster pages, so its experience is rolled back from the
--     career figure (see player_season.experience_seasons). The two agree
--     exactly for all 38 champion players in these two seasons, which is what
--     licenses mixing them; `experience_source` keeps the difference visible.
--
-- Height coverage: nothing is dropped. All 68 players have a scraped bio and a
-- height. On the champion side the roster page also carries a height, and it is
-- identical to the bio height for all 615 overlapping rows — so using the bio
-- height for both groups introduces no inconsistency.
-- ----------------------------------------------------------------------------
create table analyst_ready.d2_champion_vs_top15 as
select
    'champion_team'::text  as group_label,
    ps.season,
    ps.season_label,
    ds.champion_team_id    as team_id,
    ds.champion_team_name  as team_name,
    ps.player_id,
    ps.player_name,
    ps.height_cm,
    ps.has_bio,
    r.experience_seasons,
    'roster_page'::text    as experience_source,
    ps.age,
    ps.position,
    ps.games_played,
    ps.points_rank
from analyst_ready.dim_season as ds
join processed.rosters as r
    on r.season = ds.season
    and r.team_id = ds.champion_team_id
-- Inner join: this is the "active player" test — a roster entry with no
-- box-score row never took the floor that season.
join analyst_ready.player_season as ps
    on ps.season = r.season
    and ps.player_id = r.player_id
where ds.season in (2024, 2025)

union all

select
    'top_15'::text         as group_label,
    ps.season,
    ps.season_label,
    ps.team_id,
    ps.team_name,
    ps.player_id,
    ps.player_name,
    ps.height_cm,
    ps.has_bio,
    ps.experience_seasons,
    'career_rolled_back'::text as experience_source,
    ps.age,
    ps.position,
    ps.games_played,
    ps.points_rank
from analyst_ready.player_season as ps
where ps.season in (2024, 2025)
  and ps.points_rank <= 15;


-- ----------------------------------------------------------------------------
-- d3_point_guard_candidates — D3: which Point Guard should the club buy?
--
-- "The club's ability metric is presence on the Michael Jordan Trophy list, and
--  a player with more appearances has higher priority. Using seasons 2019-20
--  through 2023-24, produce a list of suitable players and present 3
--  recommendations."
--
-- Grain: one row per player. 13 rows — every point guard who received at least
--        one MVP vote in the window.
--
-- Definitional choices:
--   * "POINT GUARD" = the position the player actually played in that season,
--     from the box-score page, not the career primary position from his bio.
--     A player therefore counts only for the seasons he was listed at PG. This
--     is the original analysis's reading and the stricter one.
--   * "APPEARANCE ON THE LIST" = one season on the MVP ballot. Rank is ignored
--     for the count, exactly as the brief states.
--   * TIE-BREAK — the brief gives none, and three players cannot be picked from
--     a count alone: Luka Dončić has 5 appearances, then Stephen Curry and
--     Chris Paul have 3 each. Ties are broken by average ballot rank (lower is
--     better), which is the same tie-break the original analysis applied one
--     tier further down, then by name for determinism. Under it Curry (mean
--     rank 6.67) edges Chris Paul (7.00), so the recommended three are
--     Dončić, Curry, Paul — the same three players the original recommended,
--     with second and third swapped. The original's ordering came from an
--     unordered SQL result, so it was arbitrary; this one is reproducible.
--   * `is_recommended` marks the top three, which is what the club asked for.
--     The rest of the list is kept because "produce a list" is also asked for.
-- ----------------------------------------------------------------------------
create table analyst_ready.d3_point_guard_candidates as
with pg_ballots as (
    select
        ps.player_id,
        ps.player_name,
        ps.season,
        ps.season_label,
        ps.team_id,
        ps.team_name,
        mc.rank as mvp_rank,
        ps.points_per_game,
        ps.assists_per_game
    from processed.mvp_candidates as mc
    join analyst_ready.player_season as ps
        on ps.season = mc.season
        and ps.player_id = mc.player_id
    where mc.season between 2020 and 2024
      and ps.position = 'PG'
),
per_player as (
    select
        player_id,
        max(player_name)                                as player_name,
        count(*)                                        as mvp_appearances,
        round(avg(mvp_rank), 2)                         as avg_mvp_rank,
        min(mvp_rank)                                   as best_mvp_rank,
        min(season)                                     as first_season,
        max(season)                                     as last_season,
        string_agg(season_label, ', ' order by season)  as seasons_listed,
        round(avg(points_per_game), 2)                  as avg_points_per_game,
        round(avg(assists_per_game), 2)                 as avg_assists_per_game
    from pg_ballots
    group by player_id
),
ranked as (
    select
        pp.player_id,
        pp.player_name,
        pp.mvp_appearances,
        pp.avg_mvp_rank,
        pp.best_mvp_rank,
        pp.first_season,
        pp.last_season,
        pp.seasons_listed,
        pp.avg_points_per_game,
        pp.avg_assists_per_game,
        -- The club he was with in the most recent of those seasons — context
        -- for a buying decision, not part of the ranking.
        last_club.team_name as most_recent_team_name,
        row_number() over (
            order by
                pp.mvp_appearances desc,
                pp.avg_mvp_rank asc,
                pp.player_name
        ) as recommendation_rank
    from per_player as pp
    join lateral (
        select b.team_name
        from pg_ballots as b
        where b.player_id = pp.player_id
        order by b.season desc
        limit 1
    ) as last_club on true
)
select
    ranked.player_id,
    ranked.player_name,
    ranked.mvp_appearances,
    ranked.avg_mvp_rank,
    ranked.best_mvp_rank,
    ranked.first_season,
    ranked.last_season,
    ranked.seasons_listed,
    ranked.avg_points_per_game,
    ranked.avg_assists_per_game,
    ranked.most_recent_team_name,
    ranked.recommendation_rank,
    (ranked.recommendation_rank <= 3) as is_recommended
from ranked;


-- ----------------------------------------------------------------------------
-- h1_agility — H1: has the agility of the season's best players increased?
--
-- "It is claimed that the average agility of the players in the top 20 of each
--  season has increased compared with the past. Agility is height / weight.
--  Compare 2022-23..2023-24 with 2020-21..2021-22."
--
-- Grain: one row per player per season per period. 80 rows — 20 players in each
--        of four seasons.
--
-- Definitional choices:
--   * AGILITY = height_cm / weight_kg, exactly as the brief defines it. A
--     higher number means more centimetres per kilo, i.e. a leaner frame.
--     Roughly 2.2 for a guard, 1.9 for a centre.
--   * "TOP 20 OF EACH SEASON" = the 20 highest scorers, the same reading as D1
--     and D2.
--   * The comparison is BETWEEN PERIODS, pooling the two seasons on each side,
--     which is how the brief phrases it. `season` is kept so a per-season view
--     is still one group-by away.
--   * `group_label` is 'past' for 2020-21 and 2021-22, 'recent' for 2022-23 and
--     2023-24. The original notebook called them Past and New.
--
-- Height/weight coverage: nothing is dropped. All 80 player-seasons have both.
-- ----------------------------------------------------------------------------
create table analyst_ready.h1_agility as
select
    case
        when ps.season in (2021, 2022) then 'past'
        else 'recent'
    end                    as group_label,
    ps.season,
    ps.season_label,
    ps.player_id,
    ps.player_name,
    ps.has_bio,
    ps.points_rank,
    ps.position,
    ps.height_cm,
    ps.weight_kg,
    ps.height_to_weight    as agility,
    ps.age
from analyst_ready.player_season as ps
where ps.season in (2021, 2022, 2023, 2024)
  and ps.points_rank <= 20;


-- ----------------------------------------------------------------------------
-- h2_innate_ability — H2: are today's champions built from players who broke
-- through earlier in their careers?
--
-- "An analyst defines innate ability as experience / age, and claims the
--  average innate ability of the champion team's players over the last 2
--  seasons is greater than over the 2 seasons before. Examine this for the
--  active players of that team in that season."
--
-- Grain: one row per player per season. 73 rows — the four champion rosters
--        (Golden State 2021-22, Denver 2022-23, Boston 2023-24,
--        Oklahoma City 2024-25).
--
-- Definitional choices:
--   * INNATE ABILITY = experience_seasons / age. A 22-year-old with 4 seasons
--     behind him scores 0.18; a 34-year-old with 12 scores 0.35. It rewards
--     reaching the league young and staying, which is the analyst's point.
--   * AGE is the player's age DURING THAT SEASON, taken from the box-score
--     page. This matters more than it looks: an earlier version of this project
--     stored a single current age per player (2025 minus birth year), which
--     gives a 2021-22 player his 2025 age and flattens the very difference the
--     hypothesis is about. That column has been removed; this mart uses the
--     per-season value.
--   * EXPERIENCE is seasons played before this one, from the champion's roster
--     page — per season, authoritative, and populated for every roster entry.
--   * "ACTIVE PLAYERS" = roster players who appeared in at least one game that
--     season. As in D2 this removes nobody from these four rosters, but it is
--     the stated definition.
--   * 'past' = 2021-22 and 2022-23, 'recent' = 2023-24 and 2024-25.
--
-- No height is involved, so `has_bio` costs this mart nothing.
-- ----------------------------------------------------------------------------
create table analyst_ready.h2_innate_ability as
select
    case
        when ds.season in (2022, 2023) then 'past'
        else 'recent'
    end                     as group_label,
    ds.season,
    ds.season_label,
    ds.champion_team_id     as team_id,
    ds.champion_team_name   as team_name,
    ps.player_id,
    ps.player_name,
    r.experience_seasons,
    ps.age,
    round(r.experience_seasons::numeric / nullif(ps.age, 0), 4)
                            as innate_ability,
    ps.position,
    ps.games_played,
    ps.minutes_played,
    ps.height_cm
from analyst_ready.dim_season as ds
join processed.rosters as r
    on r.season = ds.season
    and r.team_id = ds.champion_team_id
join analyst_ready.player_season as ps
    on ps.season = r.season
    and ps.player_id = r.player_id
where ds.season in (2022, 2023, 2024, 2025);
