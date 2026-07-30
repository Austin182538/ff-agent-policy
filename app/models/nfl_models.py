from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
import uuid
from datetime import datetime


class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(String, unique=True, index=True)  # ESPN/NFL API team ID
    name = Column(String, nullable=False)
    abbreviation = Column(String(3), nullable=False)
    city = Column(String, nullable=False)
    conference = Column(String(3))  # AFC or NFC
    division = Column(String(10))   # North, South, East, West
    primary_color = Column(String(7))  # Hex color code
    secondary_color = Column(String(7))
    logo_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    players = relationship("Player", back_populates="team")
    home_games = relationship("Game", foreign_keys="Game.home_team_id", back_populates="home_team")
    away_games = relationship("Game", foreign_keys="Game.away_team_id", back_populates="away_team")


class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, unique=True, index=True)  # ESPN/NFL API player ID
    name = Column(String, nullable=False, index=True)
    position = Column(String(3), nullable=False, index=True)
    jersey_number = Column(Integer)
    height = Column(String)  # e.g., "6'2"
    weight = Column(Integer)
    age = Column(Integer)
    experience = Column(Integer)  # Years in NFL
    college = Column(String)
    team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    team = relationship("Team", back_populates="players")
    game_stats = relationship("PlayerGameStats", back_populates="player")
    season_stats = relationship("PlayerSeasonStats", back_populates="player")
    fantasy_data = relationship("FantasyData", back_populates="player")


class Season(Base):
    __tablename__ = "seasons"
    
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, unique=True, index=True)
    start_date = Column(Date)
    end_date = Column(Date)
    playoff_start_date = Column(Date)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    games = relationship("Game", back_populates="season")
    player_season_stats = relationship("PlayerSeasonStats", back_populates="season")


class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, unique=True, index=True)  # ESPN/NFL API game ID
    season_id = Column(Integer, ForeignKey("seasons.id"), index=True)
    week = Column(Integer, nullable=False, index=True)
    game_date = Column(DateTime, nullable=False, index=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    away_team_id = Column(Integer, ForeignKey("teams.id"), index=True)
    home_score = Column(Integer)
    away_score = Column(Integer)
    game_status = Column(String)  # scheduled, in_progress, final
    weather_condition = Column(String)
    temperature = Column(Integer)
    wind_speed = Column(Integer)
    is_playoff = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    season = relationship("Season", back_populates="games")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_games")
    player_game_stats = relationship("PlayerGameStats", back_populates="game")


class PlayerGameStats(Base):
    __tablename__ = "player_game_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    game_id = Column(Integer, ForeignKey("games.id"), index=True)
    
    # Passing stats
    passing_attempts = Column(Integer, default=0)
    passing_completions = Column(Integer, default=0)
    passing_yards = Column(Integer, default=0)
    passing_touchdowns = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    
    # Rushing stats
    rushing_attempts = Column(Integer, default=0)
    rushing_yards = Column(Integer, default=0)
    rushing_touchdowns = Column(Integer, default=0)
    
    # Receiving stats
    receptions = Column(Integer, default=0)
    receiving_yards = Column(Integer, default=0)
    receiving_touchdowns = Column(Integer, default=0)
    targets = Column(Integer, default=0)
    
    # Fantasy points
    fantasy_points_standard = Column(Float, default=0.0)
    fantasy_points_ppr = Column(Float, default=0.0)
    fantasy_points_half_ppr = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="game_stats")
    game = relationship("Game", back_populates="player_game_stats")


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), index=True)
    
    games_played = Column(Integer, default=0)
    
    # Passing stats
    passing_attempts = Column(Integer, default=0)
    passing_completions = Column(Integer, default=0)
    passing_yards = Column(Integer, default=0)
    passing_touchdowns = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    
    # Rushing stats
    rushing_attempts = Column(Integer, default=0)
    rushing_yards = Column(Integer, default=0)
    rushing_touchdowns = Column(Integer, default=0)
    
    # Receiving stats
    receptions = Column(Integer, default=0)
    receiving_yards = Column(Integer, default=0)
    receiving_touchdowns = Column(Integer, default=0)
    targets = Column(Integer, default=0)
    
    # Fantasy points
    fantasy_points_standard = Column(Float, default=0.0)
    fantasy_points_ppr = Column(Float, default=0.0)
    fantasy_points_half_ppr = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="season_stats")
    season = relationship("Season", back_populates="player_season_stats")


class FantasyData(Base):
    __tablename__ = "fantasy_data"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True)
    season_year = Column(Integer, nullable=False, index=True)
    
    # Average Draft Position data
    adp_overall = Column(Float)
    adp_position = Column(Float)
    draft_percentage = Column(Float)  # % of drafts player was selected
    
    # Projections
    projected_points_standard = Column(Float)
    projected_points_ppr = Column(Float)
    projected_points_half_ppr = Column(Float)
    
    # Value calculations (to be computed)
    value_score = Column(Float)  # Our calculated value vs ADP
    trend_score = Column(Float)  # Based on historical trends
    
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    player = relationship("Player", back_populates="fantasy_data") 