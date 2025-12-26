# 🏀 NBA Data Engineering & Analytics Pipeline

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-red)
![MySQL](https://img.shields.io/badge/Database-MySQL-00618a)
![Scraping](https://img.shields.io/badge/Scraping-Selenium%20%7C%20BS4%20%7C%20Requests-green)
![Visualization](https://img.shields.io/badge/Visualization-Matplotlib%20%7C%20Seaborn-ff69b4)
![Stats](https://img.shields.io/badge/Statistical_Analysis-Mann--Whitney%20%7C%20Shapiro--Wilk%20%7C%20Yeo--Johnson-blueviolet)
![Status](https://img.shields.io/badge/Status-In%20Progress-yellow)

> **Credit & Collaboration Note:**  
> This project was originally developed as a group effort for Quera's Data Analysis bootcamp. This repository is a **continuation/fork** containing my own refactored code, database optimizations, and extended analysis.  
> **Original Team:** 
  [@AlirezaNyi](https://github.com/AlirezaNyi)
  [@arianmokhtariha](https://github.com/arianmokhtariha)
  [@mohsen20roohi-hue](https://github.com/mohsen20roohi-hue)
  [@MonaKheirieh](https://github.com/MonaKheirieh)
  [@anooshanth](https://github.com/anooshanth)

---

## 📖 Project Overview
This project is an end-to-end data pipeline that extracts historical NBA data, normalizes it into a relational database, and performs statistical analysis to identify player performance trends.

Unlike simple CSV analysis, this project builds a robust **Data Warehouse** using **MySQL** and **SQLAlchemy**, featuring a custom-built Object-Oriented Web Scraper and a normalized Star Schema database design.

## 🏗️ Architecture & Workflow

The project is divided into four distinct engineering stages:

### 1. Data Collection (Web Scraping)
*   **Tools:** `Selenium`, `BeautifulSoup4` (BS4), `Requests`
*   **Logic:** A custom `BasketballScraper` class (`Scraper.py`) automates the extraction of:
    *   Player bios and career stats (1980-2025).
    *   Season-by-season rosters and MVP voting results.
    *   Advanced metrics (PER, Win Shares, VORP).
    *   *Includes anti-bot detection handling and user-agent rotation.*

### 2. Data Cleaning & Normalization
*   **Tools:** `Pandas`, `NumPy`
*   **Process:** 
    *   Standardized player names and resolved ID conflicts.
    *   Converted imperial measurements (height/weight) to metric.
    *   Handled missing values for historical data (e.g., pre-3-point era).
    *   Output: Cleaned CSVs ready for database ingestion.

### 3. Database Architecture (Data Warehousing)
*   **Tools:** `MySQL`, `SQLAlchemy` (ORM)
*   **Schema:** Designed a Relational Database with Foreign Key constraints to ensure data integrity.
*   **Key Tables:**
    *   `players` (Dimension): Static player details.
    *   `player_stats` (Fact): Per-season performance.
    *   `mvp_winners` & `mvp_candidates`: Historical award tracking.
    *   `advanced_stats`: Sabermetrics (VORP, WS/48).

### 4. Statistical Analysis & Methodology
*   **Tools:** `SciPy`, `Statsmodels`, `Seaborn`
*   **Normalization & Distributions:**
    *   Applied **Yeo-Johnson transformations** to stabilize variance and normalize non-Gaussian distributions (e.g., Salary data, Win Shares).
    *   Validated distributional assumptions using **Shapiro-Wilk** tests and visualized results via **Q-Q Plots**.
*   **Hypothesis Testing:**
    *   **Mann-Whitney U Test:** Conducted non-parametric tests to compare median performance metrics (e.g., VORP) across distinct player clusters (e.g., Top 5 Draft Picks vs. Late Round Picks).
    *   **Pearson Correlation:** Calculated coefficients ($r$) and p-values to quantify the "Superstar Tax" (relationship between Usage Rate and True Shooting Percentage).
*   **Feature Engineering:**
    *   Derived "Availability" metrics by joining Roster data with Team Performance tables to calculate game participation ratios.

---

## 📂 Project Structure

```text
├── Scraper.py                   # Main OO-Scraper Class
├── create_db/
│   ├── data_classes.py          # SQLAlchemy ORM Models (Schema Definition)
│   ├── load_data_to_db.py       # ETL Script (CSV -> MySQL)
│   └── config_local.sample      # Database connection config
├── data_analysis/
│   └── data_preprocessing/      # Cleaning pipelines
├── presentation.ipynb           # 🚀 FINAL ANALYSIS & STORYTELLING
├── presentation_utils.py        # Helper functions for plotting & stats
├── docs/                        # Schema diagrams & Documentation
└── requirements.txt             # Dependencies
```

## 📊 Database Schema
The project uses a normalized schema defined in Python using SQLAlchemy. Below is a high-level view:

| Table | Description |
| :--- | :--- |
| **Players** | Primary dimension table. Contains biological info, draft history, and physical stats. |
| **Player_Stats** | Fact table linking Players to Seasons. Contains box score data (PTS, AST, REB). |
| **Advanced_Stats** | Analytical metrics including PER, Win Shares, and Box Plus/Minus. |
| **Rosters** | Link table tracking which team a player played for in a specific season. |
| **MVP_Candidates** | Voting shares and ranks for historical MVP races. |

---

## 🚀 How to Run

### 1. Prerequisites
*   Python 3.9+
*   MySQL Server installed locally.
*   Chrome Driver (managed automatically by `webdriver_manager`).

### 2. Setup
Clone the repository and install dependencies:
```bash
git clone https://github.com/YourUsername/NBA-Data-Pipeline.git
pip install -r requirements.txt
```

### 3. Database Configuration
1.  Navigate to `create_db/`.
2.  Rename `config_local.sample` to `config_local.py`.
3.  Update the file with your MySQL credentials:
    ```python
    DB_USER = "root"
    DB_PASSWORD = "yourpassword"
    DB_NAME = "basketball_stats"
    ```

### 4. Run the Pipeline
**To Scrape Data (Optional - data is already in `data/`):**
```bash
# Runs the interactive scraper notebook
jupyter notebook main_scraper.ipynb
```

**To Load Database:**
```bash
# Creates tables and loads clean CSVs into MySQL
python main.py load_data
```

**To View Analysis:**
Open `presentation.ipynb` in Jupyter Notebook/Lab to see the visualizations and statistical breakdown.

---

## 📈 Future Improvements
*   **Predictive Modeling:** Train a model to predict the next season's MVP based on the `mvp_candidates` historical data.