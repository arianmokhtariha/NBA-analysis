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

[`00_data_overview.ipynb`](../notebooks/00_data_overview.ipynb) answers none of
the questions below. It reads the layers with the data in front of it: 4,466
player-seasons from 2018-19 through 2025-26, 1,278 players, 30 clubs,
`team_season` back to 1949-50, and where the columns run out. Read it first.

---

## Definitions used across several questions

Settle these once; they are what the questions actually turn on.

| Term | Definition used | Why |
| --- | --- | --- |
| **"Top N players of a season"** | The N highest **point scorers** — `points_rank <= N`. | It is the order Basketball-Reference's own season pages use, and this data carries no wins, minutes-weighted rating, or all-round score to rank by instead. It is a **scoring-volume** reading and every finding must be phrased that way. |
| **"The Michael Jordan Trophy list"** | The MVP **ballot** — everyone who received a vote — via `is_mvp_candidate`. | The brief asks about a *list* of players, not a single winner. `processed.mvp_winners` holds the one winner per season since 1955-56; the ballot exists from 2018-19 and covers every window we study. |
| **"Experience"** | Seasons played **before** the season in question. A rookie is `0`. | Basketball-Reference's own roster-page convention. `processed.rosters.experience_seasons` is the authoritative per-season figure and the one to use. `player_season.experience_seasons` is rolled back from a career total, so it cannot see a season a player missed; see D2 for the two cases where the two disagree. |
| **"Active player"** | On the roster **and** appeared in at least one game that season. | A roster entry alone does not mean he played. In practice this excludes almost nobody, but the two are not the same claim. |
| **A season** | Its **ending year**. 2023-24 is `2024`. | Applies database-wide. |
| **"The last two seasons"** | `2025` and `2026`: 2024-25 Oklahoma City and 2025-26 New York. "The two before that" are `2023` and `2024`, Denver and Boston. | The re-scrape brought 2025-26 in as a complete season, so both windows sit one year later than in the original bootcamp analysis. Used by D2 and H2. |

---

## Descriptive statistics

### D1. Height: the MVP ballot vs. the season's top 50 scorers

> Produce the height distribution of players on the Michael Jordan Trophy list
> compared with the top 50 players of the season, seasons 2019-20 through
> 2023-24.

**Needs deciding:** the two groups **overlap** — most MVP candidates are also
top-50 scorers. The question asks to compare two named populations, not to
partition the league, so the overlap is kept and stated rather than removed.

**Watch for:** any height difference is largely a *position* difference. Report
position alongside height or the finding is unexplained.

**Answered in** [`../notebooks/01_D1_height.ipynb`](../notebooks/01_D1_height.ipynb).
The ballot runs 2.35 cm taller than the top 50, but that is a few very tall men
appearing on it every year: one row per player instead of one per season leaves
p = 0.46 and identical medians of 198.1 cm. What separates the two groups is
spread, not height.

### D2. Champion squads vs. the season's top 15, in height and experience

> Compare the distribution of experience of active players on the champion team,
> and their height, over the last two seasons, with the experience and height
> distribution of the top 15 players of that season.

**Needs deciding:** which experience figure both groups use. The worry was that
the champion roster page states it per season while the top-15 group would have
to be rolled back from a career total. `processed.rosters` covers all 30 clubs
from 2018-19, so both groups take the source's stated figure and nothing is
rolled back. The check did turn up two defects in the derived
`player_season.experience_seasons`, both on 2024-25 Oklahoma City: Adam Flagler
is stated at 1 season and derived as 0, because the roll-back cannot see the
season he missed, and Alex Ducas is stated at 0 and derived as NULL. Prefer
`processed.rosters`.

**Answered in** [`../notebooks/02_D2_champions.ipynb`](../notebooks/02_D2_champions.ipynb).
Experience splits the groups hard (2.56 seasons against 8.47 in 2024-25,
p = 0.0001) and height does not (p = 0.64 and 0.40). Most of the experience gap
is structural: a whole squad and the 15 leading scorers in the league are
assembled by different rules.

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

**Answered in** [`../notebooks/03_D3_point_guard.ipynb`](../notebooks/03_D3_point_guard.ipynb).
Thirteen point guards drew a vote in the window and the metric ranks Dončić,
Curry, Paul. The recommendation drops Paul for Gilgeous-Alexander: Paul's last
ballot as a PG was 2021-22, and by 2023-24 he was 38 with a PER of 14.7, which
the metric cannot see because that season brought him no votes.

---

## Hypothesis tests

### H1. Has the "agility" of the top 20 increased?

> The average agility of the players in the top 20 of each season has increased
> compared with the past. Agility = height / weight. Compare 2022-23…2023-24 with
> 2020-21…2021-22.

**Needs deciding:** "agility" here is the brief's own definition, not a
basketball metric — it is `height_cm / weight_kg`, available as
`player_season.height_to_weight`. Higher means leaner.

**Watch for:**
- The ratio tracks *position* closely (~2.2 for a guard, ~1.9 for a centre), so
  the test is largely asking whether the top 20 has shifted toward guards. Say
  that rather than implying players became more athletic.
- **The column cannot see the change the question asks about.**
  `height_to_weight` comes from the bio page and is constant per player: 0 of
  929 multi-season players have a ratio that varies. It cannot register a player
  getting leaner from one season to the next, only a change in *who* is in the
  top 20. The question as posed is not answerable with this column, and the
  answer has to be phrased around roster turnover.

**Answered in** [`../notebooks/04_H1_agility.ipynb`](../notebooks/04_H1_agility.ipynb).
No increase: 2.0210 recent against 2.0244 earlier, Welch t = −0.0682, two-tailed
p = 0.946, Hedges' g = −0.015. Counting each player once per period flips the
sign of the difference, which is another way of saying it has no direction.

### H2. Has the "innate ability" of champion squads increased?

> An analyst defines innate ability as experience / age, and claims the average
> for the champion team's players over the last 2 seasons is greater than over the
> 2 seasons before. Examine this for the active players of that team in that
> season.

**Needs deciding:** age must be the player's age **during that season**, not a
current age — a single stored current age would give every season the same
number and flatten the exact difference being tested.

**Two faults carried over from the original analysis, both now settled.** It ran
a one-tailed test (`alternative='greater'`) and reported p ≈ 0.97 / "cannot
reject H0" while the t-statistic was **−4.918**, a large effect in the *opposite*
direction that a two-tailed test would have flagged as highly significant. Its
Yeo-Johnson transform was also fitted separately per group, which distorts a
between-group comparison. Neither was a data problem. The rebuild runs two-tailed
as the primary result and reports the original's one-tailed p = 0.9477 next to
it, so a reader can see that on a sample which moved the wrong way a one-tailed p
near 1 restates the direction rather than defending H0. The per-group transform
is gone; the toolkit picked a distribution-free test on the raw ratios instead.

**Answered in** [`../notebooks/05_H2_innate.ipynb`](../notebooks/05_H2_innate.ipynb).
The claim is not supported and the ratio moved against it: 0.129 recent against
0.187 earlier, two-tailed Mann-Whitney p = 0.1075, Cliff's δ = −0.235. Experience
over age is career stage, so a champion built around young players scores low on
it by construction.

---

## Adding a question

1. Add an entry here: the question, what has to be decided, what to watch for.
2. Write the notebook. Query `analyst_ready` directly.
3. If the query needs a feature that is genuinely general — a rate, a ratio, a
   flag that any question might want — add it to `player_season` or
   `team_season`. If it is specific to this one question, it belongs in the
   notebook.

That last distinction is the rule this schema is organised around.
