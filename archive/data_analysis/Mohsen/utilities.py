import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from scipy import stats
import statsmodels.formula.api as smf


def Get_BestPicks_df_Ready(BestPicks_df:pd.DataFrame):
    # Replacing player_name with unusual characters with their correct name 
    BestPicks_df.loc[1, 'player_name'] = 'luka doncic'
    BestPicks_df.loc[27, 'player_name'] = 'jonas valančiūnas'
    BestPicks_df.loc[38, 'player_name'] = 'kristaps porziņģis'
    #making new columns
    BestPicks_df.loc[BestPicks_df['draft_overall_pick_rank']<=5 , 'Top5_picks'] =1
    BestPicks_df.loc[BestPicks_df['draft_overall_pick_rank']>5, 'Top5_picks']=0

    BestPicks_df.loc[BestPicks_df['total_value_over_replacement_player']>=20 , 'vorp_tier'] ='high_vorp'
    BestPicks_df.loc[BestPicks_df['total_value_over_replacement_player']<20, 'vorp_tier']='low_vorp'

    BestPicks_df.loc[BestPicks_df['age']<=30 , 'age_group'] ='20-30'
    BestPicks_df.loc[BestPicks_df['age']>=30, 'age_group']='30-40'

    y= np.asarray(BestPicks_df['total_defensive_box_plus_minus'])
    choices= ['great','decent','bad']
    def_conditions = [
        (y < 0),
        (y == 0) ,
        (y > 0) 
    ]

    BestPicks_df['defense_tier']= np.select(def_conditions,choices, default= 'other')

    x= np.asarray(BestPicks_df['average_efficiency_rate'])
    choices= ['not_a_starter','all-star_candidate','mvp_candidate']
    per_conditions = [
        (x <= 20),
        (x >= 20) & (x <= 25),
        (x >= 25) 
    ]

    BestPicks_df['per_reference_guide']= np.select(per_conditions,choices, default= 'other')
    #Changing format of numbers
    continuous_stats = ['average_efficiency_rate' ,'total_win_shares' ,'average_rebound_percentage' ,'average_assist_percentage' ,'average_steal_percentage' ,'average_block_percentage' ,'total_offensive_box_plus_minus', 'total_defensive_box_plus_minus', 'total_value_over_replacement_player']
    counts_stats = ['triple_doubles' , 'draft_overall_pick_rank' , 'age' , 'experience' , 'Top5_picks']
    for stat in continuous_stats:
        BestPicks_df[stat]=BestPicks_df[stat].apply(lambda x : np.round(x, 2))
    BestPicks_df=BestPicks_df.dropna(subset=['experience'])
    for stat in counts_stats:
        BestPicks_df[stat] = BestPicks_df[stat].apply(lambda x : int(x))
    BestPicks_df.reset_index(inplace=True)
    BestPicks_df=BestPicks_df.drop('index', axis=1)

#################################################### Data Visualization ##############################################################


