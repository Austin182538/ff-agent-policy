#!/usr/bin/env python3
"""
Scrapes fantasypoints.com's six season-prop articles (see
app/integrations/fantasypoints_scraper.py), and:

  1. Appends one full batch of rows to player_prop_line_snapshots (a
     permanent, timestamped history -- never overwritten), so
     scripts/compare_vegas_snapshots.py can diff "now" vs. "last run".
  2. Upserts player_season_prop_lines (the "current" table the ranking
     pipeline reads) so a fresh scrape automatically flows into the next
     analysis/player_ranking_v1.py run without any extra step.

Meant to run unattended on a schedule (every few hours) -- see
data/README.md for Windows Task Scheduler setup. Safe to run repeatedly;
each run is a new snapshot batch, and the "current" table is upserted, not
duplicated.

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\scrape_vegas_snapshot.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.market_models import PlayerPropLineSnapshot, PlayerSeasonPropLine
import app.models.historical_models  # noqa: F401
import app.models.news_models  # noqa: F401
from app.integrations.fantasypoints_scraper import scrape_all_prop_lines
from analysis.player_ranking_v1 import normalize_name

SEASON_YEAR = 2026
STAT_FIELDS = ["rec_yards_line", "rec_tds_line", "rush_yards_line", "rush_tds_line", "pass_yards_line", "pass_tds_line"]
SOURCE = "fantasypoints.com (auto-scraped)"

# fantasypoints.com occasionally misspells a name inconsistently across
# their own articles (e.g. "Jeremiah Love" instead of "Jeremiyah Love",
# "Bhaysul Tuten" instead of "Bhayshul Tuten") -- these don't match our
# DB's correctly-spelled rows via normalize_name, so they'd otherwise come
# through as position=NULL and never merge with the player's other lines.
# Add an entry here whenever a scrape run logs an "unmatched" name that's
# actually a known player with a typo'd spelling.
NAME_CORRECTIONS = {
    "Jeremiah Love": "Jeremiyah Love",
    "Bhaysul Tuten": "Bhayshul Tuten",
}


def _load_position_lookup(db) -> dict:
    """merge_key -> position, from the current season's consensus rankings
    -- used to classify scraped names (the scraper itself has no notion of
    position; the receiving/rushing articles mix WR+TE and RB+QB)."""
    from app.models.historical_models import FantasyConsensusRanking
    rows = db.query(FantasyConsensusRanking.player_name, FantasyConsensusRanking.position).filter(
        FantasyConsensusRanking.season_year == SEASON_YEAR
    ).all()
    lookup = {}
    for name, position in rows:
        lookup[normalize_name(name)] = position
    return lookup


def main():
    Base.metadata.create_all(bind=engine)

    print("Scraping fantasypoints.com (6 articles)...")
    scraped_raw = scrape_all_prop_lines()
    scraped = {NAME_CORRECTIONS.get(name, name): lines for name, lines in scraped_raw.items()}
    print(f"  -> {len(scraped)} unique player names found.")

    db = SessionLocal()
    try:
        position_lookup = _load_position_lookup(db)
        scraped_at = datetime.utcnow()

        snapshot_rows, unmatched = [], []
        for name, lines in scraped.items():
            position = position_lookup.get(normalize_name(name))
            if position is None:
                unmatched.append(name)
            snapshot_rows.append(PlayerPropLineSnapshot(
                player_name=name, position=position, season_year=SEASON_YEAR,
                source=SOURCE, scraped_at=scraped_at,
                **{f: lines.get(f) for f in STAT_FIELDS},
            ))

        db.bulk_save_objects(snapshot_rows)
        db.commit()
        print(f"Appended {len(snapshot_rows)} rows to player_prop_line_snapshots (scraped_at={scraped_at}).")
        if unmatched:
            print(f"  {len(unmatched)} names had no position match in fantasy_consensus_rankings "
                  f"(kept anyway, position=NULL): {', '.join(unmatched[:10])}"
                  f"{' ...' if len(unmatched) > 10 else ''}")

        inserted, updated = 0, 0
        for name, lines in scraped.items():
            merge_key = normalize_name(name)
            position = position_lookup.get(merge_key)
            existing = db.query(PlayerSeasonPropLine).filter(
                PlayerSeasonPropLine.player_name == name,
                PlayerSeasonPropLine.season_year == SEASON_YEAR,
            ).first()
            values = {f: lines.get(f) for f in STAT_FIELDS}
            values["source"] = SOURCE
            values["as_of_date"] = scraped_at
            if position:
                values["position"] = position
            if existing:
                for k, v in values.items():
                    if v is not None or k in ("source", "as_of_date"):
                        setattr(existing, k, v)
                updated += 1
            else:
                values.setdefault("position", "UNK")
                db.add(PlayerSeasonPropLine(player_name=name, season_year=SEASON_YEAR, **values))
                inserted += 1
        db.commit()
        print(f"player_season_prop_lines: {inserted} inserted, {updated} updated.")
    except Exception as e:
        db.rollback()
        print(f"Error during scrape/snapshot: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
