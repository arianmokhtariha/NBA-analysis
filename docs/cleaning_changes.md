# Cleaning changes: `data/data_clean/` -> `data/processed/`

This document is the acceptance record for the rewritten cleaning pipeline in
`cleaning/`. It lists, for each of the nine files the old pipeline committed,
what the new pipeline produces instead and **why** the output differs. The
output is *expected* to differ: every deviation below is either a bug fix or a
deliberate design decision, and each one is justified here.

**Reproduce everything:**

```bash
python -m cleaning.run_all   # data/raw -> data/processed
python -m cleaning.verify    # deletes data/processed, rebuilds, checks integrity
```

Verified on the current raw inputs: deleting `data/processed/` and rebuilding
produces **all 11 files, byte-for-byte identical** on repeat runs.

---

## 1. Why the old output could not be trusted

Three independently verifiable facts, not opinions:

1. **Two of the nine committed files had no producing code.** `rosters.csv` and
   `advanced_stats.csv` were only ever *re-read and re-written* by
   `normalize_advanced_and_roster()`, which loaded them from `data/data_clean/`
   — their contents were never derived from anything in the repository.
2. **The old script cannot run at all any more.** It reads
   `data/Players_table.csv`, `data/Player_table.csv`, `data/Mvp_table.csv`,
   `data/new_mvp_candidates.xlsx`, `data/seasons_table.xlsx`,
   `data/seasons_teams_total_stats_clean.csv` and `data/player_stats.csv`.
   None of those paths exist; the raw files were renamed and moved to
   `data/raw/` in Phase 1.
3. **The committed output does not match the committed code.** The committed
   `data/data_clean/player_stats.csv` contains seven rows whose `player_id` is
   the literal string `"tot"` (one per season, all statistics missing). No code
   path in `01_data_cleaning_anoosha.py` produces that value in `player_id`.
   Those seven rows are Basketball-Reference's *League Average* summary line,
   which arrives with a blank `player_id`; some earlier, uncommitted version of
   the script filled them in and turned them into a fake player.

---

## 2. File map

| Old file (`data/data_clean/`) | New file (`data/processed/`) | Rows | Columns |
| --- | --- | --- | --- |
| `players.csv` | `players.csv` + `player_positions.csv` | 1,175 -> 1,989 (+1,643) | 27 -> 30 (+4) |
| `team_lookup.csv` | `teams.csv` | 37 -> 75 | 2 -> 4 |
| `teams_performance.csv` | `team_season_stats.csv` | 775 -> 1,693 | 26 -> 26 |
| `season_stats.csv` | `season_awards.csv` (+ new `seasons.csv`) | 26 -> 88 (+80) | 9 -> 8 |
| `rosters.csv` | `rosters.csv` | 1,870 -> 1,873 | 5 -> 14 |
| `player_stats.csv` | `player_season_stats.csv` | 3,891 -> 5,025 | 32 -> 34 |
| `advanced_stats.csv` | `player_advanced_stats.csv` | 3,884 -> 5,025 | 21 -> 25 |
| `mvp_winners.csv` | `mvp_winners.csv` | 70 -> 70 | 17 -> 17 |
| `mvp_candidates.csv` | `mvp_candidates.csv` | 85 -> 85 | 22 -> 22 |

`seasons.csv` (80 rows) is new: nothing in the old output was a season
dimension.

---

## 3. The decision that changes the most rows: complete dimensions

The old output could not be loaded into PostgreSQL with foreign keys enforced.
It violated them in three places:

* 810 distinct roster `player_id`s (of 1,381) and 26 of the 70 `mvp_winners`
  `player_id`s (Jordan `jordami01`, Kareem `abdulka01`, Bird `birdla01`,
  Magic `johnsma02`, Wilt `chambwi01`, ...) had no row in `players`. 22 of
  those 26 MVP winners are also in the roster set, so the two lists together
  account for exactly the 814 players added below;
* 17 historical and ABA team codes were referenced but missing from
  `team_lookup`, because it was built only from seasons >= 2000;
