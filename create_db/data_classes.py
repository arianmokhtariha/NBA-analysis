from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    ForeignKey,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from importlib import import_module

config_local = import_module("create_db.config_local")
DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME = (
    config_local.DB_USER,
    config_local.DB_PASSWORD,
    config_local.DB_HOST,
    config_local.DB_PORT,
    config_local.DB_NAME,
)


Base = declarative_base()
engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine)

########data classes (schemas) ############################################


class Player(Base):
    __tablename__ = "players"

    player_id = Column(String(20), primary_key=True)
    player_name = Column(String(50))
    shoots = Column(String(50))
    last_season_games = Column(Integer)
    last_season_points = Column(Float)
    last_season_total_rebound_pct = Column(Float)
    last_season_assists_pct = Column(Float)
    last_season_field_goal_pct = Column(Float)
    last_season_three_point_pct = Column(Float)
    last_season_free_throw_pct = Column(Float)
    last_season_effective_fg_pct = Column(Float)
    last_season_player_efficiency_rating = Column(Float)
    last_season_win_shares = Column(Float)
    experience = Column(String(20))
    career_games = Column(Integer)
    career_points = Column(Float)
    career_total_rebound_pct = Column(Float)
    career_assists_pct = Column(Float)
    career_field_goal_pct = Column(Float)
    career_three_point_pct = Column(Float)
    career_free_throw_pct = Column(Float)
    career_effective_fg_pct = Column(Float)
    career_player_efficiency_rating = Column(Float)
    career_win_shares = Column(Float)
    pos1 = Column(String(50))
    pos2 = Column(String(50))
    pos3 = Column(String(50))
    pos4 = Column(String(50))
    pos5 = Column(String(50))
    pos6 = Column(String(50))
    height_in_cm = Column(Float)
    weight_in_kg = Column(Float)
    age = Column(Integer)

    playerstats = relationship(
        "PlayerStat", back_populates="player", cascade="all, delete-orphan"
    )
    mvp_finishes = relationship(
        "MVPCandidate", back_populates="player", cascade="all, delete-orphan"
    )
    mvp_titles = relationship(
        "MVPWinner", back_populates="player", cascade="all, delete-orphan"
    )
    rosters = relationship(
        "Roster", back_populates="player", cascade="all, delete-orphan"
    )
    advanced_stats = relationship(
        "AdvancedStat", back_populates="player", cascade="all, delete-orphan"
    )


class Team(Base):
    __tablename__ = "team_lookup"
    team_id = Column(String(20), primary_key=True)
    team_name = Column(String(50), nullable=False, unique=True)

    performances = relationship(
        "TeamPerformance", back_populates="team", cascade="all, delete-orphan"
    )
    player_stats = relationship("PlayerStat", back_populates="team")
    roster_entries = relationship(
        "Roster", back_populates="team", cascade="all, delete-orphan"
    )
    mvp_titles = relationship("MVPWinner", back_populates="team")
    mvp_finishes = relationship("MVPCandidate", back_populates="team")
    advanced_stats = relationship("AdvancedStat", back_populates="team")


class PlayerStat(Base):
    __tablename__ = "player_stats"

    season = Column(Integer, primary_key=True)
    player_id = Column(String(20), ForeignKey("players.player_id"), primary_key=True)
    rank = Column(Integer)
    age = Column(Integer)
    team_id = Column(String(20), ForeignKey("team_lookup.team_id"))
    position = Column(String(50))
    games_played = Column(Integer)
    games_started = Column(Integer)
    minutes_played = Column(Integer)
    field_goals_made = Column(Integer)
    field_goals_attempted = Column(Integer)
    field_goal_pct = Column(Float)
    three_pointers_made = Column(Integer)
    three_pointers_attempted = Column(Integer)
    three_point_pct = Column(Float)
    two_pointers_made = Column(Integer)
    two_pointers_attempted = Column(Integer)
    two_point_pct = Column(Float)
    effective_fg_pct = Column(Float)
    free_throws_made = Column(Integer)
    free_throws_attempted = Column(Integer)
    free_throw_pct = Column(Float)
    offensive_rebounds = Column(Integer)
    defensive_rebounds = Column(Integer)
    total_rebounds = Column(Integer)
    assists = Column(Integer)
    steals = Column(Integer)
    blocks = Column(Integer)
    turnovers = Column(Integer)
    personal_fouls = Column(Integer)
    points = Column(Integer)
    triple_doubles = Column(Integer)

    player = relationship("Player", back_populates="playerstats")
    team = relationship("Team", back_populates="player_stats")


