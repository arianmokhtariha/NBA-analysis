# The questions this project answers

The register of what we are asking of the data. Each entry states the question,
what it needs decided before it can be answered, and where the answer lives.

**These questions are deliberately not built into the database.** `analyst_ready`
is a general-purpose analytical layer — enriched, de-duplicated, feature-rich —
and every question below is answered by *querying* it, in the notebook that owns
the question. Nothing here has a table of its own.

That is the point. A question baked into a schema hides its own assumptions:
"top 50 scorers" becomes a row filter nobody can see, and the next question that
wants "top 50 by efficiency" has nowhere to go. Keeping the definitions in the
query keeps them visible, arguable, and cheap to change.

**This list is expected to grow.** Add a row, add a notebook. No schema change
is needed, and that is the whole design.

---

## Where the answer comes from

| Layer | Role |
| --- | --- |
| `analyst_ready.player_season` | One row per player per season — box score, advanced metrics, bio, club, honours. The base for every player question. |
| `analyst_ready.team_season` | One row per club per season — totals plus the derived rates, including the four factors. The base for every team question. |
| `analyst_ready.dim_player` / `dim_team` / `dim_season` | Who / which club / which year. |
| `processed.*` | The full uncut source, for anything the enriched layer flattens — most often a traded player's per-club stints. |

See [`data_dictionary.md`](data_dictionary.md) for every column of all of these.

---

## Definitions used across several questions

Settle these once; they are what the questions actually turn on.

| Term | Definition used | Why |
| --- | --- | --- |
| **"Top N players of a season"** | The N highest **point scorers** — `points_rank <= N`. | It is the order Basketball-Reference's own season pages use, and this data carries no wins, minutes-weighted rating, or all-round score to rank by instead. It is a **scoring-volume** reading and every finding must be phrased that way. |
| **"The Michael Jordan Trophy list"** | The MVP **ballot** — everyone who received a vote — via `is_mvp_candidate`. | The brief asks about a *list* of players, not a single winner. `processed.mvp_winners` holds the one winner per season since 1955-56; the ballot exists from 2018-19 and covers every window we study. |
| **"Experience"** | Seasons played **before** the season in question. A rookie is `0`. | Basketball-Reference's own roster-page convention. `processed.rosters.experience_seasons` is the authoritative per-season figure; `player_season.experience_seasons` is rolled back from the career total and agrees with it wherever both exist. |
| **"Active player"** | On the roster **and** appeared in at least one game that season. | A roster entry alone does not mean he played. In practice this excludes almost nobody, but the two are not the same claim. |
| **A season** | Its **ending year**. 2023-24 is `2024`. | Applies database-wide. |

---

## Assigned — descriptive statistics

### D1. Height: the MVP ballot vs. the season's top 50 scorers

> Produce the height distribution of players on the Michael Jordan Trophy list
> compared with the top 50 players of the season, seasons 2019-20 through
> 2023-24.

**Needs deciding:** the two groups **overlap** — most MVP candidates are also
top-50 scorers. The question asks to compare two named populations, not to
partition the league, so the overlap is kept and stated rather than removed.

**Watch for:** any height difference is largely a *position* difference. Report
position alongside height or the finding is unexplained.

**Status:** notebook pending.

### D2. Champion squads vs. the season's top 15, in height and experience

> Compare the distribution of experience of active players on the champion team,
> and their height, over the last two seasons, with the experience and height
> distribution of the top 15 players of that season.

**Needs deciding:** the two groups draw experience from different sources — the
champion roster page states it per season, while the top-15 group is not on
those pages and must be rolled back from the career total. Confirm the two agree
on the overlap before comparing them, and say which each group used.

**Status:** notebook pending.

### D3. Which point guard should the club buy?

> The club's ability metric is presence on the Michael Jordan Trophy list, and a
> player with more appearances has higher priority. Using seasons 2019-20 through
> 2023-24, produce a list and present 3 recommendations.

**Needs deciding:**
- **"Point guard"** — the position actually played that season, not the career
  primary position from the bio page. A player counts only for the seasons he
  was listed at PG. This is the stricter reading.