* rosters span 1947-2026 while the season table covered only 2000-2025.

**Resolution:** `players`, `teams` and `seasons` are built as the **union of
every key referenced by any fact table**, not just from the file that happens
to carry the descriptive attributes. Rows with no descriptive data carry
`has_bio = False` (players) or `has_detail = False` (teams) and NULL
attributes.

This is why the dimensions grew and why **not one fact row and not one season
of history had to be deleted**. Michael Jordan is in the database with his
name (recovered from the championship rosters) and his five MVP awards; he
simply has no bio attributes.

Result, from `python -m cleaning.verify`: **0 orphan foreign keys across all
20 relationships, and 0 duplicate or NULL primary keys across all 11 tables.**

---

## 4. Per-file changes

### 4.1 `players.csv` -> `players.csv` + `player_positions.csv`

**Rows 1,175 -> 1,989.** 814 players added that are referenced by rosters or
the MVP tables but were never scraped as bios (`has_bio = False`). No player
was removed. 1,985 of the 1,989 have a name; the four without one
(`barklch01`, `iversal01`, `malonka01`, `nashst01`) are MVP winners who never
won a title, so they appear in neither the bios nor the championship rosters.

| Change | Why |
| --- | --- |
| **49 player names repaired** (`nikola jokiä` -> `Nikola Jokić`, `luka donäiä` -> `Luka Dončić`, `dennis schrã¶der` -> `Dennis Schröder`) | The scrape stored UTF-8 bytes that were then read as Latin-1 (mojibake). `fix_mojibake` re-encodes to Latin-1 and decodes as UTF-8, keeping the original string whenever that round-trip fails or is a no-op — so correct text is never damaged and the fix is safe to run twice. |
| **`position_1 ... position_6` replaced by `player_positions(player_id, slot, position, position_code)`** | Two problems in one. (a) A repeating group of six columns is not normalised. (b) The slots were **misaligned**: the raw string contains an empty token, e.g. Paul George is `"Small Forward, Power Forward, , Shooting Guard"`, so his third position landed in slot 4. Old fill counts were `{1: 1175, 2: 424, 3: 3, 4: 38, 5: 2, 6: 1}` — slot 3 nearly empty while slot 4 had 38. New counts are `{1: 1175, 2: 424, 3: 40, 4: 3, 5: 1}`, same 1,643 position facts, correctly ordered. Empty tokens are now dropped *before* slots are numbered. |
| **`primary_position` added** | Convenience copy of slot 1, as a two-letter code (`PG`/`SG`/`SF`/`PF`/`C`) so it joins to the season tables, which use codes rather than the bio page's spelled-out names. |
| **`age` column dropped** | It was `2025 - birthyear`, hard-coded in two places. Age is not an attribute of a person, and this one silently becomes wrong on 1 January. `birth_year`, `birth_month`, `birth_day` and `birth_date` are stored instead; correct per-season age already exists in `player_season_stats.age`. |
| **`shoots`: `"right_left"` -> `"both"`, and three hard-coded row patches removed** | The old code patched `.loc[169]`, `.loc[235]` and `.loc[884]` by row number — which breaks the moment the source file is re-scraped in a different order. Those rows are real data problems: `plumlma01` and `thomptr01` are genuinely both-handed and the scrape captured `"\n Shoots:\n \nRight Left"`, and for `vildolu01` the selector missed and dumped a whole bio paragraph into the field. All three are now covered by one rule: look for the words *Right* and *Left*; both -> `both`, one -> that hand, neither -> NULL. Result: 1,066 right, 106 left, 2 both, 1 NULL (plus the 814 bio-less players). |
| **`draft_round` added; `draft_round_pick_rank`/`draft_overall_pick_rank` renamed to `draft_round_pick`/`draft_overall_pick`** | The round number was parsed away and discarded; `"1st round (10th pick 10th overall)"` carries three facts, not two. |
| **`college` restored** | The old pipeline dropped it. It is also repaired: the scraper joined multi-word names with a comma (`"Arizona,State"` -> `"Arizona State"`, 349 rows) and wrote the literal word `"Colleges"` for the 169 players who never attended one, which is now NULL. |
| **`nba_debut` (year) -> `nba_debut_date` + `nba_debut_year`** | The full date was in the source and was being thrown away. |
| **`experience` -> `experience_seasons`** | Clearer name; gaps in the bio page are filled from the career-stats page, which reports the same figure. |
| **`career_games` restored** | The old pipeline dropped it for no stated reason. |
| **`last_season_*` columns still excluded** | These describe whichever season happened to be most recent at scrape time. They are ambiguous and fully reproducible from `player_season_stats`. |
| **Heights ±0.5 cm, weights up to ±0.7 kg different** | Height is now rounded to one decimal instead of whole centimetres, and pounds convert with the exact factor 0.45359237 instead of 0.453. |
| **Names keep their real capitalisation** | The old pipeline lower-cased every text column, producing `"james harden"`. Only identifier columns (`player_id`, `team_id`) are lower-cased now — they are keys, so their case must be stable — while human-readable names keep their source spelling. |