class MVPWinner(Base):
    __tablename__ = "mvp_winners"

    season = Column(Integer, primary_key=True)
    league = Column(String(20), primary_key=True)
    player_id = Column(String(20), ForeignKey("players.player_id"))
    age = Column(Integer)
    team_id = Column(String(20), ForeignKey("team_lookup.team_id"))
    games = Column(Integer)
    minutes_per_game = Column(Float)
    points_per_game = Column(Float)
    rebounds_per_game = Column(Float)
    assists_per_game = Column(Float)
    steals_per_game = Column(Float)
    blocks_per_game = Column(Float)
    field_goal_pct = Column(Float)
    three_point_pct = Column(Float)
    free_throw_pct = Column(Float)
    win_shares = Column(Float)
    win_shares_per_48 = Column(Float)

    player = relationship("Player", back_populates="mvp_titles")
    team = relationship("Team", back_populates="mvp_titles")


class TeamPerformance(Base):
    __tablename__ = "teams_performance"

    season = Column(Integer, primary_key=True)
    team_id = Column(String(20), ForeignKey("team_lookup.team_id"), primary_key=True)
    rank = Column(Integer)
    games = Column(Integer)
    minutes_played = Column(Integer)
    field_goals_made = Column(Integer)
    field_goals_attempted = Column(Integer)
    field_goal_pct = Column(Float)
    three_pointers_made = Column(Integer)
    three_pointers_attempted = Column(Integer)
    three_point_pct = Column(Float)
    two_pointers_made = Column(Integer)
    two_pointers_attempted = Column(Integer)
    two_point_pct = Column(Float)
    free_throws_made = Column(Integer)
    free_throws_attempted = Column(Integer)
    free_throw_pct = Column(Float)
    offensive_rebounds = Column(Integer)
    defensive_rebounds = Column(Integer)
    total_rebounds = Column(Integer)
    assists = Column(Integer)
    steals = Column(Integer)
    blocks = Column(Integer)
    turnovers = Column(Integer)
    personal_fouls = Column(Integer)
    points = Column(Integer)

    team = relationship("Team", back_populates="performances")


class SeasonStat(Base):
    __tablename__ = "season_stats"
    season = Column(Integer, primary_key=True)
    league = Column(String(20))
    champion_name = Column(String(50), ForeignKey("team_lookup.team_name"))
    mvp = Column(String(50))
    rookie_of_the_year = Column(String(50))
    most_points = Column(String(50))
    most_rebounds = Column(String(50))
    most_assists = Column(String(50))
    most_winshares = Column(String(50))


class Roster(Base):
    __tablename__ = "rosters"

    season = Column(Integer, ForeignKey("season_stats.season"), primary_key=True)
    player_id = Column(String(20), ForeignKey("players.player_id"), primary_key=True)
    team_id = Column(String(20), ForeignKey("team_lookup.team_id"), primary_key=True)
    pos1 = Column(String(50))
    pos2 = Column(String(50))

    player = relationship("Player", back_populates="rosters")
    team = relationship("Team", back_populates="roster_entries")


class AdvancedStat(Base):
    __tablename__ = "advanced_stats"

    season = Column(Integer, ForeignKey("season_stats.season"), primary_key=True)
    player_id = Column(String(20), ForeignKey("players.player_id"), primary_key=True)

    player_efficiency_rate = Column(Float)
    true_shooting_percentage = Column(Float)
    three_point_attempt_rate = Column(Float)
    free_throw_attempt_rate = Column(Float)

    offensive_rebound_percentage = Column(Float)
    defensive_rebound_percentage = Column(Float)
    total_rebound_percentage = Column(Float)

    assist_percentage = Column(Float)
    steal_percentage = Column(Float)
    block_percentage = Column(Float)
    turnover_percentage = Column(Float)
    usage_percentage = Column(Float)

    offensive_win_shares = Column(Float)
    defensive_win_shares = Column(Float)
    win_shares = Column(Float)
    win_shares_per_48_minutes = Column(Float)

    offensive_box_plus_minus = Column(Float)
    defensive_box_plus_minus = Column(Float)
    value_over_replacement_player = Column(Float)

    player = relationship("Player", back_populates="advanced_stats")


class MVPCandidate(Base):
    __tablename__ = "mvp_candidates"

    year = Column(Integer, primary_key=True)
    player_id = Column(String(20), ForeignKey("players.player_id"), primary_key=True)
    rank = Column(Integer)
    tie = Column(Boolean)
    age = Column(Integer)
    team_id = Column(String(20), ForeignKey("team_lookup.team_id"))
    first_place_votes = Column(Integer)
    points_won = Column(Integer)
    points_max = Column(Integer)
    share = Column(Float)
    games = Column(Integer)
    mp = Column(Float)
    pts = Column(Float)
    trb = Column(Float)
    ast = Column(Float)
    stl = Column(Float)
    blk = Column(Float)
    fg_pct = Column(Float)
    three_pct = Column(Float)
    ft_pct = Column(Float)
    ws = Column(Float)
    ws_per_48 = Column(Float)

    player = relationship("Player", back_populates="mvp_finishes")
    team = relationship("Team", back_populates="mvp_finishes")


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
