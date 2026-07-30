#!/usr/bin/env python3
"""
Data-driven 2026 fantasy ranking (v2 methodology, filename kept as v1 for
continuity with existing references).

Design changes from the first pass, based on real feedback:

1. K/DST excluded entirely -- not modeled well, not needed.
2. No player-specific "how did THIS player do last season" signal anymore.
   Team situations change too much (scheme, coordinator, teammates) for a
   specific player's raw last-season production to be a fair baseline --
   this was also unfairly penalizing rookies with zero NFL history (e.g. a
   highly-drafted rookie RB was scoring worse than a bad veteran purely for
   lacking a stat history, even when Vegas itself projects him for 1000+
   rushing yards).
3. Instead, each player's projected PPR points come from, in priority order:
     a. Vegas season-long player prop lines (yards, +TDs where quoted) --
        the most direct, forward-looking market signal available. Missing
        TD/reception counts are estimated using a league-average rate for
        the position (yards-per-catch, yards-per-TD), never a specific
        player's own history -- an earlier version used a player's own
        rate when their prior season hit a sample-size threshold, but that
        still gave established veterans a better conversion rate than
        rookies/lesser-known players purely for having a track record,
        which is exactly the bias this model is trying to avoid. See
        app/integrations/player_projection.py.
     b. An ECR-rank-to-points calibration curve: "historically, a player
        who entered a season ranked Nth at their position by expert
        consensus scored about X points." This is historical data, but
        about the *rank's* predictive power in general, not about what a
        specific player/team did -- so it doesn't reintroduce the bias in
        (2), and it's exactly why a highly-drafted rookie isn't penalized.
   Both are scaled by the player's team's 2026 Vegas win-total vs. league
   average (a forward-looking signal for this specific season).
4. Positional cost-benefit via Value Over Replacement (VOR): a QB's raw
   points look huge next to a RB's, but that's misleading for a draft
   decision -- there's a much deeper pool of viable QBs than viable RBs.
   VOR = projected points minus the projected points of the last
   startable player at that position in a standard 12-team league. This is
   the actual "cost-benefit" the mid-round QB-vs-RB argument is about, and
   it's the primary sort key now (not raw points, not a position-scaled
   0-100 hack like v1 had).

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\player_ranking_v1.py
"""

import os
import re
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sqlalchemy import text

