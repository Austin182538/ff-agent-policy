#!/usr/bin/env python3
"""
Backfill historical NFL / fantasy data from nflverse (via nflreadpy) into
historical_player_stats, historical_team_stats, season_final_records,
fantasy_consensus_rankings, and fantasy_opportunity.

Requires Python >= 3.10 (nflreadpy). Run with the dedicated data venv:
    venv_data\\Scripts\\python.exe scripts\\ingest_historical_data.py

Safe to re-run: for each table, existing rows for the requested seasons are
deleted and replaced (a "replace this season's data" strategy), rather than
upserting row-by-row.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.historical_models import (
    HistoricalPlayerStats, HistoricalTeamStats, SeasonFinalRecord,
    FantasyConsensusRanking, FantasyOpportunity,
)
import app.models.market_models  # noqa: F401
import app.models.news_models  # noqa: F401

from app.integrations import nflverse_client as nv

# Completed regular seasons to backfill stats for.
STATS_SEASONS = list(range(2018, 2026))
# ECR/ADP-equivalent rankings are only available from nflverse starting Oct 2020,
# so the earliest full preseason (Aug/Sep) snapshot is 2021. 2026 is included as
# the *current* preseason snapshot for this year's ranking model (not a backtest).
ECR_SEASONS = list(range(2021, 2027))


def replace_rows(db, model, season_years, df, column_map=None):
    """Delete existing rows for the given seasons, then bulk-insert df's rows."""
    if df is None or df.empty:
        print(f"  (no rows to load for {model.__tablename__})")
        return 0

    db.query(model).filter(model.season_year.in_(season_years)).delete(synchronize_session=False)
    db.commit()

    records = df.where(df.notnull(), None).to_dict(orient="records")
    db.bulk_insert_mappings(model, records)
    db.commit()
    return len(records)


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        print(f"Loading player stats for seasons {STATS_SEASONS[0]}-{STATS_SEASONS[-1]}...")
        player_stats_df = nv.load_player_stats_normalized(STATS_SEASONS)
        n = replace_rows(db, HistoricalPlayerStats, STATS_SEASONS, player_stats_df)
        print(f"  -> {n} rows in historical_player_stats")

        print("Loading team game results + season totals from schedules...")
        team_stats_df = nv.load_team_game_results(STATS_SEASONS)
        n = replace_rows(db, HistoricalTeamStats, STATS_SEASONS, team_stats_df)
        print(f"  -> {n} rows in historical_team_stats")

        print("Computing final season records (for grading Vegas win totals)...")
        final_records_df = nv.load_season_final_records(STATS_SEASONS)
        n = replace_rows(db, SeasonFinalRecord, STATS_SEASONS, final_records_df)
        print(f"  -> {n} rows in season_final_records")

        print("Loading fantasy opportunity (expected vs actual production)...")
        opportunity_df = nv.load_fantasy_opportunity_normalized(STATS_SEASONS)
        n = replace_rows(db, FantasyOpportunity, STATS_SEASONS, opportunity_df)
        print(f"  -> {n} rows in fantasy_opportunity")

        print(f"Finding preseason ECR scrape dates for seasons {ECR_SEASONS}...")
        season_to_date = nv.find_preseason_scrape_dates(ECR_SEASONS)
        print(f"  -> {season_to_date}")
        rankings_df = nv.load_preseason_consensus_rankings(season_to_date)
        n = replace_rows(db, FantasyConsensusRanking, list(season_to_date.keys()), rankings_df)
        print(f"  -> {n} rows in fantasy_consensus_rankings")

        print("\nDone.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
