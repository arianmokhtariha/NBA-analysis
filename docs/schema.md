# Database Schema Overview

All curated tables are derived from Basketball-Reference data and cleaned via the pipeline in `data_analysis/data_preprocessing/01_data_cleaning_anoosha.py`. Columns and descriptions below map one-to-one with the exported CSVs in `data/data_clean/` and the SQLAlchemy models in `create_db/data_classes.py`.

---

## players
| Column | Type | Description |
| --- | --- | --- |
| `player_id` | varchar(20) | Basketball-Reference identifier (primary key) used across all referencing tables. |
| `player_name` | varchar(50) | Player full name as listed on Basketball-Reference; useful for human-readable displays or search. |
| `shoots` | varchar(20) | Dominant shooting hand (`"right"`, `"left"`, `"right_left"`) |
| `draft_team_name` | varchar(50) | Text name of the franchise that drafted the player (even if they never played for it). |
| `experience` | float | Seasons of NBA experience; contains `NaN` for rookies or players without logged seasons. |
| `nba_debut` | int | Season (end year) of the player's debut, e.g., `2013` for the 2012-13 season. |
| `position_1` | varchar(20) | Primary position tag parsed from Basketball-Reference (PG/SG/SF/PF/C), used in roster splits. |
| `position_2` | varchar(20) | Secondary position tag if available; `NaN` when the player is single-position. |
| `position_3` | varchar(20) | Tertiary position tag; sparsely populated. |
| `position_4` | varchar(20) | Quaternary position tag; sparsely populated. |
| `position_5` | varchar(20) | Quinary position tag; sparsely populated. |
| `position_6` | varchar(20) | Senary position tag; sparsely populated. |
| `draft_year` | int | Draft class season (ending year). |
| `height_cm` | float | Player height converted to centimeters from feet-inches. |
| `weight_kg` | float | Player weight converted to kilograms from pounds. |
| `age` | int | Age calculated relative to 2025 to align with player profiles. |
| `draft_round_pick_rank` | float | Draft round pick number; granularity preserved as float to retain `NaN` for undrafted players. |
| `draft_overall_pick_rank` | float | Draft overall pick number; `NaN` for undrafted players. |
| `career_points` | float | Career points per game average. |
| `career_total_rebound_pct` | float | Career rebound percentage (share of available rebounds secured). |
| `career_assists_pct` | float | Career assist percentage (share of teammate field goals assisted). |
| `career_field_goal_pct` | float | Career field-goal percentage. |
| `career_three_point_pct` | float | Career 3-point percentage. |
| `career_free_throw_pct` | float | Career free-throw percentage. |
| `career_effective_fg_pct` | float | Career effective field-goal percentage (accounts for 3P bonus). |
| `career_per` | float | Career Player Efficiency Rating (PER). |
| `career_win_shares` | float | Career cumulative Win Shares. |

---

## team_lookup
| Column | Type | Description |
| --- | --- | --- |
| `team_id` | varchar(20) | Basketball-Reference team identifier (primary key) shared by all tables referencing franchises. |
| `team_name` | varchar(50) | Long-form club name used for display or joining to external data. |

---

## player_stats
Per-season totals and traditional box-score stats for every player.