from app.core.database import engine
from app.integrations.player_projection import (
    implied_receiving_points, implied_rushing_points, implied_passing_points,
    QB_POCKET_PASSER_RUSHING_BASELINE, LEAGUE_AVG_RUSH_YARDS_PER_TD,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
AVAILABILITY_CSV = os.path.join(PROJECT_ROOT, "data", "player_availability.csv")
MANUAL_PROP_OVERRIDES_CSV = os.path.join(PROJECT_ROOT, "data", "manual_prop_overrides.csv")
RANKING_SEASON = 2026
CALIBRATION_SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ["QB", "RB", "WR", "TE"]

# Full NFL regular season length. A player projected to miss games keeps only
# (games_played / GAMES_IN_SEASON) of their VALUE OVER REPLACEMENT -- not that
# fraction of their raw points -- because a replacement-level fill-in backfills
# the missed weeks. See load_availability() and the VOR adjustment in main().
GAMES_IN_SEASON = 17

# Standard 12-team half-PPR league (0.5 pt/reception, 4 pt passing TD,
# -2 pt INT, 6 pt rush/rec TD, 1 pt/10 yards): 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX
# (RB/WR/TE). All historical calibration below uses fantasy_points_half_ppr,
# not nflverse's default full-PPR column, to match this scoring exactly.
NUM_TEAMS = 12
DEDICATED_STARTERS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
FLEX_SLOTS_PER_TEAM = 1
FLEX_ELIGIBLE = ["RB", "WR", "TE"]

# Streaming-adjusted replacement level for the positions nobody rosters two of.
# In a 1-QB/1-TE league managers stack their bench with RB/WR (the scarce, high-
# upside, injury-lottery positions) and carry a single QB and TE -- so quality
# QBs and TEs are perpetually on waivers, and a manager who WAITS can stream
# near-starter production for free all year. That makes the true baseline you're
# drafting *above* a low-end starter, not the "last starter" a roster-slot count
# implies. Concretely (avg 2021-25 actual finishes): a QB streamer realizes
# ~QB9 (~296 pts) and a TE streamer ~TE10 (~131 pts). Pricing QB/TE against that
# higher bar collapses their VOR to what the market already knows -- taking one
# early isn't value, because you forgo scarce RB/WR for points you'd have gotten
# free. RB/WR keep their deep, roster-based (flex-simulated) replacement.
STREAMING_REPLACEMENT_RANK = {"QB": 9, "TE": 10}

# --- Team-environment favorability (the win / projected-points tie-breaker) ---
# Calibrated in POINTS space, because projected team POINTS drives fantasy
# scoring more directly than wins -- team points is a tighter predictor than
# wins at every position (analysis/wins_vs_fantasy_finish.py, volume-controlled
# R^2 improves for QB/RB/WR/TE when swapping wins -> points_for). Coefficients =
# extra half-PPR points per +1 projected team point, at EQUAL opportunity
# (volume-controlled regression, 2021-2025). The position spread is the whole
# point: QB scoring is TD-heavy and TDs scale hardest with team points, TE least.
ENV_FPTS_PER_TEAM_POINT = {"QB": 0.345, "RB": 0.125, "WR": 0.100, "TE": 0.057}
# The only 2026 team-strength signal we have is the Vegas win-total line (no
# season point-total market is posted), so map wins -> projected team points via
# the historical fit points_for ~= 228.9 + 18.1 * wins (R^2 0.63); only the
# slope matters for a league-relative adjustment.
TEAM_POINTS_PER_WIN = 18.1
# The coefficients above are the FULL equal-volume effect, but Vegas prop lines
# (especially TD lines) already price in most of a good offense's MEDIAN
# production. So apply only a fraction as a ceiling / tie-break premium on top of
# the median projection -- a redraft UPSIDE knob, not a re-projection. Set to 1.0
# for the full measured effect.
ENV_STRENGTH = 0.6
# Cap the adjustment at a ~4-win-equivalent full-strength swing per position, so
# it can only flip genuinely close calls, never override a real projection gap.
ENV_CAP_WINS = 4.0


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[.'’]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    return name.strip()


def load_current_rankings() -> pd.DataFrame:
    query = text("""
        SELECT player_name, position, team_abbr, ecr_overall_rank, ecr_position_rank
        FROM fantasy_consensus_rankings
        WHERE season_year = :season AND position IN ('QB','RB','WR','TE')
    """)
    df = pd.read_sql(query, engine, params={"season": RANKING_SEASON})
    df["merge_key"] = df["player_name"].apply(normalize_name)
    return df.drop_duplicates("merge_key")


def load_availability() -> dict:
    """Read data/player_availability.csv -> {merge_key: games_missed}.

    This is the hand/agent-editable hook for the headline->rerank workflow: when
    a suspension/injury headline lands (e.g. "Bijan suspended 4 games"), add one
    row here, rerun the ranking, and the diff report will show the move. Kept as
    a standalone CSV (not the Vegas-prop tables) specifically so the auto-scraper
    never overwrites it. Missing file / empty file => no adjustments (every
    healthy player implicitly has games_missed = 0).

    Expected columns: player_name, games_missed[, reason, source].
    """
    if not os.path.exists(AVAILABILITY_CSV):
        return {}
    df = pd.read_csv(AVAILABILITY_CSV)
    if df.empty or "player_name" not in df.columns or "games_missed" not in df.columns:
        return {}
    df = df.dropna(subset=["player_name", "games_missed"])
    out = {}
    for _, row in df.iterrows():
        games = float(row["games_missed"])
        games = max(0.0, min(float(GAMES_IN_SEASON), games))  # clamp to [0, 17]
        out[normalize_name(str(row["player_name"]))] = games
    return out


def load_prior_season_stats() -> pd.DataFrame:
    """2025 season totals, used ONLY as a FALLBACK team source when the current
    consensus feed is missing a team for a player. The consensus feed is
    authoritative for current teams (it reflects offseason moves), so this never
    overrides it. NOT used as a scoring input in any way -- see
    app/integrations/player_projection.py for why even "rate" stats from a
    player's own history were removed from the projection math.
    """
    query = text("""
        SELECT player_name, team_abbr, receptions, receiving_yards, receiving_tds,
               rushing_yards, rushing_tds
        FROM historical_player_stats
        WHERE season_year = 2025 AND week = 0
    """)
    df = pd.read_sql(query, engine)
    df["merge_key"] = df["player_name"].apply(normalize_name)
    return df.drop_duplicates("merge_key").set_index("merge_key")


PROP_LINE_COLS = ["rec_yards_line", "rec_tds_line", "rush_yards_line",
                  "rush_tds_line", "pass_yards_line", "pass_tds_line",
                  "receptions_line"]


def _first_valid(s: pd.Series):
    s = s.dropna()
    return s.iloc[0] if len(s) else np.nan


def load_manual_prop_overrides() -> pd.DataFrame:
    """Hand/agent-editable overrides for prop lines the auto-scraper can't get
    or gets wrong. The scraped source (fantasypoints.com) posts receiving lines
    for WR/TE only, so every RB's receiving line is missing there -- this CSV is
    where a real RB receiving line (from a book that posts them, e.g.
    bettingpros) gets injected. Any non-empty cell overrides/fills the matching
    scraped line for that player; empty cells are ignored. Kept separate from the
    prop tables so the scraper never clobbers a manual correction.

    Columns: player_name[, position], + any of PROP_LINE_COLS[, source].
    Returns a frame indexed by merge_key (empty if the file is absent/empty).
    """
    if not os.path.exists(MANUAL_PROP_OVERRIDES_CSV):
        return pd.DataFrame()
    ov = pd.read_csv(MANUAL_PROP_OVERRIDES_CSV)
    if ov.empty or "player_name" not in ov.columns:
        return pd.DataFrame()
    ov = ov.dropna(subset=["player_name"])
    ov["merge_key"] = ov["player_name"].apply(normalize_name)
    return ov.drop_duplicates("merge_key").set_index("merge_key")


def load_player_props() -> pd.DataFrame:
    query = text("""
        SELECT player_name, position, rec_yards_line, rec_tds_line, rush_yards_line, rush_tds_line,
               pass_yards_line, pass_tds_line, receptions_line
        FROM player_season_prop_lines
        WHERE season_year = :season
    """)
    df = pd.read_sql(query, engine, params={"season": RANKING_SEASON})
    df["merge_key"] = df["player_name"].apply(normalize_name)

    # Coalesce duplicate spellings of the same player into one row. The scrape
    # keys rows by the exact scraped name, so "James Cook" vs "James Cook III"
    # and smart-quote vs straight-apostrophe ("De'Von" vs "De'Von") land as
    # separate rows -- a plain drop_duplicates would keep the first and could
    # DROP a line that only exists on the other spelling. Instead take the first
    # non-null value per line across all spellings so nothing is lost.
    grouped = df.groupby("merge_key")
    props = grouped[PROP_LINE_COLS].agg(_first_valid)
    props["player_name"] = grouped["player_name"].first()
    props["position"] = grouped["position"].first()

    # Apply manual overrides last (they win over the scraped/coalesced lines).
    overrides = load_manual_prop_overrides()
    for mk, orow in overrides.iterrows():
        if mk not in props.index:
            props.loc[mk, "player_name"] = orow.get("player_name")
            if "position" in overrides.columns and pd.notna(orow.get("position")):
                props.loc[mk, "position"] = orow.get("position")
        for col in PROP_LINE_COLS:
            if col in overrides.columns and pd.notna(orow.get(col)):
                props.loc[mk, col] = orow[col]

    return props


def load_team_win_totals(season: int) -> pd.Series:
    query = text("SELECT team_abbr, win_total_line FROM team_season_win_totals WHERE season_year = :season")
    df = pd.read_sql(query, engine, params={"season": season})
    return df.set_index("team_abbr")["win_total_line"]


def compute_rb_receiving_baseline_components() -> dict:
    """League-average receiving contribution for a real-role RB (median,
    2021-2025), used as a flat add-on for RBs where we have a Vegas
    *rushing* line but no receiving-yards prop to work with.

    This intentionally does NOT use the specific player's own last-season
    receiving total (that was an earlier bug here -- it made Christian
    McCaffrey's 102-catch 2025 season inflate his 2026 projection by ~150
    points on its own, reintroducing exactly the "previous performance"
    bias this model is supposed to avoid). A flat, position-wide baseline
    means real pass-catching specialists are probably underrated here --
    a known gap, not a hidden one, EXCEPT where a real Vegas rec_tds_line
    exists without a rec_yards_line (fantasypoints.com's receiving-TD
    article covers a few pass-catching backs -- Bijan Robinson, Jahmyr
    Gibbs, Christian McCaffrey -- even though their receiving-yards article
    is WR/TE only). Returned as yards/receptions/TDs components (not one
    bundled points total) specifically so the caller can swap in a real TD
    line while still using the baseline for yards/receptions -- see
    `rb_receiving_points()` below.
    """
    seasons_clause = ",".join(str(y) for y in CALIBRATION_SEASONS)
    query = text(f"""
        SELECT receptions, receiving_yards, receiving_tds
        FROM historical_player_stats
        WHERE week = 0 AND season_year IN ({seasons_clause}) AND position = 'RB' AND rushing_yards > 200
    """)
    df = pd.read_sql(query, engine)
    return {
        "median_yards": float(df["receiving_yards"].median()),
        "median_receptions": float(df["receptions"].median()),
        "median_tds": float(df["receiving_tds"].median()),
    }


def rb_receiving_points(baseline: dict, rec_tds_line: Optional[float]) -> float:
    """RB receiving points when there's no real Vegas receiving-*yards* line.
    Yards/receptions use the flat position baseline; TDs use the real Vegas
    line when one exists, else the baseline median. Team environment is NOT
    applied here -- it's handled once, at the VOR level, as a single capped
    favorability tie-breaker (see the ENV_* constants and main()), so baselines
    stay clean and environment is never counted twice.
    """
    yards_receptions_points = baseline["median_yards"] / 10.0 + baseline["median_receptions"] * 0.5
    if rec_tds_line is not None:
        return yards_receptions_points + rec_tds_line * 6.0
    return yards_receptions_points + baseline["median_tds"] * 6.0


def build_ecr_calibration_curve() -> pd.DataFrame:
    """For each position, the historical (2021-2025) relationship between
    preseason ECR position-rank and that season's actual PPR points. This
    is about the *rank's* general predictive value, not any specific
    player/team, so a rookie with a good rank gets full credit.

    Raw per-rank averages are noisy with only 5 seasons of data (e.g. a
    single season-ending injury at RB29 can make it score below RB35;
    small-sample QB averages jump around non-monotonically rank to rank).
    An isotonic (monotonic-decreasing) regression is fit on the raw
    player-seasons per position -- it's the statistically appropriate tool
    for "value should decrease as rank gets worse, but noisily" data, and
    removes that noise without hiding real positional shape differences
    (a flat curve stays flat, a steep drop-off stays steep).
    """
    seasons_clause = ",".join(str(y) for y in CALIBRATION_SEASONS)
    query = text(f"""
        SELECT c.position, c.ecr_position_rank, s.fantasy_points_half_ppr AS actual_points
        FROM fantasy_consensus_rankings c
        JOIN historical_player_stats s
          ON s.player_name = c.player_name AND s.season_year = c.season_year AND s.week = 0
        WHERE c.season_year IN ({seasons_clause}) AND c.position IN ('QB','RB','WR','TE')
    """)
    return pd.read_sql(query, engine)


def _kernel_smooth(ranks: np.ndarray, points: np.ndarray, bandwidth: float = 3.0):
    """Nadaraya-Watson kernel smoothing: at each integer rank, average
    nearby data points weighted by distance instead of only the (often
    tiny -- as few as 3 seasons) sample exactly at that rank. Rank 1 for
    QB, for example, only has 3 raw seasons in our data (all Mahomes/Allen,
    who never had a down year in this window) -- fit directly, that's an
    unreliable, survivorship-biased estimate with zero downside captured.
    Borrowing strength from ranks 2-6 as well gives a far more stable
    estimate without hiding the position's real shape.
    """
    query_ranks = np.arange(ranks.min(), ranks.max() + 1)
    smoothed = np.empty(len(query_ranks))
    for i, r in enumerate(query_ranks):
        weights = np.exp(-0.5 * ((ranks - r) / bandwidth) ** 2)
        smoothed[i] = np.sum(weights * points) / np.sum(weights)
    return query_ranks, smoothed


def make_calibration_lookup(raw: pd.DataFrame, rank_col: str = "ecr_position_rank"):
    fits = {}
    for pos in POSITIONS:
        sub = raw[raw["position"] == pos]
        if len(sub) < 5:
            continue
        smoothed_ranks, smoothed_points = _kernel_smooth(sub[rank_col].to_numpy(), sub["actual_points"].to_numpy())
        model = IsotonicRegression(increasing=False, out_of_bounds="clip")
        model.fit(smoothed_ranks, smoothed_points)
        fits[pos] = (model, smoothed_ranks.min(), smoothed_ranks.max())

    def lookup(position: str, rank: float) -> float:
        if position not in fits:
            return 100.0
        model, rank_min, rank_max = fits[position]
        clipped_rank = min(max(rank, rank_min), rank_max)
        return float(model.predict([clipped_rank])[0])

    return lookup


def build_actual_finish_curve() -> pd.DataFrame:
    """For each position, ACTUAL final-season rank (1st-best, 2nd-best, ...)
    vs. that season's actual points, across 2021-2025. Used ONLY for
    replacement level, not for projecting a specific player.

    This is deliberately different from build_ecr_calibration_curve(),
    which maps *preseason ADP rank* to actual points. ADP rank bakes in the
    market's bust/breakout uncertainty (e.g. the QB drafted 12th often
    ISN'T the 12th-best QB by year's end), so an ADP-based replacement
    level is biased low. Replacement level should reflect what's actually
    achievable via streaming/waivers in-season, which is a property of
    real final-season outcomes, not preseason forecasting accuracy.
    """
    seasons_clause = ",".join(str(y) for y in CALIBRATION_SEASONS)
    query = text(f"""
        SELECT position, season_year, fantasy_points_half_ppr
        FROM historical_player_stats
        WHERE week = 0 AND season_year IN ({seasons_clause}) AND position IN ('QB','RB','WR','TE')
    """)
    df = pd.read_sql(query, engine)
    df["actual_rank"] = df.groupby(["position", "season_year"])["fantasy_points_half_ppr"].rank(
        ascending=False, method="first"
    )
    return df.rename(columns={"fantasy_points_half_ppr": "actual_points"})


def compute_flex_adjusted_replacement_ranks(actual_finish_lookup) -> dict:
    """Replacement rank per position, given the real roster construction: 12
    teams x (1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX where FLEX is RB/WR/TE).

    QB has no flex competition, so it's simply NUM_TEAMS. For RB/WR/TE, we
    don't assume a fixed split of the 12 flex spots -- instead we simulate
    who'd actually win them: pool every RB ranked below the dedicated cutoff
    (24th), every WR below 24th, and every TE below 12th, using real
    actual-outcome points (comparable across positions here, since this is
    literally "who would a manager actually start", not a scarcity
    question), and take the top 12 by points. Whichever positions those 12
    slots go to determines each position's true effective replacement rank.
    """
    dedicated_cutoff = {pos: DEDICATED_STARTERS[pos] * NUM_TEAMS for pos in POSITIONS}
    total_flex_slots = FLEX_SLOTS_PER_TEAM * NUM_TEAMS

    remainder_pool = []
    for pos in FLEX_ELIGIBLE:
        for rank in range(dedicated_cutoff[pos] + 1, dedicated_cutoff[pos] + 60):
            remainder_pool.append((pos, rank, actual_finish_lookup(pos, rank)))

    remainder_pool.sort(key=lambda row: row[2], reverse=True)
    flex_winners = remainder_pool[:total_flex_slots]

    flex_count = {pos: 0 for pos in FLEX_ELIGIBLE}
    for pos, _, _ in flex_winners:
        flex_count[pos] += 1

    replacement_rank = {"QB": dedicated_cutoff["QB"]}
    for pos in FLEX_ELIGIBLE:
        replacement_rank[pos] = dedicated_cutoff[pos] + flex_count[pos]

    print(f"Flex allocation (of {total_flex_slots} spots), simulated from real outcomes: "
          f"RB={flex_count['RB']}, WR={flex_count['WR']}, TE={flex_count['TE']}")
    return replacement_rank


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    current = load_current_rankings()
    if current.empty:
        print("No current-season rankings found -- run scripts/ingest_historical_data.py first.")
        return

    prior_stats = load_prior_season_stats()
    props = load_player_props()
    win_totals = load_team_win_totals(RANKING_SEASON)
    league_avg_win_total = win_totals.mean()

    calibration_curve = build_ecr_calibration_curve()
    calibrated_points = make_calibration_lookup(calibration_curve)
    rb_receiving_baseline = compute_rb_receiving_baseline_components()

    actual_finish_curve = build_actual_finish_curve()
    actual_finish_lookup = make_calibration_lookup(actual_finish_curve, rank_col="actual_rank")
    replacement_rank = compute_flex_adjusted_replacement_ranks(actual_finish_lookup)
    # Streamable positions (QB/TE) are drafted against a low-end-starter baseline,
    # not the last starter -- see STREAMING_REPLACEMENT_RANK. Override the
    # roster-slot rank so their VOR reflects free-agent/streaming availability.
    for _pos, _rk in STREAMING_REPLACEMENT_RANK.items():
        replacement_rank[_pos] = _rk
    print(f"Streaming-adjusted replacement rank: QB{replacement_rank['QB']}, TE{replacement_rank['TE']} "
          "(waiver/stream baseline, not last starter)")

    df = current.set_index("merge_key")
    # The current-season consensus feed is authoritative for a player's team (it
    # already reflects offseason trades/signings, e.g. Waddle -> DEN). Use the
    # 2025 stats team ONLY as a fallback to fill a missing/NaN feed team -- never
    # to override it, or offseason movers get reverted to last year's roster.
    df["corrected_team_abbr"] = df["team_abbr"].combine_first(prior_stats["team_abbr"])
    df["team_win_total"] = df["corrected_team_abbr"].map(win_totals)

    # Component stat columns we surface alongside the point total, so the
    # graphics can print the projected stat line behind each player's number
    # (e.g. "1,180 rec yds / 8.5 TD / 92 rec"). Only populated for prop-derived
    # projections -- ECR-calibrated players have no per-stat breakdown, just a
    # points estimate, so their component columns stay blank.
    STAT_KEYS = ["proj_pass_yards", "proj_pass_tds", "proj_rush_yards",
                 "proj_rush_tds", "proj_rec_yards", "proj_rec_tds", "proj_receptions"]

    projected_points = []
    projection_sources = []
    stat_components = []
    for merge_key, row in df.iterrows():
        prop_row = props.loc[merge_key] if merge_key in props.index else None

        points = None
        source = "ecr_calibrated"
        comp = {k: np.nan for k in STAT_KEYS}

        if prop_row is not None:
            if row["position"] in ("WR", "TE") and pd.notna(prop_row.get("rec_yards_line")):
                result = implied_receiving_points(
                    prop_row["rec_yards_line"],
                    prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None,
                    row["position"],
                    receptions_line=prop_row["receptions_line"] if pd.notna(prop_row.get("receptions_line")) else None,
                )
                points = result["points"]
                source = "vegas_prop"
                comp["proj_rec_yards"] = prop_row["rec_yards_line"]
                comp["proj_rec_tds"] = result["implied_tds"]
                comp["proj_receptions"] = result["implied_receptions"]
            elif row["position"] == "RB" and pd.notna(prop_row.get("rush_yards_line")):
                rush = implied_rushing_points(
                    prop_row["rush_yards_line"],
                    prop_row["rush_tds_line"] if pd.notna(prop_row.get("rush_tds_line")) else None,
                )
                comp["proj_rush_yards"] = prop_row["rush_yards_line"]
                comp["proj_rush_tds"] = rush["implied_tds"]
                if pd.notna(prop_row.get("rec_yards_line")):
                    # A real Vegas receiving line exists for this RB -- use it
                    # directly, same as WR/TE. This is a forward-looking market
                    # signal, not "previous performance," so it's preferred
                    # over the flat baseline below.
                    rec = implied_receiving_points(
                        prop_row["rec_yards_line"],
                        prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None,
                        "RB",
                        receptions_line=prop_row["receptions_line"] if pd.notna(prop_row.get("receptions_line")) else None,
                    )
                    receiving_points = rec["points"]
                    comp["proj_rec_yards"] = prop_row["rec_yards_line"]
                    comp["proj_rec_tds"] = rec["implied_tds"]
                    comp["proj_receptions"] = rec["implied_receptions"]
                else:
                    # No Vegas receiving-yards line for this RB -- flat
                    # position-wide baseline for yards/receptions, NOT this
                    # player's own last-season receiving total. Still uses a
                    # real Vegas rec_tds_line when one exists (a few
                    # pass-catching backs have a real TD line without a
                    # yards line) instead of a baseline TD guess -- see
                    # rb_receiving_points().
                    rec_tds = prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None
                    receiving_points = rb_receiving_points(rb_receiving_baseline, rec_tds)
                    comp["proj_rec_yards"] = rb_receiving_baseline["median_yards"]
                    comp["proj_receptions"] = rb_receiving_baseline["median_receptions"]
                    comp["proj_rec_tds"] = rec_tds if rec_tds is not None else rb_receiving_baseline["median_tds"]
                points = rush["points"] + receiving_points
                source = "vegas_prop"
            elif (row["position"] == "QB" and pd.notna(prop_row.get("pass_yards_line"))
                  and pd.notna(prop_row.get("pass_tds_line"))):
                passing = implied_passing_points(prop_row["pass_yards_line"], prop_row["pass_tds_line"])
                comp["proj_pass_yards"] = prop_row["pass_yards_line"]
                comp["proj_pass_tds"] = prop_row["pass_tds_line"]
                if pd.notna(prop_row.get("rush_yards_line")):
                    # A real Vegas rushing line exists for this QB (the
                    # current season's mobile-QB tier) -- use it directly.
                    qb_rush = implied_rushing_points(
                        prop_row["rush_yards_line"],
                        prop_row["rush_tds_line"] if pd.notna(prop_row.get("rush_tds_line")) else None,
                        position="QB",
                    )
                    rushing_points = qb_rush["points"]
                    comp["proj_rush_yards"] = prop_row["rush_yards_line"]
                    comp["proj_rush_tds"] = qb_rush["implied_tds"]
                else:
                    # No Vegas rushing line -- "pocket passer" flat baseline,
                    # not this QB's own last-season rushing total. Split the
                    # baseline POINTS back into displayable yds/TD components
                    # using the league-avg QB yards-per-rush-TD, so
                    # yards/10 + tds*6 == the baseline points exactly (the
                    # point total is unchanged; this only fills the stat line).
                    rushing_points = QB_POCKET_PASSER_RUSHING_BASELINE
                    ypt = LEAGUE_AVG_RUSH_YARDS_PER_TD["QB"]
                    base_rush_yards = rushing_points / (0.1 + 6.0 / ypt)
                    comp["proj_rush_yards"] = base_rush_yards
                    comp["proj_rush_tds"] = base_rush_yards / ypt
                points = passing["points"] + rushing_points
                source = "vegas_prop"

        if points is None:
            points = calibrated_points(row["position"], row["ecr_position_rank"])

        projected_points.append(points)
        projection_sources.append(source)
        stat_components.append(comp)

    df["projected_ppr_points"] = projected_points
    df["projection_source"] = projection_sources
    comp_df = pd.DataFrame(stat_components, index=df.index)
    for k in STAT_KEYS:
        df[k] = comp_df[k]

    # Replacement level from ACTUAL historical final-season outcomes at each
    # rank (see build_actual_finish_curve docstring) -- not from our own
    # generated projections, which would be circular, and not from the
    # ADP-rank curve, which understates replacement level because it bakes
    # in preseason bust/breakout uncertainty.
    replacement_points = {pos: actual_finish_lookup(pos, replacement_rank[pos]) for pos in POSITIONS}
    df["replacement_points_at_position"] = df["position"].map(replacement_points)
    df["vor"] = df["projected_ppr_points"] - df["replacement_points_at_position"]

    # Team-environment favorability: a position-scaled, capped premium on VOR for
    # players in strong projected scoring environments (and a penalty for weak
    # ones) -- the win / projected-points tie-breaker. Projected team points come
    # from the win-total line (TEAM_POINTS_PER_WIN); the effect is expressed
    # relative to the league-average environment, scaled per position by how much
    # a position's fantasy points actually move with team points, dampened
    # (ENV_STRENGTH) since Vegas medians already price most of it, and capped
    # (ENV_CAP_WINS). Added to VOR -- never multiplied into the Vegas lines -- so
    # it only tips genuinely close calls (favor the better team) rather than
    # re-projecting anyone. Applied before the games-missed scaling so a player's
    # environment upside is pro-rated for missed time too.
    points_env = TEAM_POINTS_PER_WIN * (df["team_win_total"] - league_avg_win_total)
    env_coeff = df["position"].map(ENV_FPTS_PER_TEAM_POINT).fillna(0.0)
    env_cap = env_coeff * TEAM_POINTS_PER_WIN * ENV_CAP_WINS
    df["team_env_adj"] = np.clip(ENV_STRENGTH * env_coeff * points_env, -env_cap, env_cap)
    df["team_env_adj"] = df["team_env_adj"].fillna(0.0)
    df["vor"] = df["vor"] + df["team_env_adj"]

    # Games-missed adjustment (df is still indexed by merge_key here).
    # A player who will miss G games keeps only (17-G)/17 of his VALUE OVER
    # REPLACEMENT, because the missed weeks are backfilled at replacement level.
    # We scale VOR, NOT raw points: naively prorating points would compare a
    # partial-season total against a full-season replacement and massively
    # over-penalize an elite player for a short absence. projected_ppr_points is
    # left as the healthy full-season projection (a talent/role signal);
    # games_missed is surfaced so the lower VOR is self-explanatory.
    availability = load_availability()
    df["games_missed"] = [availability.get(mk, 0.0) for mk in df.index]
    df["vor"] = df["vor"] * (GAMES_IN_SEASON - df["games_missed"]) / GAMES_IN_SEASON

    df = df.sort_values("vor", ascending=False).reset_index(drop=True)
    df["our_rank"] = df.index + 1
    df["value_vs_adp"] = df["ecr_overall_rank"] - df["our_rank"]

    out_cols = [
        "our_rank", "player_name", "position", "corrected_team_abbr", "vor",
        "projected_ppr_points", "games_missed", "team_env_adj", "projection_source",
        "ecr_overall_rank", "ecr_position_rank", "value_vs_adp", "team_win_total",
        "replacement_points_at_position",
        "proj_pass_yards", "proj_pass_tds", "proj_rush_yards", "proj_rush_tds",
        "proj_rec_yards", "proj_rec_tds", "proj_receptions",
    ]
    result = df[out_cols].rename(columns={"corrected_team_abbr": "team_abbr"})

    out_path = os.path.join(OUTPUT_DIR, f"player_rankings_{RANKING_SEASON}.csv")
    result.to_csv(out_path, index=False)

    # Archive a timestamped copy of every run (never overwritten) so
    # analysis/ranking_diff_report.py can show exactly how rankings changed
    # between two runs -- the "latest" CSV above alone can't support that
    # once the next run overwrites it.
    history_dir = os.path.join(OUTPUT_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)
    run_timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive_path = os.path.join(history_dir, f"player_rankings_{RANKING_SEASON}_{run_timestamp}.csv")
    result.to_csv(archive_path, index=False)

    print("=" * 100)
    print(f"REPLACEMENT LEVEL BY POSITION (12-team PPR, flex-simulated: QB{replacement_rank['QB']}, "
          f"RB{replacement_rank['RB']}, WR{replacement_rank['WR']}, TE{replacement_rank['TE']})")
    print("=" * 100)
    for pos in POSITIONS:
        print(f"  {pos}: {replacement_points[pos]:.1f} pts")

    print("\n" + "=" * 100)
    print(f"TOP 30 OVERALL BY VALUE OVER REPLACEMENT (VOR) -- {RANKING_SEASON}")
    print("=" * 100)
    print(result.head(30).to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    print("\n" + "=" * 100)
    print("QB POSITIONAL COST-BENEFIT CHECK")
    print("=" * 100)
    qb_check = result[result["position"] == "QB"].head(8)
    print(qb_check.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    print("\n" + "=" * 100)
    print("BIGGEST VALUES (we rank them meaningfully higher than current ADP/ECR)")
    print("=" * 100)
    # Restricted to VOR > 0 (i.e. our own model considers them startable-caliber).
    # Below replacement level, "value_vs_adp" is not a meaningful signal: a
    # mediocre TE (shallow position, low replacement bar) will always look
    # like a bigger "value" than a mediocre QB (deep positional spread, high
    # replacement bar) purely because of where each position's replacement
    # level sits, not because either is actually worth rostering.
    print(result[(result["our_rank"] <= 150) & (result["vor"] > 0)].nlargest(10, "value_vs_adp").to_string(
        index=False, float_format=lambda x: f"{x:.1f}"))

    print("\n" + "=" * 100)
    print("BIGGEST FADES (we rank them meaningfully lower than current ADP/ECR)")
    print("=" * 100)
    print(result[(result["ecr_overall_rank"] <= 100) & (result["vor"] > 0)].nsmallest(10, "value_vs_adp").to_string(
        index=False, float_format=lambda x: f"{x:.1f}"))

    print("\n" + "=" * 100)
    print("ROOKIE CHECK -- notable rookies, no penalty for lacking NFL history")
    print("=" * 100)
    rookie_names = ["jeremiyah love", "ashton jeanty", "tetairoa mcmillan", "colston loveland",
                     "omarion hampton", "quinshon judkins", "cam ward", "travis hunter"]
    rookies = result[result["player_name"].apply(lambda n: normalize_name(n) in rookie_names)]
    print(rookies.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    vegas_covered = (result["projection_source"] == "vegas_prop").sum()
    print(f"\n{vegas_covered} of {len(result)} players ({vegas_covered / len(result) * 100:.0f}%) "
          f"use a real Vegas prop-derived projection; the rest use the ECR-rank-calibrated baseline.")
    print(f"Full rankings written to {out_path}")
    print(f"Archived this run to {archive_path} (for analysis/ranking_diff_report.py)")


if __name__ == "__main__":
    main()
