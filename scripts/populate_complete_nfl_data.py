#!/usr/bin/env python3
"""
Complete NFL Data Population Script (2025 Season - Pro Football Reference Data)
Uses real 2025 fantasy football data with accurate player-team assignments and ADP values
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine
from app.models.nfl_models import Base, Team, Player, Season, FantasyData
from sqlalchemy.orm import Session
import random
from datetime import datetime

# Complete NFL Teams Data
NFL_TEAMS = [
    # AFC East
    {"name": "Buffalo Bills", "abbreviation": "BUF", "conference": "AFC", "division": "East", "city": "Buffalo"},
    {"name": "Miami Dolphins", "abbreviation": "MIA", "conference": "AFC", "division": "East", "city": "Miami"},
    {"name": "New England Patriots", "abbreviation": "NE", "conference": "AFC", "division": "East", "city": "New England"},
    {"name": "New York Jets", "abbreviation": "NYJ", "conference": "AFC", "division": "East", "city": "New York"},
    
    # AFC North
    {"name": "Baltimore Ravens", "abbreviation": "BAL", "conference": "AFC", "division": "North", "city": "Baltimore"},
    {"name": "Cincinnati Bengals", "abbreviation": "CIN", "conference": "AFC", "division": "North", "city": "Cincinnati"},
    {"name": "Cleveland Browns", "abbreviation": "CLE", "conference": "AFC", "division": "North", "city": "Cleveland"},
    {"name": "Pittsburgh Steelers", "abbreviation": "PIT", "conference": "AFC", "division": "North", "city": "Pittsburgh"},
    
    # AFC South
    {"name": "Houston Texans", "abbreviation": "HOU", "conference": "AFC", "division": "South", "city": "Houston"},
    {"name": "Indianapolis Colts", "abbreviation": "IND", "conference": "AFC", "division": "South", "city": "Indianapolis"},
    {"name": "Jacksonville Jaguars", "abbreviation": "JAX", "conference": "AFC", "division": "South", "city": "Jacksonville"},
    {"name": "Tennessee Titans", "abbreviation": "TEN", "conference": "AFC", "division": "South", "city": "Tennessee"},
    
    # AFC West
    {"name": "Denver Broncos", "abbreviation": "DEN", "conference": "AFC", "division": "West", "city": "Denver"},
    {"name": "Kansas City Chiefs", "abbreviation": "KC", "conference": "AFC", "division": "West", "city": "Kansas City"},
    {"name": "Las Vegas Raiders", "abbreviation": "LV", "conference": "AFC", "division": "West", "city": "Las Vegas"},
    {"name": "Los Angeles Chargers", "abbreviation": "LAC", "conference": "AFC", "division": "West", "city": "Los Angeles"},
    
    # NFC East
    {"name": "Dallas Cowboys", "abbreviation": "DAL", "conference": "NFC", "division": "East", "city": "Dallas"},
    {"name": "New York Giants", "abbreviation": "NYG", "conference": "NFC", "division": "East", "city": "New York"},
    {"name": "Philadelphia Eagles", "abbreviation": "PHI", "conference": "NFC", "division": "East", "city": "Philadelphia"},
    {"name": "Washington Commanders", "abbreviation": "WAS", "conference": "NFC", "division": "East", "city": "Washington"},
    
    # NFC North
    {"name": "Chicago Bears", "abbreviation": "CHI", "conference": "NFC", "division": "North", "city": "Chicago"},
    {"name": "Detroit Lions", "abbreviation": "DET", "conference": "NFC", "division": "North", "city": "Detroit"},
    {"name": "Green Bay Packers", "abbreviation": "GB", "conference": "NFC", "division": "North", "city": "Green Bay"},
    {"name": "Minnesota Vikings", "abbreviation": "MIN", "conference": "NFC", "division": "North", "city": "Minnesota"},
    
    # NFC South
    {"name": "Atlanta Falcons", "abbreviation": "ATL", "conference": "NFC", "division": "South", "city": "Atlanta"},
    {"name": "Carolina Panthers", "abbreviation": "CAR", "conference": "NFC", "division": "South", "city": "Carolina"},
    {"name": "New Orleans Saints", "abbreviation": "NO", "conference": "NFC", "division": "South", "city": "New Orleans"},
    {"name": "Tampa Bay Buccaneers", "abbreviation": "TB", "conference": "NFC", "division": "South", "city": "Tampa Bay"},
    
    # NFC West
    {"name": "Arizona Cardinals", "abbreviation": "ARI", "conference": "NFC", "division": "West", "city": "Arizona"},
    {"name": "Los Angeles Rams", "abbreviation": "LAR", "conference": "NFC", "division": "West", "city": "Los Angeles"},
    {"name": "San Francisco 49ers", "abbreviation": "SF", "conference": "NFC", "division": "West", "city": "San Francisco"},
    {"name": "Seattle Seahawks", "abbreviation": "SEA", "conference": "NFC", "division": "West", "city": "Seattle"},
]

# Real 2025 Fantasy Football Data from Pro Football Reference - ALL 326 PLAYERS
FANTASY_PLAYERS_2025 = [
    {"name": "Ja'Marr Chase", "team": "CIN", "position": "WR", "adp": 1.0, "rank": "WR1"},
    {"name": "Bijan Robinson", "team": "ATL", "position": "RB", "adp": 2.0, "rank": "RB1"},
    {"name": "Jahmyr Gibbs", "team": "DET", "position": "RB", "adp": 3.0, "rank": "RB2"},
    {"name": "Saquon Barkley", "team": "PHI", "position": "RB", "adp": 4.0, "rank": "RB3"},
    {"name": "CeeDee Lamb", "team": "DAL", "position": "WR", "adp": 5.0, "rank": "WR2"},
    {"name": "Justin Jefferson", "team": "MIN", "position": "WR", "adp": 6.0, "rank": "WR3"},
    {"name": "Christian McCaffrey", "team": "SF", "position": "RB", "adp": 7.0, "rank": "RB4"},
    {"name": "Ashton Jeanty", "team": "LV", "position": "RB", "adp": 8.0, "rank": "RB5"},
    {"name": "Malik Nabers", "team": "NYG", "position": "WR", "adp": 9.0, "rank": "WR4"},
    {"name": "Puka Nacua", "team": "LAR", "position": "WR", "adp": 10.0, "rank": "WR5"},
    {"name": "Amon-Ra St. Brown", "team": "DET", "position": "WR", "adp": 11.0, "rank": "WR6"},
    {"name": "Derrick Henry", "team": "BAL", "position": "RB", "adp": 12.0, "rank": "RB6"},
    {"name": "De'Von Achane", "team": "MIA", "position": "RB", "adp": 13.0, "rank": "RB7"},
    {"name": "Brian Thomas Jr.", "team": "JAX", "position": "WR", "adp": 14.0, "rank": "WR7"},
    {"name": "Nico Collins", "team": "HOU", "position": "WR", "adp": 15.0, "rank": "WR8"},
    {"name": "Josh Jacobs", "team": "GB", "position": "RB", "adp": 16.0, "rank": "RB8"},
    {"name": "Bucky Irving", "team": "TB", "position": "RB", "adp": 17.0, "rank": "RB9"},
    {"name": "Brock Bowers", "team": "LV", "position": "TE", "adp": 18.0, "rank": "TE1"},
    {"name": "Lamar Jackson", "team": "BAL", "position": "QB", "adp": 19.0, "rank": "QB1"},
    {"name": "Drake London", "team": "ATL", "position": "WR", "adp": 20.0, "rank": "WR9"},
    {"name": "Chase Brown", "team": "CIN", "position": "RB", "adp": 21.0, "rank": "RB10"},
    {"name": "Jonathan Taylor", "team": "IND", "position": "RB", "adp": 22.0, "rank": "RB11"},
    {"name": "Josh Allen", "team": "BUF", "position": "QB", "adp": 23.0, "rank": "QB2"},
    {"name": "Kyren Williams", "team": "LAR", "position": "RB", "adp": 24.0, "rank": "RB12"},
    {"name": "A.J. Brown", "team": "PHI", "position": "WR", "adp": 25.0, "rank": "WR10"},
    {"name": "Breece Hall", "team": "NYJ", "position": "RB", "adp": 26.0, "rank": "RB13"},
    {"name": "Tyreek Hill", "team": "MIA", "position": "WR", "adp": 27.0, "rank": "WR11"},
    {"name": "Jayden Daniels", "team": "WAS", "position": "QB", "adp": 28.0, "rank": "QB3"},
    {"name": "Trey McBride", "team": "ARI", "position": "TE", "adp": 29.0, "rank": "TE2"},
    {"name": "Ladd McConkey", "team": "LAC", "position": "WR", "adp": 30.0, "rank": "WR12"},
    {"name": "Joe Burrow", "team": "CIN", "position": "QB", "adp": 31.0, "rank": "QB4"},
    {"name": "James Cook", "team": "BUF", "position": "RB", "adp": 32.0, "rank": "RB14"},
    {"name": "Alvin Kamara", "team": "NO", "position": "RB", "adp": 33.0, "rank": "RB15"},
    {"name": "Jaxon Smith-Njigba", "team": "SEA", "position": "WR", "adp": 34.0, "rank": "WR13"},
    {"name": "Garrett Wilson", "team": "NYJ", "position": "WR", "adp": 35.0, "rank": "WR14"},
    {"name": "Davante Adams", "team": "LAR", "position": "WR", "adp": 36.0, "rank": "WR15"},
    {"name": "Tee Higgins", "team": "CIN", "position": "WR", "adp": 37.0, "rank": "WR16"},
    {"name": "Jalen Hurts", "team": "PHI", "position": "QB", "adp": 38.0, "rank": "QB5"},
    {"name": "Marvin Harrison Jr.", "team": "ARI", "position": "WR", "adp": 39.0, "rank": "WR17"},
    {"name": "George Kittle", "team": "SF", "position": "TE", "adp": 40.0, "rank": "TE3"},
    {"name": "Terry McLaurin", "team": "WAS", "position": "WR", "adp": 41.0, "rank": "WR18"},
    {"name": "Kenneth Walker III", "team": "SEA", "position": "RB", "adp": 42.0, "rank": "RB16"},
    {"name": "Omarion Hampton", "team": "LAC", "position": "RB", "adp": 43.0, "rank": "RB17"},
    {"name": "Chuba Hubbard", "team": "CAR", "position": "RB", "adp": 44.0, "rank": "RB18"},
    {"name": "Rashee Rice", "team": "KC", "position": "WR", "adp": 45.0, "rank": "WR19"},
    {"name": "D'Andre Swift", "team": "CHI", "position": "RB", "adp": 46.0, "rank": "RB19"},
    {"name": "DJ Moore", "team": "CHI", "position": "WR", "adp": 47.0, "rank": "WR20"},
    {"name": "Mike Evans", "team": "TB", "position": "WR", "adp": 48.0, "rank": "WR21"},
    {"name": "Joe Mixon", "team": "HOU", "position": "RB", "adp": 49.0, "rank": "RB20"},
    {"name": "RJ Harvey", "team": "DEN", "position": "RB", "adp": 50.0, "rank": "RB21"},
    {"name": "Courtland Sutton", "team": "DEN", "position": "WR", "adp": 51.0, "rank": "WR22"},
    {"name": "James Conner", "team": "ARI", "position": "RB", "adp": 52.0, "rank": "RB22"},
    {"name": "TreVeyon Henderson", "team": "NE", "position": "RB", "adp": 53.0, "rank": "RB23"},
    {"name": "Patrick Mahomes II", "team": "KC", "position": "QB", "adp": 54.0, "rank": "QB6"},
    {"name": "DK Metcalf", "team": "PIT", "position": "WR", "adp": 55.0, "rank": "WR23"},
    {"name": "DeVonta Smith", "team": "PHI", "position": "WR", "adp": 56.0, "rank": "WR24"},
    {"name": "Tetairoa McMillan", "team": "CAR", "position": "WR", "adp": 57.0, "rank": "WR25"},
    {"name": "Sam LaPorta", "team": "DET", "position": "TE", "adp": 58.0, "rank": "TE4"},
    {"name": "Aaron Jones Sr.", "team": "MIN", "position": "RB", "adp": 59.0, "rank": "RB24"},
    {"name": "David Montgomery", "team": "DET", "position": "RB", "adp": 60.0, "rank": "RB25"},
    {"name": "Kaleb Johnson", "team": "PIT", "position": "RB", "adp": 61.0, "rank": "RB26"},
    {"name": "Travis Kelce", "team": "KC", "position": "TE", "adp": 62.0, "rank": "TE5"},
    {"name": "Baker Mayfield", "team": "TB", "position": "QB", "adp": 63.0, "rank": "QB7"},
    {"name": "Jameson Williams", "team": "DET", "position": "WR", "adp": 64.0, "rank": "WR26"},
    {"name": "Zay Flowers", "team": "BAL", "position": "WR", "adp": 65.0, "rank": "WR27"},
    {"name": "Isiah Pacheco", "team": "KC", "position": "RB", "adp": 66.0, "rank": "RB27"},
    {"name": "Tony Pollard", "team": "TEN", "position": "RB", "adp": 67.0, "rank": "RB28"},
    {"name": "Chris Godwin", "team": "TB", "position": "WR", "adp": 68.0, "rank": "WR28"},
    {"name": "Jerry Jeudy", "team": "CLE", "position": "WR", "adp": 69.0, "rank": "WR29"},
    {"name": "Quinshon Judkins", "team": "CLE", "position": "RB", "adp": 70.0, "rank": "RB29"},
    {"name": "Calvin Ridley", "team": "TEN", "position": "WR", "adp": 71.0, "rank": "WR30"},
    {"name": "Travis Hunter", "team": "JAX", "position": "WR", "adp": 72.0, "rank": "WR31"},
    {"name": "Xavier Worthy", "team": "KC", "position": "WR", "adp": 73.0, "rank": "WR32"},
    {"name": "Tyrone Tracy Jr.", "team": "NYG", "position": "RB", "adp": 74.0, "rank": "RB30"},
    {"name": "Bo Nix", "team": "DEN", "position": "QB", "adp": 75.0, "rank": "QB8"},
    {"name": "George Pickens", "team": "DAL", "position": "WR", "adp": 76.0, "rank": "WR33"},
    {"name": "Chris Olave", "team": "NO", "position": "WR", "adp": 77.0, "rank": "WR34"},
    {"name": "T.J. Hockenson", "team": "MIN", "position": "TE", "adp": 78.0, "rank": "TE6"},
    {"name": "Jaylen Waddle", "team": "MIA", "position": "WR", "adp": 79.0, "rank": "WR35"},
    {"name": "Deebo Samuel Sr.", "team": "WAS", "position": "WR", "adp": 80.0, "rank": "WR36"},
    {"name": "Brian Robinson Jr.", "team": "WAS", "position": "RB", "adp": 81.0, "rank": "RB31"},
    {"name": "Jordan Addison", "team": "MIN", "position": "WR", "adp": 82.0, "rank": "WR37"},
    {"name": "Jaylen Warren", "team": "PIT", "position": "RB", "adp": 83.0, "rank": "RB32"},
    {"name": "Cooper Kupp", "team": "SEA", "position": "WR", "adp": 84.0, "rank": "WR38"},
    {"name": "Caleb Williams", "team": "CHI", "position": "QB", "adp": 85.0, "rank": "QB9"},
    {"name": "Kyler Murray", "team": "ARI", "position": "QB", "adp": 86.0, "rank": "QB10"},
    {"name": "Jauan Jennings", "team": "SF", "position": "WR", "adp": 87.0, "rank": "WR39"},
    {"name": "Evan Engram", "team": "DEN", "position": "TE", "adp": 88.0, "rank": "TE7"},
    {"name": "Rome Odunze", "team": "CHI", "position": "WR", "adp": 89.0, "rank": "WR40"},
    {"name": "Travis Etienne Jr.", "team": "JAX", "position": "RB", "adp": 90.0, "rank": "RB33"},
    {"name": "Cam Skattebo", "team": "NYG", "position": "RB", "adp": 91.0, "rank": "RB34"},
    {"name": "Javonte Williams", "team": "DAL", "position": "RB", "adp": 92.0, "rank": "RB35"},
    {"name": "Dak Prescott", "team": "DAL", "position": "QB", "adp": 93.0, "rank": "QB11"},
    {"name": "Mark Andrews", "team": "BAL", "position": "TE", "adp": 94.0, "rank": "TE8"},
    {"name": "Jared Goff", "team": "DET", "position": "QB", "adp": 95.0, "rank": "QB12"},
    {"name": "Najee Harris", "team": "LAC", "position": "RB", "adp": 96.0, "rank": "RB36"},
    {"name": "Stefon Diggs", "team": "NE", "position": "WR", "adp": 97.0, "rank": "WR41"},
    {"name": "Matthew Golden", "team": "GB", "position": "WR", "adp": 98.0, "rank": "WR42"},
    {"name": "Zach Charbonnet", "team": "SEA", "position": "RB", "adp": 99.0, "rank": "RB37"},
    {"name": "Khalil Shakir", "team": "BUF", "position": "WR", "adp": 100.0, "rank": "WR43"},
    {"name": "Justin Fields", "team": "NYJ", "position": "QB", "adp": 101.0, "rank": "QB13"},
    {"name": "Jordan Mason", "team": "MIN", "position": "RB", "adp": 102.0, "rank": "RB38"},
    {"name": "Jayden Reed", "team": "GB", "position": "WR", "adp": 103.0, "rank": "WR44"},
    {"name": "Ricky Pearsall", "team": "SF", "position": "WR", "adp": 104.0, "rank": "WR45"},
    {"name": "Brock Purdy", "team": "SF", "position": "QB", "adp": 105.0, "rank": "QB14"},
    {"name": "Tyjae Spears", "team": "TEN", "position": "RB", "adp": 106.0, "rank": "RB39"},
    {"name": "David Njoku", "team": "CLE", "position": "TE", "adp": 107.0, "rank": "TE9"},
    {"name": "Colston Loveland", "team": "CHI", "position": "TE", "adp": 108.0, "rank": "TE10"},
    {"name": "Jakobi Meyers", "team": "LV", "position": "WR", "adp": 109.0, "rank": "WR46"},
    {"name": "J.K. Dobbins", "team": "DEN", "position": "RB", "adp": 110.0, "rank": "RB40"},
    {"name": "Justin Herbert", "team": "LAC", "position": "QB", "adp": 111.0, "rank": "QB15"},
    {"name": "Rhamondre Stevenson", "team": "NE", "position": "RB", "adp": 112.0, "rank": "RB41"},
    {"name": "Tucker Kraft", "team": "GB", "position": "TE", "adp": 113.0, "rank": "TE11"},
    {"name": "Michael Pittman Jr.", "team": "IND", "position": "WR", "adp": 114.0, "rank": "WR47"},
    {"name": "Tyler Warren", "team": "IND", "position": "TE", "adp": 115.0, "rank": "TE12"},
    {"name": "Jaydon Blue", "team": "DAL", "position": "RB", "adp": 116.0, "rank": "RB42"},
    {"name": "Brandon Aiyuk", "team": "SF", "position": "WR", "adp": 117.0, "rank": "WR48"},
    {"name": "Josh Downs", "team": "IND", "position": "WR", "adp": 118.0, "rank": "WR49"},
    {"name": "Rachaad White", "team": "TB", "position": "RB", "adp": 119.0, "rank": "RB43"},
    {"name": "Darnell Mooney", "team": "ATL", "position": "WR", "adp": 120.0, "rank": "WR50"},
    {"name": "Jonnu Smith", "team": "PIT", "position": "TE", "adp": 121.0, "rank": "TE13"},
    {"name": "J.J. McCarthy", "team": "MIN", "position": "QB", "adp": 122.0, "rank": "QB16"},
    {"name": "Drake Maye", "team": "NE", "position": "QB", "adp": 123.0, "rank": "QB17"},
    {"name": "Isaac Guerendo", "team": "SF", "position": "RB", "adp": 124.0, "rank": "RB44"},
    {"name": "Austin Ekeler", "team": "WAS", "position": "RB", "adp": 125.0, "rank": "RB45"},
    {"name": "Jake Ferguson", "team": "DAL", "position": "TE", "adp": 126.0, "rank": "TE14"},
    {"name": "Emeka Egbuka", "team": "TB", "position": "WR", "adp": 127.0, "rank": "WR51"},
    {"name": "Tank Bigsby", "team": "JAX", "position": "RB", "adp": 128.0, "rank": "RB46"},
    {"name": "Bhayshul Tuten", "team": "JAX", "position": "RB", "adp": 129.0, "rank": "RB47"},
    {"name": "C.J. Stroud", "team": "HOU", "position": "QB", "adp": 130.0, "rank": "QB18"},
    {"name": "Jordan Love", "team": "GB", "position": "QB", "adp": 131.0, "rank": "QB19"},
    {"name": "Dalton Kincaid", "team": "BUF", "position": "TE", "adp": 132.0, "rank": "TE15"},
    {"name": "Jayden Higgins", "team": "HOU", "position": "WR", "adp": 133.0, "rank": "WR52"},
    {"name": "Jerome Ford", "team": "CLE", "position": "RB", "adp": 134.0, "rank": "RB48"},
    {"name": "Ray Davis", "team": "BUF", "position": "RB", "adp": 135.0, "rank": "RB49"},
    {"name": "Trey Benson", "team": "ARI", "position": "RB", "adp": 136.0, "rank": "RB50"},
    {"name": "Trevor Lawrence", "team": "JAX", "position": "QB", "adp": 137.0, "rank": "QB20"},
    {"name": "Keon Coleman", "team": "BUF", "position": "WR", "adp": 138.0, "rank": "WR53"},
    {"name": "Tua Tagovailoa", "team": "MIA", "position": "QB", "adp": 139.0, "rank": "QB21"},
    {"name": "Marvin Mims Jr.", "team": "DEN", "position": "WR", "adp": 140.0, "rank": "WR54"},
    {"name": "Nick Chubb", "team": "HOU", "position": "RB", "adp": 141.0, "rank": "RB51"},
    {"name": "Tre Harris", "team": "LAC", "position": "WR", "adp": 142.0, "rank": "WR55"},
    {"name": "Kyle Pitts", "team": "ATL", "position": "TE", "adp": 143.0, "rank": "TE16"},
    {"name": "Braelon Allen", "team": "NYJ", "position": "RB", "adp": 144.0, "rank": "RB52"},
    {"name": "Jack Bech", "team": "LV", "position": "WR", "adp": 145.0, "rank": "WR56"},
    {"name": "Tyler Allgeier", "team": "ATL", "position": "RB", "adp": 146.0, "rank": "RB53"},
    {"name": "Rico Dowdle", "team": "CAR", "position": "RB", "adp": 147.0, "rank": "RB54"},
    {"name": "Dallas Goedert", "team": "PHI", "position": "TE", "adp": 148.0, "rank": "TE17"},
    {"name": "Marquise Brown", "team": "KC", "position": "WR", "adp": 149.0, "rank": "WR57"},
    {"name": "Jaylen Wright", "team": "MIA", "position": "RB", "adp": 150.0, "rank": "RB55"},
    {"name": "Hunter Henry", "team": "NE", "position": "TE", "adp": 151.0, "rank": "TE18"},
    {"name": "Michael Penix Jr.", "team": "ATL", "position": "QB", "adp": 152.0, "rank": "QB22"},
    {"name": "Isaiah Likely", "team": "BAL", "position": "TE", "adp": 153.0, "rank": "TE19"},
    {"name": "Bryce Young", "team": "CAR", "position": "QB", "adp": 154.0, "rank": "QB23"},
    {"name": "Matthew Stafford", "team": "LAR", "position": "QB", "adp": 155.0, "rank": "QB24"},
    {"name": "Luther Burden III", "team": "CHI", "position": "WR", "adp": 156.0, "rank": "WR58"},
    {"name": "DeAndre Hopkins", "team": "BAL", "position": "WR", "adp": 157.0, "rank": "WR59"},
    {"name": "Christian Kirk", "team": "HOU", "position": "WR", "adp": 158.0, "rank": "WR60"},
    {"name": "Rashid Shaheed", "team": "NO", "position": "WR", "adp": 159.0, "rank": "WR61"},
    {"name": "Zach Ertz", "team": "WAS", "position": "TE", "adp": 160.0, "rank": "TE20"},
    {"name": "Brenton Strange", "team": "JAX", "position": "TE", "adp": 161.0, "rank": "TE21"},
    {"name": "Geno Smith", "team": "LV", "position": "QB", "adp": 162.0, "rank": "QB25"},
    {"name": "Cedric Tillman", "team": "CLE", "position": "WR", "adp": 163.0, "rank": "WR62"},
    {"name": "Cameron Ward", "team": "TEN", "position": "QB", "adp": 164.0, "rank": "QB26"},
    {"name": "Sam Darnold", "team": "SEA", "position": "QB", "adp": 165.0, "rank": "QB27"},
    {"name": "Justice Hill", "team": "BAL", "position": "RB", "adp": 166.0, "rank": "RB56"},
    {"name": "Cade Otton", "team": "TB", "position": "TE", "adp": 167.0, "rank": "TE22"},
    {"name": "Brandon Aubrey", "team": "DAL", "position": "K", "adp": 168.0, "rank": "K1"},
    {"name": "Aaron Rodgers", "team": "PIT", "position": "QB", "adp": 169.0, "rank": "QB28"},
    {"name": "Xavier Legette", "team": "CAR", "position": "WR", "adp": 170.0, "rank": "WR63"},
    {"name": "Kareem Hunt", "team": "KC", "position": "RB", "adp": 171.0, "rank": "RB57"},
    {"name": "Dylan Sampson", "team": "CLE", "position": "RB", "adp": 172.0, "rank": "RB58"},
    {"name": "Denver Broncos", "team": "DEN", "position": "DST", "adp": 173.0, "rank": "DST1"},
    {"name": "Mason Taylor", "team": "NYJ", "position": "TE", "adp": 174.0, "rank": "TE23"},
    {"name": "Kyle Monangai", "team": "CHI", "position": "RB", "adp": 175.0, "rank": "RB59"},
    {"name": "Wan'Dale Robinson", "team": "NYG", "position": "WR", "adp": 176.0, "rank": "WR64"},
    {"name": "Rashod Bateman", "team": "BAL", "position": "WR", "adp": 177.0, "rank": "WR65"},
    {"name": "Adam Thielen", "team": "CAR", "position": "WR", "adp": 178.0, "rank": "WR66"},
    {"name": "Chig Okonkwo", "team": "TEN", "position": "TE", "adp": 179.0, "rank": "TE24"},
    {"name": "MarShawn Lloyd", "team": "GB", "position": "RB", "adp": 180.0, "rank": "RB60"},
    {"name": "Anthony Richardson Sr.", "team": "IND", "position": "QB", "adp": 181.0, "rank": "QB29"},
    {"name": "Roschon Johnson", "team": "CHI", "position": "RB", "adp": 182.0, "rank": "RB61"},
    {"name": "Kyle Williams", "team": "NE", "position": "WR", "adp": 183.0, "rank": "WR67"},
    {"name": "Russell Wilson", "team": "NYG", "position": "QB", "adp": 184.0, "rank": "QB30"},
    {"name": "Mike Gesicki", "team": "CIN", "position": "TE", "adp": 185.0, "rank": "TE25"},
    {"name": "Jarquez Hunter", "team": "LAR", "position": "RB", "adp": 186.0, "rank": "RB62"},
    {"name": "Philadelphia Eagles", "team": "PHI", "position": "DST", "adp": 187.0, "rank": "DST2"},
    {"name": "Cameron Dicker", "team": "LAC", "position": "K", "adp": 188.0, "rank": "K2"},
    {"name": "Buffalo Bills", "team": "BUF", "position": "DST", "adp": 189.0, "rank": "DST3"},
    {"name": "Romeo Doubs", "team": "GB", "position": "WR", "adp": 190.0, "rank": "WR68"},
    {"name": "Keenan Allen", "team": "CHI", "position": "WR", "adp": 191.0, "rank": "WR69"},
    {"name": "Darren Waller", "team": "MIA", "position": "TE", "adp": 192.0, "rank": "TE26"},
    {"name": "Jalen McMillan", "team": "TB", "position": "WR", "adp": 193.0, "rank": "WR70"},
    {"name": "Houston Texans", "team": "HOU", "position": "DST", "adp": 194.0, "rank": "DST4"},
    {"name": "Dalton Schultz", "team": "HOU", "position": "TE", "adp": 195.0, "rank": "TE27"},
    {"name": "Pat Freiermuth", "team": "PIT", "position": "TE", "adp": 196.0, "rank": "TE28"},
    {"name": "Jake Bates", "team": "DET", "position": "K", "adp": 197.0, "rank": "K3"},
    {"name": "Daniel Jones", "team": "IND", "position": "QB", "adp": 198.0, "rank": "QB31"},
    {"name": "Pittsburgh Steelers", "team": "PIT", "position": "DST", "adp": 199.0, "rank": "DST5"},
    {"name": "Tyler Shough", "team": "NO", "position": "QB", "adp": 200.0, "rank": "QB32"},
    {"name": "Will Shipley", "team": "PHI", "position": "RB", "adp": 201.0, "rank": "RB63"},
    {"name": "Alec Pierce", "team": "IND", "position": "WR", "adp": 202.0, "rank": "WR71"},
    {"name": "Baltimore Ravens", "team": "BAL", "position": "DST", "adp": 203.0, "rank": "DST6"},
    {"name": "Joe Flacco", "team": "CLE", "position": "QB", "adp": 204.0, "rank": "QB33"},
    {"name": "Quentin Johnston", "team": "LAC", "position": "WR", "adp": 205.0, "rank": "WR72"},
    {"name": "Miles Sanders", "team": "DAL", "position": "RB", "adp": 206.0, "rank": "RB64"},
    {"name": "Brashard Smith", "team": "KC", "position": "RB", "adp": 207.0, "rank": "RB65"},
    {"name": "Ka'imi Fairbairn", "team": "HOU", "position": "K", "adp": 208.0, "rank": "K4"},
    {"name": "DJ Giddens", "team": "IND", "position": "RB", "adp": 209.0, "rank": "RB66"},
    {"name": "Elijah Mitchell", "team": "KC", "position": "RB", "adp": 210.0, "rank": "RB67"},
    {"name": "Minnesota Vikings", "team": "MIN", "position": "DST", "adp": 211.0, "rank": "DST7"},
    {"name": "DeMario Douglas", "team": "NE", "position": "WR", "adp": 212.0, "rank": "WR73"},
    {"name": "Wil Lutz", "team": "DEN", "position": "K", "adp": 213.0, "rank": "K5"},
    {"name": "Chase McLaughlin", "team": "TB", "position": "K", "adp": 214.0, "rank": "K6"},
    {"name": "Joshua Palmer", "team": "BUF", "position": "WR", "adp": 215.0, "rank": "WR74"},
    {"name": "Blake Corum", "team": "LAR", "position": "RB", "adp": 216.0, "rank": "RB68"},
    {"name": "Zack Moss", "team": "CIN", "position": "RB", "adp": 217.0, "rank": "RB69"},
    {"name": "Juwan Johnson", "team": "NO", "position": "TE", "adp": 218.0, "rank": "TE29"},
    {"name": "Jaxson Dart", "team": "NYG", "position": "QB", "adp": 219.0, "rank": "QB34"},
    {"name": "Tyler Conklin", "team": "LAC", "position": "TE", "adp": 220.0, "rank": "TE30"},
    {"name": "Devin Neal", "team": "NO", "position": "RB", "adp": 221.0, "rank": "RB70"},
    {"name": "New York Giants", "team": "NYG", "position": "DST", "adp": 222.0, "rank": "DST8"},
    {"name": "Raheem Mostert", "team": "LV", "position": "RB", "adp": 223.0, "rank": "RB71"},
    {"name": "Harrison Butker", "team": "KC", "position": "K", "adp": 224.0, "rank": "K7"},
    {"name": "Kirk Cousins", "team": "ATL", "position": "QB", "adp": 225.0, "rank": "QB35"},
    {"name": "Kansas City Chiefs", "team": "KC", "position": "DST", "adp": 226.0, "rank": "DST9"},
    {"name": "Darius Slayton", "team": "NYG", "position": "WR", "adp": 227.0, "rank": "WR75"},
    {"name": "Dallas Cowboys", "team": "DAL", "position": "DST", "adp": 228.0, "rank": "DST10"},
    {"name": "Jason Sanders", "team": "MIA", "position": "K", "adp": 229.0, "rank": "K8"},
    {"name": "Dyami Brown", "team": "JAX", "position": "WR", "adp": 230.0, "rank": "WR76"},
    {"name": "Chris Boswell", "team": "PIT", "position": "K", "adp": 231.0, "rank": "K9"},
    {"name": "Tyler Higbee", "team": "LAR", "position": "TE", "adp": 232.0, "rank": "TE31"},
    {"name": "Jaylin Noel", "team": "HOU", "position": "WR", "adp": 233.0, "rank": "WR77"},
    {"name": "Antonio Gibson", "team": "NE", "position": "RB", "adp": 234.0, "rank": "RB72"},
    {"name": "Ray-Ray McCloud III", "team": "ATL", "position": "WR", "adp": 235.0, "rank": "WR78"},
    {"name": "Brandon McManus", "team": "GB", "position": "K", "adp": 236.0, "rank": "K10"},
    {"name": "Jaleel McLaughlin", "team": "DEN", "position": "RB", "adp": 237.0, "rank": "RB73"},
    {"name": "A.J. Dillon", "team": "PHI", "position": "RB", "adp": 238.0, "rank": "RB74"},
    {"name": "Tahj Brooks", "team": "CIN", "position": "RB", "adp": 239.0, "rank": "RB75"},
    {"name": "Shedeur Sanders", "team": "CLE", "position": "QB", "adp": 240.0, "rank": "QB36"},
    {"name": "Keaton Mitchell", "team": "BAL", "position": "RB", "adp": 241.0, "rank": "RB76"},
    {"name": "Los Angeles Rams", "team": "LAR", "position": "DST", "adp": 242.0, "rank": "DST11"},
    {"name": "Dont'e Thornton Jr.", "team": "LV", "position": "WR", "adp": 243.0, "rank": "WR79"},
    {"name": "Jalen Milroe", "team": "SEA", "position": "QB", "adp": 244.0, "rank": "QB37"},
    {"name": "Jake Elliott", "team": "PHI", "position": "K", "adp": 245.0, "rank": "K11"},
    {"name": "Theo Johnson", "team": "NYG", "position": "TE", "adp": 246.0, "rank": "TE32"},
    {"name": "Tampa Bay Buccaneers", "team": "TB", "position": "DST", "adp": 247.0, "rank": "DST12"},
    {"name": "Calvin Austin III", "team": "PIT", "position": "WR", "adp": 248.0, "rank": "WR80"},
    {"name": "Detroit Lions", "team": "DET", "position": "DST", "adp": 249.0, "rank": "DST13"},
    {"name": "Elijah Arroyo", "team": "SEA", "position": "TE", "adp": 250.0, "rank": "TE33"},
    {"name": "Ollie Gordon II", "team": "MIA", "position": "RB", "adp": 251.0, "rank": "RB77"},
    {"name": "San Francisco 49ers", "team": "SF", "position": "DST", "adp": 252.0, "rank": "DST14"},
    {"name": "Pat Bryant", "team": "DEN", "position": "WR", "adp": 253.0, "rank": "WR81"},
    {"name": "Noah Gray", "team": "KC", "position": "TE", "adp": 254.0, "rank": "TE34"},
    {"name": "Matt Gay", "team": "WAS", "position": "K", "adp": 255.0, "rank": "K12"},
    {"name": "Green Bay Packers", "team": "GB", "position": "DST", "adp": 256.0, "rank": "DST15"},
    {"name": "Tyler Bass", "team": "BUF", "position": "K", "adp": 257.0, "rank": "K13"},
    {"name": "Trevor Etienne", "team": "CAR", "position": "RB", "adp": 258.0, "rank": "RB78"},
    {"name": "Kenny Pickett", "team": "CLE", "position": "QB", "adp": 259.0, "rank": "QB38"},
    {"name": "New England Patriots", "team": "NE", "position": "DST", "adp": 260.0, "rank": "DST16"},
    {"name": "Ja'Tavion Sanders", "team": "CAR", "position": "TE", "adp": 261.0, "rank": "TE35"},
    {"name": "Jacory Croskey-Merritt", "team": "WAS", "position": "RB", "adp": 262.0, "rank": "RB79"},
    {"name": "Taysom Hill", "team": "NO", "position": "TE", "adp": 263.0, "rank": "TE36"},
    {"name": "Michael Wilson", "team": "ARI", "position": "WR", "adp": 264.0, "rank": "WR82"},
    {"name": "Evan McPherson", "team": "CIN", "position": "K", "adp": 265.0, "rank": "K14"},
    {"name": "Will Reichard", "team": "MIN", "position": "K", "adp": 266.0, "rank": "K15"},
    {"name": "Jalen Nailor", "team": "MIN", "position": "WR", "adp": 267.0, "rank": "WR83"},
    {"name": "Diontae Johnson", "team": "CLE", "position": "WR", "adp": 268.0, "rank": "WR84"},
    {"name": "Joshua Karty", "team": "LAR", "position": "K", "adp": 269.0, "rank": "K16"},
    {"name": "Tyler Loop", "team": "BAL", "position": "K", "adp": 270.0, "rank": "K17"},
    {"name": "Arizona Cardinals", "team": "ARI", "position": "DST", "adp": 271.0, "rank": "DST17"},
    {"name": "Andrei Iosivas", "team": "CIN", "position": "WR", "adp": 272.0, "rank": "WR85"},
    {"name": "Alexander Mattison", "team": "MIA", "position": "RB", "adp": 273.0, "rank": "RB80"},
    {"name": "Daniel Carlson", "team": "LV", "position": "K", "adp": 274.0, "rank": "K18"},
    {"name": "Cole Kmet", "team": "CHI", "position": "TE", "adp": 275.0, "rank": "TE37"},
    {"name": "Younghoe Koo", "team": "ATL", "position": "K", "adp": 276.0, "rank": "K19"},
    {"name": "Jake Moody", "team": "SF", "position": "K", "adp": 277.0, "rank": "K20"},
    {"name": "Sean Tucker", "team": "TB", "position": "RB", "adp": 278.0, "rank": "RB81"},
    {"name": "Jameis Winston", "team": "NYG", "position": "QB", "adp": 279.0, "rank": "QB39"},
    {"name": "Tre Tucker", "team": "LV", "position": "WR", "adp": 280.0, "rank": "WR86"},
    {"name": "Chicago Bears", "team": "CHI", "position": "DST", "adp": 281.0, "rank": "DST18"},
    {"name": "Cleveland Browns", "team": "CLE", "position": "DST", "adp": 282.0, "rank": "DST19"},
    {"name": "Noah Fant", "team": "SEA", "position": "TE", "adp": 283.0, "rank": "TE38"},
    {"name": "Roman Wilson", "team": "PIT", "position": "WR", "adp": 284.0, "rank": "WR87"},
    {"name": "Terrance Ferguson", "team": "LAR", "position": "TE", "adp": 285.0, "rank": "TE39"},
    {"name": "Kenneth Gainwell", "team": "PIT", "position": "RB", "adp": 286.0, "rank": "RB82"},
    {"name": "Emanuel Wilson", "team": "GB", "position": "RB", "adp": 287.0, "rank": "RB83"},
    {"name": "Amari Cooper", "team": "BUF", "position": "WR", "adp": 288.0, "rank": "WR88"},
    {"name": "Woody Marks", "team": "HOU", "position": "RB", "adp": 289.0, "rank": "RB84"},
    {"name": "Jalen Royals", "team": "KC", "position": "WR", "adp": 290.0, "rank": "WR89"},
    {"name": "Los Angeles Chargers", "team": "LAC", "position": "DST", "adp": 291.0, "rank": "DST20"},
    {"name": "Brandin Cooks", "team": "NO", "position": "WR", "adp": 292.0, "rank": "WR90"},
    {"name": "Audric Estime", "team": "DEN", "position": "RB", "adp": 293.0, "rank": "RB85"},
    {"name": "New York Jets", "team": "NYJ", "position": "DST", "adp": 294.0, "rank": "DST21"},
    {"name": "Devin Singletary", "team": "NYG", "position": "RB", "adp": 295.0, "rank": "RB86"},
    {"name": "Dontayvion Wicks", "team": "GB", "position": "WR", "adp": 296.0, "rank": "WR91"},
    {"name": "Seattle Seahawks", "team": "SEA", "position": "DST", "adp": 297.0, "rank": "DST22"},
    {"name": "Kendre Miller", "team": "NO", "position": "RB", "adp": 298.0, "rank": "RB87"},
    {"name": "Jalen Tolbert", "team": "DAL", "position": "WR", "adp": 299.0, "rank": "WR92"},
    {"name": "Samaje Perine", "team": "CIN", "position": "RB", "adp": 300.0, "rank": "RB88"},
    {"name": "Jordan James", "team": "SF", "position": "RB", "adp": 301.0, "rank": "RB89"},
    {"name": "Oronde Gadsden II", "team": "LAC", "position": "TE", "adp": 302.0, "rank": "TE40"},
    {"name": "Adonai Mitchell", "team": "IND", "position": "WR", "adp": 303.0, "rank": "WR93"},
    {"name": "Joe Milton III", "team": "DAL", "position": "QB", "adp": 304.0, "rank": "QB40"},
    {"name": "Harold Fannin Jr.", "team": "CLE", "position": "TE", "adp": 305.0, "rank": "TE41"},
    {"name": "Elic Ayomanor", "team": "TEN", "position": "WR", "adp": 306.0, "rank": "WR94"},
    {"name": "Cincinnati Bengals", "team": "CIN", "position": "DST", "adp": 307.0, "rank": "DST23"},
    {"name": "Jermaine Burton", "team": "CIN", "position": "WR", "adp": 308.0, "rank": "WR95"},
    {"name": "Tutu Atwell", "team": "LAR", "position": "WR", "adp": 309.0, "rank": "WR96"},
    {"name": "Tyler Lockett", "team": "TEN", "position": "WR", "adp": 310.0, "rank": "WR97"},
    {"name": "Washington Commanders", "team": "WAS", "position": "DST", "adp": 311.0, "rank": "DST24"},
    {"name": "Kayshon Boutte", "team": "NE", "position": "WR", "adp": 312.0, "rank": "WR98"},
    {"name": "Mason Rudolph", "team": "PIT", "position": "QB", "adp": 313.0, "rank": "QB41"},
    {"name": "Isaac TeSlaa", "team": "DET", "position": "WR", "adp": 314.0, "rank": "WR99"},
    {"name": "Spencer Rattler", "team": "NO", "position": "QB", "adp": 315.0, "rank": "QB42"},
    {"name": "Jalen Coker", "team": "CAR", "position": "WR", "adp": 316.0, "rank": "WR100"},
    {"name": "Elijah Moore", "team": "BUF", "position": "WR", "adp": 317.0, "rank": "WR101"},
    {"name": "Troy Franklin", "team": "DEN", "position": "WR", "adp": 318.0, "rank": "WR102"},
    {"name": "Khalil Herbert", "team": "IND", "position": "RB", "adp": 319.0, "rank": "RB90"},
    {"name": "Aidan O'Connell", "team": "LV", "position": "QB", "adp": 320.0, "rank": "QB43"},
    {"name": "Dameon Pierce", "team": "HOU", "position": "RB", "adp": 321.0, "rank": "RB91"},
    {"name": "Devaughn Vele", "team": "DEN", "position": "WR", "adp": 322.0, "rank": "WR103"},
    {"name": "Isaiah Davis", "team": "NYJ", "position": "RB", "adp": 323.0, "rank": "RB92"},
    {"name": "Ty Johnson", "team": "BUF", "position": "RB", "adp": 324.0, "rank": "RB93"},
    {"name": "Savion Williams", "team": "GB", "position": "WR", "adp": 325.0, "rank": "WR104"},
    {"name": "Phil Mafah", "team": "DAL", "position": "RB", "adp": 326.0, "rank": "RB94"},
]

# Historical NFL Team Performance (2022-2024) and 2025 Vegas Projections
TEAM_HISTORICAL_DATA = {
    "ARI": {"2022": {"wins": 4, "points": 340}, "2023": {"wins": 4, "points": 289}, "2024": {"wins": 4, "points": 314}, "vegas_2025_wins": 4.5},
    "ATL": {"2022": {"wins": 7, "points": 365}, "2023": {"wins": 7, "points": 361}, "2024": {"wins": 8, "points": 381}, "vegas_2025_wins": 8.5},
    "BAL": {"2022": {"wins": 10, "points": 394}, "2023": {"wins": 13, "points": 460}, "2024": {"wins": 12, "points": 435}, "vegas_2025_wins": 11.5},
    "BUF": {"2022": {"wins": 13, "points": 483}, "2023": {"wins": 11, "points": 414}, "2024": {"wins": 13, "points": 456}, "vegas_2025_wins": 11.5},
    "CAR": {"2022": {"wins": 7, "points": 347}, "2023": {"wins": 2, "points": 273}, "2024": {"wins": 5, "points": 298}, "vegas_2025_wins": 5.5},
    "CHI": {"2022": {"wins": 3, "points": 326}, "2023": {"wins": 7, "points": 334}, "2024": {"wins": 5, "points": 317}, "vegas_2025_wins": 8.5},
    "CIN": {"2022": {"wins": 12, "points": 418}, "2023": {"wins": 9, "points": 365}, "2024": {"wins": 9, "points": 384}, "vegas_2025_wins": 9.5},
    "CLE": {"2022": {"wins": 7, "points": 361}, "2023": {"wins": 11, "points": 355}, "2024": {"wins": 3, "points": 235}, "vegas_2025_wins": 8.5},
    "DAL": {"2022": {"wins": 12, "points": 467}, "2023": {"wins": 12, "points": 432}, "2024": {"wins": 7, "points": 353}, "vegas_2025_wins": 8.5},
    "DEN": {"2022": {"wins": 5, "points": 318}, "2023": {"wins": 8, "points": 382}, "2024": {"wins": 10, "points": 388}, "vegas_2025_wins": 9.5},
    "DET": {"2022": {"wins": 9, "points": 424}, "2023": {"wins": 12, "points": 473}, "2024": {"wins": 15, "points": 542}, "vegas_2025_wins": 11.5},
    "GB": {"2022": {"wins": 8, "points": 370}, "2023": {"wins": 9, "points": 406}, "2024": {"wins": 11, "points": 456}, "vegas_2025_wins": 10.5},
    "HOU": {"2022": {"wins": 3, "points": 289}, "2023": {"wins": 10, "points": 387}, "2024": {"wins": 10, "points": 409}, "vegas_2025_wins": 9.5},
    "IND": {"2022": {"wins": 4, "points": 344}, "2023": {"wins": 9, "points": 366}, "2024": {"wins": 8, "points": 331}, "vegas_2025_wins": 8.5},
    "JAX": {"2022": {"wins": 9, "points": 365}, "2023": {"wins": 9, "points": 371}, "2024": {"wins": 4, "points": 296}, "vegas_2025_wins": 6.5},
    "KC": {"2022": {"wins": 14, "points": 496}, "2023": {"wins": 11, "points": 421}, "2024": {"wins": 15, "points": 456}, "vegas_2025_wins": 11.5},
    "LV": {"2022": {"wins": 6, "points": 364}, "2023": {"wins": 8, "points": 335}, "2024": {"wins": 4, "points": 296}, "vegas_2025_wins": 6.5},
    "LAC": {"2022": {"wins": 10, "points": 396}, "2023": {"wins": 5, "points": 319}, "2024": {"wins": 11, "points": 397}, "vegas_2025_wins": 8.5},
    "LAR": {"2022": {"wins": 5, "points": 273}, "2023": {"wins": 10, "points": 424}, "2024": {"wins": 10, "points": 402}, "vegas_2025_wins": 9.5},
    "MIA": {"2022": {"wins": 9, "points": 404}, "2023": {"wins": 11, "points": 406}, "2024": {"wins": 8, "points": 377}, "vegas_2025_wins": 8.5},
    "MIN": {"2022": {"wins": 13, "points": 424}, "2023": {"wins": 7, "points": 344}, "2024": {"wins": 14, "points": 460}, "vegas_2025_wins": 9.5},
    "NE": {"2022": {"wins": 8, "points": 368}, "2023": {"wins": 4, "points": 289}, "2024": {"wins": 4, "points": 241}, "vegas_2025_wins": 4.5},
    "NO": {"2022": {"wins": 7, "points": 330}, "2023": {"wins": 9, "points": 382}, "2024": {"wins": 5, "points": 340}, "vegas_2025_wins": 6.5},
    "NYG": {"2022": {"wins": 9, "points": 365}, "2023": {"wins": 6, "points": 321}, "2024": {"wins": 3, "points": 245}, "vegas_2025_wins": 6.5},
    "NYJ": {"2022": {"wins": 7, "points": 295}, "2023": {"wins": 7, "points": 311}, "2024": {"wins": 5, "points": 300}, "vegas_2025_wins": 9.5},
    "PHI": {"2022": {"wins": 14, "points": 477}, "2023": {"wins": 11, "points": 379}, "2024": {"wins": 14, "points": 481}, "vegas_2025_wins": 10.5},
    "PIT": {"2022": {"wins": 9, "points": 308}, "2023": {"wins": 10, "points": 321}, "2024": {"wins": 10, "points": 327}, "vegas_2025_wins": 8.5},
    "SF": {"2022": {"wins": 13, "points": 450}, "2023": {"wins": 12, "points": 456}, "2024": {"wins": 6, "points": 355}, "vegas_2025_wins": 9.5},
    "SEA": {"2022": {"wins": 9, "points": 407}, "2023": {"wins": 9, "points": 417}, "2024": {"wins": 10, "points": 423}, "vegas_2025_wins": 8.5},
    "TB": {"2022": {"wins": 8, "points": 313}, "2023": {"wins": 9, "points": 387}, "2024": {"wins": 10, "points": 436}, "vegas_2025_wins": 9.5},
    "TEN": {"2022": {"wins": 7, "points": 329}, "2023": {"wins": 6, "points": 290}, "2024": {"wins": 3, "points": 246}, "vegas_2025_wins": 6.5},
    "WAS": {"2022": {"wins": 8, "points": 321}, "2023": {"wins": 4, "points": 290}, "2024": {"wins": 12, "points": 481}, "vegas_2025_wins": 9.5},
}

# NFL Divisions for strength calculations (teams play division rivals twice each)
NFL_DIVISIONS = {
    "AFC_EAST": ["BUF", "MIA", "NYJ", "NE"],
    "AFC_NORTH": ["BAL", "CIN", "CLE", "PIT"], 
    "AFC_SOUTH": ["HOU", "IND", "JAX", "TEN"],
    "AFC_WEST": ["KC", "LAC", "LV", "DEN"],
    "NFC_EAST": ["PHI", "DAL", "WAS", "NYG"],
    "NFC_NORTH": ["DET", "GB", "MIN", "CHI"],
    "NFC_SOUTH": ["TB", "ATL", "NO", "CAR"],
    "NFC_WEST": ["SF", "LAR", "SEA", "ARI"]
}

def get_team_division(team_abbr):
    """Get which division a team belongs to"""
    for division, teams in NFL_DIVISIONS.items():
        if team_abbr in teams:
            return division, teams
    return None, []

def calculate_divisional_strength_impact(team_abbr, all_team_projections):
    """
    Calculate how divisional strength affects win projections
    Teams play division rivals twice (6 games vs 3 teams)
    """
    division, division_teams = get_team_division(team_abbr)
    if not division:
        return 0
    
    # Calculate average strength of division rivals (excluding self)
    rivals = [t for t in division_teams if t != team_abbr and t in all_team_projections]
    if not rivals:
        return 0
    
    rival_avg_wins = sum(all_team_projections[rival]["projected_wins"] for rival in rivals) / len(rivals)
    
    # Strong divisions hurt your win total, weak divisions help
    # Average team wins ~8.5, so adjust based on how strong/weak your division is
    divisional_impact = (8.5 - rival_avg_wins) * 0.4  # Each game above/below average affects ~0.4 wins
    
    return divisional_impact

def calculate_realistic_team_projections(team_abbr, historical_data):
    """
    Calculate realistic 2025 projections based on historical trends, Vegas odds, and divisional strength
    """
    team_data = historical_data[team_abbr]
    
    # Get historical performance
    recent_wins = [team_data["2022"]["wins"], team_data["2023"]["wins"], team_data["2024"]["wins"]]
    recent_points = [team_data["2022"]["points"], team_data["2023"]["points"], team_data["2024"]["points"]]
    vegas_wins = team_data["vegas_2025_wins"]
    
    # Calculate trend-adjusted projections
    # Weight: 20% 2022, 30% 2023, 40% 2024, 10% vegas regression
    historical_win_trend = (0.2 * recent_wins[0] + 0.3 * recent_wins[1] + 0.4 * recent_wins[2])
    projected_wins = round((0.9 * historical_win_trend + 0.1 * vegas_wins) * 10) / 10
    
    # Ensure realistic bounds (NFL teams rarely go from 3 wins to 13+ wins in one year)
    max_improvement = recent_wins[-1] + 4  # Max 4-win improvement year-over-year
    max_decline = max(recent_wins[-1] - 3, 2)  # Max 3-win decline, minimum 2 wins
    projected_wins = min(max(projected_wins, max_decline), min(max_improvement, 16))
    
    # Calculate projected points based on wins correlation
    # Strong correlation: more wins = more points scored
    historical_point_trend = (0.2 * recent_points[0] + 0.3 * recent_points[1] + 0.4 * recent_points[2])
    win_point_correlation = 25  # ~25 points per additional win on average
    projected_points = int(historical_point_trend + (projected_wins - historical_win_trend) * win_point_correlation)
    
    # Ensure realistic point bounds (200-550 range)
    projected_points = min(max(projected_points, 200), 550)
    
    return {
        "projected_wins": projected_wins,
        "projected_points": projected_points,
        "historical_wins": recent_wins,
        "historical_points": recent_points,
        "vegas_baseline": vegas_wins
    }

def distribute_team_fantasy_points(team_projections, players_on_team):
    """
    Distribute fantasy points with proper position hierarchy and team performance correlation
    """
    projected_points = team_projections["projected_points"]
    projected_wins = team_projections["projected_wins"]
    
    # Calculate total fantasy points available for the team
    # Higher-scoring teams have more fantasy points to distribute
    base_team_fantasy_pool = projected_points * 2.5  # Adjusted conversion factor
    
    # Position-based players
    qb_players = [p for p in players_on_team if p["position"] == "QB"]
    rb_players = [p for p in players_on_team if p["position"] == "RB"]
    wr_players = [p for p in players_on_team if p["position"] == "WR"]
    te_players = [p for p in players_on_team if p["position"] == "TE"]
    k_players = [p for p in players_on_team if p["position"] == "K"]
    dst_players = [p for p in players_on_team if p["position"] == "DST"]
    
    fantasy_distributions = {}
    starting_qb_points = 300  # Default value, will be updated if QB exists
    
    # ====== QB SPECIAL HANDLING (Highest scorers) ======
    if qb_players:
        # Sort QBs by ADP (lower ADP = starting QB)
        qb_players_sorted = sorted(qb_players, key=lambda x: x["adp"])
        starting_qb = qb_players_sorted[0]
        backup_qbs = qb_players_sorted[1:]
        
        # QB points strongly correlated with team success
        if projected_wins >= 12:  # Elite teams
            qb_base_points = 400 + (projected_points - 400) * 0.8  # Scale with team scoring
        elif projected_wins >= 10:  # Good teams
            qb_base_points = 340 + (projected_points - 350) * 0.7
        elif projected_wins >= 8:  # Average teams  
            qb_base_points = 290 + (projected_points - 300) * 0.6
        elif projected_wins >= 6:  # Below average
            qb_base_points = 240 + (projected_points - 275) * 0.5
        elif projected_wins >= 4:  # Bad teams
            qb_base_points = 200 + (projected_points - 250) * 0.4
        else:  # Terrible teams
            qb_base_points = 160 + (projected_points - 200) * 0.3
            
        # Ensure realistic QB bounds
        starting_qb_points = max(160, min(450, qb_base_points))
        fantasy_distributions[starting_qb["name"]] = starting_qb_points
        
        # Backup QBs get minimal points
        for backup_qb in backup_qbs:
            fantasy_distributions[backup_qb["name"]] = min(50, starting_qb_points * 0.1)
    
    # ====== RB/WR DISTRIBUTION (Below QB level) ======
    # Total points for skill positions (should be less than QB)
    skill_position_pool = base_team_fantasy_pool * 0.65  # 65% for RB+WR combined
    rb_pool = skill_position_pool * 0.45  # RBs get 45% of skill pool
    wr_pool = skill_position_pool * 0.55  # WRs get 55% of skill pool
    
    # Distribute RBs (max points should be ~70-85% of QB points)
    if rb_players:
        rb_players_sorted = sorted(rb_players, key=lambda x: x["adp"])
        max_rb_points = starting_qb_points * 0.85 if qb_players else 300  # Cap RB points
        
        total_weight = sum(1/max(i+1, 1)**0.8 for i in range(len(rb_players_sorted)))
        for i, player in enumerate(rb_players_sorted):
            weight = 1/max(i+1, 1)**0.8
            player_points = min(max_rb_points, (weight / total_weight) * rb_pool)
            fantasy_distributions[player["name"]] = player_points
    
    # Distribute WRs (max points should be ~75-80% of QB points)  
    if wr_players:
        wr_players_sorted = sorted(wr_players, key=lambda x: x["adp"])
        max_wr_points = starting_qb_points * 0.80 if qb_players else 280  # Cap WR points
        
        total_weight = sum(1/max(i+1, 1)**0.7 for i in range(len(wr_players_sorted)))
        for i, player in enumerate(wr_players_sorted):
            weight = 1/max(i+1, 1)**0.7
            player_points = min(max_wr_points, (weight / total_weight) * wr_pool)
            fantasy_distributions[player["name"]] = player_points
    
    # ====== TE/K/DST (Lower tier positions) ======
    te_pool = base_team_fantasy_pool * 0.12  # TEs get 12%
    k_pool = base_team_fantasy_pool * 0.02   # Kickers get 2%
    dst_pool = base_team_fantasy_pool * 0.01 # Defense gets 1%
    
    for players, pool, max_multiplier in [(te_players, te_pool, 0.45), (k_players, k_pool, 0.30), (dst_players, dst_pool, 0.25)]:
        if not players:
            continue
            
        players_sorted = sorted(players, key=lambda x: x["adp"])
        max_position_points = starting_qb_points * max_multiplier if qb_players else pool
        
        if len(players) == 1:
            fantasy_distributions[players[0]["name"]] = min(max_position_points, pool)
        else:
            total_weight = sum(1/max(i+1, 1)**0.6 for i in range(len(players)))
            for i, player in enumerate(players_sorted):
                weight = 1/max(i+1, 1)**0.6
                player_points = min(max_position_points, (weight / total_weight) * pool)
                fantasy_distributions[player["name"]] = player_points
    
    return fantasy_distributions

# Team abbreviation to full name mapping
TEAM_MAPPING = {
    "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills", "CAR": "Carolina Panthers",
    "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers", "HOU": "Houston Texans",
    "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs", "LV": "Las Vegas Raiders",
    "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams", "MIA": "Miami Dolphins", "MIN": "Minnesota Vikings",
    "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants", "NYJ": "New York Jets",
    "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SF": "San Francisco 49ers", "SEA": "Seattle Seahawks",
    "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders", "ARI": "Arizona Cardinals"
}

def create_all_teams(db: Session):
    """Create all 32 NFL teams"""
    print("🏈 Creating all 32 NFL teams...")
    
    # Clear existing teams
    db.query(Team).delete()
    db.commit()
    
    teams_created = []
    for team_data in NFL_TEAMS:
        team = Team(
            name=team_data["name"],
            abbreviation=team_data["abbreviation"],
            city=team_data["city"],
            conference=team_data["conference"],
            division=team_data["division"]
        )
        db.add(team)
        teams_created.append(team)
    
    db.commit()
    print(f"✅ Created {len(teams_created)} teams")
    return teams_created

def create_players_from_fantasy_data(db: Session, teams, fantasy_data_string: str):
    """
    Create players and their fantasy data from a provided string,
    with realistic projections based on team performance trends.
    """
    print("👥 Creating players with REALISTIC fantasy projections based on team trends...")

    # Clear existing players and fantasy data
    db.query(Player).delete()
    db.query(FantasyData).filter(FantasyData.season_year == 2025).delete()
    db.commit()

    players_created = []
    fantasy_data_created = []
    team_map = {team.abbreviation: team for team in teams}
    
    # Group players by team for realistic point distribution
    team_players = {}
    
    lines = fantasy_data_string.strip().split('\n')
    for line in lines:
        parts = line.split('\t')
        if len(parts) < 4:
            continue

        adp_overall_str = parts[0]
        player_info = parts[1]
        position = parts[2]
        adp_value_str = parts[3]

        # Extract player name and team abbreviation
        import re
        match = re.match(r"(.+?)\s+([A-Z]{2,3})\s*\((\d+)\)", player_info)
        if not match:
            print(f"  ⚠️  Could not parse player info: {player_info}, skipping...")
            continue

        player_name = match.group(1).strip()
        team_abbr = match.group(2).strip()
        
        # Normalize team abbreviations
        team_abbreviation_map = {"JAC": "JAX"}  # Handle common variations
        team_abbr = team_abbreviation_map.get(team_abbr, team_abbr)

        team = team_map.get(team_abbr)
        if not team:
            print(f"  ⚠️  Unknown team abbreviation: {team_abbr} for {player_name}, skipping...")
            continue

        # Group players by team
        if team_abbr not in team_players:
            team_players[team_abbr] = []
        
        # Extract position number for ADP position ranking
        position_match = re.search(r'(\D+)(\d+)', position)
        position_name = position_match.group(1) if position_match else position
        position_rank = float(position_match.group(2)) if position_match else float(adp_value_str)
        
        team_players[team_abbr].append({
            "name": player_name,
            "team": team_abbr,
            "position": position_name,
            "adp": float(adp_value_str),
            "position_rank": position_rank
        })

    # Calculate realistic projections for each team
    print("📊 Calculating realistic team projections based on historical trends...")
    team_projections = {}
    
    # Step 1: Calculate initial projections without divisional impact
    for team_abbr in team_players.keys():
        if team_abbr in TEAM_HISTORICAL_DATA:
            team_projections[team_abbr] = calculate_realistic_team_projections(team_abbr, TEAM_HISTORICAL_DATA)
    
    # Step 2: Apply divisional strength adjustments (teams play division rivals twice)
    print("🏈 Applying divisional strength adjustments...")
    for team_abbr in team_projections.keys():
        divisional_impact = calculate_divisional_strength_impact(team_abbr, team_projections)
        
        # Adjust win total based on divisional strength
        original_wins = team_projections[team_abbr]["projected_wins"]
        adjusted_wins = max(2, min(16, original_wins + divisional_impact))
        team_projections[team_abbr]["projected_wins"] = round(adjusted_wins * 10) / 10
        
        # Adjust points based on adjusted wins
        win_difference = adjusted_wins - original_wins
        points_adjustment = win_difference * 20  # ~20 points per win difference
        original_points = team_projections[team_abbr]["projected_points"]
        adjusted_points = max(200, min(550, original_points + points_adjustment))
        team_projections[team_abbr]["projected_points"] = int(adjusted_points)
        
        division, division_teams = get_team_division(team_abbr)
        division_name = division.replace("_", " ") if division else "Unknown"
        
        print(f"   {team_abbr} ({division_name}): {team_projections[team_abbr]['projected_wins']} wins, {team_projections[team_abbr]['projected_points']} points (Divisional impact: {divisional_impact:+.1f} wins)")
        
    # Remove the old printing loop since we're doing it above

    # Distribute fantasy points realistically within each team
    print("🎯 Distributing fantasy points based on team performance and player roles...")
    for team_abbr, players in team_players.items():
        if team_abbr not in team_projections:
            continue
            
        fantasy_point_distributions = distribute_team_fantasy_points(team_projections[team_abbr], players)
        
        # Create players and their fantasy data
        for player_data in players:
            # Create Player
            player = Player(
                name=player_data["name"],
                position=player_data["position"],
                team_id=team_map[team_abbr].id,
                jersey_number=random.randint(1, 99),
                height=f"{random.randint(5, 6)}'{random.randint(8, 11)}\"",
                weight=random.randint(180, 280),
                age=random.randint(22, 35),
                experience=random.randint(0, 15),
                is_active=True
            )
            db.add(player)
            players_created.append(player)
            db.flush()  # Flush to get player.id

            # Get realistic fantasy points for this player
            projected_points_ppr = fantasy_point_distributions.get(player_data["name"], 50)  # Default 50 if not found
            projected_points_standard = round(projected_points_ppr * 0.85, 1)

            # Create FantasyData with realistic projections
            fantasy_data = FantasyData(
                player_id=player.id,
                season_year=2025,
                projected_points_ppr=round(projected_points_ppr, 1),
                projected_points_standard=projected_points_standard,
                adp_overall=player_data["adp"],
                adp_position=player_data["position_rank"],
                draft_percentage=round(random.uniform(0.3, 0.95), 3),
                last_updated=datetime.now()
            )
            db.add(fantasy_data)
            fantasy_data_created.append(fantasy_data)

    db.commit()
    print(f"✅ Created {len(players_created)} players with REALISTIC fantasy projections")
    print("✅ Projections based on: Historical trends + Vegas odds + Team performance correlation")
    return players_created

def setup_seasons(db: Session):
    """Ensure proper season data exists"""
    print("📅 Setting up season data...")
    
    # Check if 2025 season exists
    season_2025 = db.query(Season).filter(Season.year == 2025).first()
    if not season_2025:
        season_2025 = Season(
            year=2025,
            is_current=True,
            start_date=datetime(2025, 9, 1),
            end_date=datetime(2026, 2, 15)
        )
        db.add(season_2025)
    
    # Make sure 2025 is the current season
    db.query(Season).filter(Season.year != 2025).update({"is_current": False})
    season_2025.is_current = True
    
    db.commit()
    print("✅ Season data configured")

def main():
    print("🏈 NFL Complete Data Population Script (2025 Pro Football Reference Data)")
    print("=" * 60)

    try:
        # Create database tables
        Base.metadata.create_all(bind=engine)

        # Create database session
        db = SessionLocal()

        # Setup seasons first
        setup_seasons(db)

        # Create all teams
        teams = create_all_teams(db)

        # User-provided fantasy data string (raw format as provided)
        fantasy_data_string = """1	Ja'Marr Chase CIN (10)	WR1	1.0
