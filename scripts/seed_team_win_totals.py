#!/usr/bin/env python3
"""
Load the manually-curated data/vegas_win_totals.csv into the
team_season_win_totals table (see data/README.md for sourcing notes).

Safe to re-run: upserts by (team_abbr, season_year).

Run with the main app venv (no nflreadpy dependency needed here):
    venv\\Scripts\\python.exe scripts\\seed_team_win_totals.py
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.market_models import TeamSeasonWinTotal
import app.models.historical_models  # noqa: F401  (registers tables on the shared Base)
import app.models.news_models  # noqa: F401

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "vegas_win_totals.csv")


def main():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    inserted, updated = 0, 0
    try:
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                team_abbr = row["team_abbr"].strip()
                season_year = int(row["season_year"])

                existing = db.query(TeamSeasonWinTotal).filter(
                    TeamSeasonWinTotal.team_abbr == team_abbr,
                    TeamSeasonWinTotal.season_year == season_year,
                ).first()

                over_price = float(row["over_price"]) if row.get("over_price") else None
                under_price = float(row["under_price"]) if row.get("under_price") else None

                if existing:
                    existing.win_total_line = float(row["win_total_line"])
                    existing.over_price = over_price
                    existing.under_price = under_price
                    existing.source = row["source"]
                    existing.as_of_date = datetime.utcnow()
                    updated += 1
                else:
                    db.add(TeamSeasonWinTotal(
                        team_abbr=team_abbr,
                        season_year=season_year,
                        win_total_line=float(row["win_total_line"]),
                        over_price=over_price,
                        under_price=under_price,
                        source=row["source"],
                        as_of_date=datetime.utcnow(),
                    ))
                    inserted += 1

        db.commit()
        print(f"Team season win totals loaded: {inserted} inserted, {updated} updated.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding team win totals: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
