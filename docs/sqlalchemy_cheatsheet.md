# SQLAlchemy Query Cheatsheet 

This sheet focuses only on **reading data** with SQLAlchemy 2.x style queries.

1. Decide what you want (`select(...)`).
2. Tell SQLAlchemy which tables/joins supply that data.
3. Filter, group, sort, and trim the results.
4. Run the statement with `session.execute(...)` or `pd.read_sql(...)`.

## Getting Ready
```python
from datetime import date, timedelta

from sqlalchemy import select, func, case, literal_column, text
from sqlalchemy.orm import aliased


session = SessionLocal()
```

## Query Flow at a Glance
1. **Select**: `select(columns_or_models)`
2. **From / Join**: `.join(...)`, `.select_from(...)`, `.outerjoin(...)`
3. **Filter Rows**: `.where(condition1, condition2)`
4. **Group** (optional): `.group_by(...)`, `.having(...)`
5. **Order & Limit**: `.order_by(...)`, `.limit(...)`, `.offset(...)`
6. **Execute**: `session.execute(stmt)` (or `pd.read_sql(stmt, session.get_bind())`)

## 50 Query Examples (Each with Simple Steps)

### Example 1 — Fetch every player row
```python
stmt = select(Player)
rows = session.execute(stmt).scalars().all()
```
**Steps**
1. Select the whole `Player` model.  
2. Execute and use `.scalars()` to unwrap ORM objects.  
3. Collect all players into a Python list.

### Example 2 — Grab only player names
```python
stmt = select(Player.player_name)
names = session.execute(stmt).scalars().all()
```
**Steps**
1. Select exactly one column.  
2. Run the statement.  
3. `.scalars()` returns a clean list of strings.

### Example 3 — Filter by one field
```python
stmt = select(Player.player_name).where(Player.shoots == "right")
```
**Steps**
1. Select player names.  
2. Add `.where` with a simple equality check.  
3. Execute to get only right-handed shooters.

### Example 4 — Filter with multiple AND conditions
```python
stmt = select(Player.player_name).where(
    Player.position_1 == "point guard",
    Player.age <= 28,
)
```
**Steps**
1. Put every condition inside `.where`.  
2. Commas act like SQL `AND`.  
3. Run it to find young point guards.

### Example 5 — Filter with OR
```python
stmt = select(Player.player_name).where(
    or_(Player.position_1 == "center", Player.position_2 == "center")
)
```
**Steps**
1. Import `or_` from SQLAlchemy.  
2. Combine conditions inside `or_()`.  
3. Fetch players who play center anywhere.

### Example 6 — Filter with IN
```python
team_ids = ["DAL", "MIA", "DEN"]
stmt = select(Player.player_name).where(Player.team_id.in_(team_ids))
```
**Steps**
1. Prepare a Python list of team IDs.  
2. Use `.in_()` instead of many `OR`s.  
3. Execute to pull only players from those teams.

### Example 7 — Case-insensitive name search
```python
stmt = select(Player.player_name).where(Player.player_name.ilike("%luka%"))
```
**Steps**
1. Use `.ilike()` for case-insensitive `LIKE`.  
2. Wrap search text with `%` wildcards.  
3. Execute to find any player whose name contains “luka”.

### Example 8 — Sort alphabetically
```python
stmt = select(Player.player_name).order_by(Player.player_name)
```
**Steps**
1. Select one column.  
2. Add `.order_by(...)`.  
3. Run it to get names in ascending order.

### Example 9 — Sort descending
```python
stmt = select(Player.player_name, Player.career_points).order_by(Player.career_points.desc())
```
**Steps**
1. Select both name and total points.  
2. Call `.desc()` to reverse the sort.  
3. Execute to see highest scorers first.

### Example 10 — Limit results
```python
stmt = (
    select(Player.player_name)
    .order_by(Player.player_name)
    .limit(5)
)
```
**Steps**
1. Build the usual select + order.  
2. Add `.limit(5)` to keep the first five rows.  
3. Execute for a quick preview list.

### Example 11 — Pagination with offset
```python
page_size = 20
page = 3
stmt = (
    select(Player.player_name)
    .order_by(Player.player_name)
    .limit(page_size)
    .offset(page_size * (page - 1))
)
```
**Steps**
1. Decide `page_size` and `page` number.  
2. Use `.offset` to skip previous pages.  
3. Execute to fetch the third batch of 20 names.

