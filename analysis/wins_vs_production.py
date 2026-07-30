#!/usr/bin/env python3
"""
How does a team's win total actually relate to player production?

An early version of the ranking model applied a flat "+3% per win above
average" multiplier to baseline projections. That 0.03 was a guess, and it
implicitly assumes every stat scales with wins the same way. It doesn't:
winning teams run more and score more rushing/passing TDs (positive game
script), while raw passing/receiving YARDS barely move with wins (losing teams
throw a lot in garbage time). This script measured the real relationship from
2021-2025 (the 17-game era, so win totals are on one scale). It has since been
superseded by the points-based, per-position team-environment tie-breaker (see
analysis/wins_vs_fantasy_finish.py and the ENV_* constants in
player_ranking_v1.py); this script remains the record of *why* a flat, uniform
win factor was the wrong shape.

For each metric we report, across ~160 team-seasons:
  - r        : Pearson correlation with team wins
  - per_win  : OLS slope (units of the metric per +1 win)
  - %/win    : per_win as a percent of the metric's mean (directly comparable
               to the model's current 3%/win)

Run with the analysis venv:
  venv_data\\Scripts\\python.exe analysis\\wins_vs_production.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.database import engine

SEASONS = (2021, 2022, 2023, 2024, 2025)  # 17-game era -> comparable win totals
POSITIONS = ["QB", "RB", "WR", "TE"]

TEAM_VOLUME_METRICS = [
    "passing_yards", "passing_tds", "rushing_yards", "rushing_tds",
    "receptions", "receiving_yards", "receiving_tds",
]


def _seasons_clause() -> str:
    return ",".join(str(s) for s in SEASONS)


def load_wins() -> pd.DataFrame:
    return pd.read_sql(text(
        f"SELECT team_abbr, season_year, wins, points_for "
        f"FROM season_final_records WHERE season_year IN ({_seasons_clause()})"
    ), engine)


def load_player_seasons() -> pd.DataFrame:
    return pd.read_sql(text(
        f"SELECT team_abbr, season_year, position, passing_yards, passing_tds, "
        f"rushing_yards, rushing_tds, receptions, receiving_yards, receiving_tds, "
        f"fantasy_points_half_ppr AS pts "
        f"FROM historical_player_stats "
        f"WHERE week = 0 AND season_type = 'REG' AND season_year IN ({_seasons_clause()})"
    ), engine)


def fit(x: pd.Series, y: pd.Series) -> dict:
    """Pearson r + linear slope of y on x, plus slope as a % of y's mean."""
    mask = x.notna() & y.notna()
    x, y = x[mask].to_numpy(float), y[mask].to_numpy(float)
    if len(x) < 5 or x.std() == 0 or y.std() == 0:
        return {"n": len(x), "r": float("nan"), "per_win": float("nan"), "pct_per_win": float("nan")}
    slope, _ = np.polyfit(x, y, 1)
    r = float(np.corrcoef(x, y)[0, 1])
    mean_y = y.mean()
    return {
        "n": len(x),
        "r": r,
        "per_win": float(slope),
        "pct_per_win": float(100.0 * slope / mean_y) if mean_y else float("nan"),
    }


def print_table(title: str, rows: list):
    print("\n" + "=" * 84)
    print(title)
    print("=" * 84)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def tier_means(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Mean of value_col split by win tier -- shows the SHAPE (linear? flat then
    jump?) that a single correlation number hides."""
    bins = [-0.1, 6.5, 9.5, 20]
    labels = ["<=6 wins", "7-9 wins", "10+ wins"]
    t = df.copy()
    t["win_tier"] = pd.cut(t["wins"], bins=bins, labels=labels)
    out = t.groupby("win_tier", observed=True)[value_col].agg(["mean", "count"]).reset_index()
    out = out.rename(columns={"mean": f"avg_{value_col}", "count": "team_seasons"})
    return out


def main():
    wins = load_wins()
    players = load_player_seasons()

    # ---- Team offensive totals per season (sum of all players on the team) ----
    team_totals = players.groupby(["team_abbr", "season_year"], as_index=False)[TEAM_VOLUME_METRICS].sum()
    team = team_totals.merge(wins, on=["team_abbr", "season_year"], how="inner")
    print(f"Sample: {len(team)} team-seasons ({min(SEASONS)}-{max(SEASONS)}), "
          f"{team['team_abbr'].nunique()} teams.")

    vol_rows = []
    for m in TEAM_VOLUME_METRICS:
        f = fit(team["wins"], team[m])
        vol_rows.append({"metric": m, "n": f["n"], "r": f["r"],
                         "per_win": f["per_win"], "%/win": f["pct_per_win"]})
    # Reference: points scored (should be strongly tied to wins) and how the
    # model's flat +3%/win compares.
    f_pts = fit(team["wins"], team["points_for"])
    vol_rows.append({"metric": "points_for (team)", "n": f_pts["n"], "r": f_pts["r"],
                     "per_win": f_pts["per_win"], "%/win": f_pts["pct_per_win"]})
    print_table("TEAM OFFENSIVE VOLUME vs WINS  (2021-2025)", vol_rows)

    # ---- Fantasy points by position group per team-season vs wins ----
    pos = players[players["position"].isin(POSITIONS)]
    pos_totals = pos.groupby(["team_abbr", "season_year", "position"], as_index=False)["pts"].sum()
    pos_totals = pos_totals.merge(wins[["team_abbr", "season_year", "wins"]],
                                  on=["team_abbr", "season_year"], how="inner")

    pos_rows = []
    for p in POSITIONS:
        sub = pos_totals[pos_totals["position"] == p]
        f = fit(sub["wins"], sub["pts"])
        pos_rows.append({"position": p, "n": f["n"], "r": f["r"],
                         "half_ppr_pts_per_win": f["per_win"], "%/win": f["pct_per_win"]})
    print_table("POSITION-GROUP FANTASY POINTS (half-PPR) vs WINS", pos_rows)

    # ---- Shape check: tier means for the two extremes (pass yds vs rush yds) ----
    print("\n" + "=" * 84)
    print("SHAPE CHECK -- team totals by win tier (is it linear, or a threshold?)")
    print("=" * 84)
    for m in ["passing_yards", "rushing_yards", "rushing_tds", "passing_tds"]:
        print(f"\n{m}:")
        print(tier_means(team, m).to_string(index=False, float_format=lambda v: f"{v:.1f}"))

    # ---- Bottom line ----
    rush_pct = next(r["%/win"] for r in vol_rows if r["metric"] == "rushing_yards")
    pass_pct = next(r["%/win"] for r in vol_rows if r["metric"] == "passing_yards")
    print("\n" + "=" * 84)
    print("TAKEAWAYS")
    print("=" * 84)
    print(f"- An early model version assumed a FLAT +3.0%/win on all baseline points.")
    print(f"- Reality is not 1:1 and not uniform: rushing yards move ~{rush_pct:.1f}%/win, "
          f"passing yards ~{pass_pct:.1f}%/win.")
    print(f"- Rushing volume/TDs and passing TDs scale with wins (positive game script);")
    print(f"  raw passing/receiving yards barely do (losing teams throw in garbage time).")
    print(f"- Implication: a single flat multiplier over-credits pass-heavy production on")
    print(f"  good teams and under-credits it on bad ones. A per-category (or at least")
    print(f"  per-position) win factor calibrated to the %/win above is more defensible.")


if __name__ == "__main__":
    main()
