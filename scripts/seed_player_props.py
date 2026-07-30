#!/usr/bin/env python3
"""
Load data/vegas_player_props_2026.csv into player_season_prop_lines.
See data/README.md for sourcing notes and coverage caveats.

Safe to re-run: upserts by (player_name, season_year).

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\seed_player_props.py
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.market_models import PlayerSeasonPropLine
import app.models.historical_models  # noqa: F401
import app.models.news_models  # noqa: F401

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vegas_player_props_2026.csv")
SEASON_YEAR = 2026


def _f(value):
    return float(value) if value else None


def main():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    inserted, updated = 0, 0
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                player_name = row["player_name"].strip()

                existing = db.query(PlayerSeasonPropLine).filter(
                    PlayerSeasonPropLine.player_name == player_name,
                    PlayerSeasonPropLine.season_year == SEASON_YEAR,
                ).first()

                values = dict(
                    position=row["position"].strip(),
                    rec_yards_line=_f(row.get("rec_yards_line")),
                    rec_tds_line=_f(row.get("rec_tds_line")),
                    rush_yards_line=_f(row.get("rush_yards_line")),
                    rush_tds_line=_f(row.get("rush_tds_line")),
                    pass_yards_line=_f(row.get("pass_yards_line")),
                    pass_tds_line=_f(row.get("pass_tds_line")),
                    source=row["source"],
                    as_of_date=datetime.utcnow(),
                )

                if existing:
                    for k, v in values.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    db.add(PlayerSeasonPropLine(
                        player_name=player_name, season_year=SEASON_YEAR, **values
                    ))
                    inserted += 1

        db.commit()
        print(f"Player prop lines loaded: {inserted} inserted, {updated} updated.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding player props: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
