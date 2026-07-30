"""
Client for BettingPros' undocumented public API (the same one that powers
www.bettingpros.com). It carries **season-long** player prop O/U lines as a
consensus across the major books -- crucially including markets that
fantasypoints.com does NOT post:

  - Total Receiving Yards for *running backs* (fantasypoints only lists WR/TE
    receiving lines, so every pass-catching RB was previously defaulting to a
    flat league-average baseline -- the exact gap that made us miss Bijan
    Robinson's ~600 rec-yard line).
  - Total Receptions O/U (a real reception-count line -- previously we had to
    *derive* receptions from yards via a league-average yards-per-catch rate).

The API requires the site's `x-api-key` AND the browser `Origin`/`Referer`
headers (a bare key with no Origin gets a 403). Season markets are queried with
`?season=YYYY` (NOT an event_id, which is only for weekly/game markets), and
`offers` is paginated at a hard max of 10 rows/page.

Market IDs (from GET /v3/markets?sport=NFL, category=player-futures,
period=season) map to our prop columns as follows:

    300 total-passing-yards       -> pass_yards_line
    301 total-rushing-yards       -> rush_yards_line
    302 total-receiving-yards     -> rec_yards_line
    304 total-passing-touchdowns  -> pass_tds_line
    305 total-rushing-touchdowns  -> rush_tds_line
    306 total-rec-touchdowns      -> rec_tds_line
    330 total-receptions          -> receptions_line

Each offer's line lives in selections[side].books[].lines[].line. Book id 0 is
BettingPros' own consensus line, which is what the site displays and what we
use (falling back to any book's main line, then the opening line).
"""

import time
from typing import Dict, List, Optional

import requests

from app.core.config import settings

# market_id -> our prop-line column name. Season-long player futures only.
SEASON_MARKETS: Dict[int, str] = {
    300: "pass_yards_line",
    301: "rush_yards_line",
    302: "rec_yards_line",
    304: "pass_tds_line",
    305: "rush_tds_line",
    306: "rec_tds_line",
    330: "receptions_line",
}

_BASE = settings.bettingpros_base_url.rstrip("/")

# The Origin/Referer are as load-bearing as the key itself -- the API is CORS
# gated to www.bettingpros.com and 403s any request without them.
_HEADERS = {
    "x-api-key": settings.bettingpros_api_key,
    "Origin": "https://www.bettingpros.com",
    "Referer": "https://www.bettingpros.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class BettingProsError(RuntimeError):
    pass


def _get(path: str, params: dict) -> dict:
    if not settings.bettingpros_api_key:
        raise BettingProsError(
            "BETTINGPROS_API_KEY is not set -- add it to .env (grab it from a "
            "www.bettingpros.com XHR request's x-api-key header)."
        )
    resp = requests.get(f"{_BASE}{path}", params=params, headers=_HEADERS, timeout=30)
    if resp.status_code == 403:
        raise BettingProsError(
            f"403 from BettingPros (key rejected or Origin missing): {resp.text[:200]}"
        )
    if resp.status_code != 200:
        raise BettingProsError(f"{resp.status_code} from {path} {params}: {resp.text[:200]}")
    return resp.json()


def _extract_consensus_line(offer: dict) -> Optional[float]:
    """Pull the O/U number from an offer. Prefer BettingPros' consensus book
    (id 0) main line; fall back to any book's main line, then the opening line.
    The line is the same on the over and under, so we just take the first side
    that yields a number.
    """
    fallback_open = None
    for sel in offer.get("selections", []):
        # book 0 = BettingPros consensus (what the site shows)
        for want_id in (0,):
            for book in sel.get("books", []):
                if book.get("id") == want_id:
                    for ln in book.get("lines", []):
                        if ln.get("main") and ln.get("line") is not None:
                            return float(ln["line"])
        # any book's main line
        for book in sel.get("books", []):
            for ln in book.get("lines", []):
                if ln.get("main") and ln.get("line") is not None:
                    return float(ln["line"])
        ol = sel.get("opening_line") or {}
        if ol.get("line") is not None and fallback_open is None:
            fallback_open = float(ol["line"])
    return fallback_open


def fetch_market_offers(market_id: int, season: int, pause: float = 0.15) -> List[dict]:
    """Return a list of {name, position, team, player_id, line} for every
    player in one season-long market, paging through all results (10/page).
    """
    out: List[dict] = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = _get("/offers", {"sport": "NFL", "market_id": str(market_id),
                                "season": season, "page": page})
        pagination = data.get("_pagination") or {}
        total_pages = pagination.get("total_pages", page)
        for offer in data.get("offers", []):
            parts = offer.get("participants") or []
            if not parts:
                continue
            player = parts[0].get("player") or {}
            line = _extract_consensus_line(offer)
            if line is None:
                continue
            out.append({
                "name": parts[0].get("name") or "",
                "position": player.get("position"),
                "team": player.get("team"),
                "player_id": offer.get("player_id"),
                "headshot": player.get("image"),  # fantasypros head/shoulders cutout URL
                "line": line,
            })
        page += 1
        if page <= total_pages and pause:
            time.sleep(pause)
    return out


def fetch_all_season_props(season: int) -> Dict[str, dict]:
    """Fetch every season-long market and merge into a per-player dict keyed by
    the player's display name:

        {"Bijan Robinson": {"position": "RB", "team": "ATL",
                            "rec_yards_line": 600.5, "rush_yards_line": ...}, ...}

    Only the columns in SEASON_MARKETS are populated; a player appears if they
    have a line in at least one market.
    """
    players: Dict[str, dict] = {}
    for market_id, col in SEASON_MARKETS.items():
        rows = fetch_market_offers(market_id, season)
        for r in rows:
            name = r["name"].strip()
            if not name:
                continue
            rec = players.setdefault(name, {"position": None, "team": None, "headshot": None})
            rec[col] = r["line"]
            if r.get("position") and not rec.get("position"):
                rec["position"] = r["position"]
            if r.get("team") and not rec.get("team"):
                rec["team"] = r["team"]
            if r.get("headshot") and not rec.get("headshot"):
                rec["headshot"] = r["headshot"]
        print(f"  market {market_id} ({col}): {len(rows)} lines")
    return players