### 4.2 `team_lookup.csv` -> `teams.csv`

**Rows 37 -> 75.** Nothing was removed. 38 team codes were added:

* 31 historical franchises (`mnl` Minneapolis Lakers, `phw` Philadelphia
  Warriors, `syr` Syracuse Nationals, `blb`/`bal` Baltimore Bullets, ...) that
  the old `season >= 2000` filter had excluded even though other tables
  referenced them;
* 6 ABA clubs (`ina`, `ken`, `nya`, `oak`, `ptp`, `uts`) that appear only in
  the old championship rosters — their names come from the roster listings,
  the only place the scrape recorded them;
* `tot`, described below.

New columns `is_aggregate` and `has_detail` (68 of 75 teams have season totals).

**`tot` is now a real dimension row** (`"Multiple Teams (season total)"`,
`is_aggregate = True`). On Basketball-Reference a player traded mid-season gets
a combined line under the pseudo-team `TOT`. It is a legitimate value in 551
fact rows, so it needs somewhere to point; the flag lets an analysis exclude it
deliberately rather than by accident.

The old hard-coded rename of `cho` to `"charlotte hornets (2014-)"` is gone.
Five names are shared by two franchise eras (`bal`/`blb`, `chh`/`cho`,
`den`/`dnn`, `ind`/`ina`, `nyn`/`nya`); since `team_id` is the key, that is
legal, and inventing disambiguating text is not the cleaning layer's job.

### 4.3 `teams_performance.csv` -> `team_season_stats.csv`

**Rows 775 -> 1,693.** Same 26 columns.

* The `season >= 2000` filter is gone: seasons 1950-2026 are all kept, which is
  what makes the historical team codes above meaningful.
* The `season != 2026` filter is gone too. The 30 rows for the not-yet-played
  2025-26 season are kept with `games = 0`. **Filter on `games > 0` before
  averaging anything over team-seasons** — those rows are a snapshot of a
  season in progress, not zero performances.
* 154 rows were dropped: blank separator rows between season blocks on the
  source page, with no team code and no numbers. (The old code removed them
  indirectly by filtering on a non-null rank.)
* One row (`blb`, 1954-55) legitimately has all statistics missing — the
  franchise folded mid-season and the source has no totals for it.
* `team_name` moved out to `teams.csv`; the fact table now carries only the
  key, which is the point of having a dimension.

### 4.4 `season_stats.csv` -> `season_awards.csv` (+ new `seasons.csv`)

**Rows 26 -> 88.** The `season >= 2000` filter is gone; the summary now covers
1947-2025, including the nine ABA seasons. The primary key is
`(season, league)`, because a season can have both an NBA and an ABA champion.

