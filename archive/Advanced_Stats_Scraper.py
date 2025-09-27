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
urls = ['https://www.basketball-reference.com/leagues/NBA_' + year + '_advanced.html' for year in year_range]

Season ,Rank , Player_id ,Age , Team , Position = [] , [] , [] , [] , [] , []

Games , Games_started , Minute_Played, Player_Efficiency_Rate , True_Shooting_Percentage , Three_Point_Attempt_Rate =[], [] , [] , [] , [] , [] 

Free_Throw_Attempt_Rate , Offensive_Rebound_Percentage , Defensive_Rebound_Percentage , Total_Rebound_Percentage , Assist_Percentage = [] , [] , [] , [] , []

Steal_Percentage , Block_Percentage , Turnover_Percentage , Usage_Percentage ,Offensive_Win_Shares = [] , [] , [] , [] ,[]

Defensive_Win_Shares , Win_Shares , Win_Shares_Per_48_Minutes , Offensive_Box_Plus_Minus ,Defensive_Box_Plus_Minus  = [] , [] , [] , [] ,[]

Box_Plus_Minus ,Value_over_Replacement_Player = [] , []

for i ,url in enumerate(urls):
    driver.get(url)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.ID, "advanced")))
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    for row in soup.select('table#advanced tbody tr'):
        Season .append(year_range[i])
        Rank.append(node.text if (node := row.select_one('th[data-stat="ranker"]')) else None)
        Player_id.append(player_id_extract(node['href']) if (node := row.select_one('td[data-stat="name_display"] a')) else None)
        Age.append(node.text if (node := row.select_one('td[data-stat="age"]')) else None)
        Team.append(node.text if (node := row.select_one('td[data-stat="team_name_abbr"] a')) else None)
        Position.append(node.text if (node := row.select_one('td[data-stat="pos"]')) else None)

        Games.append(node.text if (node := row.select_one('td[data-stat="games"]')) else None)
        Games_started.append(node.text if (node := row.select_one('td[data-stat="games_started"]')) else None)
        Minute_Played.append(node.text if (node := row.select_one('td[data-stat="mp"]')) else None)
        Player_Efficiency_Rate.append(node.text if (node := row.select_one('td[data-stat="per"]')) else None)
        True_Shooting_Percentage.append(node.text if (node := row.select_one('td[data-stat="ts_pct"]')) else None)
        Three_Point_Attempt_Rate.append(node.text if (node := row.select_one('td[data-stat="fg3a_per_fga_pct"]')) else None)

        Free_Throw_Attempt_Rate.append(node.text if (node := row.select_one('td[data-stat="fta_per_fga_pct"]')) else None)
        Offensive_Rebound_Percentage.append(node.text if (node := row.select_one('td[data-stat="orb_pct"]')) else None)
        Defensive_Rebound_Percentage.append(node.text if (node := row.select_one('td[data-stat="drb_pct"]')) else None)
        Total_Rebound_Percentage.append(node.text if (node := row.select_one('td[data-stat="trb_pct"]')) else None)
        Assist_Percentage.append(node.text if (node := row.select_one('td[data-stat="ast_pct"]')) else None)

        Steal_Percentage.append(node.text if (node := row.select_one('td[data-stat="stl_pct"]')) else None)
        Block_Percentage.append(node.text if (node := row.select_one('td[data-stat="blk_pct"]')) else None)
        Turnover_Percentage.append(node.text if (node := row.select_one('td[data-stat="tov_pct"]')) else None)
        Usage_Percentage.append(node.text if (node := row.select_one('td[data-stat="usg_pct"]')) else None)
        Offensive_Win_Shares.append(node.text if (node := row.select_one('td[data-stat="ows"]')) else None)

        Defensive_Win_Shares.append(node.text if (node := row.select_one('td[data-stat="dws"]')) else None)
        Win_Shares.append(node.text if (node := row.select_one('td[data-stat="ws"]')) else None)
        Win_Shares_Per_48_Minutes.append(node.text if (node := row.select_one('td[data-stat="ws_per_48"]')) else None)
        Offensive_Box_Plus_Minus.append(node.text if (node := row.select_one('td[data-stat="obpm"]')) else None)
        Defensive_Box_Plus_Minus.append(node.text if (node := row.select_one('td[data-stat="dbpm"]')) else None)

        Box_Plus_Minus.append(node.text if (node := row.select_one('td[data-stat="bpm"]')) else None)
        Value_over_Replacement_Player.append(node.text if (node := row.select_one('td[data-stat="vorp"]')) else None)
    time.sleep(2)
driver.quit()
          
df_advanced_stats = pd.DataFrame({
    'Season': Season,
    'Rank':Rank ,
    'Player_id':Player_id,
    'Age':Age ,
    'Team':Team ,
    'Position':Position,
    'Games': Games, 
    'Games_started': Games_started, 
    'Minute_Played': Minute_Played, 
    'Player_Efficiency_Rate': Player_Efficiency_Rate, 
    'True_Shooting_Percentage':True_Shooting_Percentage , 
    'Three_Point_Attempt_Rate':Three_Point_Attempt_Rate ,
    'Free_Throw_Attempt_Rate':Free_Throw_Attempt_Rate , 
    'Offensive_Rebound_Percentage':Offensive_Rebound_Percentage , 
    'Defensive_Rebound_Percentage':Defensive_Rebound_Percentage , 
    'Total_Rebound_Percentage':Total_Rebound_Percentage , 
    'Assist_Percentage':Assist_Percentage ,
    'Steal_Percentage':Steal_Percentage , 
    'Block_Percentage':Block_Percentage , 
    'Turnover_Percentage':Turnover_Percentage , 
    'Usage_Percentage':Usage_Percentage ,
    'Offensive_Win_Shares':Offensive_Win_Shares ,
    'Defensive_Win_Shares':Defensive_Win_Shares , 
    'Win_Shares':Win_Shares , 
    'Win_Shares_Per_48_Minutes':Win_Shares_Per_48_Minutes , 
    'Offensive_Box_Plus_Minus':Offensive_Box_Plus_Minus ,
    'Defensive_Box_Plus_Minus':Defensive_Box_Plus_Minus  ,
    'Box_Plus_Minus':Box_Plus_Minus ,
    'Value_over_Replacement_Player':Value_over_Replacement_Player ,
})

df_advanced_stats.drop(df_advanced_stats[df_advanced_stats['Rank'].str.contains('Rk', case=False, na=True)].index, inplace=True)
df_advanced_stats.to_csv('player_stats' , index=False)