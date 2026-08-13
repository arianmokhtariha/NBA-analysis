-- ============================================================================
-- processed — the cleaned Basketball-Reference data, exactly as
-- cleaning/ writes it to data/processed/*.csv.
--
-- One table per CSV, same column names, same column order. Nothing is
-- reshaped here: this file only says what each value *is* and which values
-- must agree with each other.
--
-- Conventions used throughout
-- ---------------------------
-- * season          The ENDING year of the season. "2024-25" is stored as
--                   2025. Every table names it the same way.
-- * ids             player_id / team_id are Basketball-Reference's own short
--                   codes, lower-cased ("jordami01", "chi"). Code columns are
--                   varchar(n) sized a little above the widest real value, so
--                   a corrupted load fails loudly instead of quietly; free-form
--                   human text (names, colleges) is plain text.
-- * numbers         Counts are integer. Measured values use one of two shapes:
--                     numeric(5,3) — figures the source gives to 3 decimals:
--                                    shooting percentages held as a 0-1
--                                    fraction (.487), and per-attempt rates.
--                     numeric(5,1) — figures the source gives to 1 decimal:
--                                    per-game averages, advanced percentages
--                                    held on a 0-100 scale (28.4 = 28.4%),
--                                    win shares, heights and weights.
--                   The two scales are a property of the source pages, not a
--                   choice made here — which is exactly why they are visible.
-- * "tot"           A real team_id. Basketball-Reference gives a player who
--                   was traded mid-season one extra combined row under the
--                   pseudo-team TOT. teams has a genuine row for it flagged
--                   is_aggregate, so those facts have somewhere to point.
-- * missing values  Left NULL. Many dimension rows are id-only (see has_bio /
--                   has_detail below), so most attribute columns are nullable
--                   by design, not by oversight.
--
-- Foreign keys are real and enforced. The cleaning pipeline builds the three
-- dimensions from the union of every id referenced by any fact table, so no
-- constraint has to be relaxed to get the data in.
--
-- Tables are declared parents-first so this file runs top to bottom.
-- ============================================================================

drop schema if exists processed cascade;

create schema processed;


-- ============================================================================
-- DIMENSIONS
-- ============================================================================

-- Every franchise (and franchise era) referenced anywhere in the data,
-- including defunct NBA/BAA clubs and the nine ABA seasons' teams.
create table processed.teams (
    team_id       varchar(4)  not null,
    team_name     text        not null,
    -- True only for the "tot" pseudo-team: a season total across the clubs a
    -- traded player appeared for, not a real franchise. Exclude it before
    -- counting anything per team.
    is_aggregate  boolean     not null,
    -- True when this team has at least one row in team_season_stats. Seven of
    -- the 75 teams are known only from championship rosters (six ABA clubs
    -- plus "tot") and have no season totals.
    has_detail    boolean     not null,

    constraint pk_teams primary key (team_id)
);


-- Every player referenced anywhere: by a roster, a box score, or an MVP
-- award. 1,981 of the 1,985 were scraped with a full bio page; the other 4
-- are known only by their id, so has_bio is false and their attribute
-- columns are NULL. All four are early MVP winners the raw data never even
-- names — they exist so mvp_winners has something valid to point at.
create table processed.players (
    player_id                 varchar(12)  not null,
    -- NULL for four MVP winners whose name appears nowhere in the raw data.
    player_name               text,
    has_bio                   boolean      not null,

    -- ── bio attributes: populated only when has_bio is true ──────────────
    -- The player's first listed position, as the short code the season and
    -- roster pages use. 'G' and 'F' are not missing detail: the source lists
    -- players from before the five-position split at plain Guard or Forward,
    -- and rosters.position_primary already holds them that way.
    primary_position          varchar(2),
    shoots                    varchar(8),
    height_cm                 numeric(5,1),
    weight_kg                 numeric(5,1),
    -- birth_year/month/day are the source's three separate fields;
    -- birth_date is the same fact as one date. Both are kept so a query can
    -- use whichever is convenient.
    birth_year                integer,
    birth_month               integer,
    birth_day                 integer,
    birth_date                date,
    college                   text,
    experience_seasons        integer,
    nba_debut_date            date,
    nba_debut_year            integer,
    draft_year                integer,
    -- The drafting franchise as free text. Not a team_id: the source names a
    -- club as it was called on draft night, which no longer maps cleanly.
    draft_team_name           text,
    -- NULL for undrafted players (579 of the 1,981 with a bio).
    draft_round               integer,
    draft_round_pick          integer,
    draft_overall_pick        integer,

    -- ── career totals from the bio page, present for 1,980 players ──────
    career_games              integer,
    career_points             numeric(5,1),
    career_total_rebound_pct  numeric(5,1),
    career_assists_pct        numeric(5,1),
    career_field_goal_pct     numeric(5,1),
    career_three_point_pct    numeric(5,1),
    career_free_throw_pct     numeric(5,1),
    career_effective_fg_pct   numeric(5,1),
    career_per                numeric(5,1),
    career_win_shares         numeric(5,1),

    constraint pk_players primary key (player_id),
    constraint ck_players_primary_position
        check (primary_position in ('PG', 'SG', 'SF', 'PF', 'C', 'G', 'F')),
    constraint ck_players_shoots
        check (shoots in ('right', 'left', 'both')),
    -- has_bio is the definition of "we have this player's bio page", so a row
    -- flagged false must not carry bio attributes.
    constraint ck_players_bio_flag
        check (
            has_bio
            or (
                primary_position is null
                and height_cm is null
                and weight_kg is null
                and birth_date is null
                and nba_debut_date is null
                and draft_year is null
            )
        )
);


-- One row per NBA season from 1946-47 to 2025-26, so every fact table has a
-- season to point at.
create table processed.seasons (
    -- Ending year: 2025 is the 2024-25 season.
    season        integer     not null,
    -- The same season written the way Basketball-Reference prints it.
    season_label  varchar(8)  not null,
    start_year    integer     not null,
    -- True when the season has a row in season_awards. Currently true for
    -- all 80, so it distinguishes nothing today — it is kept because the
    -- awards scrape and the season list are built from different pages and
    -- have disagreed before.
    has_awards    boolean     not null,

    constraint pk_seasons primary key (season),
    constraint ck_seasons_ending_year check (season = start_year + 1),
    constraint ck_seasons_range check (season between 1947 and 2100)
);


-- ============================================================================
-- CHILDREN OF THE DIMENSIONS
-- ============================================================================

-- A player's listed positions, one row per position instead of six repeating
-- columns. slot 1 is the primary position, matching players.primary_position.
create table processed.player_positions (
    player_id      varchar(12)  not null,
    slot           integer      not null,
    -- Spelled out as the bio page writes it, e.g. "Point Guard".
    position       varchar(16)  not null,
    -- The same position as the short code the season tables use, so it joins
    -- to player_season_stats.position. 'G' and 'F' belong to players from
    -- before the five-position split, who predate that table entirely and so
    -- join to nothing in it — correctly.
    position_code  varchar(2)   not null,

    constraint pk_player_positions primary key (player_id, slot),
    constraint fk_player_positions_player
        foreign key (player_id) references processed.players (player_id),
    constraint ck_player_positions_slot check (slot >= 1),
    constraint ck_player_positions_code
        check (position_code in ('PG', 'SG', 'SF', 'PF', 'C', 'G', 'F'))
);


-- One row per season per league: who won the title, and the season's award
-- and statistical leaders. Keyed by (season, league) because the nine ABA
-- seasons have both an NBA and an ABA champion.
create table processed.season_awards (
    season              integer     not null,
    league              varchar(4)  not null,
    champion_team_id    varchar(4)  not null,

    -- The remaining columns are display names as the source prints them
    -- ("S. Castle"), not keys. They cannot be joined to players. Where a real
    -- key exists for the same fact, it lives in mvp_winners instead.
    rookie_of_the_year  text,
    most_points         text,
    most_rebounds       text,
    most_assists        text,
    most_winshares      text,

    constraint pk_season_awards primary key (season, league),
    constraint fk_season_awards_season
        foreign key (season) references processed.seasons (season),
    constraint fk_season_awards_champion
        foreign key (champion_team_id) references processed.teams (team_id),
    constraint ck_season_awards_league check (league in ('NBA', 'ABA', 'BAA'))
);


-- ============================================================================
-- FACTS
-- ============================================================================

-- Who was on which roster. Scope worth knowing before using it: this covers
-- the CHAMPION team's roster only, for every season from 1946-47 through
-- 2017-18 (both champions in the ABA seasons) — but all 30 rosters for each
-- season from 2018-19 through 2025-26. So it is league-wide exactly over the
-- eight seasons the stat tables cover, and champions-only before that. A
-- per-team average over the early seasons is a fact about champions, not
-- about the league.
create table processed.rosters (
    season              integer      not null,
    team_id             varchar(4)   not null,
    player_id           varchar(12)  not null,
    player_name         text         not null,
    -- The annotation the source appends to a name, e.g. "TW" for a two-way
    -- contract. Currently NULL for ALL 6,291 rows: the roster pages this
    -- scrape reads carry no annotations at all. The column is kept because
    -- the parsing is real and the source has published these before — but
    -- treat it as empty, not as "nobody is on a two-way contract".
    roster_note         varchar(8),
    -- As printed on the roster page: "G", "F-C", "PG", ...
    position            varchar(4)   not null,
    position_primary    varchar(2)   not null,
    -- NULL when the player is listed at a single position.
    position_secondary  varchar(2),
    height_cm           numeric(5,1) not null,
    weight_kg           numeric(5,1),
    birth_date          date,
    -- Two-letter country code parsed from the source's flag column.
    birth_country       varchar(2)   not null,
    -- Seasons of NBA experience BEFORE this one. 0 means rookie.
    experience_seasons  integer      not null,
    college             text,

    constraint pk_rosters primary key (season, team_id, player_id),
    constraint fk_rosters_season
        foreign key (season) references processed.seasons (season),
    constraint fk_rosters_team
        foreign key (team_id) references processed.teams (team_id),
    constraint fk_rosters_player
        foreign key (player_id) references processed.players (player_id),
    constraint ck_rosters_experience check (experience_seasons >= 0),
    constraint ck_rosters_height check (height_cm > 0)
);


-- Season box-score totals per player, 2018-19 through 2025-26.
--
-- Traded players keep every stint. A player who stayed at one club has a
-- single row with stint = 1. A player traded mid-season has one row per club
-- (stint 1..n) PLUS a combined season total at stint = 0 carrying
-- team_id = 'tot'.
--
-- is_primary marks exactly one row per player-season — the combined row where
-- there is one, otherwise the player's only row. `where is_primary` gives
-- 4,466 rows, one per player-season: use it for any per-player analysis, and
-- use the stint rows only when the question is about a specific club.
create table processed.player_season_stats (
    season                    integer      not null,
    player_id                 varchar(12)  not null,
    stint                     integer      not null,
    is_primary                boolean      not null,
    team_id                   varchar(4)   not null,
    -- The source page's display order, not a fact about the player.
    rank                      integer      not null,
    age                       integer      not null,
    position                  varchar(2)   not null,

    games_played              integer      not null,
    games_started             integer      not null,
    minutes_played            integer      not null,

    field_goals_made          integer      not null,
    field_goals_attempted     integer      not null,
    -- Percentage columns are NULL, not 0, when the player took no shots of
    -- that kind — 0 attempts has no percentage.
    field_goal_pct            numeric(5,3),
    three_pointers_made       integer      not null,
    three_pointers_attempted  integer      not null,
    three_point_pct           numeric(5,3),
    two_pointers_made         integer      not null,
    two_pointers_attempted    integer      not null,
    two_point_pct             numeric(5,3),
    -- Field goal percentage adjusted for a three being worth more than a two,
    -- so it can exceed 1.0.
    effective_fg_pct          numeric(5,3),
    free_throws_made          integer      not null,
    free_throws_attempted     integer      not null,
    free_throw_pct            numeric(5,3),

    offensive_rebounds        integer      not null,
    defensive_rebounds        integer      not null,
    total_rebounds            integer      not null,
    assists                   integer      not null,
    steals                    integer      not null,
    blocks                    integer      not null,
    turnovers                 integer      not null,
    personal_fouls            integer      not null,
    points                    integer      not null,
    triple_doubles            integer      not null,

    constraint pk_player_season_stats primary key (season, player_id, stint),
    constraint fk_player_season_stats_season
        foreign key (season) references processed.seasons (season),
    constraint fk_player_season_stats_player
        foreign key (player_id) references processed.players (player_id),
    constraint fk_player_season_stats_team
        foreign key (team_id) references processed.teams (team_id),
    -- The combined row and the 'tot' pseudo-team are the same fact, so one
    -- can never appear without the other.
    constraint ck_player_season_stats_tot_stint
        check ((stint = 0) = (team_id = 'tot')),
    constraint ck_player_season_stats_games
        check (
            games_played >= 1
            and games_started between 0 and games_played
            and minutes_played >= 0
        ),
    constraint ck_player_season_stats_shooting
        check (
            field_goals_made <= field_goals_attempted
            and three_pointers_made <= three_pointers_attempted
            and two_pointers_made <= two_pointers_attempted
            and free_throws_made <= free_throws_attempted
        )
);


-- Basketball-Reference's advanced metrics for the same 5,758 player-season
-- stints, from the advanced page of the same seasons.
--
-- The descriptive columns (age, position, games, minutes) are deliberately
-- NOT repeated here — they are identical to player_season_stats, which this
-- table joins to on (season, player_id, stint). That join is a foreign key,
-- so an advanced row can never exist without its box-score row.
--
-- Scale warning: the percentage columns below are on a 0-100 scale
-- (usage_percentage 28.4 means 28.4%), unlike the 0-1 shooting fractions in
-- player_season_stats. That difference comes from the source pages.
create table processed.player_advanced_stats (
    season                         integer      not null,
    player_id                      varchar(12)  not null,
    stint                          integer      not null,
    is_primary                     boolean      not null,
    team_id                        varchar(4)   not null,

    -- PER: league-average is 15.0 by construction.
    player_efficiency_rate         numeric(5,1) not null,
    -- Held as a 0-1 fraction; can exceed 1.0 for the same reason eFG% can.
    true_shooting_percentage       numeric(5,3),
    -- Share of a player's shots that were threes / free throws drawn per
    -- field-goal attempt. NULL when the player took no shots.
    three_point_attempt_rate       numeric(5,3),
    free_throw_attempt_rate        numeric(5,3),

    -- 0-100 scale: share of the available events the player accounted for
    -- while on the floor.
    offensive_rebound_percentage   numeric(5,1) not null,
    defensive_rebound_percentage   numeric(5,1) not null,
    total_rebound_percentage       numeric(5,1) not null,
    assist_percentage              numeric(5,1) not null,
    steal_percentage               numeric(5,1) not null,
    block_percentage               numeric(5,1) not null,
    turnover_percentage            numeric(5,1),
    usage_percentage               numeric(5,1) not null,

    -- Estimated wins the player produced. Can be negative.
    offensive_win_shares           numeric(5,1) not null,
    defensive_win_shares           numeric(5,1) not null,
    win_shares                     numeric(5,1) not null,
    win_shares_per_48_minutes      numeric(5,3) not null,

    -- Points per 100 possessions above a league-average player.
    offensive_box_plus_minus       numeric(5,1) not null,
    defensive_box_plus_minus       numeric(5,1) not null,
    box_plus_minus                 numeric(5,1) not null,
    value_over_replacement_player  numeric(5,1) not null,

    constraint pk_player_advanced_stats primary key (season, player_id, stint),
    constraint fk_player_advanced_stats_box_score
        foreign key (season, player_id, stint)
        references processed.player_season_stats (season, player_id, stint),
    constraint fk_player_advanced_stats_season
        foreign key (season) references processed.seasons (season),
    constraint fk_player_advanced_stats_player
        foreign key (player_id) references processed.players (player_id),
    constraint fk_player_advanced_stats_team
        foreign key (team_id) references processed.teams (team_id),
    constraint ck_player_advanced_stats_tot_stint
        check ((stint = 0) = (team_id = 'tot')),
    constraint ck_player_advanced_stats_percentages
        check (
            offensive_rebound_percentage between 0 and 100
            and defensive_rebound_percentage between 0 and 100
            and total_rebound_percentage between 0 and 100
            and assist_percentage between 0 and 100
            and steal_percentage between 0 and 100
            and block_percentage between 0 and 100
            and usage_percentage between 0 and 100
            and (turnover_percentage is null
                 or turnover_percentage between 0 and 100)
        )
);


-- Team season totals, 1949-50 through 2025-26.
--
-- Two things to know before averaging over this table:
--   * Every season here has now been played: all 30 rows of 2025-26 carry a
--     full 82 games. Earlier builds kept that season at games = 0 as a
--     placeholder, so older notebooks may still filter `where games > 0`;
--     that filter is now a no-op rather than a correction.
--   * Columns are NULL where the era did not record the statistic — there is
--     no three-point data before 1979-80, and no league-wide steals, blocks
--     or offensive/defensive rebounds before 1973-74. Turnovers go league-
--     wide in 1970-71. Those three have a handful of stray early rows (one
--     or two clubs reporting ahead of the league), so test for completeness
--     by season rather than trusting the first non-NULL year. One row
--     (blb, 1954-55) has no totals at all: the franchise folded mid-season.
create table processed.team_season_stats (
    season                    integer     not null,
    team_id                   varchar(4)  not null,
    -- The source page's display rank within the season.
    rank                      integer     not null,

    games                     integer,
    minutes_played            integer,

    field_goals_made          integer,
    field_goals_attempted     integer,
    field_goal_pct            numeric(5,3),
    three_pointers_made       integer,
    three_pointers_attempted  integer,
    three_point_pct           numeric(5,3),
    two_pointers_made         integer,
    two_pointers_attempted    integer,
    two_point_pct             numeric(5,3),
    free_throws_made          integer,
    free_throws_attempted     integer,
    free_throw_pct            numeric(5,3),

    offensive_rebounds        integer,
    defensive_rebounds        integer,
    total_rebounds            integer,
    assists                   integer,
    steals                    integer,
    blocks                    integer,
    turnovers                 integer,
    personal_fouls            integer,
    points                    integer,

    constraint pk_team_season_stats primary key (season, team_id),
    constraint fk_team_season_stats_season
        foreign key (season) references processed.seasons (season),
    constraint fk_team_season_stats_team
        foreign key (team_id) references processed.teams (team_id),
    constraint ck_team_season_stats_rank check (rank >= 1),
    -- 0 is allowed, not expected: it is how a scraped-but-unplayed season
    -- lands. No row carries it today.
    constraint ck_team_season_stats_games check (games >= 0),
    constraint ck_team_season_stats_shooting
        check (
            field_goals_made <= field_goals_attempted
            and free_throws_made <= free_throws_attempted
        )
);


-- The "Michael Jordan Trophy" — the season MVP, one row per season from
-- 1955-56 through 2025-26, with the per-game line the award was won on.
-- 71 awards shared between 37 players.
create table processed.mvp_winners (
    season             integer      not null,
    league             varchar(4)   not null,
    player_id          varchar(12)  not null,
    team_id            varchar(4)   not null,
    age                integer      not null,
    games              integer      not null,

    minutes_per_game   numeric(5,1) not null,
    points_per_game    numeric(5,1) not null,
    rebounds_per_game  numeric(5,1) not null,
    assists_per_game   numeric(5,1) not null,
    -- Steals and blocks were not recorded before 1973-74: NULL for 18 seasons.
    steals_per_game    numeric(5,1),
    blocks_per_game    numeric(5,1),

    field_goal_pct     numeric(5,3) not null,
    -- No three-point line before 1979-80: NULL for 24 seasons.
    three_point_pct    numeric(5,3),
    free_throw_pct     numeric(5,3) not null,
    win_shares         numeric(5,1) not null,
    win_shares_per_48  numeric(5,3) not null,

    constraint pk_mvp_winners primary key (season, league),
    constraint fk_mvp_winners_season
        foreign key (season) references processed.seasons (season),
    constraint fk_mvp_winners_player
        foreign key (player_id) references processed.players (player_id),
    constraint fk_mvp_winners_team
        foreign key (team_id) references processed.teams (team_id),
    constraint ck_mvp_winners_league check (league in ('NBA', 'ABA', 'BAA')),
    constraint ck_mvp_winners_games check (games >= 0 and age >= 0)
);


-- Everyone who received an MVP vote, 2018-19 through 2025-26, with the vote
-- tally. The winner also appears here at rank 1.
create table processed.mvp_candidates (
    season             integer      not null,
    player_id          varchar(12)  not null,
    rank               integer      not null,
    -- True when this player shared the rank with another (the source writes
    -- "10T"); the tie marker is stored separately from the number.
    tie                boolean      not null,
    age                integer      not null,
    -- Nullable because the source has listed a candidate without a club
    -- before; every one of the current 93 rows resolves to a real team.
    team_id            varchar(4),

    first_place_votes  integer      not null,
    points_won         integer      not null,
    points_max         integer      not null,
    -- points_won / points_max, so 1.0 is a unanimous MVP.
    share              numeric(5,3) not null,

    -- Per-game line for the season, abbreviated as the source names them.
    games              integer      not null,
    mp                 numeric(5,1) not null,
    pts                numeric(5,1) not null,
    trb                numeric(5,1) not null,
    ast                numeric(5,1) not null,
    stl                numeric(5,1) not null,
    blk                numeric(5,1) not null,
    fg_pct             numeric(5,3) not null,
    three_pct          numeric(5,3),
    ft_pct             numeric(5,3) not null,
    ws                 numeric(5,1) not null,
    ws_per_48          numeric(5,3) not null,

    constraint pk_mvp_candidates primary key (season, player_id),
    constraint fk_mvp_candidates_season
        foreign key (season) references processed.seasons (season),
    constraint fk_mvp_candidates_player
        foreign key (player_id) references processed.players (player_id),
    constraint fk_mvp_candidates_team
        foreign key (team_id) references processed.teams (team_id),
    constraint ck_mvp_candidates_rank check (rank >= 1),
    constraint ck_mvp_candidates_votes
        check (
            first_place_votes >= 0
            and points_won between 0 and points_max
            and share between 0 and 1
        )
);