def hist_plot(columns_list:list[str], dataframe:pd.DataFrame, x,y)-> None:

    N= len(columns_list)
    rows = int(np.floor(np.sqrt(N)))
    cols= int(np.ceil(N/rows))
    fig, axes = plt.subplots(rows, cols, figsize = (x,y))

    if N==1:
        axes = [axes] 
    else:
        axes=axes.flatten()

    for i, col in enumerate (columns_list):
        sns.histplot(ax= axes[i],x= col, data= dataframe, kde= True)
        axes[i].set_title(f'{col}')
        axes[i].set_ylabel('')
        axes[i].set_xlabel('')
        axes[i].tick_params(axis='y')
        axes[i].grid(axis='x', linestyle='--', linewidth=0.5, alpha=0.3)
        axes[i].tick_params(axis='both')
        sns.despine(ax=axes[i], top=True, right=True)
        

    fig.suptitle('histograms of Selected Columns', fontweight='bold')

    for j in range(N , len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    plt.show()




def ct_2var(col1_name: str, col2_name: str, df: pd.DataFrame):
    fig, ax = plt.subplots(2, 2, figsize=(15, 15))
    ax = ax.flatten()

    table = pd.crosstab(df[col1_name], df[col2_name])
    sns.heatmap(table, ax=ax[0], annot=True, fmt='.2f', cbar=False, linewidths=0.5, square=True, cmap='Greys')
    sns.heatmap(table.div(table.sum(axis=1), axis=0), ax=ax[1], annot=True, fmt='.2f', cbar=False, linewidths=0.5, square=True, cmap='Greys')

    d = df.copy()
    d[col1_name] = d[col1_name].astype('string')
    d[col2_name] = d[col2_name].astype('string')

    sns.histplot(data=d, x=col1_name, hue=col2_name, multiple="dodge", discrete=True, shrink=0.5, stat="percent", ax=ax[2])
    sns.histplot(data=d, x=col2_name, hue=col1_name, multiple="fill", discrete=True, shrink=0.5, ax=ax[3])

    sns.despine(right=True, top=True, ax=ax[2])
    sns.despine(right=True, top=True, ax=ax[3])

    ax[3].set_ylabel('proportion- normalized')

    plt.tick_params(axis='both', which='both', length=0)
    plt.tight_layout()
    plt.show()


#################################### Mohsen's code ##################################################################################

def continuous_vs_binary(Dataframe:pd.DataFrame , continuous_Column : str , Binary_Column: str , log_scale = False):
    fig , ax = plt.subplots(2,3,figsize=(20,20))
    ax= ax.flatten()

    sns.boxplot(data=Dataframe , x=continuous_Column , color="Grey" , palette="Greys" , ax=ax[0])
    sns.histplot(data=Dataframe[continuous_Column],kde=True, multiple='dodge',  shrink=0.5, ax=ax[1], log_scale=log_scale) 
    stats.probplot(Dataframe[continuous_Column] , dist='norm' , fit=True , plot= ax[2])
    stat, p_norm =stats.shapiro(Dataframe[continuous_Column])

    line_markers = ax[1].get_lines()[0]

    line_markers.set_marker('o')
    line_markers.set_markerfacecolor('#005f73') 
    line_markers.set_markeredgecolor('#22333b')
    line_markers.set_markersize(4) 
    line_markers.set_alpha(0.7) 

    ax[2].set_title(f'QQplot\n Shapiro p={np.format_float_positional(p_norm, precision=4)}')   
    
    sns.histplot(data=Dataframe ,x=continuous_Column, hue =Binary_Column ,  multiple='stack',shrink=0.3, ax= ax[3], log_scale=log_scale)

    sns.histplot(data=Dataframe ,x=continuous_Column, hue =Binary_Column , log_scale=log_scale,stat="proportion" , multiple='fill', shrink=0.3, ax= ax[5] )
    sns.despine(right=True, top=True, ax = ax[3])
    sns.despine(right=True, top=True, ax = ax[5])
    
    sns.kdeplot(
    data=Dataframe, x=continuous_Column, hue=Binary_Column,
    fill=True, common_norm=False, palette="crest",
    alpha=.5, linewidth=0,ax=ax[4], log_scale=log_scale
    )
    
    plt.tick_params(axis='both', which='both', length=0)
    plt.tight_layout()
    plt.show()

    #statistical tests
    #mann-whitney
    #group1= Dataframe[Dataframe[Binary_Column]==1][continuous_Column]
    #group2= Dataframe[Dataframe[Binary_Column]==0][continuous_Column]
    #U_statistics , mw_pvalue = stats.mannwhitneyu(group1 , group2)
    #if mw_pvalue<0.05:
        #print(f'for mann-whitney test p value {mw_pvalue} is smaller than 0.05; So there is strog evidance for rejecting the null hypothesis which is "there is no diffrence in median {continuous_Column} of sold users with conversion 1 or 0"')
    #elif mw_pvalue>=0.05:
        #print(f'for mann-whitney test p value {mw_pvalue} is larger than 0.05; So there is no evidance for rejecting the null hypothesis which is "there is no diffrence in median {continuous_Column} of sold users with conversion 1 or 0"')




def var_vs_binary_in_categorie(Dataframe:pd.DataFrame ,Categorie_Column:str , Categories_list:list , var_column:str ,target:str ):
    groups_list = [Dataframe[Dataframe[Categorie_Column]== item] for item in Categories_list]
    for group in groups_list:
        from scipy.stats import mannwhitneyu
        con_1 = group[group['conversion']==1]
        con_0= group[group['conversion']==0]
        group_U, group_pvalue = mannwhitneyu(con_1[var_column],con_0[var_column])
        if group_pvalue < 0.05 :
            print(f'pvalue:{group_pvalue}\nthere\'s a significant diffrence in {var_column} median for conversion in {list(group[Categorie_Column].unique())} categorie')
        else:print(f'there\'s no evidence for significant diffrence in {var_column} median for conversion in {list(group[Categorie_Column].unique())} categorie')




def vorp_vs_eff(col1_name: str, col2_name: str, df: pd.DataFrame):
    fig, ax = plt.subplots(2, 2, figsize=(15, 15))
    ax = ax.flatten()

    table = pd.crosstab(df[col1_name], df[col2_name])
    sns.heatmap(table, ax=ax[0], annot=True, fmt='.2f', cbar=False, linewidths=0.5, square=True, cmap='Greys')
    sns.heatmap(table.div(table.sum(axis=1), axis=0), ax=ax[1], annot=True, fmt='.2f', cbar=False, linewidths=0.5, square=True, cmap='Greys')

    d = df.copy()
    d[col1_name] = d[col1_name].astype('string')
    d[col2_name] = d[col2_name].astype('string')

    sns.histplot(data=d, x=col1_name, hue=col2_name, multiple="dodge", discrete=True, shrink=0.5, stat="percent", ax=ax[2])
    sns.histplot(data=d[d[col1_name]=='all-star_candidate'], x=col2_name, hue=col1_name, discrete=True, shrink=0.5, ax=ax[3])

    sns.despine(right=True, top=True, ax=ax[2])
    sns.despine(right=True, top=True, ax=ax[3])

    ax[3].set_ylabel('proportion- normalized')

    plt.tick_params(axis='both', which='both', length=0)
    plt.tight_layout()
    plt.show()






