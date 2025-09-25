import pandas as pd
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Chrome()

def player_id_extract(url : str):
    return url.split('/')[-1].replace('.html' , '')

year_range = [str(i) for i in range(2019 , 2026)]
urls = ['https://www.basketball-reference.com/awards/awards_' + year + '.html' for year in year_range]

year ,rank , player_id ,age , team , first_place_vote = [] , [] , [] , [] , [] , []
points_won , points_max , share , games , mp , pts =[], [] , [] , [] , [] , [] 
trb , ast , stl , blk , fg_percent = [] , [] , [] , [] , []
three_pfg_percent , ft_percent , ws , ws_per_48m = [] , [] , [] , [] 

for i ,url in enumerate(urls):
    driver.get(url)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "mvp")))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    for row in soup.select('table#mvp tbody tr'):
        year.append(year_range[i])
        rank.append(node.text if (node := row.select_one('th[data-stat="rank"]')) else None)
        player_id.append(player_id_extract(node['href']) if (node := row.select_one('td[data-stat="player"] a')) else None)
        age.append(node.text if (node := row.select_one('td[data-stat="age"]')) else None)
        team.append(node.text if (node := row.select_one('td[data-stat="team_id"] a')) else None)
        first_place_vote.append(node.text if (node := row.select_one('td[data-stat="votes_first"]')) else None)
        points_won.append(node.text if (node := row.select_one('td[data-stat="points_won"]')) else None)
        points_max.append(node.text if (node := row.select_one('td[data-stat="points_max"]')) else None)
        share.append(node.text if (node := row.select_one('td[data-stat="award_share"]')) else None)
        games.append(node.text if (node := row.select_one('td[data-stat="g"]')) else None)
        mp.append(node.text if (node := row.select_one('td[data-stat="mp_per_g"]')) else None)
        pts.append(node.text if (node := row.select_one('td[data-stat="pts_per_g"]')) else None)
        trb.append(node.text if (node := row.select_one('td[data-stat="trb_per_g"]')) else None)
        ast.append(node.text if (node := row.select_one('td[data-stat="ast_per_g"]')) else None)
        stl.append(node.text if (node := row.select_one('td[data-stat="stl_per_g"]')) else None)
        blk.append(node.text if (node := row.select_one('td[data-stat="blk_per_g"]')) else None)
        fg_percent.append(node.text if (node := row.select_one('td[data-stat="fg_pct"]')) else None)
        three_pfg_percent.append(node.text if (node := row.select_one('td[data-stat="fg3_pct"]')) else None)
        ft_percent.append(node.text if (node := row.select_one('td[data-stat="ft_pct"]')) else None)
        ws.append(node.text if (node := row.select_one('td[data-stat="ws"]')) else None)
        ws_per_48m.append(node.text if (node := row.select_one('td[data-stat="ws_per_48"]')) else None)
    time.sleep(2)
driver.quit()
          
df_mvp_candidates = pd.DataFrame({
    'Year' : year,
    'Rank' : rank,
    'Player_Id' : player_id,
    'Age' : age,
    'Team' : team,
    'First_Place_Vote' : first_place_vote,
    'Pts Won' : points_won,
    'pts Max' : points_max,
    'Share' : share,
    'Games' : games,
    'MP' : mp,
    'PTS' : pts,
    'TRB' : trb,
    'AST' : ast,
    'STL' : stl,
    'BLK' : blk,
    'FG%' : fg_percent,
    '3P%' : three_pfg_percent,
    'FT%' : ft_percent,
    'WS' : ws,
    'WS/48' : ws_per_48m
})

df_mvp_candidates.to_csv('mvp_candidates' , index=False)
