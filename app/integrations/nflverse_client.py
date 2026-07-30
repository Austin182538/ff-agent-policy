"""
Wrapper around nflreadpy (https://nflreadpy.nflverse.com) that normalizes
Polars output into plain pandas DataFrames with the column names our staging
tables (app/models/historical_models.py) expect.

Requires Python >= 3.10 -- run this (and scripts/ingest_historical_data.py)
with the venv_data interpreter, not the main app's venv. See requirements-data.txt.

Column names below were confirmed by directly inspecting nflreadpy 0.1.5
output (load_player_stats, load_team_stats, load_schedules, load_ff_rankings,
load_ff_opportunity) rather than assumed from docs.
"""

from datetime import date
from typing import Dict, List, Optional

import pandas as pd

import nflreadpy as nfl

REDRAFT_OVERALL_PAGE_TYPE = "redraft-overall"

# nflverse uses a few legacy/alternate team abbreviations; normalize to the
# ones used elsewhere in this app (data/vegas_win_totals.csv, team names).
TEAM_ABBR_FIXES = {"LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR", "JAC": "JAX"}


def _normalize_team_abbr(series: pd.Series) -> pd.Series:
    return series.replace(TEAM_ABBR_FIXES)


def load_player_stats_normalized(seasons: List[int], season_type: str = "REG") -> pd.DataFrame:
    """Weekly player stats -> our HistoricalPlayerStats shape. Also appends
    week=0 season-total rows (summed across weeks) per player/season.
    """
    df = nfl.load_player_stats(seasons).to_pandas()
    df = df[df["season_type"] == season_type].copy()

    weekly = pd.DataFrame({
        "nflverse_player_id": df["player_id"],
        "player_name": df["player_display_name"],
        "position": df["position"],
        "team_abbr": _normalize_team_abbr(df["team"]),
        "season_year": df["season"],
        "week": df["week"],
        "season_type": df["season_type"],
        "completions": df["completions"].fillna(0),
        "attempts": df["attempts"].fillna(0),
        "passing_yards": df["passing_yards"].fillna(0),
        "passing_tds": df["passing_tds"].fillna(0),
        "interceptions": df["passing_interceptions"].fillna(0),
        "carries": df["carries"].fillna(0),
        "rushing_yards": df["rushing_yards"].fillna(0),
        "rushing_tds": df["rushing_tds"].fillna(0),
        "targets": df["targets"].fillna(0),
        "receptions": df["receptions"].fillna(0),
        "receiving_yards": df["receiving_yards"].fillna(0),
        "receiving_tds": df["receiving_tds"].fillna(0),
        "fantasy_points_standard": df["fantasy_points"].fillna(0),
        "fantasy_points_ppr": df["fantasy_points_ppr"].fillna(0),
    })
    weekly["fantasy_points_half_ppr"] = (
        weekly["fantasy_points_standard"] + weekly["receptions"] * 0.5
    )
    weekly = weekly.dropna(subset=["nflverse_player_id", "player_name"])

    sum_cols = [
        "completions", "attempts", "passing_yards", "passing_tds", "interceptions",
        "carries", "rushing_yards", "rushing_tds", "targets", "receptions",
        "receiving_yards", "receiving_tds", "fantasy_points_standard",
        "fantasy_points_ppr", "fantasy_points_half_ppr",
    ]
    season_totals = weekly.groupby(["nflverse_player_id", "season_year"], as_index=False).agg({
        **{c: "sum" for c in sum_cols},
        "player_name": "last",
        "position": "last",
        "team_abbr": "last",
        "week": "nunique",
    })
    season_totals = season_totals.rename(columns={"week": "games_played"})
    season_totals["week"] = 0
    season_totals["season_type"] = season_type

    return pd.concat([weekly, season_totals], ignore_index=True)


def load_team_game_results(seasons: List[int], season_type: str = "REG") -> pd.DataFrame:
    """Per-team, per-game points/wins derived from load_schedules(), plus a
    week=0 season-total aggregate row per team. game_type filter uses
    nflverse's REG/POST/etc. convention.
    """
    sched = nfl.load_schedules(seasons).to_pandas()
    sched = sched[sched["game_type"] == season_type].copy()
    sched = sched.dropna(subset=["home_score", "away_score"])  # unplayed games
    sched["home_team"] = _normalize_team_abbr(sched["home_team"])
    sched["away_team"] = _normalize_team_abbr(sched["away_team"])

    rows = []
    for _, g in sched.iterrows():
        home_win = 1.0 if g["home_score"] > g["away_score"] else (0.5 if g["home_score"] == g["away_score"] else 0.0)
        away_win = 1.0 - home_win if home_win != 0.5 else 0.5
        rows.append({
            "team_abbr": g["home_team"], "season_year": g["season"], "week": g["week"],
            "season_type": season_type, "points_for": g["home_score"], "points_against": g["away_score"],
            "win": home_win,
        })
        rows.append({
            "team_abbr": g["away_team"], "season_year": g["season"], "week": g["week"],
            "season_type": season_type, "points_for": g["away_score"], "points_against": g["home_score"],
            "win": away_win,
        })
    games = pd.DataFrame(rows)
    if games.empty:
        return games

    # pull yardage/turnover context from load_team_stats and merge in as season totals only
    team_stats = nfl.load_team_stats(seasons).to_pandas()
    team_stats = team_stats[team_stats["season_type"] == season_type].copy()
    team_stats["team"] = _normalize_team_abbr(team_stats["team"])
    team_stats["turnovers"] = (
        team_stats["passing_interceptions"].fillna(0) + team_stats["fumbles_lost_total"].fillna(0)
    )
    team_stats["total_yards"] = team_stats["passing_yards"].fillna(0) + team_stats["rushing_yards"].fillna(0)
    season_yardage = team_stats.groupby(["team", "season"], as_index=False).agg(
        total_yards=("total_yards", "sum"),
        passing_yards=("passing_yards", "sum"),
        rushing_yards=("rushing_yards", "sum"),
        turnovers=("turnovers", "sum"),
    )

    season_totals = games.groupby(["team_abbr", "season_year"], as_index=False).agg(
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
        win=("win", "sum"),
    )
    season_totals["week"] = 0
    season_totals["season_type"] = season_type
    season_totals = season_totals.merge(
        season_yardage, left_on=["team_abbr", "season_year"], right_on=["team", "season"], how="left"
    ).drop(columns=["team", "season"])

    games["total_yards"] = None
    games["passing_yards"] = None
    games["rushing_yards"] = None
    games["turnovers"] = None

    return pd.concat([games, season_totals], ignore_index=True)


