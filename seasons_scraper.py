import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

url = 'https://www.basketball-reference.com/leagues/'

driver = webdriver.Chrome()
driver.get(url)

wait = WebDriverWait(driver, 10)
wait.until(EC.presence_of_element_located((By.ID, "stats")))

soup = BeautifulSoup(driver.page_source, 'html.parser')


season = []
league = []
champion = []
mvp = []
rookie = []
points = []
rebounds = []
assists = []
win_shares = []
for row in soup.select('table#stats tbody tr'):
    if row.select_one('th[data-stat="season"]'):
        if row.select_one('th[data-stat="season"]').text == '2025-26' or None:
            continue
        season.append(node.text if (node := row.select_one('th[data-stat="season"] a')) else None)
        league.append(node.text if (node := row.select_one('td[data-stat="lg_id"] a')) else None)
        champion.append(node.text if (node := row.select_one('td[data-stat="champion"] a')) else None)
        mvp.append(node.text if (node := row.select_one('td[data-stat="mvp"] a')) else None)
        rookie.append(node.text if (node := row.select_one('td[data-stat="roy"] a')) else None)
        points.append(node.text if (node := row.select_one('td[data-stat="pts_leader_name"] a')) else None)
        rebounds.append(node.text if (node := row.select_one('td[data-stat="trb_leader_name"] a')) else None)
        assists.append(node.text if (node := row.select_one('td[data-stat="ast_leader_name"] a')) else None)
        win_shares.append(node.text if (node := row.select_one('td[data-stat="ws_leader_name"] a')) else None)

data = {
    'Season Year': season,
    'League': league,
    'Champion Name': champion,
    'MVP': mvp,
    'Rookie of the Year': rookie,
    'Most Points' : points,
    'Most Rebounds' : rebounds,
    'Most Assists' : assists,
    'Most Winshares' : win_shares
}

df_seasons = pd.DataFrame(data)
df_seasons.dropna(how='all', inplace=True)

driver.quit()

df_seasons.to_csv('seasons_table' , index=False)