| Column | Type | Description |
| --- | --- | --- |
| `season` | int | Season end year (primary key component). |
| `rank` | int | League rank for the stat table (as published on Basketball-Reference). |
| `player_id` | varchar(20) | Player identifier (primary key component, FK → `players`). |
| `age` | int | Age during the listed season. |
| `team_id` | varchar(20) | Team code for the season; `"tot"` indicates the player's aggregated stats across multiple teams. |
| `position` | varchar(50) | Position abbreviation for the season (PG/SG/SF/PF/C or combinations). |
| `games_played` | int | Total games played. |
| `games_started` | int | Games started. |
| `minutes_played` | int | Total minutes logged. |
| `field_goals_made` | int | Made field goals. |
| `field_goals_attempted` | int | Field-goal attempts. |
| `field_goal_pct` | float | Field-goal percentage (FG%). |
| `three_pointers_made` | int | Made 3-point field goals. |
| `three_pointers_attempted` | int | 3-point attempts. |
| `three_point_pct` | float | 3-point percentage; some rows contain `NaN` if no attempts were recorded. |
| `two_pointers_made` | int | Made 2-point field goals. |
| `two_pointers_attempted` | int | 2-point attempts. |
| `two_point_pct` | float | 2-point percentage. |
| `effective_fg_pct` | float | Effective field-goal percentage (adds 3P bonus). |
| `free_throws_made` | int | Free throws made. |
| `free_throws_attempted` | int | Free-throw attempts. |
| `free_throw_pct` | float | Free-throw percentage. |
| `offensive_rebounds` | int | Offensive rebounds. |
| `defensive_rebounds` | int | Defensive rebounds. |
| `total_rebounds` | int | Total rebounds (offensive + defensive). |
| `assists` | int | Total assists. |
| `steals` | int | Total steals. |
| `blocks` | int | Total blocks. |
| `turnovers` | int | Total turnovers. |
| `personal_fouls` | int | Total personal fouls. |
| `points` | int | Total points scored. |
| `triple_doubles` | int | Number of triple-doubles recorded. |

---

## teams_performance
Team-level totals and percentages for each season.

| Column | Type | Description |
| --- | --- | --- |
| `rank` | float | League rank (float because some ranks were non-integers after cleaning). |
| `season` | int | Season end year (primary key component). |
| `team_id` | varchar(20) | Team identifier (primary key component, FK → `team_lookup`). |
| `games` | float | Games played (float to retain any partial rows during cleaning). |
| `minutes_played` | float | Team minutes logged. |
| `field_goals_made` | float | Team field-goal makes. |
| `field_goals_attempted` | float | Team field-goal attempts. |
| `field_goal_pct` | float | Team FG%. |
| `three_pointers_made` | float | Team 3PM. |
| `three_pointers_attempted` | float | Team 3PA. |
| `three_point_pct` | float | Team 3P%. |
| `two_pointers_made` | float | Team 2PM. |
| `two_pointers_attempted` | float | Team 2PA. |
| `two_point_pct` | float | Team 2P%. |
| `free_throws_made` | float | Team FTM. |
| `free_throws_attempted` | float | Team FTA. |
| `free_throw_pct` | float | Team FT%. |
| `offensive_rebounds` | float | Team offensive rebounds. |
| `defensive_rebounds` | float | Team defensive rebounds. |
| `total_rebounds` | float | Team total rebounds. |
| `assists` | float | Team assists. |
| `steals` | float | Team steals. |
| `blocks` | float | Team blocks. |
| `turnovers` | float | Team turnovers. |
| `personal_fouls` | float | Team personal fouls. |
| `points` | float | Team points scored. |

---

## season_stats
Season-wide award and accolade summary.

| Column | Type | Description |
| --- | --- | --- |
| `season` | int | Season end year (primary key). |
| `league` | varchar(20) | League abbreviation (NBA). |
| `champion_name` | varchar(50) | Championship team name (FK → `team_lookup.team_name`). |
| `mvp` | varchar(50) | Regular-season MVP. |
| `rookie_of_the_year` | varchar(50) | Rookie of the Year. |
| `most_points` | varchar(50) | Points-per-game leader. |
| `most_rebounds` | varchar(50) | Rebounds-per-game leader. |
| `most_assists` | varchar(50) | Assists-per-game leader. |
| `most_winshares` | varchar(50) | League leader in Win Shares. |

---

## rosters
Team rosters keyed by season.

| Column | Type | Description |
| --- | --- | --- |
| `season` | int | Season end year (primary key component, FK → `season_stats`). |
| `player_id` | varchar(20) | Player identifier (primary key component, FK → `players`). |
| `team_id` | varchar(20) | Team identifier (primary key component, FK → `team_lookup`). |
| `pos1` | varchar(50) | Primary roster position. |
| `pos2` | varchar(50) | Secondary position (may be blank). |

---

## advanced_stats
Advanced efficiency and impact metrics for each player season.

