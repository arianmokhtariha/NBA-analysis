import pandas as pd
import os

#####-------cleaning players data--------#######
players_raw_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "Players_table.csv"
)
players_df = pd.read_csv(players_raw_path, index_col=0)

# lower case columns
players_df.columns = players_df.columns.str.lower()

##expand and strip positions column
players_df[["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]] = players_df[
    "position"
].str.split(",", expand=True)
players_df[["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]] = players_df[
    ["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]
].map(lambda x: x.strip() if isinstance(x, str) else x)

###change height to cms
height_split = players_df["height"].str.strip().str.split("-", expand=True)

players_df["height_in_cm"] = (height_split[0].astype(float) * 30.48) + (
    height_split[1].astype(float) * 2.54
)
players_df["height_in_cm"] = players_df["height_in_cm"].round()

###change weight to kgs
players_df["weight_in_kg"] = (players_df["weight"] * 0.453).round()

###create an age column based on birth year
players_df["age"] = 2025 - players_df["birthyear"]


##drop unnecessary columns (important for Nf1, Nf2, Nf3)
players_df = players_df.drop(
    columns=[
        "position",
        "height",
        "weight",
        "birthday",
        "birthmonth",
        "birthyear",
    ]
)

###save it to csv
players_df.to_csv(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "data_clean", "players.csv"
    ),
    index=False,
)


##################-------------cleaning Mvp Candidates-----------------######################################

mvp_candidates_raw_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "new_mvp_candidates.xlsx"
)
mvp_candidates_df = pd.read_excel(mvp_candidates_raw_path)

mvp_candidates_df.columns = mvp_candidates_df.columns.str.lower()

mvp_candidates_df_col_names = {
    "first_place_vote": "first_place_votes",
    "pts won": "points_won",
    "pts max": "points_max",
    "fg%": "fg_pct",
    "3p%": "three_pct",
    "ft%": "ft_pct",
    "ws/48": "ws_per_48",
}

mvp_candidates_df = mvp_candidates_df.rename(columns=mvp_candidates_df_col_names)

print(mvp_candidates_df[["year", "player_id"]].duplicated().sum())
### this should be zero, because this pair will be our composite key ##

split_t = mvp_candidates_df["rank"].str.strip().str.extract(r"(\d+)(T?)")
split_t[1] = split_t[1].astype(bool)

mvp_candidates_df[["rank", "tie"]] = split_t[[0, 1]].values

mvp_candidates_df_col_order = [
    "year",
    "player_id",
    "rank",
    "tie",
    "age",
    "team",
    "first_place_votes",
    "points_won",
    "points_max",
    "share",
    "games",
    "mp",
    "pts",
    "trb",
    "ast",
    "stl",
    "blk",
    "fg_pct",
    "three_pct",
    "ft_pct",
    "ws",
    "ws_per_48",
]

mvp_candidates_df = mvp_candidates_df[mvp_candidates_df_col_order]

mvp_candidates_df["rank"] = mvp_candidates_df["rank"].astype("int64")
mvp_candidates_df["tie"] = mvp_candidates_df["tie"].astype(bool)


mvp_candidates_df.to_csv(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
        "data_clean",
        "mvp_candidates.csv",
    )
)
