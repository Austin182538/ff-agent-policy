"""
Converts Vegas season-long player prop lines (yards + optional TDs) into
implied half-PPR fantasy points, matching the league's actual scoring:
  - 1 point per 10 yards (receiving or rushing)
  - 6 points per rushing/receiving TD
  - 0.5 points per reception

Vegas books post yardage lines far more often than TD or reception count
lines (see data/README.md). BettingPros (see app/integrations/bettingpros_client.py)
DOES post a season-long reception-count O/U for the ~80 highest-volume pass
catchers, and when that real reception line is present it is used directly
(passed in as receptions_line). For everyone else -- and for TD counts, which
are still unquoted for a chunk of players -- the count is derived here from the
yards line using a *league-average* rate. This derivation is still the normal
path for the long tail of players without their own posted count line.
Missing TD/reception counts are estimated using a *league-average* rate
(yards-per-catch, yards-per-TD), computed directly from real 2021-2025
receiving lines (see LEAGUE_AVG_* below for the exact query/threshold used)
rather than eyeballed -- a receiving-volume threshold is applied per position
to keep the average representative of real starting-caliber usage (e.g. a
3-catch/40-yard cameo shouldn't drag down the "real role" rate).

This deliberately does NOT fall back to a player's own prior-season rate,
even a "stable, skill-based" one. An earlier version tried that (with a
minimum-sample-size guard), but it still meant an established veteran with
one big-TD-rate season (e.g. a bruising short-yardage back) got a materially
better conversion rate than a rookie or anyone else without a qualifying
season -- reintroducing exactly the previous-performance bias this whole
model is supposed to avoid, just one level removed (a rate instead of a
volume stat). Every player -- proven veteran or Day 1 rookie -- now converts
missing TDs/receptions at the same league-average rate for their position.
"""

from typing import Optional, Dict

# yards-per-catch, 2021-2025 real seasons at a "real role" volume threshold
# (WR: receiving_yards > 300, TE: receiving_yards > 200, RB: rushing_yards >
# 200 -- i.e. an every-week rushing role, not judged by receiving volume,
# since a receiving-only threshold would exclude exactly the bell-cow backs
# this constant is meant to apply to). RBs catch shorter, more efficient
# passes (checkdowns, screens) than WR/TE, hence the much lower rate.
LEAGUE_AVG_YARDS_PER_CATCH = {"WR": 12.8, "TE": 10.6, "RB": 7.4}
# receiving-yards-per-TD, same seasons/thresholds as above.
LEAGUE_AVG_REC_YARDS_PER_TD = {"WR": 164.0, "TE": 147.0, "RB": 188.0}
# QBs score a rushing TD roughly every ~96 yards (2021-2025, QBs with 100+
# rush yards/season) vs. ~140 for RBs -- short-yardage sneaks and goal-line
# scrambles convert far more efficiently than open-field RB runs, so this
# needs its own rate rather than sharing the RB constant. This is a
# position-wide (role-based) constant, not any individual player's rate.
LEAGUE_AVG_RUSH_YARDS_PER_TD = {"RB": 140.0, "QB": 96.0}

# Passing-yards-per-interception, 2021-2025 real-starter seasons (passing
# yards > 2500) -- used since no book posts a season-long INT O/U line.
LEAGUE_AVG_PASS_YARDS_PER_INT = 356.0

# Flat rushing-points baseline for "pocket passer" QBs -- i.e. any QB without
# their own real Vegas rushing line this season (2021-2025 median rushing
# points among real-starter QBs, excluding the current season's known mobile
# QBs who already have their own real rushing line). Same rationale as
# compute_rb_receiving_baseline() in analysis/player_ranking_v1.py: even a
# "pocket passer" picks up real scramble/kneel-down rushing value most
# seasons, so treating it as zero would understate them, but crediting them
# with a mobile QB's rate would overstate them -- this is the position-wide
# baseline for the archetype that doesn't have a real line to use instead.
QB_POCKET_PASSER_RUSHING_BASELINE = 26.6


def implied_receiving_points(
    rec_yards_line: float,
    rec_tds_line: Optional[float],
    position: str,
    receptions_line: Optional[float] = None,
) -> Dict[str, float]:
    """When a real season-long reception-count line exists (receptions_line,
    e.g. BettingPros market 330) it is used directly for the 0.5-per-catch
    component -- far more accurate than dividing yards by a league-average
    yards-per-catch, which systematically over-counts catches for
    high-aDOT/low-YPC role players and under-counts for checkdown backs. The
    yards-per-catch derivation remains the fallback when no reception line is
    posted for the player.
    """
    ypc = LEAGUE_AVG_YARDS_PER_CATCH.get(position, 11.0)
    yards_per_td = LEAGUE_AVG_REC_YARDS_PER_TD.get(position, 140.0)

    if receptions_line is not None:
        implied_receptions = receptions_line
        receptions_from_line = True
    else:
        implied_receptions = rec_yards_line / ypc if ypc else 0.0
        receptions_from_line = False
    implied_tds = rec_tds_line if rec_tds_line is not None else (rec_yards_line / yards_per_td if yards_per_td else 0.0)

    points = (rec_yards_line / 10.0) + (implied_tds * 6.0) + (implied_receptions * 0.5)
    return {
        "points": points,
        "implied_receptions": implied_receptions,
        "implied_tds": implied_tds,
        "yards_per_catch_used": ypc,
        "receptions_from_line": receptions_from_line,
    }


def implied_rushing_points(
    rush_yards_line: float,
    rush_tds_line: Optional[float],
    position: str = "RB",
) -> Dict[str, float]:
    yards_per_td = LEAGUE_AVG_RUSH_YARDS_PER_TD.get(position, 140.0)

    implied_tds = rush_tds_line if rush_tds_line is not None else (rush_yards_line / yards_per_td if yards_per_td else 0.0)
    points = (rush_yards_line / 10.0) + (implied_tds * 6.0)
    return {"points": points, "implied_tds": implied_tds}


def implied_passing_points(pass_yards_line: float, pass_tds_line: float) -> Dict[str, float]:
    """No book posts a season-long INT O/U line, so INTs are estimated from
    a league-average passing-yards-per-INT rate -- never a specific QB's own
    INT rate (same "no previous performance" rule as everywhere else here).
    """
    implied_ints = pass_yards_line / LEAGUE_AVG_PASS_YARDS_PER_INT
    points = (pass_yards_line / 25.0) + (pass_tds_line * 4.0) - (implied_ints * 2.0)
    return {"points": points, "implied_ints": implied_ints}
