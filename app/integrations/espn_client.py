"""
ESPN Fantasy Football's public (undocumented, no-auth-required) player
universe endpoint. Unlike Yahoo (requires an OAuth app registration even for
public data) or Sleeper (no ADP/rankings endpoint at all -- only rosters,
drafts, and player metadata), ESPN's non-league-specific "leaguedefaults"
endpoint exposes real, live, current-season expert draft ranks (STANDARD,
PPR, SUPERFLEX) and actual crowd-sourced average draft position (ADP) with
just an `x-fantasy-filter` header -- no API key, cookie, or league ID needed.

Endpoint discovered via community reverse-engineering (see e.g.
https://gist.github.com/gtonic/d05f9a5351ab1d2cd6e8c7c1857b4f01); this is not
an officially documented/supported ESPN API and could change without notice.

Note: ESPN's rank types are STANDARD / PPR / SUPERFLEX / ELIMINATION -- there
is no native "half-PPR" category, so PPR is used as the closer analog (full
PPR is closer to this league's 0.5-PPR scoring than 0-PPR "STANDARD" is).
"""

from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"

# ESPN's defaultPositionId -> our position strings.
POSITION_MAP = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}


def fetch_espn_rankings(season: int, limit: int = 500, rank_type: str = "PPR") -> List[Dict[str, Any]]:
    """Returns a list of {player_name, position, espn_rank, espn_adp} dicts,
    sorted by ESPN's own expert draft rank (not ADP -- ADP is returned
    alongside for comparison, but rank is what drives their default board).
    """
    headers = {
        "x-fantasy-filter": (
            '{"players":{"limit":%d,"sortDraftRanks":{"sortPriority":1,"sortAsc":true,"value":"%s"}}}'
            % (limit, rank_type)
        )
    }
    url = BASE_URL.format(season=season) + "?view=kona_player_info"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    rows = []
    for entry in payload.get("players", []):
        player = entry.get("player", {})
        position = POSITION_MAP.get(player.get("defaultPositionId"))
        if position is None:
            continue
        rank_info = player.get("draftRanksByRankType", {}).get(rank_type, {})
        ownership = player.get("ownership", {})
        rows.append({
            "player_name": player.get("fullName"),
            "position": position,
            "espn_rank": rank_info.get("rank"),
            "espn_adp": ownership.get("averageDraftPosition"),
            "espn_percent_owned": ownership.get("percentOwned"),
        })
    return rows


# ESPN raw-stat IDs (in the projected-stats dict) -> readable component names.
# From the widely-used espn-api mapping (statSourceId=1 = projections).
ESPN_STAT_IDS = {
    "3": "pass_yards", "4": "pass_tds", "20": "interceptions",
    "24": "rush_yards", "25": "rush_tds",
    "42": "rec_yards", "43": "rec_tds", "53": "receptions",
}


def fetch_espn_projections(season: int, limit: int = 400, rank_type: str = "PPR") -> List[Dict[str, Any]]:
    """Returns ESPN's own season-long *projected* component stats per player
    (pass/rush/rec yards + TDs, receptions, INTs) plus ESPN's projected fantasy
    point total. This is a genuine third-party projection source (not just a
    rank), so we can compare component-by-component against our Vegas-implied
    projection to see WHERE a disagreement comes from.

    ESPN returns several stat blocks per player; we take the one with
    statSourceId=1 (projection, not actuals=0) and statSplitTypeId=0 (full
    season) for the requested season.
    """
    headers = {
        "x-fantasy-filter": (
            '{"players":{"limit":%d,"sortDraftRanks":{"sortPriority":1,"sortAsc":true,"value":"%s"}}}'
            % (limit, rank_type)
        )
    }
    url = BASE_URL.format(season=season) + "?view=kona_player_info"
    resp = requests.get(url, headers=headers, timeout=25)
    resp.raise_for_status()
    payload = resp.json()

    rows = []
    for entry in payload.get("players", []):
        player = entry.get("player", {})
        position = POSITION_MAP.get(player.get("defaultPositionId"))
        if position is None:
            continue
        proj = None
        for s in player.get("stats", []):
            if (s.get("seasonId") == season and s.get("statSourceId") == 1
                    and s.get("statSplitTypeId") == 0):
                proj = s
                break
        if proj is None:
            continue
        raw = proj.get("stats", {}) or {}
        row = {
            "player_name": player.get("fullName"),
            "position": position,
            "espn_proj_points": proj.get("appliedTotal"),  # ESPN's own (PPR) total
        }
        for stat_id, name in ESPN_STAT_IDS.items():
            row[f"espn_{name}"] = raw.get(stat_id)
        rows.append(row)
    return rows