def load_season_final_records(seasons: List[int]) -> pd.DataFrame:
    """Final regular-season W-L-T per team, for grading Vegas preseason win totals."""
    team_games = load_team_game_results(seasons, season_type="REG")
    per_game = team_games[team_games["week"] > 0]
    records = per_game.groupby(["team_abbr", "season_year"], as_index=False).agg(
        wins=("win", lambda s: (s == 1.0).sum() + 0.5 * (s == 0.5).sum()),
        losses=("win", lambda s: (s == 0.0).sum()),
        ties=("win", lambda s: int((s == 0.5).sum())),
        points_for=("points_for", "sum"),
        points_against=("points_against", "sum"),
    )
    return records


def load_preseason_consensus_rankings(season_to_scrape_date: Dict[int, str]) -> pd.DataFrame:
    """Preseason overall PPR redraft ECR/consensus rank ("ADP-equivalent"),
    one row per player per season, using the scrape date closest to each
    season's kickoff (caller supplies season -> exact scrape_date, see
    scripts/ingest_historical_data.py for how those dates are picked).
    """
    all_rankings = nfl.load_ff_rankings(type="all").to_pandas()
    overall = all_rankings[all_rankings["page_type"] == REDRAFT_OVERALL_PAGE_TYPE].copy()

    frames = []
    for season, scrape_date in season_to_scrape_date.items():
        snapshot = overall[overall["scrape_date"] == scrape_date].copy()
        if snapshot.empty:
            continue
        snapshot["season_year"] = season
        frames.append(snapshot)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["season_year", "ecr"])
    combined["ecr_position_rank"] = combined.groupby(["season_year", "pos"])["ecr"].rank(method="first")

    return pd.DataFrame({
        "player_name": combined["player"],
        "position": combined["pos"],
        "team_abbr": _normalize_team_abbr(combined["team"]),
        "season_year": combined["season_year"],
        "ecr_overall_rank": combined["ecr"],
        "ecr_position_rank": combined["ecr_position_rank"],
        "adp_overall": combined["ecr"],  # FantasyPros ECR is the closest free proxy we have for ADP
        "rank_std_dev": combined["sd"],
        "as_of_date": pd.to_datetime(combined["scrape_date"]),
    })


def find_preseason_scrape_dates(seasons: List[int]) -> Dict[int, str]:
    """For each season, find the earliest available redraft-overall ECR
    scrape date in Aug or Sep of that year (closest thing we have to a true
    preseason ADP snapshot). Returns {season: 'YYYY-MM-DD'} for seasons where
    one was found.

    For the current/upcoming season (where Aug/Sep data doesn't exist yet
    because we're still in the offseason), falls back to the single most
    recent scrape available -- i.e. today's live consensus rank, used as the
    "current" ranking input rather than a historical backtest point.
    """
    all_rankings = nfl.load_ff_rankings(type="all").to_pandas()
    overall = all_rankings[all_rankings["page_type"] == REDRAFT_OVERALL_PAGE_TYPE]
    dates = sorted(pd.to_datetime(overall["scrape_date"].unique()))

    result = {}
    for season in seasons:
        window = [d for d in dates if date(season, 8, 1) <= d.date() <= date(season, 9, 15)]
        if window:
            result[season] = window[0].strftime("%Y-%m-%d")
        elif dates and dates[-1].date() < date(season, 8, 1):
            # No preseason snapshot exists yet for this season -- use the most
            # recent scrape available as a "current" stand-in.
            result[season] = dates[-1].strftime("%Y-%m-%d")
    return result


def load_fantasy_opportunity_normalized(seasons: List[int]) -> pd.DataFrame:
    """Expected-vs-actual fantasy production, week-level + a week=0 season total."""
    df = nfl.load_ff_opportunity(seasons=seasons, stat_type="weekly").to_pandas()

    weekly = pd.DataFrame({
        "nflverse_player_id": df["player_id"],
        "player_name": df["full_name"],
        "position": df["position"],
        "team_abbr": _normalize_team_abbr(df["posteam"]),
        "season_year": df["season"],
        "week": df["week"],
        "expected_fantasy_points": df["total_fantasy_points_exp"],
        "actual_fantasy_points": df["total_fantasy_points"],
        "delta_fantasy_points": df["total_fantasy_points_diff"],
    })
    weekly = weekly.dropna(subset=["nflverse_player_id", "player_name"])

    season_totals = weekly.groupby(["nflverse_player_id", "season_year"], as_index=False).agg(
        expected_fantasy_points=("expected_fantasy_points", "sum"),
        actual_fantasy_points=("actual_fantasy_points", "sum"),
        delta_fantasy_points=("delta_fantasy_points", "sum"),
        player_name=("player_name", "last"),
        position=("position", "last"),
        team_abbr=("team_abbr", "last"),
    )
    season_totals["week"] = 0

    return pd.concat([weekly, season_totals], ignore_index=True)
