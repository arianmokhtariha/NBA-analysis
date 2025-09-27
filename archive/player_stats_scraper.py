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
urls = ['https://www.basketball-reference.com/leagues/NBA_' + year + '_totals.html' for year in year_range]

year ,rank , player_id ,age , team , position = [] , [] , [] , [] , [], []
g, gs , mp , fg , fga , fg_percent , three_p = [] , [] , [] , [] , [] , [] , []
three_pa , three_p_percent , two_p , two_pa = [] , [] , [] , [] 
two_p_percent , efg_percent , ft , fta , ft_percent = [] , [] , [] , [] , [] 
orb , drb , trb , ast ,stl , blk ,tov ,pf , pts , trp_dbl = [] , [] , [] , [] , [] , [], [] , [] , [] , [] 

for i ,url in enumerate(urls):
    driver.get(url)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "totals_stats")))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    counter = 0
    for row in soup.select('table#totals_stats tbody tr'):
        if counter == 70:
            break
        year.append(year_range[i])
        rank.append(node.text if (node := row.select_one('th[data-stat="ranker"]')) else None)
        player_id.append(player_id_extract(node['href']) if (node := row.select_one('td[data-stat="name_display"] a')) else None)
        age.append(node.text if (node := row.select_one('td[data-stat="age"]')) else None)
        team.append(node.text if (node := row.select_one('td[data-stat="team_name_abbr"] a')) else None)
        position.append(node.text if (node := row.select_one('td[data-stat="pos"]')) else None)
        g.append(node.text if (node := row.select_one('td[data-stat="games"]')) else None)
        gs.append(node.text if (node := row.select_one('td[data-stat="games_started"]')) else None)
        mp.append(node.text if (node := row.select_one('td[data-stat="mp"]')) else None)
        fg.append(node.text if (node := row.select_one('td[data-stat="fg"]')) else None)
        fga.append(node.text if (node := row.select_one('td[data-stat="fga"]')) else None)
        fg_percent.append(node.text if (node := row.select_one('td[data-stat="fg_pct"]')) else None)
        three_p.append(node.text if (node := row.select_one('td[data-stat="fg3"]')) else None)
        three_pa.append(node.text if (node := row.select_one('td[data-stat="fg3a"]')) else None)
        three_p_percent.append(node.text if (node := row.select_one('td[data-stat="fg3_pct"]')) else None)
        two_p.append(node.text if (node := row.select_one('td[data-stat="fg2"]')) else None)
        two_p_percent.append(node.text if (node := row.select_one('td[data-stat="fg2_pct"]')) else None)
        two_pa.append(node.text if (node := row.select_one('td[data-stat="fg2a"]')) else None)
        efg_percent.append(node.text if (node := row.select_one('td[data-stat="efg_pct"]')) else None)
        ft.append(node.text if (node := row.select_one('td[data-stat="ft"]')) else None)
        fta.append(node.text if (node := row.select_one('td[data-stat="fta"]')) else None)
        ft_percent.append(node.text if (node := row.select_one('td[data-stat="ft_pct"]')) else None)
        pts.append(node.text if (node := row.select_one('td[data-stat="pts"]')) else None)
        trb.append(node.text if (node := row.select_one('td[data-stat="trb"]')) else None)
        ast.append(node.text if (node := row.select_one('td[data-stat="ast"]')) else None)
        stl.append(node.text if (node := row.select_one('td[data-stat="stl"]')) else None)
        blk.append(node.text if (node := row.select_one('td[data-stat="blk"]')) else None)
        tov.append(node.text if (node := row.select_one('td[data-stat="tov"]')) else None)
        orb.append(node.text if (node := row.select_one('td[data-stat="orb"]')) else None)
        drb.append(node.text if (node := row.select_one('td[data-stat="drb"]')) else None)
        pf.append(node.text if (node := row.select_one('td[data-stat="pf"]')) else None)
        trp_dbl.append(node.text if (node := row.select_one('td[data-stat="tpl_dbl"]')) else None)
        counter += 1
    time.sleep(2)
driver.quit()

df_player_stats = pd.DataFrame({
    'Year' : year,
    'Rank' : rank,
    'Player_Id' : player_id,
    'Age' : age,
    'Team' : team,
    'Position' : position,
    'Games' : g,
    'Games Started' : gs,
    'Minutes Played' : mp,
    'FG' : fg,
    'FGA' : fga,
    'FG%' : fg_percent,
    '3P' : three_p,
    '3PA' : three_pa,
    '3p%' : three_p_percent,
    '2P' : two_p,
    '2PA' : two_pa,
    '2P%' : two_p_percent,
    'eFG%' : efg_percent,
    'FT' : ft,
    'FTA' : fta,
    'FT%' : ft_percent,
    'ORB' : orb,
    'DRB' : drb,
    'TRB' : trb,
    'AST' : ast,
    'STL' : stl,
    'BLK' : blk,
    'TOV' : tov,
    'PF' : pf,
    'PTS' : pts,
    'Trp_Dbl' :trp_dbl
})

df_player_stats.drop(df_player_stats[df_player_stats['Rank'].str.contains('Rk', case=False, na=True)].index, inplace=True)
df_player_stats.to_csv('player_stats' , index=False)