- **The tie-break.** The brief gives none, and three names cannot be picked from
  an appearance count alone. Rank by appearances, then by mean ballot position,
  then by name — so the recommendation is reproducible rather than an artefact of
  an unordered result set.

**Status:** notebook pending.

---

## Assigned — hypothesis tests

### H1. Has the "agility" of the top 20 increased?

> The average agility of the players in the top 20 of each season has increased
> compared with the past. Agility = height / weight. Compare 2022-23…2023-24 with
> 2020-21…2021-22.

**Needs deciding:** "agility" here is the brief's own definition, not a
basketball metric — it is `height_cm / weight_kg`, available as
`player_season.height_to_weight`. Higher means leaner.

**Watch for:** this ratio tracks *position* closely (~2.2 for a guard, ~1.9 for
a centre), so the test is largely asking whether the top 20 has shifted toward
guards. Say that rather than implying players became more athletic.

**Status:** notebook pending.

### H2. Has the "innate ability" of champion squads increased?

> An analyst defines innate ability as experience / age, and claims the average
> for the champion team's players over the last 2 seasons is greater than over the
> 2 seasons before. Examine this for the active players of that team in that
> season.

**Needs deciding:** age must be the player's age **during that season**, not a
current age — a single stored current age would give every season the same
number and flatten the exact difference being tested.

⚠️ **Open issue carried from the original analysis.** It ran a one-tailed test
(`alternative='greater'`) and reported p ≈ 0.97 / "cannot reject H0" while the
t-statistic was **−4.918** — a large effect in the *opposite* direction that a
two-tailed test would flag as highly significant. Its Yeo-Johnson transform was
also fitted separately per group, which distorts a between-group comparison.
Both need resolving when this is rebuilt; neither is a data problem.

**Status:** notebook pending. **Test choice must be revisited.**

---

## Additional analyses

Beyond the assignment. The brief awards credit for these.

### B1. Availability — is the best ability availability?

Does the share of the schedule a player actually appears in separate the
MVP-honoured from the rest? `player_season.availability` is
`games_played / team_games`, where a traded player is measured against the
league schedule instead of one club's.

**Watch for:** availability is a share of *games*, not minutes — a two-minute
appearance counts as available.

**Status:** notebook pending.

### B2. The superstar tax — does efficiency fall as usage rises?

Usage is the share of a team's possessions a player finishes; true shooting is
how efficiently he finishes them. If carrying more costs accuracy the two trade
off, and the players who stay efficient at high usage are the genuinely elite.

**Watch for:** usage is stored 0-100 and true shooting 0-1. Converting one is
required before they share an axis, and forgetting is a silent 100× error.

**Status:** notebook pending.

### B3. Team four factors — what goes with a stronger season?

Dean Oliver's four factors — shooting, turnovers, offensive rebounding, free
throws — are precomputed on `analyst_ready.team_season` for every season the
source records the inputs for.

⚠️ **Watch for:** this database has **no wins column.** `points_rank` is a
scoring rank, not a league standing, so any finding is "what goes with scoring
more," never "what goes with winning more." State it that way or the conclusion
is wrong.

**Status:** notebook pending.

### B4. Draft position — are picks 1-5 better than picks 6-10?

The club cannot realistically land the first overall pick, so it wants to buy a
player who was one; that pool is too small, so the search widens to the top 10.

**Needs deciding:** "career" figures can only mean *over the seasons in this
database*, not a true career — a veteran and a four-year pro are summed over the
same window, so any total must be read next to the count of seasons.

⚠️ **Watch for:** defensive box plus/minus is **positive = good** (points
prevented above an average player). The original analysis had this sign
backwards and labelled the worst defenders 'great'.

**Status:** notebook pending.

---

## Adding a question

1. Add an entry here: the question, what has to be decided, what to watch for.
2. Write the notebook. Query `analyst_ready` directly.
3. If the query needs a feature that is genuinely general — a rate, a ratio, a
   flag that any question might want — add it to `player_season` or
   `team_season`. If it is specific to this one question, it belongs in the
   notebook.

That last distinction is the rule this schema is organised around.
