import os
import pandas as pd

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
DATA_CLEAN_DIR = os.path.join(RAW_DATA_DIR, "data_clean")


def clean_players() -> None:
    players_raw_path = os.path.join(RAW_DATA_DIR, "Players_table.csv")
    players_df = pd.read_csv(players_raw_path, index_col=0)

    players_df.columns = players_df.columns.str.lower()

    players_df[["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]] = players_df[
        "position"
    ].str.split(",", expand=True)
    players_df[["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]] = players_df[
        ["pos1", "pos2", "pos3", "pos4", "pos5", "pos6"]
    ].map(lambda x: x.strip() if isinstance(x, str) else x)

    height_split = players_df["height"].str.strip().str.split("-", expand=True)

    players_df["height_in_cm"] = (height_split[0].astype(float) * 30.48) + (
        height_split[1].astype(float) * 2.54
    )
    players_df["height_in_cm"] = players_df["height_in_cm"].round()

    players_df["weight_in_kg"] = (players_df["weight"] * 0.453).round()

    players_df["age"] = 2025 - players_df["birthyear"]

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

    players_df.to_csv(
        os.path.join(DATA_CLEAN_DIR, "players.csv"),
        index=False,
    )


def clean_mvp_candidates() -> None:
    mvp_candidates_raw_path = os.path.join(RAW_DATA_DIR, "new_mvp_candidates.xlsx")
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
            DATA_CLEAN_DIR,
            "mvp_candidates.csv",
        ),
        index=False,
    )


def clean_mvp_winners() -> None:
    mvp_winners_raw_path = os.path.join(RAW_DATA_DIR, "Mvp_table.csv")

    mvp_winners_df = pd.read_csv(mvp_winners_raw_path, index_col=0)

    mvp_winners_df.columns = mvp_winners_df.columns.str.lower().str.strip()

    mvp_winners_column_map = {
        "season": "season",
        "player_id": "player_id",
        "age": "age",
        "team_id": "team_id",
        "game": "games",
        "minutes played per game": "minutes_per_game",
        "points per game": "points_per_game",
        "total rebounds per game": "rebounds_per_game",
        "assists per game": "assists_per_game",
        "steals per game": "steals_per_game",
        "blocks per game": "blocks_per_game",
        "field goal percentage": "field_goal_pct",
        "3-point field goal percentage": "three_point_pct",
        "free throw percentage": "free_throw_pct",
        "win shares": "win_shares",
        "win shares per 48 minutes": "win_shares_per_48",
    }
    mvp_winners_df.rename(columns=mvp_winners_column_map, inplace=True)

    split_year_mvpwinners = mvp_winners_df["season"].str.split("-", expand=True)
    split_year_mvpwinners[0] = split_year_mvpwinners[0].astype(int) + 1
    mvp_winners_df["season"] = split_year_mvpwinners[0].values

    mvp_winners_df.to_csv(
        os.path.join(
            DATA_CLEAN_DIR,
            "mvp_winners.csv",
        ),
        index=False,
    )


def clean_player_stats() -> None:
    player_stats_raw_path = os.path.join(RAW_DATA_DIR, "player_stats.xlsx")
    player_stats = pd.read_excel(player_stats_raw_path)

    player_stats.columns = player_stats.columns.str.lower()

    player_stats_column_map = {
        "year": "season",
        "rank": "rank",
        "player_id": "player_id",
        "age": "age",
        "team": "team_id",
        "position": "position",
        "games": "games_played",
        "games started": "games_started",
        "minutes played": "minutes_played",
        "fg": "field_goals_made",
        "fga": "field_goals_attempted",
        "fg%": "field_goal_pct",
        "3p": "three_pointers_made",
        "3pa": "three_pointers_attempted",
        "3p%": "three_point_pct",
        "2p": "two_pointers_made",
        "2pa": "two_pointers_attempted",
        "2p%": "two_point_pct",
        "efg%": "effective_fg_pct",
        "ft": "free_throws_made",
        "fta": "free_throws_attempted",
        "ft%": "free_throw_pct",
        "orb": "offensive_rebounds",
        "drb": "defensive_rebounds",
        "trb": "total_rebounds",
        "ast": "assists",
        "stl": "steals",
        "blk": "blocks",
        "tov": "turnovers",
        "pf": "personal_fouls",
        "pts": "points",
        "trp_dbl": "triple_doubles",
    }

    player_stats = player_stats.rename(columns=player_stats_column_map)

    print(player_stats[player_stats[["season", "player_id"]].duplicated().sum()])
    print(player_stats.isna().sum())
    ### there are duplicates (related to players trade per season, so we had three rows per player (one total, two stints). we are only keeping the season totals here.)
    #! TOT is not a team. its season total (aggregated) across both teams. find the team from other tables

    player_stats["team_id"] = player_stats["team_id"].fillna("TOT")
    player_stats = player_stats[player_stats["team_id"] == "TOT"].copy()

    player_stats.to_csv(
        os.path.join(DATA_CLEAN_DIR, "player_stats.csv"),
        index=False,
    )


