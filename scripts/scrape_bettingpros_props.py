#!/usr/bin/env python3
"""
Pulls season-long player prop O/U lines from the BettingPros API (see
app/integrations/bettingpros_client.py) and makes them the authoritative
source for player_season_prop_lines.

BettingPros is preferred over the fantasypoints.com scrape because it posts
markets fantasypoints doesn't: RB receiving yards and a real reception-count
line. This script:

  1. Fetches all season markets (yards/TDs for pass/rush/rec + receptions).
  2. Writes a flat snapshot to data/bettingpros_player_props_2026.csv (for
     inspection / diffing).
  3. Upserts player_season_prop_lines, matching existing rows by normalized
     name (so it updates the same player row a fantasypoints scrape created,
     rather than duplicating it) and overwriting any line BettingPros has a
     value for. Manual overrides in data/manual_prop_overrides.csv still win
     at ranking time (see analysis/player_ranking_v1.load_player_props).

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\scrape_bettingpros_props.py
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import SessionLocal, engine, Base
from app.models.market_models import PlayerSeasonPropLine
import app.models.historical_models  # noqa: F401
import app.models.news_models  # noqa: F401
from app.integrations.bettingpros_client import fetch_all_season_props, SEASON_MARKETS
from analysis.player_ranking_v1 import normalize_name

SEASON_YEAR = 2026
SOURCE = "bettingpros.com (season O/U, consensus)"
CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "bettingpros_player_props_2026.csv")
LINE_COLS = list(dict.fromkeys(SEASON_MARKETS.values()))  # preserve order, dedupe


def ensure_receptions_column():
    """Idempotent migration: add receptions_line to player_season_prop_lines if
    an older DB predates it (SQLite can't ALTER ... ADD COLUMN IF NOT EXISTS)."""
    with engine.connect() as conn:
        cols = [r[1] for r in conn.execute(text("PRAGMA table_info(player_season_prop_lines)"))]
        if "receptions_line" not in cols:
            conn.execute(text("ALTER TABLE player_season_prop_lines ADD COLUMN receptions_line FLOAT"))
            conn.commit()
            print("Migrated: added receptions_line column.")


def write_csv(players: dict):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    fields = ["player_name", "position", "team"] + LINE_COLS + ["headshot_url"]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for name in sorted(players):
            rec = players[name]
            row = {"player_name": name, "position": rec.get("position"), "team": rec.get("team")}
            for c in LINE_COLS:
                row[c] = rec.get(c)
            row["headshot_url"] = rec.get("headshot")
            w.writerow(row)
    print(f"Wrote {len(players)} players -> {CSV_PATH}")


def main():
    Base.metadata.create_all(bind=engine)
    ensure_receptions_column()

    print(f"Fetching BettingPros season props for {SEASON_YEAR}...")
    players = fetch_all_season_props(SEASON_YEAR)
    print(f"  -> {len(players)} unique players with at least one line.")
    write_csv(players)

    db = SessionLocal()
    try:
        existing = db.query(PlayerSeasonPropLine).filter(
            PlayerSeasonPropLine.season_year == SEASON_YEAR
        ).all()
        by_key = {normalize_name(r.player_name): r for r in existing}

        now = datetime.utcnow()
        inserted = updated = 0
        for name, rec in players.items():
            key = normalize_name(name)
            row = by_key.get(key)
            if row is None:
                row = PlayerSeasonPropLine(player_name=name, season_year=SEASON_YEAR,
                                           position=rec.get("position") or "UNK")
                db.add(row)
                by_key[key] = row
                inserted += 1
            else:
                updated += 1
                if (not row.position or row.position == "UNK") and rec.get("position"):
                    row.position = rec["position"]
            for col in LINE_COLS:
                val = rec.get(col)
                if val is not None:
                    setattr(row, col, val)
            row.source = SOURCE
            row.as_of_date = now
        db.commit()
        print(f"player_season_prop_lines: {inserted} inserted, {updated} updated (BettingPros authoritative).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
