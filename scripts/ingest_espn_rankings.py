#!/usr/bin/env python3
"""
Pulls ESPN's live default player rankings + ADP (PPR rank type -- the
closest analog ESPN has to this league's half-PPR scoring; see
app/integrations/espn_client.py for why) and stores them in
external_consensus_rankings for side-by-side comparison against our model
and FantasyPros ECR. Does NOT touch fantasy_consensus_rankings or any part
of the VOR/replacement calibration.

Safe to re-run: upserts by (source, player_name, season_year).

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\ingest_espn_rankings.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.market_models import ExternalConsensusRanking
import app.models.historical_models  # noqa: F401
import app.models.news_models  # noqa: F401
from app.integrations.espn_client import fetch_espn_rankings

SEASON_YEAR = 2026


def main():
    Base.metadata.create_all(bind=engine)

    rows = fetch_espn_rankings(SEASON_YEAR, limit=500, rank_type="PPR")
    print(f"Fetched {len(rows)} players from ESPN.")

    db = SessionLocal()
    inserted, updated = 0, 0
    try:
        for row in rows:
            if not row["player_name"]:
                continue
            existing = db.query(ExternalConsensusRanking).filter(
                ExternalConsensusRanking.source == "ESPN",
                ExternalConsensusRanking.player_name == row["player_name"],
                ExternalConsensusRanking.season_year == SEASON_YEAR,
            ).first()

            values = dict(
                position=row["position"],
                rank=row["espn_rank"],
                adp=row["espn_adp"],
                percent_owned=row["espn_percent_owned"],
                scoring_format="PPR",
                as_of_date=datetime.utcnow(),
            )

            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(ExternalConsensusRanking(
                    source="ESPN", player_name=row["player_name"], season_year=SEASON_YEAR, **values
                ))
                inserted += 1

        db.commit()
        print(f"ESPN rankings loaded: {inserted} inserted, {updated} updated.")
    except Exception as e:
        db.rollback()
        print(f"Error ingesting ESPN rankings: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