| Change | Why |
| --- | --- |
| **`mvp` column dropped** | It held an abbreviated display name (`"n. jokić"`) that cannot be joined to a player. The `mvp_winners` table already records the same fact with a real `player_id`. Keeping both invites them to disagree. |
| **`champion_name` -> `champion_team_id`** | The old column pointed at `team_lookup.team_name`, which is not a key. It is now resolved to a real `team_id`. The merge is on **season *and* name**, not name alone, because a bare name is ambiguous across franchise history — "Indiana Pacers" is both the ABA `ina` and the NBA `ind`. All 88 champions resolve; 0 unresolved. |
| **The other award columns stay as free text** | The source only ever gives an abbreviated name (`"S. Castle"`). It is display material and is labelled as such; it is not silently presented as a key. |
| **`seasons.csv` is new** | 80 rows, 1947-2026, with `season_label`, `start_year` and `has_awards`. Without it, `rosters.season` and `team_season_stats.season` have no dimension to point at. |

### 4.5 `rosters.csv` -> `rosters.csv`

**Rows 1,870 -> 1,873; columns 5 -> 14.**

The old file had no producing code, and it does not match the committed raw
input: four of its 2025-26 entries are absent from `data/raw/`, and seven of
the raw entries are absent from it. It was generated from a different scrape of
a roster page that changes as clubs sign and waive players. The new file is
derived from `data/raw/team_season_rosters.csv` and nothing else.

* 118 rows dropped: every team-season block on the source page ends with an
  empty trailing row (a table footer the scraper captured) that has a team but
  no player. It cannot be a roster entry.
* Nine columns added that the old file discarded: `player_name` (mojibake
  repaired, 44 names), `height_cm`, `weight_kg`, `birth_date`,
  `birth_country` (parsed from `"us US"` -> `"US"`), `experience_seasons`
  (`"R"` for rookie -> `0`), `college`, the raw `position`, and `roster_note`
  (the annotation the source appends to a name, e.g. `TW` for a two-way
  contract, which used to be left inside the name).
* `pos1`/`pos2` renamed to `position_primary`/`position_secondary`.

**What this table actually covers** — worth knowing before using it: the scrape
collected the **champion team's roster for every season from 1946-47 onwards**
(both champions in the nine ABA seasons), plus all 30 rosters of the current
2025-26 season. It is not a league-wide roster history.

### 4.6 `player_stats.csv` -> `player_season_stats.csv`

**Rows 3,891 -> 5,025; columns 32 -> 34.** The row count went *up* because two
different bugs were fixed in opposite directions.

| Change | Why |
| --- | --- |
| **7 "League Average" rows removed** | One per season, `player_id` blank, only a few league-wide percentages populated. In the committed old file they had become a fake player with `player_id = "tot"`. They are now dropped explicitly, before any missing-value handling, by a helper shared with the advanced table — which is exactly why the old `advanced_stats.csv` was 7 rows shorter than the old `player_stats.csv`. |
| **1,141 traded-player rows restored** | The old code kept only the combined `TOT` line and deleted the per-team rows. Those rows are real: they say how a traded player performed for each club. A downstream analysis needs them. |
| **`stint` and `is_primary` added** | `stint = 0` on the combined season-total row, `1..n` on the per-team rows in source order (a player who stayed put has one row, `stint = 1`). `is_primary` marks exactly one row per player-season: the combined row where there is one, otherwise the player's only row. **`WHERE is_primary` gives 3,884 rows — precisely the old deduplicated table, minus the 7 fake League Average rows** — so nothing that relied on the old shape has to change, and nothing is lost. |
| **The `key=lambda s: s != "tot"` sort removed** | It was applied to all three sort columns, where it is meaningless on `season` and `player_id`, and it existed only to float the `TOT` row to the top before a `drop_duplicates`. With `stint` there is no deduplication to steer. Rows are now sorted by `(season, rank, player_id, stint)`. |
| **`team_id = "tot"` kept, and no longer duplicated meaning** | `tot` on `team_id` (551 rows) is the legitimate traded-player convention and now resolves to a real `teams` row. `tot` on `player_id` (7 rows) was a bug and is gone. |

### 4.7 `advanced_stats.csv` -> `player_advanced_stats.csv`

