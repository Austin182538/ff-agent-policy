"""
Thin client for The Odds API (https://the-odds-api.com), v4.

Free "Starter" tier: 500 credits/month, all sports/bookmakers/markets
(including player props), no card required. Get a key at
https://the-odds-api.com and set ODDS_API_KEY in .env.

Note: americanfootball_nfl has has_outrights=false -- this API does NOT carry
team season win-total futures for NFL. Use scripts/seed_team_win_totals.py
for that market instead. Super Bowl / conference futures ARE available under
the separate sport key americanfootball_nfl_super_bowl_winner.
"""

from typing import Any, Dict, List, Optional
import logging
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

NFL_SPORT_KEY = "americanfootball_nfl"
NFL_SUPER_BOWL_SPORT_KEY = "americanfootball_nfl_super_bowl_winner"

GAME_LINE_MARKETS = ["h2h", "spreads", "totals"]

# A practical default set of NFL player prop markets. Full list:
# https://the-odds-api.com/sports-odds-data/betting-markets.html#player-props-api-markets
DEFAULT_PLAYER_PROP_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_completions",
    "player_pass_attempts",
    "player_pass_interceptions",
    "player_rush_yds",
    "player_rush_attempts",
    "player_reception_yds",
    "player_receptions",
    "player_rush_reception_yds",
    "player_anytime_td",
]


class OddsAPIError(RuntimeError):
    pass


class OddsAPIClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: int = 20):
        self.api_key = api_key or settings.odds_api_key
        self.base_url = (base_url or settings.odds_api_base_url).rstrip("/")
        self.timeout = timeout
        self.last_quota_used: Optional[str] = None
        self.last_quota_remaining: Optional[str] = None

        if not self.api_key:
            logger.warning(
                "ODDS_API_KEY is not set. Get a free key at https://the-odds-api.com "
                "and add it to .env before calling the live API."
            )

    def _get(self, path: str, params: Dict[str, Any]) -> Any:
        if not self.api_key:
            raise OddsAPIError(
                "ODDS_API_KEY is not configured. Add it to .env (see .env.example)."
            )
        url = f"{self.base_url}{path}"
        params = {**params, "apiKey": self.api_key}
        response = requests.get(url, params=params, timeout=self.timeout)

        self.last_quota_used = response.headers.get("x-requests-used")
        self.last_quota_remaining = response.headers.get("x-requests-remaining")

        if response.status_code != 200:
            raise OddsAPIError(
                f"The Odds API request failed ({response.status_code}): {response.text[:500]}"
            )
        return response.json()

    def get_sports(self, all_sports: bool = False) -> List[Dict[str, Any]]:
        return self._get("/sports", {"all": str(all_sports).lower()})

    def get_nfl_game_odds(
        self,
        markets: Optional[List[str]] = None,
        regions: str = "us",
        odds_format: str = "american",
    ) -> List[Dict[str, Any]]:
        """Featured markets (moneyline/spreads/totals) for all upcoming/live NFL games."""
        return self._get(
            f"/sports/{NFL_SPORT_KEY}/odds",
            {
                "regions": regions,
                "markets": ",".join(markets or GAME_LINE_MARKETS),
                "oddsFormat": odds_format,
            },
        )

    def get_nfl_events(self) -> List[Dict[str, Any]]:
        """Lightweight list of upcoming/live NFL events (free, no quota cost) --
        use this to get event ids for get_event_player_props().
        """
        return self._get(f"/sports/{NFL_SPORT_KEY}/events", {})

    def get_event_player_props(
        self,
        event_id: str,
        markets: Optional[List[str]] = None,
        regions: str = "us",
        odds_format: str = "american",
    ) -> Dict[str, Any]:
        """Player prop odds for a single event. Player props are only available
        once a game is on the board (typically within ~1-2 weeks of kickoff),
        so this will return empty markets for games far in the future.
        """
        return self._get(
            f"/sports/{NFL_SPORT_KEY}/events/{event_id}/odds",
            {
                "regions": regions,
                "markets": ",".join(markets or DEFAULT_PLAYER_PROP_MARKETS),
                "oddsFormat": odds_format,
            },
        )

    def get_super_bowl_futures(
        self, regions: str = "us", odds_format: str = "american"
    ) -> List[Dict[str, Any]]:
        return self._get(
            f"/sports/{NFL_SUPER_BOWL_SPORT_KEY}/odds",
            {"regions": regions, "markets": "outrights", "oddsFormat": odds_format},
        )
