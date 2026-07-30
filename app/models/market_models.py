"""
Vegas / sportsbook market data models.

Populated from The Odds API (https://the-odds-api.com) for game lines, player
props, and futures, plus a small manually-curated dataset for team season
win totals (a market The Odds API does not carry for NFL).
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from app.core.database import Base
from datetime import datetime


class GameOdds(Base):
    """Featured market odds (moneyline / spread / total) for a single NFL game,
    one row per (event, bookmaker, market, outcome), matching The Odds API's
    native shape so we don't lose information by forcing it into a narrower
    schema.
    """
    __tablename__ = "game_odds"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, index=True, nullable=False)  # The Odds API event id
    season_year = Column(Integer, index=True)
    week = Column(Integer, index=True, nullable=True)
    commence_time = Column(DateTime, index=True)
    home_team = Column(String, index=True)
    away_team = Column(String, index=True)

    bookmaker_key = Column(String, index=True)
    bookmaker_title = Column(String)
    market_key = Column(String, index=True)  # h2h | spreads | totals
    outcome_name = Column(String)            # team name, or Over/Under
    price = Column(Float)                    # american odds
    point = Column(Float, nullable=True)     # spread/total line, null for h2h

    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint(
            "event_id", "bookmaker_key", "market_key", "outcome_name", "snapshot_time",
            name="uq_game_odds_row"
        ),
    )


class PlayerPropOdds(Base):
    """Per-game player prop odds, one row per (event, bookmaker, market, player, side)."""
    __tablename__ = "player_prop_odds"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, index=True, nullable=False)
    season_year = Column(Integer, index=True)
    week = Column(Integer, index=True, nullable=True)
    commence_time = Column(DateTime, index=True)
    home_team = Column(String, index=True)
    away_team = Column(String, index=True)

    bookmaker_key = Column(String, index=True)
    bookmaker_title = Column(String)
    market_key = Column(String, index=True)  # e.g. player_pass_yds, player_receptions
    player_name = Column(String, index=True)  # comes from outcome "description"
    side = Column(String)                     # Over / Under / Yes / No
    line = Column(Float, nullable=True)       # the point/handicap for this prop
    price = Column(Float)                     # american odds

    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint(
            "event_id", "bookmaker_key", "market_key", "player_name", "side", "snapshot_time",
            name="uq_player_prop_odds_row"
        ),
    )


class TeamSeasonWinTotal(Base):
    """Preseason team win-total futures (Over/Under number of regular-season wins).

    The Odds API does not carry this market for NFL (confirmed: americanfootball_nfl
    has_outrights=false, and there's no dedicated win-totals sport key), so this is
    populated from a small manually-curated/scraped dataset -- see
    data/vegas_win_totals_*.csv and scripts/seed_team_win_totals.py.
    """
    __tablename__ = "team_season_win_totals"

    id = Column(Integer, primary_key=True, index=True)
    team_abbr = Column(String(3), index=True, nullable=False)
    season_year = Column(Integer, index=True, nullable=False)
    win_total_line = Column(Float, nullable=False)
    over_price = Column(Float, nullable=True)
    under_price = Column(Float, nullable=True)
    source = Column(String)      # e.g. "covers.com", "manual"
    as_of_date = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("team_abbr", "season_year", name="uq_team_season_win_total"),
    )


class PlayerSeasonPropLine(Base):
    """Season-long individual player prop lines (receiving/rushing yards and,
    where available, TDs). The Odds API doesn't carry season-long player
    props for NFL, so this is manually curated -- see
    data/vegas_player_props_2026.csv and data/README.md for sourcing.
    """
    __tablename__ = "player_season_prop_lines"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True)
    season_year = Column(Integer, index=True, nullable=False)

    rec_yards_line = Column(Float, nullable=True)
    rec_tds_line = Column(Float, nullable=True)
    rush_yards_line = Column(Float, nullable=True)
    rush_tds_line = Column(Float, nullable=True)
    pass_yards_line = Column(Float, nullable=True)
    pass_tds_line = Column(Float, nullable=True)
    # Real season-long reception-count O/U (BettingPros market 330). When
    # present it's used directly instead of deriving receptions from rec yards
    # via a league-average yards-per-catch rate.
    receptions_line = Column(Float, nullable=True)

    source = Column(String)
    as_of_date = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("player_name", "season_year", name="uq_player_season_prop_line"),
    )


class PlayerPropLineSnapshot(Base):
    """Append-only history of scraped Vegas player-prop lines, one batch of
    rows per scrape run (all sharing the same `scraped_at`). Deliberately
    separate from `PlayerSeasonPropLine` (which is a single "current" row per
    player, upserted in place) -- this table exists specifically so a
    line-movement monitor can diff "now" against "last scrape" over time,
    which an upsert-only table can't do once the old value is overwritten.

    Populated by scripts/scrape_vegas_snapshot.py, consumed by
    scripts/compare_vegas_snapshots.py.
    """
    __tablename__ = "player_prop_line_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True, nullable=True)
    season_year = Column(Integer, index=True, nullable=False)

    rec_yards_line = Column(Float, nullable=True)
    rec_tds_line = Column(Float, nullable=True)
    rush_yards_line = Column(Float, nullable=True)
    rush_tds_line = Column(Float, nullable=True)
    pass_yards_line = Column(Float, nullable=True)
    pass_tds_line = Column(Float, nullable=True)

    source = Column(String)
    scraped_at = Column(DateTime, index=True, nullable=False, default=datetime.utcnow)


class ExternalConsensusRanking(Base):
    """Preseason rankings/ADP from a platform OTHER than the primary
    FantasyPros-via-nflverse source (see FantasyConsensusRanking in
    historical_models.py). Kept in a separate table (not just another
    `source` value in FantasyConsensusRanking) so the existing VOR/replacement
    calibration -- which was built and tuned specifically against FantasyPros
    ECR history -- can't be silently corrupted by an unfiltered query
    accidentally picking up rows from a different platform. Use this table
    for side-by-side comparison / sanity-checking, not as a drop-in
    replacement for the calibration inputs.
    """
    __tablename__ = "external_consensus_rankings"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True, nullable=False)  # e.g. "ESPN", "Yahoo", "Sleeper"
    player_name = Column(String, index=True, nullable=False)
    position = Column(String(3), index=True)
    season_year = Column(Integer, index=True, nullable=False)

    rank = Column(Float, nullable=True)         # platform's own expert/default rank
    adp = Column(Float, nullable=True)           # platform's live average draft position, if available
    percent_owned = Column(Float, nullable=True)
    scoring_format = Column(String, nullable=True)  # e.g. "PPR", "STANDARD"

    as_of_date = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source", "player_name", "season_year", name="uq_external_consensus_ranking"),
    )


class TeamFutures(Base):
    """Super Bowl / conference winner futures, from The Odds API's
    americanfootball_nfl_super_bowl_winner sport key (has_outrights=true).
    """
    __tablename__ = "team_futures"

    id = Column(Integer, primary_key=True, index=True)
    team_name = Column(String, index=True, nullable=False)
    season_year = Column(Integer, index=True, nullable=False)
    market = Column(String, index=True)  # super_bowl_winner (extend later if needed)
    bookmaker_key = Column(String, index=True)
    price = Column(Float)
    implied_probability = Column(Float, nullable=True)
    snapshot_time = Column(DateTime, default=datetime.utcnow, index=True)