### Example 12 — Remove duplicates with DISTINCT
```python
stmt = select(Player.position_1).distinct().order_by(Player.position_1)
```
**Steps**
1. Call `.distinct()` right after `select`.  
2. Order to keep the list tidy.  
3. Execute to see each primary position exactly once.

### Example 13 — Computed column (points per game)
```python
ppg = (PlayerStat.points / PlayerStat.games_played).label("ppg")
stmt = select(Player.player_name, ppg).join(Player.playerstats)
```
**Steps**
1. Build an expression and label it.  
2. Join `Player` to `PlayerStat`.  
3. Select name plus the computed “ppg” value.

### Example 14 — Sum points per player
```python
stmt = (
    select(Player.player_name, func.sum(PlayerStat.points).label("total_points"))
    .join(Player.playerstats)
    .group_by(Player.player_name)
)
```
**Steps**
1. Select name and a `SUM`.  
2. Join stats to players.  
3. Group by player name so SQL can add up their points.

### Example 15 — Keep only high scorers with HAVING
```python
stmt = (
    select(Player.player_name, func.sum(PlayerStat.points).label("total_points"))
    .join(Player.playerstats)
    .group_by(Player.player_name)
    .having(func.sum(PlayerStat.points) > 2000)
)
```
**Steps**
1. Start from the grouped sum query.  
2. Add `.having(...)` to filter aggregated rows.  
3. Execute to see only players above 2000 total points.

### Example 16 — Count rows directly
```python
stmt = select(func.count()).select_from(PlayerStat)
total_rows = session.execute(stmt).scalar_one()
```
**Steps**
1. Switch the FROM table with `.select_from()`.  
2. Use `func.count()` without columns.  
3. `.scalar_one()` pulls the single number result.

### Example 17 — Count distinct teams
```python
stmt = select(func.count(func.distinct(Player.team_id)))
team_count = session.execute(stmt).scalar_one()
```
**Steps**
1. Wrap `Player.team_id` with `func.distinct`.  
2. Count the distinct values.  
3. Execute for the total number of teams in the players table.

### Example 18 — Average rebounds per player
```python
stmt = (
    select(Player.player_name, func.avg(PlayerStat.total_rebounds).label("avg_reb"))
    .join(Player.playerstats)
    .group_by(Player.player_name)
)
```
**Steps**
1. Select name plus `AVG` of rebounds.  
2. Join stats, group by player.  
3. Execute for per-player rebound averages.

### Example 19 — Filter by date range
```python
stmt = (
    select(PlayerStat)
    .where(
        PlayerStat.game_date.between(date(2025, 1, 1), date(2025, 3, 31))
    )
)
```
**Steps**
1. Select the whole stat row.  
2. Use `.between(start, end)` on a date column.  
3. Execute to get Q1 2025 games.

### Example 20 — Extract year from a date column
```python
stmt = select(PlayerStat).where(func.year(PlayerStat.game_date) == 2025)
```
**Steps**
1. Call a database-specific date function via `func`.  
2. Compare to the target year.  
3. Execute to fetch all 2025 stat rows.

### Example 21 — Join players to their team info
```python
stmt = (
    select(Player.player_name, Team.team_name)
    .join(Player.team)
)
```
**Steps**
1. Select desired columns from both tables.  
2. Use the ORM relationship `Player.team`.  
3. Execute to pair players with team names.

### Example 22 — Chain two joins
```python
stmt = (
    select(Player.player_name, Team.team_name, TeamPerformance.points)
    .join(Player.team)
    .join(Team.performances)
    .where(TeamPerformance.season == 2025)
)
```
**Steps**
1. Start from players, then hop to teams, then team stats.  
2. Each `.join` follows the relationship graph.  
3. Filter by season after the joins.

