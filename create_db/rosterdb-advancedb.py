class Roster(Base):
    __tablename__ = "rosters"

    season = Column(Integer, ForeignKey("season_stats.season"), primary_key=True)
    player_id = Column(String(50), ForeignKey("players.player_id"), primary_key=True)
    team_id = Column(String(50), ForeignKey("team_lookup.team_id"), primary_key=True)
    pos1 = Column(String(50))
    pos2 = Column(String(50))
    player = relationship("Player", backref="roster_entries")
    team = relationship("Team", backref="roster_entries")


class AdvancedStat(Base):
    __tablename__ = "advanced_stats"

    season = Column(Integer, ForeignKey("season_stats.season"), primary_key=True)
    player_id = Column(String(50), ForeignKey("players.player_id"), primary_key=True)

    rank = Column(Integer)
    age = Column(Integer)
    team = Column(String(50), ForeignKey("team_lookup.team_id"))
    position = Column(String(50))
    games = Column(Integer)
    games_started = Column(Integer)
    minute_played = Column(Float)

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

    player = relationship("Player", backref="advanced_stats")
    team_ref = relationship("Team", backref="advanced_stats", foreign_keys=[team])

