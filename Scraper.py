from bs4 import BeautifulSoup, NavigableString
import requests
import re
import pandas as pd
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
from selenium.webdriver.support import expected_conditions as EC
import random
from urllib.parse import urljoin, urlparse
import time
from datetime import datetime
from Utilies import *


class BasketballScraper:
    def __init__(self, headers, more_user_agent=[], way=1):
        self.way = way
        self._default_csv_folder = "data/"
        self._default_temp_path = "temp/"
        self._start_url = "https://www.basketball-reference.com/"

        USER_AGENTS = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/16.0 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/116.0.5845.96 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6; rv:130.0) Gecko/20100101 Firefox/130.0",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S916B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/22.0 Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.0.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/94.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]

        if more_user_agent is not None:
            USER_AGENTS.extend(more_user_agent)

        self._USER_AGENTS = USER_AGENTS

        session = requests.Session()
        session.headers.update(headers)
        self._session = session
        ensure_packages(["tqdm", "webdriver_manager"])
        self._tqdm = importlib.import_module("tqdm")

        try:
            self.get_teams("https://www.basketball-reference.com/leagues/")
            self.get_seasons("https://www.basketball-reference.com/leagues/")
        except Exception as e:
            print(f"[ERROR] {e} happend when making temp data pls run th cell again")

    def _fetch_page(self, url, max_retries=5, delay=3, way=1):
        session = self._session
        USER_AGENTS = self._USER_AGENTS
        # way = self.way
        # print(way)

        for attempt in range(1, max_retries + 1):
            ua = random.choice(USER_AGENTS)
            if way == 1:
                session.headers.update({"User-Agent": ua})
            else:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument(f"user-agent={ua}")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument(
                    "--disable-blink-features=AutomationControlled"
                )

            try:
                if way != 1:
                    driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=chrome_options,
                    )
                    driver.get(url)

                    time.sleep(delay + random.uniform(0, 2))

                    html = driver.page_source
                    driver.quit()
                    return html
                else:
                    resp = session.get(url, timeout=30)
                    if resp.status_code == 429:
                        wait = delay + random.uniform(0, 2)
                        print(
                            f"[WARN] 429 Too Many Requests. Waiting {wait:.1f}s (attempt {attempt})"
                        )
                        time.sleep(wait)
                        continue
                    resp.raise_for_status()
                    time.sleep(delay)
                    return resp.text

            except Exception as e:
                if way == 1:
                    wait = delay + random.uniform(0, 2)
                    print(
                        f"[WARN] Request failed ({e}). Retrying in {wait:.1f}s (attempt {attempt})"
                    )
                    time.sleep(wait)
                    print(
                        f"[ERROR] Failed to fetch {url} after {max_retries} attempts."
                    )
                else:
                    print(
                        f"[WARN] Selenium fetch failed ({e}). Retrying in {delay:.1f}s (attempt {attempt})"
                    )
                    time.sleep(delay + random.uniform(0, 2))
                    try:
                        driver.quit()
                    except:
                        pass
                    print(
                        f"[ERROR] Failed to fetch {url} after {max_retries} attempts with Selenium."
                    )

        return None

    def _to_snake(self, s):
        s = s.strip()
        s = s.rstrip(":")
        s = re.sub(r"[^\w]+", "_", s)
        s = re.sub(r"__+", "_", s)
        return s.strip("_").lower()

    def _try_int(self, v):
        v_stripped = v.replace(",", "").strip()
        if re.fullmatch(r"\d+", v_stripped):
            return int(v_stripped)
        return v

    def _parse_seasons(self, value):
        parts = [p.strip() for p in value.split(";") if p.strip()]
        out = {"raw": value, "count": None, "range": None}
        if not parts:
            return out
        m = re.match(r"^(\d+)$", parts[0])
        if m:
            out["count"] = int(m.group(1))
            if len(parts) > 1:
                out["range"] = parts[1]
        else:
            if len(parts) == 1 and re.search(r"\d{4}", parts[0]):
                out["range"] = parts[0]
        return out

    def _normalized(self, url):
        p = urlparse(url)
        return p._replace(fragment="").geturl()

    def _save_to_csv(self, file_name, target_arr, is_temp=False):
        target_df = None
        path_to_save = None

        try:
            target_df = pd.DataFrame(target_arr)
            make_df_pretty(target_df)

            if is_temp == True:
                path_to_save = f"{self._default_temp_path}{file_name}"
            else:
                path_to_save = f"{self._default_csv_folder}{file_name}"

            target_df.to_csv(path_to_save, index=False)
            print(f"[SUCCESS] {path_to_save} saved.")
        except Exception as e:
            print(f"[ERROR] Failed to save {file_name}.")
            print(f"[ERROR-DEATIL] :{e}")

        return None

    def get_teams(self, url):
        page = self._fetch_page(url, way=1)
        soup = BeautifulSoup(page, "html.parser")
        teamlinks = soup.find_all("a", href=re.compile(r"^/teams"))
        start_url = self._start_url
        teams = []

        p = self._tqdm.tqdm(total=len(teamlinks), desc="Teams Temp")
        for item in teamlinks:
            teams.append(
                {
                    "TeamName": item.get_text(strip=False),
                    "Link": urljoin(self._normalized(start_url), item["href"]),
                }
            )
            p.update(1)

        self._save_to_csv("teams_link.csv", teams, True)
        self._teams = teams
        p.close()

        return teams

    def get_seasons(self, url):
        html = self._fetch_page(url, way=1)
        if html is None:
            return None
        soup = BeautifulSoup(html, "html.parser")
        seasons = []
        seasonlinks = soup.find_all(
            "a", href=re.compile(r"^/leagues/NBA_[0-9]{4}.html$")
        )
        start_url = self._start_url

        p = self._tqdm.tqdm(total=len(seasonlinks), desc="Seasons Temp")
        for item in seasonlinks:
            if item.get_text(strip=False) == "NBA":
                continue
            seasons.append(
                {
                    "Season": item.get_text(strip=False),
                    "Link": urljoin(self._normalized(start_url), item["href"]),
                }
            )
            p.update(1)

        self._save_to_csv("seasons_link.csv", seasons, True)
        self._seasons = seasons
        p.close()

        return seasons

    def team_detail(self, team, seen):
        url = team["Link"]
        parsed = urlparse(url)
        parts = parsed.path.split("/")
        base_path = "/".join(parts[:3])
        href = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        if href in seen:
            return None

        html = self._fetch_page(href, way=1)
        if html is None:
            return {"link": href}

        soup = BeautifulSoup(html, "html.parser")
        seen.append(href)
        meta = None
        meta = soup.select_one("#info > #meta")
        result = {"link": href}
        if meta is None:
            return {"link": href}

        title_span = meta.select_one("h1 span")
        result["team_full_name"] = (
            title_span.get_text(strip=True) if title_span else None
        )

        for p in meta.select("p"):
            strong = p.find("strong")
            if not strong:
                continue

            label = strong.get_text(strip=True).rstrip(":")
            key = self._to_snake(label)

            parts = []
            for sib in strong.next_siblings:
                if isinstance(sib, NavigableString):
                    txt = str(sib)
                else:
                    txt = sib.get_text(separator=" ", strip=True)
                if txt and txt != "\n":
                    parts.append(txt)
            raw_value = " ".join(parts)
            value = re.sub(r"\s+", " ", raw_value).strip()
            value = value.strip(" ;:\n\t,")

            coerced = self._try_int(value)

            result[key] = coerced
            if key == "team_name":
                result["team_names"] = coerced
                del result["team_name"]
            if key == "seasons":
                parsed = self._parse_seasons(value)
                result["seasons_count"] = parsed.get("count")
                result["seasons_range"] = parsed.get("range")

        return result

    def all_teams_detail(self, max_test=None):

        seen = []
        teams_filterd = [
            d
            for d in self._teams
            if d.get("TeamName") != "F" and d.get("TeamName") != "Teams"
        ]
        team_details = []
        counter = 0

        p = self._tqdm.tqdm(total=len(teams_filterd), desc="Links")

        for team in teams_filterd:
            if max_test != None and counter > max_test:
                break
            res = self.team_detail(team, seen)
            if res != None:
                team_details.append(res)
            counter = counter + 1
            p.update(1)

        self._save_to_csv("teams.csv", team_details)
        p.close()

        return team_details

    def team_seasons_detail(self, team, seen):
        url = team["Link"]

        href = url
        if href in seen:
            return None

        html = self._fetch_page(href, way=1)
        if html is None:
            return {"link": href}

        soup = BeautifulSoup(html, "html.parser")
        seen.append(href)
        meta = None
        meta = soup.select_one("#info > #meta")
        result = {"link": href}
        if meta is None:
            return {"link": href}

        title_span = meta.select("h1 > span")
        result["team_full_name"] = (
            title_span[1].get_text(strip=True) if title_span[1] else None
        )
        result["season"] = title_span[0].get_text(strip=True) if title_span[0] else None

        for p in meta.select("p"):
            strong = p.find("strong")
            if not strong:
                continue

            label = strong.get_text(strip=True).rstrip(":")
            key = self._to_snake(label)

            if "_playoffs" in key:
                continue
            parts = []

            for sib in strong.next_siblings:
                if isinstance(sib, NavigableString):
                    txt = str(sib)
                else:
                    txt = sib.get_text(separator=" ", strip=True)
                if txt and txt != "\n":
                    parts.append(txt)
            raw_value = " ".join(parts)

            value = re.sub(r"\s+", " ", raw_value).strip()
            value = value.strip(" ;:\n\t,")

            coerced = self._try_int(value)
            result[key] = coerced

        return result

    def all_teams_seasons_detail(self, max_test=None):
        seen = []
        teams_filterd = [
            d
            for d in self._teams
            if d.get("TeamName") != "F" and d.get("TeamName") != "Teams"
        ]
        team_seasons_details = []
        counter = 0

        p = self._tqdm.tqdm(total=len(teams_filterd), desc="Links")

        for team in teams_filterd:
            if max_test != None and counter > max_test:
                break
            res = self.team_seasons_detail(team, seen)
            if res != None:
                team_seasons_details.append(res)

            counter = counter + 1
            p.update(1)

        self._save_to_csv("teams_seasons.csv", team_seasons_details)
        p.close()

        return team_seasons_details

    def team_seasons_roasters(self, team, seen):
        url = team["Link"]
        parsed = urlparse(url)
        parts = parsed.path.split("/")
        team_id = parts[2]
        href = url
        if href in seen:
            return None

        html = self._fetch_page(href, way=1)
        if html is None:
            return {"link": href}

        soup = BeautifulSoup(html, "html.parser")
        seen.append(href)
        meta = None
        meta = soup.select_one("#info > #meta")
        result = {"link": href}

        roasters = []

        if meta is None:
            return {"link": href}

        title_span = meta.select("h1 > span")
        result["team_full_name"] = (
            title_span[1].get_text(strip=True) if title_span[1] else None
        )
        result["season"] = title_span[0].get_text(strip=True) if title_span[0] else None
        roasters_table = soup.select_one("#roster")
        if roasters_table is None:
            return []

        trs_roaster = roasters_table.find_all("tr")

        for i in range(len(trs_roaster)):
            roasters.append(
                {
                    "TeamName": result["team_full_name"],
                    "Season": result["season"],
                    "PlayerName": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(2)"
                        )
                    ],
                    "Player_id": [
                        node.get_attribute_list("href")[0].split("/")[-1].split(".")[0]
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(2) > a"
                        )
                    ],
                    "Team_id": team_id,
                    "Pos": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(3)"
                        )
                    ],
                    "Ht": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(4)"
                        )
                    ],
                    "Wt": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(5)"
                        )
                    ],
                    "Birth Date": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(6)"
                        )
                    ],
                    "Birth": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(7)"
                        )
                    ],
                    "Exp": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(8)"
                        )
                    ],
                    "College": [
                        node.text.strip()
                        for node in roasters_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(9)"
                        )
                    ],
                }
            )

        return roasters

    def all_team_seasons_roasters(self, max_test=None):
        seen = []
        teams_filterd = [
            d
            for d in self._teams
            if d.get("TeamName") != "F" and d.get("TeamName") != "Teams"
        ]

        team_seasons_roasters = []
        counter = 0

        p = self._tqdm.tqdm(total=len(teams_filterd), desc="Links")
        for team in teams_filterd:
            if max_test != None and counter > max_test:
                break
            res = self.team_seasons_roasters(team, seen)
            if res != None:
                team_seasons_roasters.extend(res)
            counter = counter + 1
            p.update(1)

        self._save_to_csv("teams_seasons_rosters_clean.csv", team_seasons_roasters)
        p.close()

        return team_seasons_roasters

    def seasons_total_stats(self, season, seen):
        url = season["Link"]
        season = season["Season"]
        href = url
        if href in seen:
            return None
        html = self._fetch_page(href, way=1)
        if html is None:
            return {"link": href}

        soup = BeautifulSoup(html, "html.parser")
        seen.append(href)

        meta = None
        meta = soup.select_one("#info > #meta")
        result = {"link": href}

        stats = []
        if meta is None:
            return {"link": href}

        result["season"] = season
        total_table = soup.select_one("#totals-team")

        if total_table is None:
            return []
        trs_total = len(total_table.find_all("tr"))

        for i in range(trs_total):
            stats.append(
                {
                    "Rk": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > th:nth-child(1)"
                        )
                    ],
                    "Season": result["season"],
                    "TeamName": [
                        node.get_text(strip=True)
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(2) > a"
                        )
                    ],
                    "TeamId": [
                        node.get_attribute_list("href")[0].split("/")[-2].split(".")[0]
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(2) > a"
                        )
                    ],
                    "G": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(3)"
                        )
                    ],
                    "MP": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(4)"
                        )
                    ],
                    "FG": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(5)"
                        )
                    ],
                    "FGA": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(6)"
                        )
                    ],
                    "FG%": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(7)"
                        )
                    ],
                    "3P": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(8)"
                        )
                    ],
                    "3PA": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(9)"
                        )
                    ],
                    "3P%": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(10)"
                        )
                    ],
                    "2P": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(11)"
                        )
                    ],
                    "2PA": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(12)"
                        )
                    ],
                    "2P%": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(13)"
                        )
                    ],
                    "FT": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(14)"
                        )
                    ],
                    "FTA": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(15)"
                        )
                    ],
                    "FT%": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(16)"
                        )
                    ],
                    "ORB": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(17)"
                        )
                    ],
                    "DRB": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(18)"
                        )
                    ],
                    "TRB": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(19)"
                        )
                    ],
                    "AST": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(20)"
                        )
                    ],
                    "STL": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(21)"
                        )
                    ],
                    "BLK": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(22)"
                        )
                    ],
                    "TOV": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(23)"
                        )
                    ],
                    "PF": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(24)"
                        )
                    ],
                    "PTS": [
                        node.text.strip()
                        for node in total_table.select(
                            f"tbody > tr:nth-child({i+1}) > td:nth-child(25)"
                        )
                    ],
                }
            )
        return stats

    def all_seasons_total_stats(self, max_text=None):
        seen = []
        seasons_teams_total_stats = []
        counter = 0

        p = self._tqdm.tqdm(total=len(self._seasons), desc="Links")

        for season in self._seasons:
            if max_text != None and counter > max_text:
                break
            res = self.seasons_total_stats(season, seen)
            if res != None:
                seasons_teams_total_stats.extend(res)

            counter = counter + 1
            p.update(1)

        self._save_to_csv("seasons_teams_total_stats.csv", seasons_teams_total_stats)
        p.close()

        return seasons_teams_total_stats

    def _player_id_extract(self, url):
        return url.split("/")[-1].replace(".html", "")

    def mvp_candidate(
        self,
        url,
        year_range,
        i,
        year,
        rank,
        player_id,
        age,
        team,
        first_place_vote,
        points_won,
        points_max,
        share,
        games,
        mp,
        pts,
        trb,
        ast,
        stl,
        blk,
        fg_percent,
        three_pfg_percent,
        ft_percent,
        ws,
        ws_per_48m,
    ):

        html = self._fetch_page(url, way=1)
        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("table#mvp tbody tr"):
            year.append(year_range[i])
            rank.append(
                node.text if (node := row.select_one('th[data-stat="rank"]')) else None
            )
            player_id.append(
                self._player_id_extract(node["href"])
                if (node := row.select_one('td[data-stat="player"] a'))
                else None
            )
            age.append(
                node.text if (node := row.select_one('td[data-stat="age"]')) else None
            )
            team.append(
                node.text
                if (node := row.select_one('td[data-stat="team_id"] a'))
                else None
            )
            first_place_vote.append(
                node.text
                if (node := row.select_one('td[data-stat="votes_first"]'))
                else None
            )
            points_won.append(
                node.text
                if (node := row.select_one('td[data-stat="points_won"]'))
                else None
            )
            points_max.append(
                node.text
                if (node := row.select_one('td[data-stat="points_max"]'))
                else None
            )
            share.append(
                node.text
                if (node := row.select_one('td[data-stat="award_share"]'))
                else None
            )
            games.append(
                node.text if (node := row.select_one('td[data-stat="g"]')) else None
            )
            mp.append(
                node.text
                if (node := row.select_one('td[data-stat="mp_per_g"]'))
                else None
            )
            pts.append(
                node.text
                if (node := row.select_one('td[data-stat="pts_per_g"]'))
                else None
            )
            trb.append(
                node.text
                if (node := row.select_one('td[data-stat="trb_per_g"]'))
                else None
            )
            ast.append(
                node.text
                if (node := row.select_one('td[data-stat="ast_per_g"]'))
                else None
            )
            stl.append(
                node.text
                if (node := row.select_one('td[data-stat="stl_per_g"]'))
                else None
            )
            blk.append(
                node.text
                if (node := row.select_one('td[data-stat="blk_per_g"]'))
                else None
            )
            fg_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="fg_pct"]'))
                else None
            )
            three_pfg_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="fg3_pct"]'))
                else None
            )
            ft_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="ft_pct"]'))
                else None
            )
            ws.append(
                node.text if (node := row.select_one('td[data-stat="ws"]')) else None
            )
            ws_per_48m.append(
                node.text
                if (node := row.select_one('td[data-stat="ws_per_48"]'))
                else None
            )

    def all_mvp_candidate(
        self, base_url="https://www.basketball-reference.com/awards/awards_"
    ):
        year_range = [str(i) for i in range(2019, 2026)]
        urls = [base_url + year + ".html" for year in year_range]

        year, rank, player_id, age, team, first_place_vote = [], [], [], [], [], []
        points_won, points_max, share, games, mp, pts = [], [], [], [], [], []
        trb, ast, stl, blk, fg_percent = [], [], [], [], []
        three_pfg_percent, ft_percent, ws, ws_per_48m = [], [], [], []

        p = self._tqdm.tqdm(total=len(urls), desc="Links")

        for i, url in enumerate(urls):
            self.mvp_candidate(
                url,
                year_range,
                i,
                year,
                rank,
                player_id,
                age,
                team,
                first_place_vote,
                points_won,
                points_max,
                share,
                games,
                mp,
                pts,
                trb,
                ast,
                stl,
                blk,
                fg_percent,
                three_pfg_percent,
                ft_percent,
                ws,
                ws_per_48m,
            )
            time.sleep(1)
            p.update(1)

        self._save_to_csv(
            "mvp_candidates.csv",
            {
                "Year": year,
                "Rank": rank,
                "Player_Id": player_id,
                "Age": age,
                "Team": team,
                "First_Place_Vote": first_place_vote,
                "Pts Won": points_won,
                "pts Max": points_max,
                "Share": share,
                "Games": games,
                "MP": mp,
                "PTS": pts,
                "TRB": trb,
                "AST": ast,
                "STL": stl,
                "BLK": blk,
                "FG%": fg_percent,
                "3P%": three_pfg_percent,
                "FT%": ft_percent,
                "WS": ws,
                "WS/48": ws_per_48m,
            },
        )
        p.close()

    def player_stats(
        self,
        url,
        year_range,
        i,
        year,
        rank,
        player_id,
        age,
        team,
        position,
        g,
        gs,
        mp,
        fg,
        fga,
        fg_percent,
        three_p,
        three_pa,
        three_p_percent,
        two_p,
        two_pa,
        two_p_percent,
        efg_percent,
        ft,
        fta,
        ft_percent,
        orb,
        drb,
        trb,
        ast,
        stl,
        blk,
        tov,
        pf,
        pts,
        trp_dbl,
    ):

        html = self._fetch_page(url, way=1)
        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")

        counter = 0
        for row in soup.select("table#totals_stats tbody tr"):
            if (
                "Rk" in node.text
                if (node := row.select_one('th[data-stat="ranker"]'))
                else ""
            ):
                continue
            if counter == 70:
                break
            year.append(year_range[i])
            rank.append(
                node.text
                if (node := row.select_one('th[data-stat="ranker"]'))
                else None
            )
            player_id.append(
                self._player_id_extract(node["href"])
                if (node := row.select_one('td[data-stat="name_display"] a'))
                else None
            )
            age.append(
                node.text if (node := row.select_one('td[data-stat="age"]')) else None
            )
            team.append(
                node.text
                if (node := row.select_one('td[data-stat="team_name_abbr"] a'))
                else None
            )
            position.append(
                node.text if (node := row.select_one('td[data-stat="pos"]')) else None
            )
            g.append(
                node.text if (node := row.select_one('td[data-stat="games"]')) else None
            )
            gs.append(
                node.text
                if (node := row.select_one('td[data-stat="games_started"]'))
                else None
            )
            mp.append(
                node.text if (node := row.select_one('td[data-stat="mp"]')) else None
            )
            fg.append(
                node.text if (node := row.select_one('td[data-stat="fg"]')) else None
            )
            fga.append(
                node.text if (node := row.select_one('td[data-stat="fga"]')) else None
            )
            fg_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="fg_pct"]'))
                else None
            )
            three_p.append(
                node.text if (node := row.select_one('td[data-stat="fg3"]')) else None
            )
            three_pa.append(
                node.text if (node := row.select_one('td[data-stat="fg3a"]')) else None
            )
            three_p_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="fg3_pct"]'))
                else None
            )
            two_p.append(
                node.text if (node := row.select_one('td[data-stat="fg2"]')) else None
            )
            two_p_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="fg2_pct"]'))
                else None
            )
            two_pa.append(
                node.text if (node := row.select_one('td[data-stat="fg2a"]')) else None
            )
            efg_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="efg_pct"]'))
                else None
            )
            ft.append(
                node.text if (node := row.select_one('td[data-stat="ft"]')) else None
            )
            fta.append(
                node.text if (node := row.select_one('td[data-stat="fta"]')) else None
            )
            ft_percent.append(
                node.text
                if (node := row.select_one('td[data-stat="ft_pct"]'))
                else None
            )
            pts.append(
                node.text if (node := row.select_one('td[data-stat="pts"]')) else None
            )
            trb.append(
                node.text if (node := row.select_one('td[data-stat="trb"]')) else None
            )
            ast.append(
                node.text if (node := row.select_one('td[data-stat="ast"]')) else None
            )
            stl.append(
                node.text if (node := row.select_one('td[data-stat="stl"]')) else None
            )
            blk.append(
                node.text if (node := row.select_one('td[data-stat="blk"]')) else None
            )
            tov.append(
                node.text if (node := row.select_one('td[data-stat="tov"]')) else None
            )
            orb.append(
                node.text if (node := row.select_one('td[data-stat="orb"]')) else None
            )
            drb.append(
                node.text if (node := row.select_one('td[data-stat="drb"]')) else None
            )
            pf.append(
                node.text if (node := row.select_one('td[data-stat="pf"]')) else None
            )
            trp_dbl.append(
                node.text
                if (node := row.select_one('td[data-stat="tpl_dbl"]'))
                else None
            )
            counter += 1

    def all_player_stats(
        self, base_url="https://www.basketball-reference.com/leagues/NBA_"
    ):
        year_range = [str(i) for i in range(2019, 2026)]
        urls = [base_url + year + "_totals.html" for year in year_range]

        year, rank, player_id, age, team, position = [], [], [], [], [], []
        g, gs, mp, fg, fga, fg_percent, three_p = [], [], [], [], [], [], []
        three_pa, three_p_percent, two_p, two_pa = [], [], [], []
        two_p_percent, efg_percent, ft, fta, ft_percent = [], [], [], [], []
        orb, drb, trb, ast, stl, blk, tov, pf, pts, trp_dbl = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )

        p = self._tqdm.tqdm(total=len(urls), desc="Links")

        for i, url in enumerate(urls):
            self.player_stats(
                url,
                year_range,
                i,
                year,
                rank,
                player_id,
                age,
                team,
                position,
                g,
                gs,
                mp,
                fg,
                fga,
                fg_percent,
                three_p,
                three_pa,
                three_p_percent,
                two_p,
                two_pa,
                two_p_percent,
                efg_percent,
                ft,
                fta,
                ft_percent,
                orb,
                drb,
                trb,
                ast,
                stl,
                blk,
                tov,
                pf,
                pts,
                trp_dbl,
            )
            time.sleep(1)
            p.update(1)

        self._save_to_csv(
            "player_stats.csv",
            {
                "Year": year,
                "Rank": rank,
                "Player_Id": player_id,
                "Age": age,
                "Team": team,
                "Position": position,
                "Games": g,
                "Games Started": gs,
                "Minutes Played": mp,
                "FG": fg,
                "FGA": fga,
                "FG%": fg_percent,
                "3P": three_p,
                "3PA": three_pa,
                "3p%": three_p_percent,
                "2P": two_p,
                "2PA": two_pa,
                "2P%": two_p_percent,
                "eFG%": efg_percent,
                "FT": ft,
                "FTA": fta,
                "FT%": ft_percent,
                "ORB": orb,
                "DRB": drb,
                "TRB": trb,
                "AST": ast,
                "STL": stl,
                "BLK": blk,
                "TOV": tov,
                "PF": pf,
                "PTS": pts,
                "Trp_Dbl": trp_dbl,
            },
        )
        p.close()

    def seasons_details(self, base_url="https://www.basketball-reference.com/leagues/"):
        html = self._fetch_page(base_url, way=2)

        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")
        season = []
        league = []
        champion = []
        mvp = []
        rookie = []
        points = []
        rebounds = []
        assists = []
        win_shares = []

        p = self._tqdm.tqdm(
            total=len(soup.select("table#stats tbody tr")), desc="Links"
        )

        for row in soup.select("table#stats tbody tr"):
            if row.select_one('th[data-stat="season"]'):
                if row.select_one('th[data-stat="season"]').text == "2025-26" or None:
                    continue
                season.append(
                    node.text
                    if (node := row.select_one('th[data-stat="season"] a'))
                    else None
                )
                league.append(
                    node.text
                    if (node := row.select_one('td[data-stat="lg_id"] a'))
                    else None
                )
                champion.append(
                    node.text
                    if (node := row.select_one('td[data-stat="champion"] a'))
                    else None
                )
                mvp.append(
                    node.text
                    if (node := row.select_one('td[data-stat="mvp"] a'))
                    else None
                )
                rookie.append(
                    node.text
                    if (node := row.select_one('td[data-stat="roy"] a'))
                    else None
                )
                points.append(
                    node.text
                    if (node := row.select_one('td[data-stat="pts_leader_name"] a'))
                    else None
                )
                rebounds.append(
                    node.text
                    if (node := row.select_one('td[data-stat="trb_leader_name"] a'))
                    else None
                )
                assists.append(
                    node.text
                    if (node := row.select_one('td[data-stat="ast_leader_name"] a'))
                    else None
                )
                win_shares.append(
                    node.text
                    if (node := row.select_one('td[data-stat="ws_leader_name"] a'))
                    else None
                )
                p.update(1)

        data = {
            "Season Year": season,
            "League": league,
            "Champion Name": champion,
            "MVP": mvp,
            "Rookie of the Year": rookie,
            "Most Points": points,
            "Most Rebounds": rebounds,
            "Most Assists": assists,
            "Most Winshares": win_shares,
        }
        self._save_to_csv("seasons_table.csv", data)
        p.close()

        return None

    def advanced_stats(
        self,
        url,
        year_range,
        i,
        Season,
        Rank,
        Player_id,
        Age,
        Team,
        Position,
        Games,
        Games_started,
        Minute_Played,
        Player_Efficiency_Rate,
        True_Shooting_Percentage,
        Three_Point_Attempt_Rate,
        Free_Throw_Attempt_Rate,
        Offensive_Rebound_Percentage,
        Defensive_Rebound_Percentage,
        Total_Rebound_Percentage,
        Assist_Percentage,
        Steal_Percentage,
        Block_Percentage,
        Turnover_Percentage,
        Usage_Percentage,
        Offensive_Win_Shares,
        Defensive_Win_Shares,
        Win_Shares,
        Win_Shares_Per_48_Minutes,
        Offensive_Box_Plus_Minus,
        Defensive_Box_Plus_Minus,
        Box_Plus_Minus,
        Value_over_Replacement_Player,
    ):

        html = self._fetch_page(url, way=1)
        if html is None:
            return None

        soup = BeautifulSoup(html, "html.parser")

        for row in soup.select("table#advanced tbody tr"):
            if (
                "Rk" in node.text
                if (node := row.select_one('th[data-stat="ranker"]'))
                else ""
            ):
                continue
            Season.append(year_range[i])
            Rank.append(
                node.text
                if (node := row.select_one('th[data-stat="ranker"]'))
                else None
            )
            Player_id.append(
                self._player_id_extract(node["href"])
                if (node := row.select_one('td[data-stat="name_display"] a'))
                else None
            )
            Age.append(
                node.text if (node := row.select_one('td[data-stat="age"]')) else None
            )
            Team.append(
                node.text
                if (node := row.select_one('td[data-stat="team_name_abbr"] a'))
                else None
            )
            Position.append(
                node.text if (node := row.select_one('td[data-stat="pos"]')) else None
            )

            Games.append(
                node.text if (node := row.select_one('td[data-stat="games"]')) else None
            )
            Games_started.append(
                node.text
                if (node := row.select_one('td[data-stat="games_started"]'))
                else None
            )
            Minute_Played.append(
                node.text if (node := row.select_one('td[data-stat="mp"]')) else None
            )
            Player_Efficiency_Rate.append(
                node.text if (node := row.select_one('td[data-stat="per"]')) else None
            )
            True_Shooting_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="ts_pct"]'))
                else None
            )
            Three_Point_Attempt_Rate.append(
                node.text
                if (node := row.select_one('td[data-stat="fg3a_per_fga_pct"]'))
                else None
            )

            Free_Throw_Attempt_Rate.append(
                node.text
                if (node := row.select_one('td[data-stat="fta_per_fga_pct"]'))
                else None
            )
            Offensive_Rebound_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="orb_pct"]'))
                else None
            )
            Defensive_Rebound_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="drb_pct"]'))
                else None
            )
            Total_Rebound_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="trb_pct"]'))
                else None
            )
            Assist_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="ast_pct"]'))
                else None
            )

            Steal_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="stl_pct"]'))
                else None
            )
            Block_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="blk_pct"]'))
                else None
            )
            Turnover_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="tov_pct"]'))
                else None
            )
            Usage_Percentage.append(
                node.text
                if (node := row.select_one('td[data-stat="usg_pct"]'))
                else None
            )
            Offensive_Win_Shares.append(
                node.text if (node := row.select_one('td[data-stat="ows"]')) else None
            )

            Defensive_Win_Shares.append(
                node.text if (node := row.select_one('td[data-stat="dws"]')) else None
            )
            Win_Shares.append(
                node.text if (node := row.select_one('td[data-stat="ws"]')) else None
            )
            Win_Shares_Per_48_Minutes.append(
                node.text
                if (node := row.select_one('td[data-stat="ws_per_48"]'))
                else None
            )
            Offensive_Box_Plus_Minus.append(
                node.text if (node := row.select_one('td[data-stat="obpm"]')) else None
            )
            Defensive_Box_Plus_Minus.append(
                node.text if (node := row.select_one('td[data-stat="dbpm"]')) else None
            )

            Box_Plus_Minus.append(
                node.text if (node := row.select_one('td[data-stat="bpm"]')) else None
            )
            Value_over_Replacement_Player.append(
                node.text if (node := row.select_one('td[data-stat="vorp"]')) else None
            )

    def all_advanced_stats(
        self, base_url="https://www.basketball-reference.com/leagues/NBA_"
    ):
        year_range = [str(i) for i in range(2019, 2026)]
        urls = [base_url + year + "_advanced.html" for year in year_range]

        Season, Rank, Player_id, Age, Team, Position = [], [], [], [], [], []
        (
            Games,
            Games_started,
            Minute_Played,
            Player_Efficiency_Rate,
            True_Shooting_Percentage,
            Three_Point_Attempt_Rate,
        ) = ([], [], [], [], [], [])
        (
            Free_Throw_Attempt_Rate,
            Offensive_Rebound_Percentage,
            Defensive_Rebound_Percentage,
            Total_Rebound_Percentage,
            Assist_Percentage,
        ) = ([], [], [], [], [])
        (
            Steal_Percentage,
            Block_Percentage,
            Turnover_Percentage,
            Usage_Percentage,
            Offensive_Win_Shares,
        ) = ([], [], [], [], [])
        (
            Defensive_Win_Shares,
            Win_Shares,
            Win_Shares_Per_48_Minutes,
            Offensive_Box_Plus_Minus,
            Defensive_Box_Plus_Minus,
        ) = ([], [], [], [], [])
        Box_Plus_Minus, Value_over_Replacement_Player = [], []

        p = self._tqdm.tqdm(total=len(urls), desc="Links")

        for i, url in enumerate(urls):
            self.advanced_stats(
                url,
                year_range,
                i,
                Season,
                Rank,
                Player_id,
                Age,
                Team,
                Position,
                Games,
                Games_started,
                Minute_Played,
                Player_Efficiency_Rate,
                True_Shooting_Percentage,
                Three_Point_Attempt_Rate,
                Free_Throw_Attempt_Rate,
                Offensive_Rebound_Percentage,
                Defensive_Rebound_Percentage,
                Total_Rebound_Percentage,
                Assist_Percentage,
                Steal_Percentage,
                Block_Percentage,
                Turnover_Percentage,
                Usage_Percentage,
                Offensive_Win_Shares,
                Defensive_Win_Shares,
                Win_Shares,
                Win_Shares_Per_48_Minutes,
                Offensive_Box_Plus_Minus,
                Defensive_Box_Plus_Minus,
                Box_Plus_Minus,
                Value_over_Replacement_Player,
            )
            time.sleep(1)
            p.update(1)

        self._save_to_csv(
            "Advanced_stats.csv",
            {
                "Season": Season,
                "Rank": Rank,
                "Player_id": Player_id,
                "Age": Age,
                "Team": Team,
                "Position": Position,
                "Games": Games,
                "Games_started": Games_started,
                "Minute_Played": Minute_Played,
                "Player_Efficiency_Rate": Player_Efficiency_Rate,
                "True_Shooting_Percentage": True_Shooting_Percentage,
                "Three_Point_Attempt_Rate": Three_Point_Attempt_Rate,
                "Free_Throw_Attempt_Rate": Free_Throw_Attempt_Rate,
                "Offensive_Rebound_Percentage": Offensive_Rebound_Percentage,
                "Defensive_Rebound_Percentage": Defensive_Rebound_Percentage,
                "Total_Rebound_Percentage": Total_Rebound_Percentage,
                "Assist_Percentage": Assist_Percentage,
                "Steal_Percentage": Steal_Percentage,
                "Block_Percentage": Block_Percentage,
                "Turnover_Percentage": Turnover_Percentage,
                "Usage_Percentage": Usage_Percentage,
                "Offensive_Win_Shares": Offensive_Win_Shares,
                "Defensive_Win_Shares": Defensive_Win_Shares,
                "Win_Shares": Win_Shares,
                "Win_Shares_Per_48_Minutes": Win_Shares_Per_48_Minutes,
                "Offensive_Box_Plus_Minus": Offensive_Box_Plus_Minus,
                "Defensive_Box_Plus_Minus": Defensive_Box_Plus_Minus,
                "Box_Plus_Minus": Box_Plus_Minus,
                "Value_over_Replacement_Player": Value_over_Replacement_Player,
            },
        )
        p.close()

    def players(self,url='https://www.basketball-reference.com/players/g/gilgesh01.html'):
        page = self._fetch_page(url, way=1)
        soup = BeautifulSoup(page , 'html.parser')
        posts=[]

        posts.append(
            {
                'player_id': url.split('/')[-1].split('.')[0],
                'player_name': [node.text.strip() for node in soup.select("h1")],
                'Position':[node.text.strip().split('\n\n\n  \n  ▪\n  \n  \n  ') for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')][0].strip('Position:'),
                'Shoots':[node.text.strip().split('\n\n\n  \n  ▪\n  \n  \n  ') for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')][1].split('Shoots:\n  \n  ')[1],
                'Height':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][0].replace(',',''),
                'Weight':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][1].replace('lb',''),
                'Birthday':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][1],
                'Birthmonth':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][0],
                'Birthyear':[node.text.split() for node in soup.select('a[href*=birthyears]')][0],
                'College' : [node.text.split() for node in soup.select('a[href*=colleges]')][0],
                'Last Season Games':[node.text.split() for node in soup.select('.p1 p')][0],
                'Last Season Points':[node.text.split() for node in soup.select('.p1 p')][2],
                'Last Season Total Rebound Percentage':[node.text.split() for node in soup.select('.p1 p')][4],
                'Last Season Assists Percentage':[node.text.split() for node in soup.select('.p1 p')][6],

                'Last Season Field Goal Percentage':[node.text.split() for node in soup.select('.p1 p')][0],
                'Last Season 3pt Field Goal Percentage':[node.text.split() for node in soup.select('.p1 p')][2],
                'Last Season TFree Throw Percentage':[node.text.split() for node in soup.select('.p1 p')][4],
                'Last Season Effective Field Goal Percentage':[node.text.split() for node in soup.select('.p1 p')][6],

                'Experience':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Experience:')][1],
                'Career Games':[node.text.split() for node in soup.select('.p1 p')][1],
                'Career Points':[node.text.split() for node in soup.select('.p1 p')][3],
                'Career Total Rebound Percentage':[node.text.split() for node in soup.select('.p1 p')][5],
                'Career Assists Percentage':[node.text.split() for node in soup.select('.p1 p')][7],

                'Career Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][1],
                'Career 3pt Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][3],
                'Career Free Throw Percentage':[node.text.split() for node in soup.select('.p2 p')][5],
                'Career Effective Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][7],

                })
        self._save_to_csv('Players_table.csv',posts)
        return posts
        
    def mvps(self,url='https://www.basketball-reference.com/awards/mvp.html'):
        page = self._fetch_page(url, way=1)
        soup = BeautifulSoup(page , 'html.parser')
        posts = []
        for i in range(70):
            posts.append(
                {
                    'Season':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > th")],
                    'League':'NBA',
                    'Player_id':[node.get_attribute_list('href')[0].split('/')[-1].split('.')[0] for node in soup.select(f"a[href*='players']")][i+1],
                    'Age': [node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(5)")],
                    'Team_id': [node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(6)")],
                    'Game': [node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(7)")],
                    'Minutes Played Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(8)")],
                    'Points Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(9)")],
                    'Total Rebounds Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(10)")],
                    'Assists Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(11)")],
                    'Steals Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(12)")],
                    'Blocks Per Game':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(13)")],
                    'Field Goal Percentage':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(14)")],
                    '3-Point Field Goal Percentage':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(15)")],
                    'Free Throw Percentage':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(16)")],
                    'Win Shares':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(17)")],
                    'Win Shares Per 48 Minutes':[node.text.strip() for node in soup.select(f"#mvp_NBA > tbody > tr:nth-child({i+1}) > td:nth-child(18)")],
                }
            )
        self._save_to_csv('Mvp_table.csv',posts)
        return posts