| Column | Type | Description |
| --- | --- | --- |
| `season` | int | Season end year (primary key component, FK → `season_stats`). |
| `player_id` | varchar(20) | Player identifier (primary key component, FK → `players`). |
| `player_efficiency_rate` | float | PER; per-minute production relative to league average. |
| `true_shooting_percentage` | float | TS%; shooting efficiency combining twos, threes and free throws. |
| `three_point_attempt_rate` | float | Ratio of 3PA to total FGA; shows perimeter volume. |
| `free_throw_attempt_rate` | float | Ratio of FTA to FGA; proxy for rim pressure and foul drawing. |
| `offensive_rebound_percentage` | float | ORB%; percent of available offensive rebounds collected. |
| `defensive_rebound_percentage` | float | DRB%; percent of available defensive boards collected. |
| `total_rebound_percentage` | float | TRB%; percent of all available boards collected. |
| `assist_percentage` | float | AST%; share of teammate field goals assisted while on the floor. |
| `steal_percentage` | float | STL%; steals generated per opponent possession. |
| `block_percentage` | float | BLK%; blocks recorded per opponent 2PA. |
| `turnover_percentage` | float | TOV%; turnovers per possession used. |
| `usage_percentage` | float | USG%; share of team possessions finished by the player. |
| `offensive_win_shares` | float | Offensive Win Shares; wins produced from offensive contribution. |
| `defensive_win_shares` | float | Defensive Win Shares; wins produced from defense. |
| `win_shares` | float | Total Win Shares (offense + defense). |
| `win_shares_per_48_minutes` | float | WS per 48 minutes; normalizes win shares for playing time. |
| `offensive_box_plus_minus` | float | OBPM; box-score-derived offensive impact per 100 possessions. |
| `defensive_box_plus_minus` | float | DBPM; defensive counterpart to OBPM. |
| `value_over_replacement_player` | float | VORP; total contribution above replacement level. |


---

## mvp_winners
Season MVP winners with per-game stats.

| Column | Type | Description |
| --- | --- | --- |
| `season` | int | Season end year (primary key component). |
| `league` | varchar(20) | League abbreviation (primary key component). |
| `player_id` | varchar(20) | Player identifier (FK → `players`). |
| `age` | int | Age during MVP season. |
| `team_id` | varchar(20) | Team identifier (FK → `team_lookup`). |
| `games` | int | Games played. |
| `minutes_per_game` | float | Minutes per game (MPG). |
| `points_per_game` | float | Points per game (PPG). |
| `rebounds_per_game` | float | Rebounds per game (RPG). |
| `assists_per_game` | float | Assists per game (APG). |
| `steals_per_game` | float | Steals per game (SPG). |
| `blocks_per_game` | float | Blocks per game (BPG). |
| `field_goal_pct` | float | Field-goal percentage (FG%). |
| `three_point_pct` | float | 3-point percentage (3P%). |
| `free_throw_pct` | float | Free-throw percentage (FT%). |
| `win_shares` | float | Total Win Shares generated in the MVP season. |
| `win_shares_per_48` | float | Win Shares per 48 minutes. |

---

## mvp_candidates
Voting results plus per-game production for every MVP ballot entry.

| Column | Type | Description |
| --- | --- | --- |
| `year` | int | Award voting year (primary key component). |
| `player_id` | varchar(20) | Player identifier (primary key component, FK → `players`). |
| `rank` | int | Final MVP ballot rank. |
| `tie` | boolean | Indicates whether the ballot position was shared via a tie. |
| `age` | int | Player age during the voting season. |
| `team_id` | varchar(20) | Team code registered for the ballot (FK → `team_lookup`). |
| `first_place_votes` | int | Number of first-place votes received. |
| `points_won` | int | Total voting points earned. |
| `points_max` | int | Maximum possible voting points in that season's ballot. |
| `share` | float | Voting share (`points_won / points_max`). |
| `games` | int | Games played in the voting season. |
| `mp` | float | Minutes per game. |
| `pts` | float | Points per game. |
| `trb` | float | Rebounds per game. |
| `ast` | float | Assists per game. |
| `stl` | float | Steals per game. |
| `blk` | float | Blocks per game. |
| `fg_pct` | float | Field-goal percentage. |
| `three_pct` | float | 3-point percentage. |
| `ft_pct` | float | Free-throw percentage. |
| `ws` | float | Win Shares accumulated that season. |
| `ws_per_48` | float | Win Shares per 48 minutes. |