### Example 23 — Join with a manual ON clause
```python
stmt = (
    select(Player.player_name, PlayerStat.points)
    .join(PlayerStat, Player.player_id == PlayerStat.player_id)
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Spell out the join condition yourself.  
2. Useful when foreign keys or relationships are missing.  
3. Execute to read 2025 points with explicit ON logic.

### Example 24 — Left outer join
```python
stmt = (
    select(Player.player_name, PlayerStat.points)
    .outerjoin(Player.playerstats)
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Replace `.join` with `.outerjoin`.  
2. Keeps players even if they lack 2025 stats (they get `None`).  
3. Execute to see missing data clearly.

### Example 25 — Self-join with aliases
```python
teammate = aliased(Player)
stmt = (
    select(Player.player_name, teammate.player_name.label("teammate"))
    .join(Roster, Roster.player_id == Player.player_id)
    .join(teammate, teammate.player_id == Roster.teammate_id)
)
```
**Steps**
1. Create `aliased(Player)` for the second appearance.  
2. Join through a link table (`Roster`).  
3. Execute to get player/teammate pairs.

### Example 26 — Conditional column with CASE
```python
role = case(
    (Player.position_1 == "center", "big"),
    else_="guard_or_wing",
).label("role")
stmt = select(Player.player_name, role)
```
**Steps**
1. Build a CASE expression using `case`.  
2. Label it so the output column has a name.  
3. Execute to classify each player.

### Example 27 — Coalesce missing data
```python
stmt = select(
    Player.player_name,
    func.coalesce(PlayerStat.three_point_pct, 0).label("three_pct")
).join(Player.playerstats)
```
**Steps**
1. Wrap the nullable column in `func.coalesce`.  
2. Provide a fallback (0).  
3. Execute to avoid `None` values in output.

### Example 28 — Subquery in a WHERE IN clause
```python
scoring_team_ids = (
    select(TeamPerformance.team_id)
    .where(
        TeamPerformance.season == 2025,
        TeamPerformance.points > 9000,
    )
)
stmt = select(Team.team_name).where(Team.team_id.in_(scoring_team_ids))
```
**Steps**
1. Build a subquery that returns team IDs.  
2. Use it inside `.in_()`.  
3. Execute to list only high-scoring teams.

### Example 29 — Scalar subquery for league average minutes
```python
avg_minutes = (
    select(func.avg(PlayerStat.minutes_played))
    .where(PlayerStat.season == 2025)
    .scalar_subquery()
)
stmt = (
    select(Player.player_name, PlayerStat.minutes_played)
    .join(Player.playerstats)
    .where(PlayerStat.season == 2025, PlayerStat.minutes_played > avg_minutes)
)
```
**Steps**
1. Turn the average calculation into `.scalar_subquery()`.  
2. Use it like a number inside `.where`.  
3. Execute to see who plays above-average minutes.

### Example 30 — EXISTS to test for related data
```python
has_2025_stats = (
    select(1)
    .where(PlayerStat.player_id == Player.player_id, PlayerStat.season == 2025)
)
stmt = select(Player.player_name).where(has_2025_stats.exists())
```
**Steps**
1. Build a subquery that links stats back to the outer player.  
2. Call `.exists()` on it.  
3. Execute to fetch players who appear in 2025 stats.

### Example 31 — NOT EXISTS pattern
```python
no_stats = (
    select(1)
    .where(PlayerStat.player_id == Player.player_id)
)
stmt = select(Player.player_name).where(~no_stats.exists())
```
**Steps**
1. Same idea as Example 30.  
2. Use `~` (bitwise NOT) to invert `exists()`.  
3. Execute to find players with zero stat rows.

### Example 32 — Subquery in the FROM clause
```python
player_totals = (
    select(
        PlayerStat.player_id,
        func.sum(PlayerStat.points).label("points")
    )
    .group_by(PlayerStat.player_id)
    .subquery()
)
stmt = (
    select(Player.player_name, player_totals.c.points)
    .join(player_totals, player_totals.c.player_id == Player.player_id)
)
```
**Steps**
1. Aggregate inside a subquery.  
2. Join the subquery to `Player` to attach names.  
3. Execute for name-plus-total-points rows.

### Example 33 — Simple CTE for clarity
```python
recent_games = (
    select(PlayerStat.player_id, PlayerStat.points)
    .where(PlayerStat.game_date >= date.today() - timedelta(days=30))
    .cte("recent_games")
)
stmt = (
    select(recent_games.c.player_id, func.avg(recent_games.c.points).label("avg_recent"))
    .group_by(recent_games.c.player_id)
)
```
**Steps**
1. Wrap a filter in `.cte("name")`.  
2. Select from that CTE in the main query.  
3. Execute to get 30-day scoring averages.

### Example 34 — CTE reused twice
```python
per_game = (
    select(
        PlayerStat.player_id,
        (PlayerStat.points / PlayerStat.games_played).label("ppg"),
    )
    .cte("per_game")
)
stmt = (
    select(
        Player.player_name,
        func.avg(per_game.c.ppg).label("avg_ppg"),
    )
    .join(per_game, per_game.c.player_id == Player.player_id)
    .group_by(Player.player_name)
)
```
**Steps**
1. Compute per-game scoring once inside a CTE.  
2. Join the CTE to `Player`.  
3. Group by player to average the per-game metric.

### Example 35 — Recursive CTE for a simple depth walk
```python
cte = (
    select(Team.team_id, Team.parent_team_id, literal_column("0").label("depth"))
    .where(Team.team_id == "DAL")
    .cte(name="team_tree", recursive=True)
)
cte = cte.union_all(
    select(Team.team_id, Team.parent_team_id, (cte.c.depth + 1))
    .join(cte, Team.parent_team_id == cte.c.team_id)
)
stmt = select(cte)
```
**Steps**
1. Anchor part grabs the starting team (`DAL`).  
2. Recursive part climbs parent relationships.  
3. Final select lists the hierarchy with depth levels.

### Example 36 — Window ROW_NUMBER
```python
stmt = (
    select(
        PlayerStat.player_id,
        PlayerStat.points,
        func.row_number().over(order_by=PlayerStat.points.desc()).label("rank"),
    )
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Add a window function via `.over(...)`.  
2. Order within the window for ranking.  
3. Execute to rank 2025 stat rows by points.

### Example 37 — Window running total per player
```python
stmt = (
    select(
        PlayerStat.player_id,
        PlayerStat.game_date,
        func.sum(PlayerStat.points)
        .over(partition_by=PlayerStat.player_id, order_by=PlayerStat.game_date)
        .label("running_points"),
    )
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Partition by player so each player resets their own sum.  
2. Order by date to create the running total.  
3. Execute to see cumulative scoring after each game.

### Example 38 — Window rank per team (dense)
```python
stmt = (
    select(
        PlayerStat.team_id,
        PlayerStat.player_id,
        func.dense_rank().over(
            partition_by=PlayerStat.team_id,
            order_by=PlayerStat.points.desc(),
        ).label("team_rank"),
    )
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Partition by `team_id`.  
2. Order by points to rank players inside each team.  
3. Execute to find each player’s scoring rank on their team.

### Example 39 — Top scorer per team using window + filter
```python
top_scorers = (
    select(
        PlayerStat.team_id,
        PlayerStat.player_id,
        func.row_number().over(
            partition_by=PlayerStat.team_id,
            order_by=PlayerStat.points.desc(),
        ).label("rownum"),
    )
    .where(PlayerStat.season == 2025)
).subquery()
stmt = select(top_scorers).where(top_scorers.c.rownum == 1)
```
**Steps**
1. Build a subquery that ranks players inside each team.  
2. Filter to rows where `rownum == 1`.  
3. Execute to keep only each team’s top scorer.

### Example 40 — Combine window result with player names
```python
ranked = (
    select(
        PlayerStat.player_id,
        func.row_number().over(order_by=PlayerStat.points.desc()).label("rank"),
    )
    .where(PlayerStat.season == 2025)
    .subquery()
)
stmt = (
    select(Player.player_name, ranked.c.rank)
    .join(ranked, ranked.c.player_id == Player.player_id)
)
```
**Steps**
1. Compute ranks in a subquery.  
2. Join back to `Player` for names.  
3. Execute to see names with their overall rank.

### Example 41 — Use `select_from` to change the starting table
```python
stmt = (
    select(PlayerStat.player_id, PlayerStat.points)
    .select_from(PlayerStat)
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Explicitly set the FROM table (`PlayerStat`).  
2. This is handy when the select columns don’t imply a single table.  
3. Execute normally.

### Example 42 — Order by multiple columns
```python
stmt = (
    select(Player.player_name, Player.career_points, Player.career_assists_pct)
    .order_by(Player.career_points.desc(), Player.career_assists_pct.desc())
)
```
**Steps**
1. Provide a list of columns to `.order_by`.  
2. SQL sorts by the first column, then the second to break ties.  
3. Execute to see consistent ordering.

### Example 43 — Combine AND and OR cleanly
```python
stmt = select(Player.player_name).where(
    and_(
        Player.age <= 28,
        or_(Player.position_1 == "point guard", Player.position_2 == "point guard"),
    )
)
```
**Steps**
1. Use `and_` and `or_` to spell out logic explicitly.  
2. Avoid mixing Python’s `and`/`or` with SQLAlchemy columns.  
3. Execute to get young guards.

### Example 44 — Use text fragment for advanced filter
```python
stmt = select(Player.player_name).where(text("players.career_win_shares > 50"))
```
**Steps**
1. Import `text` and pass raw SQL when the expression API is awkward.  
2. Be careful—this bypasses automatic quoting.  
3. Execute for players with high win shares.

### Example 45 — Hybrid expression or literal in select
```python
stmt = select(Player.player_name, literal_column("'NBA'").label("league"))
```
**Steps**
1. Use `literal_column` for a literal value at SQL level.  
2. Label it so the column has a friendly name.  
3. Execute to append a constant column to every row.

### Example 46 — Correlated subquery for latest stat
```python
latest_points = (
    select(PlayerStat.points)
    .where(
        PlayerStat.player_id == Player.player_id,
        PlayerStat.game_date == select(func.max(PlayerStat.game_date))
            .where(PlayerStat.player_id == Player.player_id)
            .scalar_subquery(),
    )
    .scalar_subquery()
)
stmt = select(Player.player_name, latest_points.label("latest_points"))
```
**Steps**
1. Inner scalar subquery finds each player’s latest game date.  
2. Outer scalar subquery grabs points from that game.  
3. Final select lists players with their most recent points.

### Example 47 — Conditional sum with CASE
```python
clutch_points = func.sum(
    case((PlayerStat.game_time_remaining <= 120, PlayerStat.points), else_=0)
).label("clutch_points")
stmt = (
    select(Player.player_name, clutch_points)
    .join(Player.playerstats)
    .group_by(Player.player_name)
)
```
**Steps**
1. Use `case` inside `sum` to count only points in the last two minutes.  
2. Join stats and group by player.  
3. Execute to see clutch scoring totals.

### Example 48 — Bucket minutes into tiers
```python
minutes_bucket = case(
    (PlayerStat.minutes_played >= 35, "workhorse"),
    (PlayerStat.minutes_played >= 20, "rotation"),
    else_="bench",
).label("minutes_tier")
stmt = (
    select(Player.player_name, minutes_bucket)
    .join(Player.playerstats)
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. Define tiers with multiple CASE branches.  
2. Label the tier column.  
3. Execute to describe each player’s usage tier per game.

### Example 49 — Percent of team points via CTE
```python
team_totals = (
    select(
        PlayerStat.team_id,
        func.sum(PlayerStat.points).label("team_points"),
    )
    .where(PlayerStat.season == 2025)
    .group_by(PlayerStat.team_id)
    .cte("team_totals")
)
stmt = (
    select(
        PlayerStat.player_id,
        (PlayerStat.points / team_totals.c.team_points).label("team_share"),
    )
    .join(team_totals, team_totals.c.team_id == PlayerStat.team_id)
    .where(PlayerStat.season == 2025)
)
```
**Steps**
1. CTE sums points per team.  
2. Join game rows to team totals.  
3. Compute each row’s share of team scoring.

### Example 50 — Load into pandas directly
```python
stmt = (
    select(Player.player_name, PlayerStat.points)
    .join(Player.playerstats)
    .where(PlayerStat.season == 2025)
)
df = pd.read_sql(stmt, session.get_bind())
```
**Steps**
1. Build the statement the same way as other examples.  
2. Call `pd.read_sql` with the statement and engine/connection.  
3. Work with the results in a pandas DataFrame.

Keep experimenting—swap columns, stack more conditions, or convert a query into its raw SQL with:
```python
print(stmt.compile(compile_kwargs={"literal_binds": True}))
```
Understanding these examples will make any SQLAlchemy query feel approachable, even the ones with subqueries, CTEs, or window functions.
