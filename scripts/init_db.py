#!/usr/bin/env python3
"""
Script to initialize the database with sample NFL data
"""

import sys
import os
from datetime import datetime, date

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import SessionLocal, engine
from app.models.nfl_models import Base, Team, Player, Season, Game, PlayerSeasonStats, FantasyData


def create_tables():
    """Create all database tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully")


def add_sample_teams():
    """Add sample NFL teams"""
    db = SessionLocal()
    try:
        print("Adding sample teams...")
        
        sample_teams = [
            {
                "team_id": "ari", "name": "Arizona Cardinals", "abbreviation": "ARI", 
                "city": "Arizona", "conference": "NFC", "division": "West",
                "primary_color": "#97233F", "secondary_color": "#000000"
            },
            {
                "team_id": "atl", "name": "Atlanta Falcons", "abbreviation": "ATL",
                "city": "Atlanta", "conference": "NFC", "division": "South", 
                "primary_color": "#A71930", "secondary_color": "#000000"
            },
            {
                "team_id": "buf", "name": "Buffalo Bills", "abbreviation": "BUF",
                "city": "Buffalo", "conference": "AFC", "division": "East",
                "primary_color": "#00338D", "secondary_color": "#C60C30"
            },
            {
                "team_id": "car", "name": "Carolina Panthers", "abbreviation": "CAR",
                "city": "Carolina", "conference": "NFC", "division": "South",
                "primary_color": "#0085CA", "secondary_color": "#101820"
            },
            {
                "team_id": "dal", "name": "Dallas Cowboys", "abbreviation": "DAL",
                "city": "Dallas", "conference": "NFC", "division": "East",
                "primary_color": "#003594", "secondary_color": "#869397"
            }
        ]
        
        for team_data in sample_teams:
            existing_team = db.query(Team).filter(Team.team_id == team_data["team_id"]).first()
            if not existing_team:
                team = Team(**team_data)
                db.add(team)
        
        db.commit()
        print(f"✓ Added {len(sample_teams)} sample teams")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error adding teams: {e}")
    finally:
        db.close()


def add_sample_seasons():
    """Add sample seasons"""
    db = SessionLocal()
    try:
        print("Adding sample seasons...")
        
        sample_seasons = [
            {
                "year": 2021,
                "start_date": date(2021, 9, 9),
                "end_date": date(2022, 1, 9),
                "playoff_start_date": date(2022, 1, 15),
                "is_current": False
            },
            {
                "year": 2022,
                "start_date": date(2022, 9, 8),
                "end_date": date(2023, 1, 8),
                "playoff_start_date": date(2023, 1, 14),
                "is_current": False
            },
            {
                "year": 2023,
                "start_date": date(2023, 9, 7),
                "end_date": date(2024, 1, 7),
                "playoff_start_date": date(2024, 1, 13),
                "is_current": True
            }
        ]
        
        for season_data in sample_seasons:
            existing_season = db.query(Season).filter(Season.year == season_data["year"]).first()
            if not existing_season:
                season = Season(**season_data)
                db.add(season)
        
        db.commit()
        print(f"✓ Added {len(sample_seasons)} sample seasons")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error adding seasons: {e}")
    finally:
        db.close()


def add_sample_players():
    """Add sample players"""
    db = SessionLocal()
    try:
        print("Adding sample players...")
        
        # Get team IDs
        teams = db.query(Team).all()
        if not teams:
            print("✗ No teams found. Please add teams first.")
            return
        
        sample_players = [
            {
                "player_id": "josh_allen", "name": "Josh Allen", "position": "QB",
                "jersey_number": 17, "height": "6'5\"", "weight": 237, "age": 27,
                "experience": 5, "college": "Wyoming", "team_id": teams[2].id  # Buffalo
            },
            {
                "player_id": "dak_prescott", "name": "Dak Prescott", "position": "QB", 
                "jersey_number": 4, "height": "6'2\"", "weight": 238, "age": 30,
                "experience": 7, "college": "Mississippi State", "team_id": teams[4].id  # Dallas
            },
            {
                "player_id": "christian_mccaffrey", "name": "Christian McCaffrey", "position": "RB",
                "jersey_number": 22, "height": "5'11\"", "weight": 205, "age": 27,
                "experience": 6, "college": "Stanford", "team_id": teams[3].id  # Carolina
            }
        ]
        
        for player_data in sample_players:
            existing_player = db.query(Player).filter(Player.player_id == player_data["player_id"]).first()
            if not existing_player:
                player = Player(**player_data)
                db.add(player)
        
        db.commit()
        print(f"✓ Added {len(sample_players)} sample players")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error adding players: {e}")
    finally:
        db.close()


def add_sample_stats():
    """Add sample player statistics"""
    db = SessionLocal()
    try:
        print("Adding sample player statistics...")
        
        # Get players and seasons
        players = db.query(Player).all()
        seasons = db.query(Season).all()
        
        if not players or not seasons:
            print("✗ No players or seasons found. Please add them first.")
            return
        
        stats_added = 0
        for player in players[:3]:  # Just first 3 players
            for season in seasons:
                # Generate sample stats based on position
                if player.position == "QB":
                    stats_data = {
                        "player_id": player.id,
                        "season_id": season.id,
                        "games_played": 16,
                        "passing_attempts": 650,
                        "passing_completions": 420,
                        "passing_yards": 4800,
                        "passing_touchdowns": 35,
                        "interceptions": 12,
                        "fantasy_points_standard": 285.5,
                        "fantasy_points_ppr": 285.5,
                        "fantasy_points_half_ppr": 285.5
                    }
                elif player.position == "RB":
                    stats_data = {
                        "player_id": player.id,
                        "season_id": season.id,
                        "games_played": 14,
                        "rushing_attempts": 280,
                        "rushing_yards": 1200,
                        "rushing_touchdowns": 12,
                        "receptions": 65,
                        "receiving_yards": 520,
                        "receiving_touchdowns": 3,
                        "targets": 85,
                        "fantasy_points_standard": 245.0,
                        "fantasy_points_ppr": 310.0,
                        "fantasy_points_half_ppr": 277.5
                    }
                else:  # Default stats
                    stats_data = {
                        "player_id": player.id,
                        "season_id": season.id,
                        "games_played": 16,
                        "fantasy_points_standard": 150.0,
                        "fantasy_points_ppr": 180.0,
                        "fantasy_points_half_ppr": 165.0
                    }
                
                existing_stats = db.query(PlayerSeasonStats).filter(
                    PlayerSeasonStats.player_id == player.id,
                    PlayerSeasonStats.season_id == season.id
                ).first()
                
                if not existing_stats:
                    stats = PlayerSeasonStats(**stats_data)
                    db.add(stats)
                    stats_added += 1
        
        db.commit()
        print(f"✓ Added {stats_added} sample player statistics")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error adding stats: {e}")
    finally:
        db.close()


def main():
    """Main initialization function"""
    print("🏈 Initializing NFL Analytics Database")
    print("=" * 40)
    
    try:
        create_tables()
        add_sample_teams()
        add_sample_seasons()
        add_sample_players()
        add_sample_stats()
        
        print("\n" + "=" * 40)
        print("✅ Database initialization completed successfully!")
        print("\nYou can now:")
        print("1. Start the API server: python run_api.py")
        print("2. Visit the API docs: http://localhost:8000/docs")
        print("3. Test the endpoints with sample data")
        
    except Exception as e:
        print(f"\n❌ Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 