2	Bijan Robinson ATL (5)	RB1	2.0
3	Jahmyr Gibbs DET (8)	RB2	3.0
4	Saquon Barkley PHI (9)	RB3	4.0
5	CeeDee Lamb DAL (10)	WR2	5.0
6	Justin Jefferson MIN (6)	WR3	6.0
7	Christian McCaffrey SF (14)	RB4	7.0
8	Ashton Jeanty LV (8)	RB5	8.0
9	Malik Nabers NYG (14)	WR4	9.0
10	Puka Nacua LAR (8)	WR5	10.0
11	Amon-Ra St. Brown DET (8)	WR6	11.0
12	Derrick Henry BAL (7)	RB6	12.0
13	De'Von Achane MIA (12)	RB7	13.0
14	Brian Thomas Jr. JAX (8)	WR7	14.0
15	Nico Collins HOU (6)	WR8	15.0
16	Josh Jacobs GB (5)	RB8	16.0
17	Bucky Irving TB (9)	RB9	17.0
18	Brock Bowers LV (8)	TE1	18.0
19	Lamar Jackson BAL (7)	QB1	19.0
20	Drake London ATL (5)	WR9	20.0
21	Chase Brown CIN (10)	RB10	21.0
22	Jonathan Taylor IND (11)	RB11	22.0
23	Josh Allen BUF (7)	QB2	23.0
24	Kyren Williams LAR (8)	RB12	24.0
25	A.J. Brown PHI (9)	WR10	25.0
26	Breece Hall NYJ (9)	RB13	26.0
27	Tyreek Hill MIA (12)	WR11	27.0
28	Jayden Daniels WAS (12)	QB3	28.0
29	Trey McBride ARI (8)	TE2	29.0
30	Ladd McConkey LAC (12)	WR12	30.0
31	Joe Burrow CIN (10)	QB4	31.0
32	James Cook BUF (7)	RB14	32.0
33	Alvin Kamara NO (11)	RB15	33.0
34	Jaxon Smith-Njigba SEA (8)	WR13	34.0
35	Garrett Wilson NYJ (9)	WR14	35.0
36	Davante Adams LAR (8)	WR15	36.0
37	Tee Higgins CIN (10)	WR16	37.0
38	Jalen Hurts PHI (9)	QB5	38.0
39	Marvin Harrison Jr. ARI (8)	WR17	39.0
40	George Kittle SF (14)	TE3	40.0
41	Terry McLaurin WAS (12)	WR18	41.0
42	Kenneth Walker III SEA (8)	RB16	42.0
43	Omarion Hampton LAC (12)	RB17	43.0
44	Chuba Hubbard CAR (14)	RB18	44.0
45	Rashee Rice KC (10)	WR19	45.0
46	D'Andre Swift CHI (5)	RB19	46.0
47	DJ Moore CHI (5)	WR20	47.0
48	Mike Evans TB (9)	WR21	48.0
49	Joe Mixon HOU (6)	RB20	49.0
50	RJ Harvey DEN (12)	RB21	50.0
51	Courtland Sutton DEN (12)	WR22	51.0
52	James Conner ARI (8)	RB22	52.0
53	TreVeyon Henderson NE (14)	RB23	53.0
54	Patrick Mahomes II KC (10)	QB6	54.0
55	DK Metcalf PIT (5)	WR23	55.0
56	DeVonta Smith PHI (9)	WR24	56.0
57	Tetairoa McMillan CAR (14)	WR25	57.0
58	Sam LaPorta DET (8)	TE4	58.0
59	Aaron Jones Sr. MIN (6)	RB24	59.0
60	David Montgomery DET (8)	RB25	60.0
61	Kaleb Johnson PIT (5)	RB26	61.0
62	Travis Kelce KC (10)	TE5	62.0
63	Baker Mayfield TB (9)	QB7	63.0
64	Jameson Williams DET (8)	WR26	64.0
65	Zay Flowers BAL (7)	WR27	65.0
66	Isiah Pacheco KC (10)	RB27	66.0
67	Tony Pollard TEN (10)	RB28	67.0
68	Chris Godwin TB (9)	WR28	68.0
69	Jerry Jeudy CLE (9)	WR29	69.0
70	Quinshon Judkins CLE (9)	RB29	70.0
71	Calvin Ridley TEN (10)	WR30	71.0
72	Travis Hunter JAX (8)	WR31	72.0
73	Xavier Worthy KC (10)	WR32	73.0
74	Tyrone Tracy Jr. NYG (14)	RB30	74.0
75	Bo Nix DEN (12)	QB8	75.0
76	George Pickens DAL (10)	WR33	76.0
77	Chris Olave NO (11)	WR34	77.0
78	T.J. Hockenson MIN (6)	TE6	78.0
79	Jaylen Waddle MIA (12)	WR35	79.0
80	Deebo Samuel Sr. WAS (12)	WR36	80.0
81	Brian Robinson Jr. WAS (12)	RB31	81.0
82	Jordan Addison MIN (6)	WR37	82.0
83	Jaylen Warren PIT (5)	RB32	83.0
84	Cooper Kupp SEA (8)	WR38	84.0
85	Caleb Williams CHI (5)	QB9	85.0
86	Kyler Murray ARI (8)	QB10	86.0
87	Jauan Jennings SF (14)	WR39	87.0
88	Evan Engram DEN (12)	TE7	88.0
89	Rome Odunze CHI (5)	WR40	89.0
90	Travis Etienne Jr. JAX (8)	RB33	90.0
91	Cam Skattebo NYG (14)	RB34	91.0
92	Javonte Williams DAL (10)	RB35	92.0
93	Dak Prescott DAL (10)	QB11	93.0
94	Mark Andrews BAL (7)	TE8	94.0
95	Jared Goff DET (8)	QB12	95.0
96	Najee Harris LAC (12)	RB36	96.0
97	Stefon Diggs NE (14)	WR41	97.0
98	Matthew Golden GB (5)	WR42	98.0
99	Zach Charbonnet SEA (8)	RB37	99.0
100	Khalil Shakir BUF (7)	WR43	100.0
101	Justin Fields NYJ (9)	QB13	101.0
102	Jordan Mason MIN (6)	RB38	102.0
103	Jayden Reed GB (5)	WR44	103.0
104	Ricky Pearsall SF (14)	WR45	104.0
105	Brock Purdy SF (14)	QB14	105.0
106	Tyjae Spears TEN (10)	RB39	106.0
107	David Njoku CLE (9)	TE9	107.0
108	Colston Loveland CHI (5)	TE10	108.0
109	Jakobi Meyers LV (8)	WR46	109.0
110	J.K. Dobbins DEN (12)	RB40	110.0
111	Justin Herbert LAC (12)	QB15	111.0
112	Rhamondre Stevenson NE (14)	RB41	112.0
113	Tucker Kraft GB (5)	TE11	113.0
114	Michael Pittman Jr. IND (11)	WR47	114.0
115	Tyler Warren IND (11)	TE12	115.0
116	Jaydon Blue DAL (10)	RB42	116.0
117	Brandon Aiyuk SF (14)	WR48	117.0
118	Josh Downs IND (11)	WR49	118.0
119	Rachaad White TB (9)	RB43	119.0
120	Darnell Mooney ATL (5)	WR50	120.0
121	Jonnu Smith PIT (5)	TE13	121.0
122	J.J. McCarthy MIN (6)	QB16	122.0
123	Drake Maye NE (14)	QB17	123.0
124	Isaac Guerendo SF (14)	RB44	124.0
125	Austin Ekeler WAS (12)	RB45	125.0
126	Jake Ferguson DAL (10)	TE14	126.0
127	Emeka Egbuka TB (9)	WR51	127.0
128	Tank Bigsby JAX (8)	RB46	128.0
129	Bhayshul Tuten JAX (8)	RB47	129.0
130	C.J. Stroud HOU (6)	QB18	130.0
131	Jordan Love GB (5)	QB19	131.0
132	Dalton Kincaid BUF (7)	TE15	132.0
133	Jayden Higgins HOU (6)	WR52	133.0
134	Jerome Ford CLE (9)	RB48	134.0
135	Ray Davis BUF (7)	RB49	135.0
136	Trey Benson ARI (8)	RB50	136.0
137	Trevor Lawrence JAX (8)	QB20	137.0
138	Keon Coleman BUF (7)	WR53	138.0
139	Tua Tagovailoa MIA (12)	QB21	139.0
140	Marvin Mims Jr. DEN (12)	WR54	140.0
141	Nick Chubb HOU (6)	RB51	141.0
142	Tre Harris LAC (12)	WR55	142.0
143	Kyle Pitts ATL (5)	TE16	143.0
144	Braelon Allen NYJ (9)	RB52	144.0
145	Jack Bech LV (8)	WR56	145.0
146	Tyler Allgeier ATL (5)	RB53	146.0
147	Rico Dowdle CAR (14)	RB54	147.0
148	Dallas Goedert PHI (9)	TE17	148.0
149	Marquise Brown KC (10)	WR57	149.0
150	Jaylen Wright MIA (12)	RB55	150.0
151	Hunter Henry NE (14)	TE18	151.0
152	Michael Penix Jr. ATL (5)	QB22	152.0
153	Isaiah Likely BAL (7)	TE19	153.0
154	Bryce Young CAR (14)	QB23	154.0
155	Matthew Stafford LAR (8)	QB24	155.0
156	Luther Burden III CHI (5)	WR58	156.0
157	DeAndre Hopkins BAL (7)	WR59	157.0
158	Christian Kirk HOU (6)	WR60	158.0
159	Rashid Shaheed NO (11)	WR61	159.0
160	Zach Ertz WAS (12)	TE20	160.0
161	Brenton Strange JAX (8)	TE21	161.0
162	Geno Smith LV (8)	QB25	162.0
163	Cedric Tillman CLE (9)	WR62	163.0
164	Cameron Ward TEN (10)	QB26	164.0
165	Sam Darnold SEA (8)	QB27	165.0
166	Justice Hill BAL (7)	RB56	166.0
167	Cade Otton TB (9)	TE22	167.0
168	Brandon Aubrey DAL (10)	K1	168.0
169	Aaron Rodgers PIT (5)	QB28	169.0
170	Xavier Legette CAR (14)	WR63	170.0
171	Kareem Hunt KC (10)	RB57	171.0
172	Dylan Sampson CLE (9)	RB58	172.0
173	Denver Broncos DEN (12)	DST1	173.0
174	Mason Taylor NYJ (9)	TE23	174.0
175	Kyle Monangai CHI (5)	RB59	175.0
176	Wan'Dale Robinson NYG (14)	WR64	176.0
177	Rashod Bateman BAL (7)	WR65	177.0
178	Adam Thielen CAR (14)	WR66	178.0
179	Chig Okonkwo TEN (10)	TE24	179.0
180	MarShawn Lloyd GB (5)	RB60	180.0
181	Anthony Richardson Sr. IND (11)	QB29	181.0
182	Roschon Johnson CHI (5)	RB61	182.0
183	Kyle Williams NE (14)	WR67	183.0
184	Russell Wilson NYG (14)	QB30	184.0
185	Mike Gesicki CIN (10)	TE25	185.0
186	Jarquez Hunter LAR (8)	RB62	186.0
187	Philadelphia Eagles PHI (9)	DST2	187.0
188	Cameron Dicker LAC (12)	K2	188.0
189	Buffalo Bills BUF (7)	DST3	189.0
190	Romeo Doubs GB (5)	WR68	190.0
191	Keenan Allen CHI (5)	WR69	191.0
192	Darren Waller MIA (12)	TE26	192.0
193	Jalen McMillan TB (9)	WR70	193.0
194	Houston Texans HOU (6)	DST4	194.0
195	Dalton Schultz HOU (6)	TE27	195.0
196	Pat Freiermuth PIT (5)	TE28	196.0
197	Jake Bates DET (8)	K3	197.0
198	Daniel Jones IND (11)	QB31	198.0
199	Pittsburgh Steelers PIT (5)	DST5	199.0
200	Tyler Shough NO (11)	QB32	200.0
201	Will Shipley PHI (9)	RB63	201.0
202	Alec Pierce IND (11)	WR71	202.0
203	Baltimore Ravens BAL (7)	DST6	203.0
204	Joe Flacco CLE (9)	QB33	204.0
205	Quentin Johnston LAC (12)	WR72	205.0
206	Miles Sanders DAL (10)	RB64	206.0
207	Brashard Smith KC (10)	RB65	207.0
208	Ka'imi Fairbairn HOU (6)	K4	208.0
209	DJ Giddens IND (11)	RB66	209.0
210	Elijah Mitchell KC (10)	RB67	210.0
211	Minnesota Vikings MIN (6)	DST7	211.0
212	DeMario Douglas NE (14)	WR73	212.0
213	Wil Lutz DEN (12)	K5	213.0
214	Chase McLaughlin TB (9)	K6	214.0
215	Joshua Palmer BUF (7)	WR74	215.0
216	Blake Corum LAR (8)	RB68	216.0
217	Zack Moss CIN (10)	RB69	217.0
218	Juwan Johnson NO (11)	TE29	218.0
219	Jaxson Dart NYG (14)	QB34	219.0
220	Tyler Conklin LAC (12)	TE30	220.0
221	Devin Neal NO (11)	RB70	221.0
222	New York Giants NYG (14)	DST8	222.0
223	Raheem Mostert LV (8)	RB71	223.0
224	Harrison Butker KC (10)	K7	224.0
225	Kirk Cousins ATL (5)	QB35	225.0
226	Kansas City Chiefs KC (10)	DST9	226.0
227	Darius Slayton NYG (14)	WR75	227.0
228	Dallas Cowboys DAL (10)	DST10	228.0
229	Jason Sanders MIA (12)	K8	229.0
230	Dyami Brown JAX (8)	WR76	230.0
231	Chris Boswell PIT (5)	K9	231.0
232	Tyler Higbee LAR (8)	TE31	232.0
233	Jaylin Noel HOU (6)	WR77	233.0
234	Antonio Gibson NE (14)	RB72	234.0
235	Ray-Ray McCloud III ATL (5)	WR78	235.0
236	Brandon McManus GB (5)	K10	236.0
237	Jaleel McLaughlin DEN (12)	RB73	237.0
238	A.J. Dillon PHI (9)	RB74	238.0
239	Tahj Brooks CIN (10)	RB75	239.0
240	Shedeur Sanders CLE (9)	QB36	240.0
241	Keaton Mitchell BAL (7)	RB76	241.0
242	Los Angeles Rams LAR (8)	DST11	242.0
243	Dont'e Thornton Jr. LV (8)	WR79	243.0
244	Jalen Milroe SEA (8)	QB37	244.0
245	Jake Elliott PHI (9)	K11	245.0
246	Theo Johnson NYG (14)	TE32	246.0
247	Tampa Bay Buccaneers TB (9)	DST12	247.0
248	Calvin Austin III PIT (5)	WR80	248.0
249	Detroit Lions DET (8)	DST13	249.0
250	Elijah Arroyo SEA (8)	TE33	250.0
251	Ollie Gordon II MIA (12)	RB77	251.0
252	San Francisco 49ers SF (14)	DST14	252.0
253	Pat Bryant DEN (12)	WR81	253.0
254	Noah Gray KC (10)	TE34	254.0
255	Matt Gay WAS (12)	K12	255.0
256	Green Bay Packers GB (5)	DST15	256.0
257	Tyler Bass BUF (7)	K13	257.0
258	Trevor Etienne CAR (14)	RB78	258.0
259	Kenny Pickett CLE (9)	QB38	259.0
260	New England Patriots NE (14)	DST16	260.0
261	Ja'Tavion Sanders CAR (14)	TE35	261.0
262	Jacory Croskey-Merritt WAS (12)	RB79	262.0
263	Taysom Hill NO (11)	TE36	263.0
264	Michael Wilson ARI (8)	WR82	264.0
265	Evan McPherson CIN (10)	K14	265.0
266	Will Reichard MIN (6)	K15	266.0
267	Jalen Nailor MIN (6)	WR83	267.0
268	Diontae Johnson CLE (9)	WR84	268.0
269	Joshua Karty LAR (8)	K16	269.0
270	Tyler Loop BAL (7)	K17	270.0
271	Arizona Cardinals ARI (8)	DST17	271.0
272	Andrei Iosivas CIN (10)	WR85	272.0
273	Alexander Mattison MIA (12)	RB80	273.0
274	Daniel Carlson LV (8)	K18	274.0
275	Cole Kmet CHI (5)	TE37	275.0
276	Younghoe Koo ATL (5)	K19	276.0
277	Jake Moody SF (14)	K20	277.0
278	Sean Tucker TB (9)	RB81	278.0
279	Jameis Winston NYG (14)	QB39	279.0
280	Tre Tucker LV (8)	WR86	280.0
281	Chicago Bears CHI (5)	DST18	281.0
282	Cleveland Browns CLE (9)	DST19	282.0
283	Noah Fant SEA (8)	TE38	283.0
284	Roman Wilson PIT (5)	WR87	284.0
285	Terrance Ferguson LAR (8)	TE39	285.0
286	Kenneth Gainwell PIT (5)	RB82	286.0
287	Emanuel Wilson GB (5)	RB83	287.0
288	Amari Cooper BUF (7)	WR88	288.0
289	Woody Marks HOU (6)	RB84	289.0
290	Jalen Royals KC (10)	WR89	290.0
291	Los Angeles Chargers LAC (12)	DST20	291.0
292	Brandin Cooks NO (11)	WR90	292.0
293	Audric Estime DEN (12)	RB85	293.0
294	New York Jets NYJ (9)	DST21	294.0
295	Devin Singletary NYG (14)	RB86	295.0
296	Dontayvion Wicks GB (5)	WR91	296.0
297	Seattle Seahawks SEA (8)	DST22	297.0
298	Kendre Miller NO (11)	RB87	298.0
299	Jalen Tolbert DAL (10)	WR92	299.0
300	Samaje Perine CIN (10)	RB88	300.0
301	Jordan James SF (14)	RB89	301.0
302	Oronde Gadsden II LAC (12)	TE40	302.0
303	Adonai Mitchell IND (11)	WR93	303.0
304	Joe Milton III DAL (10)	QB40	304.0
305	Harold Fannin Jr. CLE (9)	TE41	305.0
306	Elic Ayomanor TEN (10)	WR94	306.0
307	Cincinnati Bengals CIN (10)	DST23	307.0
308	Jermaine Burton CIN (10)	WR95	308.0
309	Tutu Atwell LAR (8)	WR96	309.0
310	Tyler Lockett TEN (10)	WR97	310.0
311	Washington Commanders WAS (12)	DST24	311.0
312	Kayshon Boutte NE (14)	WR98	312.0
313	Mason Rudolph PIT (5)	QB41	313.0
314	Isaac TeSlaa DET (8)	WR99	314.0
315	Spencer Rattler NO (11)	QB42	315.0
316	Jalen Coker CAR (14)	WR100	316.0
317	Elijah Moore BUF (7)	WR101	317.0
318	Troy Franklin DEN (12)	WR102	318.0
319	Khalil Herbert IND (11)	RB90	319.0
320	Aidan O'Connell LV (8)	QB43	320.0
321	Dameon Pierce HOU (6)	RB91	321.0
322	Devaughn Vele DEN (12)	WR103	322.0
323	Isaiah Davis NYJ (9)	RB92	323.0
324	Ty Johnson BUF (7)	RB93	324.0
325	Savion Williams GB (5)	WR104	325.0
326	Phil Mafah DAL (10)	RB94	326.0"""

        # Create players from real fantasy data with realistic projections
        players = create_players_from_fantasy_data(db, teams, fantasy_data_string)

        # Fantasy projections are now created within create_players_from_fantasy_data
        # create_fantasy_projections(db, players)  # No longer needed

        db.close()

        print("\n" + "=" * 60)
        print("✅ COMPLETE! 2025 Pro Football Reference data population with REALISTIC projections!")
        print(f"📊 Summary:")
        print(f"   • {len(NFL_TEAMS)} NFL teams created")
        print(f"   • {len(players)} fantasy-relevant players with REAL team assignments")
        print(f"   • REALISTIC projections based on historical trends + Vegas odds")
        print(f"   • Team performance correlation applied to fantasy points")

        print(f"\n🎯 Key projection improvements:")
        print(f"   • Historical team performance trends (2022-2024)")
        print(f"   • Vegas win totals as baselines")
        print(f"   • Realistic year-over-year change limits")
        print(f"   • Team scoring correlation to fantasy points")
        print(f"   • Position-based point distribution within teams")

    except Exception as e:
        print(f"\n❌ Error during data population: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 