#### Data-Analysis-Projects-2-Basketball
----

- **Stage 1** – Data Scraping: Player, team, roster, and award datasets were scraped from basketball-reference.com into the raw data/ directory

- **Stage 2** – Data Cleaning & Schema Creation: The raw files were normalized in data_analysis/data_preprocessing/, where identifiers, positions, and metrics were made consistent.

- **Stage 3** – Data Architecture & Relational Management: A MySQL warehouse was defined via create_db/data_classes.py, loaded through the companion ETL scripts, and documented with ER diagrams.

- **Stage 4** – Data Analysis & Visualization: --



-----
#### Project Ownership
----
##### Data Collection / Web Scraping 

- [@AlirezaNyi](https://github.com/AlirezaNyi)
  - `Scraper.py`
  - `data/seasons_teams_total_stats_clean.csv`
  - `data/teams_seasons_rosters_clean.csv`
- [@arianmokhtariha](https://github.com/arianmokhtariha)
  - `data/new_mvp_candidates.xlsx`
  - `data/seasons_table.xlsx`
  - `data/player_stats.csv`
- [@mohsen20roohi-hue](https://github.com/mohsen20roohi-hue)
  - `data/Player_table.csv`
  - `data/Players_table.csv`
  - `data/Mvp_table.csv`
  - `data/Advanced_stats.csv`

##### Data Cleaning & Schema Creation 

- [@MonaKheirieh](https://github.com/MonaKheirieh)
  - `data/data_clean/rosters.csv`
  - `data/data_clean/advanced_stats.csv`
  - `create_db/rosterdb-advancedb.py`
  - `data_analysis/data_preprocessing/advance_teamclean-mona.ipynb`
- [@anooshanth](https://github.com/anooshanth)
  - `data_analysis/data_preprocessing/01_data_cleaning_anoosha.py`
  - `data/data_clean/players.csv`
  - `data/data_clean/player_stats.csv`
  - `data/data_clean/mvp_candidates.csv`
  - `data/data_clean/mvp_winners.csv`
  - `data/data_clean/season_stats.csv`
  - `data/data_clean/team_lookup.csv`
  - `data/data_clean/teams_performance.csv`
  - `docs/schema.md`

##### Database Architecture & Documentation
- [@anooshanth](https://github.com/anooshanth)
  - `create_db/data_classes.py`
  - `create_db/load_data_to_db.py`
  - Database launch scripts, ER diagrams, and supporting docs

##### Data Analysis



