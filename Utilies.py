from bs4 import BeautifulSoup
import requests
import re 
import pandas as pd
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import importlib 
from datetime import datetime

def players_links(url):
    base_url='https://www.basketball-reference.com/'
    useragent ='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    headers={
        'User-Agent' : useragent,
        'Accept-Language': 'en'
        }

    page=requests.get(url , headers=headers).text
    soup = BeautifulSoup(page , 'html.parser')

    players_pages = [
        base_url + '/' + node['href']
        
    for node in soup.select("table a[href*=players]")
    ]
    return players_pages


def Get_Players(url):
    useragent ='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    headers={
        'User-Agent' : useragent,
        'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
        'cookie': "_ga_NR1HN85GXQ=deleted; __cf_bm=.hoW4l7KUjknsOPC7nWgMFsRBf4p5Y4FcWEe9cfMPjo-1758757769-1.0.1.1-DvvaFiwifjQcB7j7DVViDrU.xasPybFbqFqWp69g8DIwEmQnj3UkmKMNLDyRHLN_zBBYWzgmaaPkT1EbNcpD6mfSXanupTRFs3n6oozehQQ; srcssfull=yes; is_live=true; osano_consentmanager_uuid=2c3fd343-d76a-4f06-9140-31bf42095f26; _ga=GA1.1.1702063434.1758757785; __hstc=180814520.0556b9f6c2f4ee0424c7ebac7681a50f.1758757824863.1758757824863.1758757824863.1; hubspotutk=0556b9f6c2f4ee0424c7ebac7681a50f; __hssrc=1; __hssc=180814520.2.1758757824863; _ga_NR1HN85GXQ=GS2.1.s1758757784$o1$g1$t1758758795$j60$l0$h0; _ga_80FRT7VJ60=GS2.1.s1758757784$o22$g1$t1758758795$j60$l0$h0",

        }

    posts=[]
    page=requests.get(url , headers=headers , timeout=20).text
    soup = BeautifulSoup(page , 'html.parser')
    
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
            # 'Draft_id': TO Do[node.get_attribute_list('href')[0].split('/')[2] for node in soup.select('a[href*=draft]')][1]
            'Last Season Games':[node.text.split() for node in soup.select('.p1 p')][0],
            'Last Season Points':[node.text.split() for node in soup.select('.p1 p')][2],
            'Last Season Total Rebound Percentage':[node.text.split() for node in soup.select('.p1 p')][4],
            'Last Season Assists Percentage':[node.text.split() for node in soup.select('.p1 p')][6],

            'Last Season Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][0],
            'Last Season 3pt Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][2],
            'Last Season TFree Throw Percentage':[node.text.split() for node in soup.select('.p2 p')][4],
            'Last Season Effective Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][6],
            'Last Season Player Efficiency Rating': [node.text.split() for node in soup.select('.p3 p')][0],
            'Last Season Win Shares':[node.text.split() for node in soup.select('.p3 p')][2],

            'Experience':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Experience:')][1],

            'Career Games':[node.text.split() for node in soup.select('.p1 p')][1],
            'Career Points':[node.text.split() for node in soup.select('.p1 p')][3],
            'Career Total Rebound Percentage':[node.text.split() for node in soup.select('.p1 p')][5],
            'Career Assists Percentage':[node.text.split() for node in soup.select('.p1 p')][7],

            'Career Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][1],
            'Career 3pt Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][3],
            'Career Free Throw Percentage':[node.text.split() for node in soup.select('.p2 p')][5],
            'Career Effective Field Goal Percentage':[node.text.split() for node in soup.select('.p2 p')][7],
            'Career Player Efficiency Rating': [node.text.split() for node in soup.select('.p3 p')][1],
            'Career Win Shares':[node.text.split() for node in soup.select('.p3 p')][3],

            })
    return posts


def Get_MVPs(url:str):
    useragent ='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    headers={
        'User-Agent' : useragent,
        'Accept-Language': 'en'
        }
    posts=[]
    page=requests.get(url , headers=headers).text
    soup = BeautifulSoup(page , 'html.parser')
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

    return posts


def make_df_pretty(dataframe:pd.DataFrame):#This func make list objects string if there is just one item in list and raplaces empty strings with pd.Na
    for i in dataframe.columns:
        if type(dataframe[i][0]) is list: 
            dataframe[i]=dataframe[i].apply(lambda lst : list(dict.fromkeys(lst)))
            dataframe[i]=dataframe[i].apply(lambda x: ",".join(map(str,x)))
    dataframe=dataframe.replace('' , pd.NA)
 