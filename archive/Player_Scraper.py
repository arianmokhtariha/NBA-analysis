from bs4 import BeautifulSoup,NavigableString
import requests
import re 
import pandas as pd
import importlib 
from urllib.parse import urljoin, urlparse
import time
import csv
from datetime import datetime
import time



def players_links(urls):
    base_url='https://www.basketball-reference.com/'
    useragent ='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
    headers={
        'User-Agent' : useragent,
        'Accept-Language': 'en'
        }
    
    players_pages=[]

    for url in urls :
        page=requests.get(url , headers=headers).text
        soup = BeautifulSoup(page , 'html.parser')
        players_pages.extend(
            [ base_url + '/' + node['href'] 
                              for node in soup.select("table a[href*=players]")]
        )
    links=[]
    for link in players_pages:
        if link not in links:
            links.append(link)
    
    return links

year_range = [str(i) for i in range(2019 , 2026)]
urls = ['https://www.basketball-reference.com/leagues/NBA_' + year + '_totals.html' for year in year_range]
links=players_links(urls)
#30 seconds
#6560 diffrent ids
#1175 unique id

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
    
    Experience_Condition= ('Experience:' in [node.text.split()[0] for node in soup.select('#info #meta div p')])
    Draft_Condition=('Draft:' in [node.text.split()[0] for node in soup.select('#info #meta div p')])

    if Experience_Condition:
        posts.append(
            {
                'player_id': url.split('/')[-1].split('.')[0],
                'player_name': [node.text.strip() for node in soup.select("h1")],
                'Position':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')].split(' \n  ')[1].split('\n')[0],
                'Shoots':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')].split(' \n  ')[-1],
                'Height':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][0].replace(',',''),
                'Weight':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][1].replace('lb',''),

                'Birthday':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][1],
                'Birthmonth':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][0],
                'Birthyear':[node.text.split() for node in soup.select('a[href*=birthyears]')][0],
                'College' : [node.text.split() for node in soup.select('a[href*=colleges]')][0],
                'Draft': [node.text.strip() for node in soup.select("a[href*='draft']")][2],
                'Draft Team':[node.text.strip() for node in soup.select("a[href*='draft']")][1],
                
                'Draf Pick' : [node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Draft:')].split(',')[1]+ [node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Draft:')].split(',')[2] if Draft_Condition else pd.NA,
                'Experience':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Experience:')][1],
                'NBA Debut':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('NBA')].split(':')[1],

                })
    else:
        posts.append(
            {
                'player_id': url.split('/')[-1].split('.')[0],
                'player_name': [node.text.strip() for node in soup.select("h1")],
                'Position':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')].split(' \n  ')[1].split('\n')[0],
                'Shoots':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')].split(' \n  ')[-1],
                'Height':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][0].replace(',',''),
                'Weight':[node.text.split() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Position:')+1][1].replace('lb',''),
                'Birthday':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][1],
                'Birthmonth':[node.text.split() for node in soup.select('a[href*=birthdays]')][0][0],
                'Birthyear':[node.text.split() for node in soup.select('a[href*=birthyears]')][0],
                'College' : [node.text.split() for node in soup.select('a[href*=colleges]')][0],
                'Draft': [node.text.strip() for node in soup.select("a[href*='draft']")][2],
                'Draft Team':[node.text.strip() for node in soup.select("a[href*='draft']")][1],
                'Draf Pick' : [node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Draft:')].split(',')[1]+ [node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('Draft:')].split(',')[2] if Draft_Condition else pd.NA,
                'Experience':pd.NA,
                'NBA Debut':[node.text.strip() for node in soup.select('#info #meta div p')][[node.text.split()[0] for node in soup.select('#info #meta div p')].index('NBA')].split(':')[1],

                })
    return posts

player_Data=[]

for url in links:
    time.sleep(2)
    try:
        player_Data.append(Get_Players(url))
    except Exception as e:
        print(f"An unknown error occurred: {e} \nfor {url}")

rows = [item[0] if isinstance(item , list) and item else item for item in player_Data]
players_Df=pd.DataFrame(rows)
def make_df_pretty(dataframe):
    for i in dataframe.columns:
        if type(dataframe[i][0]) is list: 
            dataframe[i]=dataframe[i].apply(lambda lst : list(dict.fromkeys(lst)))
            dataframe[i]=dataframe[i].apply(lambda x: ",".join(map(str,x)))
players_Df['Position']=players_Df['Position'].apply(str.strip)
players_Df['Position']=players_Df['Position'].map(lambda x :str.replace(x ,'and' , ','))
players_Df.to_csv('Player_table' , index=False)