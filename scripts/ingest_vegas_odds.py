#!/usr/bin/env python3
"""
Pull current NFL game lines (+ player props once games are on the board, +
Super Bowl/conference futures) from The Odds API and store snapshots in
game_odds / player_prop_odds / team_futures.

Requires ODDS_API_KEY in .env (free key: https://the-odds-api.com).
Safe to re-run any time -- each run adds a new snapshot rather than
overwriting, so you can track line movement over time.

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\ingest_vegas_odds.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.core.config import settings
from app.models.market_models import GameOdds, PlayerPropOdds, TeamFutures
import app.models.historical_models  # noqa: F401
import app.models.news_models  # noqa: F401
from app.integrations.odds_api_client import OddsAPIClient, OddsAPIError


def _parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def ingest_game_lines(client: OddsAPIClient, db) -> int:
    events = client.get_nfl_game_odds()
    count = 0
    snapshot_time = datetime.utcnow()

    for event in events:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    db.add(GameOdds(
                        event_id=event["id"],
                        commence_time=_parse_dt(event.get("commence_time")),
                        home_team=event.get("home_team"),
                        away_team=event.get("away_team"),
                        bookmaker_key=bookmaker.get("key"),
                        bookmaker_title=bookmaker.get("title"),
                        market_key=market.get("key"),
                        outcome_name=outcome.get("name"),
                        price=outcome.get("price"),
                        point=outcome.get("point"),
                        snapshot_time=snapshot_time,
                    ))
                    count += 1
    return count


def ingest_player_props(client: OddsAPIClient, db) -> int:
    """Player props are only posted once a game is close enough (typically
    inside ~1-2 weeks of kickoff), so this may add 0 rows in the off-season --
    that's expected, not an error. Re-run weekly during the season.
    """
    events = client.get_nfl_events()
    count = 0
    snapshot_time = datetime.utcnow()

    for event in events:
        try:
            event_odds = client.get_event_player_props(event["id"])
        except OddsAPIError as e:
            print(f"  (skipping {event.get('away_team')} @ {event.get('home_team')}: {e})")
            continue

        for bookmaker in event_odds.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    db.add(PlayerPropOdds(
                        event_id=event_odds["id"],
                        commence_time=_parse_dt(event_odds.get("commence_time")),
                        home_team=event_odds.get("home_team"),
                        away_team=event_odds.get("away_team"),
                        bookmaker_key=bookmaker.get("key"),
                        bookmaker_title=bookmaker.get("title"),
                        market_key=market.get("key"),
                        player_name=outcome.get("description"),
                        side=outcome.get("name"),
                        line=outcome.get("point"),
                        price=outcome.get("price"),
                        snapshot_time=snapshot_time,
                    ))
                    count += 1
    return count


def ingest_super_bowl_futures(client: OddsAPIClient, db) -> int:
    events = client.get_super_bowl_futures()
    count = 0
    snapshot_time = datetime.utcnow()
    season_year = datetime.utcnow().year

    for event in events:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    implied_prob = None
                    if price:
                        implied_prob = (100 / (price + 100)) if price > 0 else (-price / (-price + 100))
                    db.add(TeamFutures(
                        team_name=outcome.get("name"),
                        season_year=season_year,
                        market="super_bowl_winner",
                        bookmaker_key=bookmaker.get("key"),
                        price=price,
                        implied_probability=implied_prob,
                        snapshot_time=snapshot_time,
                    ))
                    count += 1
    return count


def main():
    Base.metadata.create_all(bind=engine)

    if not settings.odds_api_key:
        print("ODDS_API_KEY is not set in .env -- get a free key at https://the-odds-api.com")
        print("Everything else in the pipeline can still run; this step will just be skipped.")
        return

    client = OddsAPIClient()
    db = SessionLocal()
    try:
        print("Fetching NFL game lines (h2h/spreads/totals)...")
        game_line_rows = ingest_game_lines(client, db)
        db.commit()
        print(f"  -> {game_line_rows} game odds rows stored.")

        print("Fetching NFL player props (only present close to kickoff)...")
        prop_rows = ingest_player_props(client, db)
        db.commit()
        print(f"  -> {prop_rows} player prop rows stored.")

        print("Fetching Super Bowl winner futures...")
        futures_rows = ingest_super_bowl_futures(client, db)
        db.commit()
        print(f"  -> {futures_rows} futures rows stored.")

        print(f"Quota used this call: {client.last_quota_used}, remaining: {client.last_quota_remaining}")
    except OddsAPIError as e:
        db.rollback()
        print(f"Odds API error: {e}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