**Rows 3,884 -> 5,025; columns 21 -> 25.** This file also had no producing code
in the repository; the only related artefact was a notebook hard-coded to
another machine's `C:/Users/Zagros/Desktop/...` paths. Its deduplication logic
was ported; everything else is new.

* Same League Average and traded-player fixes as the box-score table, via the
  same shared helpers.
* `team_id`, `stint` and `is_primary` added. `WHERE is_primary` gives 3,884
  rows, matching the old file's key set.
* **`box_plus_minus` restored** — the combined BPM column existed in the raw
  data and was missing from the old file, which kept only its offensive and
  defensive halves.
* `rank`, `age`, `position`, `games`, `games_started` and `minutes_played`
  are **not** carried here. They were verified identical to
  `player_season_stats` on all 5,025 shared rows, and the two tables join on
  `(season, player_id, stint)`; storing them twice is what normalisation
  exists to prevent. `rank` in particular was the display order of the source
  web page, not a fact about the player — the raw file ranks by a different
  sort than the box-score file does.

### 4.8 `mvp_winners.csv` -> `mvp_winners.csv`

**Unchanged in shape (70 x 17).** The only differences are column order and
that `player_id`/`team_id` are explicitly lower-cased. The 26 winners with no
scraped bio page now have valid `players` rows to point at, so this table no
longer breaks the foreign key.

### 4.9 `mvp_candidates.csv` -> `mvp_candidates.csv`

**Unchanged in shape (85 x 22).** `year` is renamed to `season` so that every
fact table names its season column the same way and the foreign key to
`seasons` is uniform. The `rank`/`tie` split (`"10T"` -> rank 10, tie true) is
ported unchanged.

---

## 5. Conventions applied everywhere

* **Casing** — only `player_id` and `team_id` are lower-cased (they are keys).
  Human-readable names keep their source capitalisation. The old pipeline
  lower-cased everything, which is why the old files read `"james harden"` and
  `"atlanta hawks"`.
* **Seasons** — always stored as the **ending year** (`"2024-25"` -> `2025`),
  ported verbatim from the old script and applied through one shared helper.
* **Units** — heights in centimetres, weights in kilograms, one decimal place,
  exact conversion factors.
* **Missing values** — left missing. Nothing is filled with a placeholder that
  could be mistaken for data; the `tot` incident above is what that produces.
* **Determinism** — every table is sorted by its primary key and written with
  UTF-8 and `\n` line endings, so a rebuild is byte-identical and a diff shows
  only real changes.

---

## 6. Judgment calls worth a second opinion

1. **Not-yet-played 2025-26 team rows are kept** (`games = 0`, 30 rows). They
   are an honest snapshot, and the instruction was to drop no history — but
   they will distort any average taken over team-seasons that does not filter
   `games > 0`. The alternative (a rule dropping team-seasons with zero games)
   is one line in `cleaning/teams.py` if that trade-off is preferred.
2. **`rank` is kept in `player_season_stats` but dropped from
   `player_advanced_stats`.** Both are display artefacts of their source page;
   `rank` was kept in the box-score table only because the old table had it and
   downstream code may sort by it.
3. **The `last_season_*` columns of `player_career_stats` are still not
   loaded.** Ten columns of real scraped data are unused. They are ambiguous
   (which season?) and derivable, but a case can be made for keeping them.
4. **`advanced_stats` descriptive columns were dropped after verifying they are
   identical.** If a future re-scrape makes them diverge, the check that
   justified the drop no longer holds.
5. **Four MVP winners have a NULL `player_name`** (`barklch01`, `iversal01`,
   `malonka01`, `nashst01`). Their names exist nowhere in the raw data.
   Hard-coding four names would fix the display; re-scraping their bio pages
   would fix the data.

---

## 7. Follow-up

`docs/schema.md` used to describe the old `data/data_clean/` tables and point
at `data_analysis/data_preprocessing/01_data_cleaning_anoosha.py`, which this
change deletes. It has since been folded into `docs/data_dictionary.md`, which
now documents both the `processed` schema as loaded into PostgreSQL and the
`analyst_ready` marts built on top of it.
