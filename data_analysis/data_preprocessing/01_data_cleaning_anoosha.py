import pandas as pd
import os

#####-------cleaning players data--------#######
players_raw_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "Players_table.csv"
)
players_df = pd.read_csv(players_raw_path, index_col=0)

#lower case columns
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
        os.path.dirname(__file__), "..", "..", "data", "data_clean", "players_clean.csv"
    ),
    index=False,
)