def clean_seasons() -> None:
    seasons_raw_path = os.path.join(RAW_DATA_DIR, "seasons_table.xlsx")
    seasons = pd.read_excel(seasons_raw_path)

    seasons.columns = seasons.columns.str.lower()
    seasons_column_map = {
        "season year": "season",
        "league": "league",
        "champion name": "champion_name",
        "mvp": "mvp",
        "rookie of the year": "rookie_of_the_year",
        "most points": "most_points",
        "most rebounds": "most_rebounds",
        "most assists": "most_assists",
        "most winshares": "most_winshares",
    }
    seasons = seasons.rename(columns=seasons_column_map)
    season = (
        seasons["season"].str.strip().str.split("-", expand=True)[0].astype(int) + 1
    )
    seasons["season"] = season.values

    seasons.to_csv(os.path.join(DATA_CLEAN_DIR, "season_stats.csv"), index=False)


def clean_team_stats() -> None:
    teams_raw_path = os.path.join(RAW_DATA_DIR, "seasons_teams_total_stats_clean.csv")
    teams = pd.read_csv(teams_raw_path)
    teams.columns = teams.columns.str.lower()

    teams_column_map = {
        "rk": "rank",
        "season": "season",
        "teamname": "team_name",
        "teamid": "team_id",
        "g": "games",
        "mp": "minutes_played",
        "fg": "field_goals_made",
        "fga": "field_goals_attempted",
        "fg%": "field_goal_pct",
        "3p": "three_pointers_made",
        "3pa": "three_pointers_attempted",
        "3p%": "three_point_pct",
        "2p": "two_pointers_made",
        "2pa": "two_pointers_attempted",
        "2p%": "two_point_pct",
        "ft": "free_throws_made",
        "fta": "free_throws_attempted",
        "ft%": "free_throw_pct",
        "orb": "offensive_rebounds",
        "drb": "defensive_rebounds",
        "trb": "total_rebounds",
        "ast": "assists",
        "stl": "steals",
        "blk": "blocks",
        "tov": "turnovers",
        "pf": "personal_fouls",
        "pts": "points",
    }

    teams = teams.rename(columns=teams_column_map)
    season = teams["season"].str.strip().str.split("-", expand=True)[0].astype(int) + 1
    teams["season"] = season.values

    teams = teams[(teams["rank"].notna()) & (teams["season"] != 2026)]
    print(teams.isna().sum())
    teams = teams[teams["season"] >= 2000]
    print("-" * 30)
    print(teams.isna().sum())

    team_lookup = teams.groupby("team_id")["team_name"].unique().reset_index()
    team_lookup["team_name"] = (
        team_lookup["team_name"].explode().groupby(level=0).first()
    )

    teams.drop(columns="team_name", axis=1, inplace=True)

    team_lookup.to_csv(os.path.join(DATA_CLEAN_DIR, "team_lookup.csv"), index=False)

    teams.to_csv(os.path.join(DATA_CLEAN_DIR, "teams_performance.csv"), index=False)


def main() -> None:
    clean_players()
    clean_mvp_candidates()
    clean_mvp_winners()
    clean_player_stats()
    clean_seasons()
    clean_team_stats()


if __name__ == "__main__":
    main()
