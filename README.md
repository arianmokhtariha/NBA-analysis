# NBA Data Analysis

![Python](https://img.shields.io/badge/Python-3.13-blue)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_17-336791)
![Scraping](https://img.shields.io/badge/Scraping-Requests_%7C_BeautifulSoup-green)
![Analysis](https://img.shields.io/badge/Analysis-pandas_%7C_SciPy_%7C_statsmodels-blueviolet)
![Status](https://img.shields.io/badge/Status-In%20Progress-yellow)

> **Credit & Collaboration Note:**
> This project was originally developed as a group effort for Quera's Data Analysis bootcamp. This repository is a **continuation/fork** containing my own refactored code, database work, and extended analysis.
> **Original Team:**
> [@AlirezaNyi](https://github.com/AlirezaNyi)
> [@arianmokhtariha](https://github.com/arianmokhtariha)
> [@mohsen20roohi-hue](https://github.com/mohsen20roohi-hue)
> [@MonaKheirieh](https://github.com/MonaKheirieh)
> [@anooshanth](https://github.com/anooshanth)

---

## What this is

This project scrapes historical NBA data from
[basketball-reference.com](https://www.basketball-reference.com), loads it
into a PostgreSQL database with real referential-integrity constraints, and
uses it to answer a set of specific questions: how player height, playing
experience, and a simple "agility" measure (height relative to weight)
compare between MVP-calibre players and the rest of the league, and whether
those patterns have shifted over recent seasons.

The repository below has been rewritten from the original bootcamp
submission into a four-stage, reproducible pipeline: scrape, clean, load,
and build analysis-ready tables. Every stage can be re-run from scratch and
is checked against the last one.

---

## Architecture

Four stages, each owned by one part of the repo:

1. **Scrape** (`scrapers/`) — pulls raw data from basketball-reference.com
   with plain `requests` + BeautifulSoup and writes it to `data/raw/`. One
   module per scraped table (10 tables), plus shared HTTP/parsing helpers
   and a runner that scrapes them all in the right order.
2. **Clean** (`cleaning/`) — reads `data/raw/`, fixes real data problems
   (mojibake'd names, misaligned columns, duplicate rows, missing
   dimension entries), and writes normalised CSVs to `data/processed/`.
   `cleaning/verify.py` deletes `data/processed/` and rebuilds it from
   scratch as an acceptance test. Every decision the cleaning step makes is
   written down in [`docs/cleaning_changes.md`](docs/cleaning_changes.md).
3. **Load** (`db_setup.py`) — creates the `nba_analysis` PostgreSQL
   database, applies the schema in `sql/processed/`, and loads the 11
   cleaned CSVs into it. This is the slow step; run it only when the data
   changes.
4. **Build marts** (`rebuild.py`) — builds the `analyst_ready` schema (13
   tables and views, one relation per project question) by running
   `sql/analyst_ready/*.sql` against `processed`. This is the fast step —
   it loads no data and never touches `processed` — so it is safe to
   re-run constantly while writing analysis queries.

```text
basketball/
├── scrapers/                    # Stage 1 — scrape basketball-reference.com
│   ├── fetch.py                  #   shared HTTP layer (requests, retries, no Selenium)
│   ├── parse.py                  #   shared HTML-table parsing (BeautifulSoup)
│   ├── teams.py
│   ├── team_seasons.py
│   ├── team_season_rosters.py
│   ├── team_season_totals.py
│   ├── player_stats.py
│   ├── advanced_stats.py
│   ├── player_bios.py
│   ├── mvp_candidates.py
│   ├── mvp_winners.py
│   ├── season_summaries.py
│   └── run_all.py                #   runs every scraper in dependency order
│
├── cleaning/                    # Stage 2 — data/raw -> data/processed
│   ├── normalize.py              #   shared cleaning helpers
│   ├── players.py
│   ├── teams.py
│   ├── seasons.py
│   ├── rosters.py
│   ├── player_stats.py
│   ├── advanced_stats.py
│   ├── mvp.py
│   ├── run_all.py                #   runs the whole cleaning pipeline
│   └── verify.py                 #   rebuilds from scratch and checks the result
│
├── sql/
│   ├── processed/                #   DDL for Stage 3 (the `processed` schema)
│   │   ├── 00_schema.sql
│   │   └── 10_indexes.sql
│   └── analyst_ready/            #   DDL for Stage 4 (the `analyst_ready` marts)
│       ├── 10_dimensions.sql
│       ├── 20_player_season.sql
│       ├── 30_question_marts.sql
│       ├── 40_bonus_marts.sql
│       └── 50_indexes.sql
│
├── db_setup.py                  # Stage 3 — build `processed`, load the CSVs (slow, asks to confirm)
├── rebuild.py                   # Stage 4 — build `analyst_ready` from `processed` (fast)
├── verify_db.py                 # checks the loaded database's structure and row counts
├── db_config.py                 # reads DB credentials from .env
│
├── utils/
│   └── db_utils.py               # shared query helper for notebooks
│
├── notebooks/                   # one notebook per question — in progress, see below
│   └── _setup.py
│
├── data/
│   ├── raw/                      # scraped output, 9 files — committed, so scraping is optional
│   └── processed/                # cleaned output, 11 CSVs — committed
│
├── docs/
│   ├── schema.md                 #   the `processed` schema, column by column
│   ├── data_dictionary.md        #   the `analyst_ready` schema, column by column
│   └── cleaning_changes.md       #   what the cleaning rewrite changed, and why
│
├── reports/                     # stakeholder write-up — in progress, see below
│   ├── assets/
│   └── figures/
│
├── environment.yml              # conda environment definition
└── .env.example                  # shape of the required .env file
```

Two things from the original bootcamp submission are still in the tree:
`data_analysis/` (each team member's exploratory notebooks) and
`presentation.ipynb` / `presentation_utils.py` (the original presentation).
Nothing in the pipeline above reads them. They are being kept only until
the per-question notebooks have been rebuilt from them, and will be removed
once that is done — the git history keeps them either way.

---

## How to run it

All commands are run from the repository root, with the conda environment
active.

**1. Create the environment.**

```bash
conda env create -f environment.yml
conda activate nba-analysis
```

**2. Set up credentials.** Copy `.env.example` to `.env` and fill in your
local PostgreSQL connection details (user, password, host, port, database
name). `.env` is gitignored — it never gets committed.

```bash
cp .env.example .env
```

**3. (Optional) Re-scrape the raw data.** `data/raw/` is already committed
to the repository, so this step can be skipped entirely unless you want
fresher data. It is polite to the source site (retries, backing off, and
throttling between requests), so a full run takes a while.

```bash
python -m scrapers.run_all
```

**4. Clean the raw data.** Fast — a few seconds. Also optional if you
didn't re-scrape, since `data/processed/` is committed too.

```bash
python -m cleaning.run_all
```

**5. Build the database.** This is the slow step: it creates the
`nba_analysis` database, applies the schema, and loads all 11 cleaned
tables with foreign keys enforced. **It asks for an explicit yes/no
confirmation before it drops and recreates the database**, since that is a
destructive operation.

```bash
python db_setup.py
```

**6. Build the analysis-ready marts.** Fast — seconds, not minutes. Safe to
re-run as often as you like; it never modifies the database built in step
5, only the derived tables layered on top of it.

```bash
python rebuild.py
```

That's the whole pipeline. To check the result:

```bash
python verify_db.py       # checks the loaded database's structure
python -m cleaning.verify # rebuilds data/processed/ from scratch and checks it
```

---

## Why the data can be trusted

A few things were specifically built to make this pipeline reproducible
rather than "it worked once":

- **The cleaning step reproduces itself.** `cleaning/verify.py` deletes
  `data/processed/` and rebuilds all 11 files from `data/raw/` from
  scratch; the output is byte-for-byte identical on repeat runs.
- **Foreign keys are enforced, not disabled.** The `processed` schema
  carries 11 primary keys, 21 foreign keys, and 22 check constraints — all
  active, none marked `NOT VALID` or deferred. The data satisfies its own
  keys, so nothing had to be relaxed to load it. (An earlier version of
  this project's database loader had to turn foreign-key checking off
  entirely to load the same data; that is no longer true.)
- **`verify_db.py` checks the loaded database's structure**, not a
  hard-coded list of expected numbers — it confirms every foreign key
  actually resolves and every row count matches its source CSV. That means
  it keeps working correctly after a future re-scrape changes the row
  counts, and it exits with an error code so it can block a bad rebuild.
- **Every analysis table's grain is a real primary key.** Each of the 13
  tables in `analyst_ready` states in a comment what one row of it means
  (e.g. "one row per player per season"); a Postgres primary key enforces
  that statement, so a query bug that silently duplicates a traded
  player's stats fails the build instead of quietly producing a wrong
  average.
- **`rebuild.py` cannot touch the base data.** It refuses to drop or
  modify the `processed` schema — the guard runs before any destructive
  statement — so an error in the analysis-table SQL can't corrupt the data
  that took a full reload to produce.

---

## The questions this project answers

Three descriptive-statistics questions and two hypothesis tests were
assigned; four further analyses were added beyond that. Each has exactly
one table in `analyst_ready` behind it — see
[`docs/data_dictionary.md`](docs/data_dictionary.md) for the column-level
detail and [`sql/analyst_ready/30_question_marts.sql`](sql/analyst_ready/30_question_marts.sql)
/ [`40_bonus_marts.sql`](sql/analyst_ready/40_bonus_marts.sql) for the exact
definitions and the reasoning behind each one.

**Descriptive statistics**

- **D1** — How does the height of players on the MVP ballot compare with
  the height of the season's 50 highest scorers, across the 2019-20
  through 2023-24 seasons?
- **D2** — How does the playing experience and height of an NBA champion's
  active roster compare with the season's 15 highest scorers, over the
  last two championship seasons?
- **D3** — Which point guard should a club chasing a strong start buy,
  using "appearances on the MVP ballot" as the ability metric? (Three
  recommendations, ranked.)

**Hypothesis tests**

- **H1** — Has the average "agility" (height ÷ weight) of each season's 20
  highest scorers increased in 2022-23/2023-24 compared with
  2020-21/2021-22?
- **H2** — Has the average "innate ability" (experience ÷ age) of NBA
  champions' active rosters increased over the last two championship
  seasons compared with the two before that?

**Bonus analyses** — availability (how much of the season MVP-calibre
players actually play), the "superstar tax" (whether shooting efficiency
falls as a player's share of team possessions rises), team four factors
(Dean Oliver's shooting/turnover/rebounding/free-throw framework, rebuilt
from team season totals), and a comparison of top-5 versus 6-10 draft picks
on career defensive box plus/minus.

None of the analysis or interpretation lives in this README — the notebooks
and the stakeholder write-up below are where the actual results, statistics
and conclusions will be presented.

---

## Project status

- **Scraping, cleaning, database, and analysis-ready marts are all built
  and verified** — this is the part described above, and it works
  end-to-end.
- **`notebooks/`** is set up (`_setup.py` gives every notebook the same
  path to the repo root and to `utils`/`db_config`) but does not yet
  contain the per-question notebooks. That is the next phase of this
  project: one notebook per question, querying its `analyst_ready` table
  directly, with no analysis logic duplicated elsewhere.
- **`reports/`** currently holds only image assets (`assets/`) carried over
  from earlier chart drafts; the final, non-technical write-up for
  stakeholders has not been written yet.

---

## Documentation

- [`docs/schema.md`](docs/schema.md) — the `processed` schema: every table,
  every column, and the conventions that apply across all of them.
- [`docs/data_dictionary.md`](docs/data_dictionary.md) — the
  `analyst_ready` schema: what question each table answers, its grain, and
  every column.
- [`docs/cleaning_changes.md`](docs/cleaning_changes.md) — exactly what the
  cleaning rewrite changed from the original bootcamp output, and why each
  change was made.
