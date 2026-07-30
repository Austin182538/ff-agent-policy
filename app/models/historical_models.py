"""
Historical NFL / fantasy data models, populated from nflverse via nflreadpy
(see app/integrations/nflverse_client.py and scripts/ingest_historical_data.py).

These are kept as separate staging tables (keyed by nflverse's own player_id /
team abbreviation / season / week) rather than reusing app.models.nfl_models'
Player/Team tables, since those use invented sequential IDs with no reliable
join key back to nflverse. Matching to the app's Player table (by name) can
happen downstream in the analysis layer where needed.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from app.core.database import Base
from datetime import datetime


class HistoricalPlayerStats(Base):
    """Per-player, per-week (or season-total) real stats from nflreadpy's
    load_player_stats(). One row per player per week per season.
    """
    __tablename__ = "historical_player_stats"

    id = Column(Integer, primary_key=True, index=True)
    nflverse_player_id = Column(String, index=True)  # gsis_id
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True)
    team_abbr = Column(String(4), index=True)
    season_year = Column(Integer, index=True, nullable=False)
    week = Column(Integer, index=True, nullable=False)  # 0 = season total row
    season_type = Column(String, default="REG")

    completions = Column(Float, default=0)
    attempts = Column(Float, default=0)
    passing_yards = Column(Float, default=0)
    passing_tds = Column(Float, default=0)
    interceptions = Column(Float, default=0)

    carries = Column(Float, default=0)
    rushing_yards = Column(Float, default=0)
    rushing_tds = Column(Float, default=0)

    targets = Column(Float, default=0)
    receptions = Column(Float, default=0)
    receiving_yards = Column(Float, default=0)
    receiving_tds = Column(Float, default=0)

    fantasy_points_standard = Column(Float, nullable=True)
    fantasy_points_ppr = Column(Float, nullable=True)
    fantasy_points_half_ppr = Column(Float, nullable=True)

    # Only populated on week=0 season-total rows: count of distinct weeks
    # the player recorded a real stat line that season (nflreadpy only
    # emits a weekly row when a player actually appeared in that game).
    # Used to exclude injury/benching-shortened seasons from analyses that
    # would otherwise be skewed by a handful of games' worth of production.
    games_played = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "nflverse_player_id", "season_year", "week", "season_type",
            name="uq_historical_player_stats_row"
        ),
    )


class HistoricalTeamStats(Base):
    """Per-team, per-week (or season-total) stats from nflreadpy's load_team_stats(),
    plus final schedule results from load_schedules() (points_for/points_against/win).
    """
    __tablename__ = "historical_team_stats"

    id = Column(Integer, primary_key=True, index=True)
    team_abbr = Column(String(4), index=True, nullable=False)
    season_year = Column(Integer, index=True, nullable=False)
    week = Column(Integer, index=True, nullable=False)  # 0 = season total row
    season_type = Column(String, default="REG")

    points_for = Column(Float, nullable=True)
    points_against = Column(Float, nullable=True)
    win = Column(Float, nullable=True)  # 1 / 0 / 0.5 (tie) / null, only meaningful per-game (week>0)

    total_yards = Column(Float, nullable=True)
    passing_yards = Column(Float, nullable=True)
    rushing_yards = Column(Float, nullable=True)
    turnovers = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "team_abbr", "season_year", "week", "season_type",
            name="uq_historical_team_stats_row"
        ),
    )


class SeasonFinalRecord(Base):
    """Actual final regular-season win total per team per season, derived from
    load_schedules(). Used to grade Vegas preseason win totals.
    """
    __tablename__ = "season_final_records"

    id = Column(Integer, primary_key=True, index=True)
    team_abbr = Column(String(4), index=True, nullable=False)
    season_year = Column(Integer, index=True, nullable=False)
    wins = Column(Float, nullable=False)   # includes 0.5 per tie
    losses = Column(Float, nullable=False)
    ties = Column(Integer, default=0)
    points_for = Column(Float, nullable=True)
    points_against = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("team_abbr", "season_year", name="uq_season_final_record"),
    )


class FantasyConsensusRanking(Base):
    """Historical + current preseason ADP / expert-consensus-rank (ECR) data
    from nflreadpy's load_ff_rankings(type="draft") (FantasyPros consensus via
    the dynastyprocess project).
    """
    __tablename__ = "fantasy_consensus_rankings"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True)
    team_abbr = Column(String(4), index=True, nullable=True)
    season_year = Column(Integer, index=True, nullable=False)

    ecr_overall_rank = Column(Float, nullable=True)   # expert consensus rank, overall
    ecr_position_rank = Column(Float, nullable=True)  # expert consensus rank, within position
    adp_overall = Column(Float, nullable=True)        # average draft position, if present
    rank_std_dev = Column(Float, nullable=True)        # spread of expert opinion

    source = Column(String, default="FantasyPros (via nflverse/dynastyprocess)")
    as_of_date = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("player_name", "season_year", "position", name="uq_fantasy_consensus_ranking"),
    )


class FantasyOpportunity(Base):
    """Expected-vs-actual production from nflreadpy's load_ff_opportunity() --
    a measure of efficiency/luck (e.g. a player getting more/fewer fantasy
    points than their volume/opportunity would predict).
    """
    __tablename__ = "fantasy_opportunity"

    id = Column(Integer, primary_key=True, index=True)
    nflverse_player_id = Column(String, index=True, nullable=True)
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True)
    team_abbr = Column(String(4), index=True)
    season_year = Column(Integer, index=True, nullable=False)
    week = Column(Integer, index=True, nullable=False)  # 0 = season total row

    expected_fantasy_points = Column(Float, nullable=True)
    actual_fantasy_points = Column(Float, nullable=True)
    delta_fantasy_points = Column(Float, nullable=True)  # actual - expected

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "player_name", "season_year", "week", "position",
            name="uq_fantasy_opportunity_row"
        ),
    )
