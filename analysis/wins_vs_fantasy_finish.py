#!/usr/bin/env python3
"""
Does a winning team environment raise a player's fantasy CEILING?

This is the upside question, not the point-mapping question. The decision it's
meant to inform: if two players project within ~5-15 points of each other but
one is on a team projected for ~4 more wins, is the higher-win player the better
pick because of upside? To answer it we look at ACTUAL fantasy finishes
(2021-2025) three ways:

  1. Composition -- where do top-5 / top-10 positional finishers actually come
     from? Are elite finishes only available on good teams, or can a top-10 RB
     come off a 5-win team?
  2. Upside curve -- among each team's LEAD player at a position, how does the
     probability of a top-10 finish (and the mean finish) change by team-win
     tier? And how does that gradient differ across QB/RB/WR/TE?
  3. Volume-controlled upside (the actual decision rule) -- holding OPPORTUNITY
     roughly constant (touches/targets, the closest proxy for "same
     projection"), how many extra fantasy points does each additional team win
     buy? That's the real "same cost, more ceiling" number, and it flows
     straight from the prior finding that wins convert to TDs, not yards.

Run with the analysis venv:
  venv_data\\Scripts\\python.exe analysis\\wins_vs_fantasy_finish.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.database import engine

SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ["QB", "RB", "WR", "TE"]
MIN_GAMES = 6  # exclude tiny-sample injury seasons from pools/regressions

WIN_TIER_BINS = [-0.1, 6.5, 9.5, 20]
WIN_TIER_LABELS = ["bad (<=6 W)", "avg (7-9 W)", "good (10+ W)"]


def _seasons_clause() -> str:
    return ",".join(str(s) for s in SEASONS)


def load_data() -> pd.DataFrame:
    players = pd.read_sql(text(
        f"SELECT player_name, position, team_abbr, season_year, games_played, "
        f"attempts, carries, targets, receptions, "
        f"rushing_tds, receiving_tds, passing_tds, "
        f"fantasy_points_half_ppr AS pts "
        f"FROM historical_player_stats "
        f"WHERE week = 0 AND season_type = 'REG' AND season_year IN ({_seasons_clause()})"
    ), engine)
    wins = pd.read_sql(text(
        f"SELECT team_abbr, season_year, wins, points_for FROM season_final_records "
        f"WHERE season_year IN ({_seasons_clause()})"
    ), engine)

    df = players[players["position"].isin(POSITIONS)].merge(
        wins, on=["team_abbr", "season_year"], how="inner"
    )
    df["pts"] = df["pts"].fillna(0.0)
    # Positional finish rank within each season (1 = best that year).
    df["finish_rank"] = df.groupby(["season_year", "position"])["pts"].rank(
        ascending=False, method="min"
    )
    # Total touchdowns (the win-sensitive component, from wins_vs_production.py).
    df["total_tds"] = df[["rushing_tds", "receiving_tds", "passing_tds"]].fillna(0).sum(axis=1)
    # Opportunity proxy per position.
    df["touches"] = np.select(
        [df["position"] == "QB", df["position"] == "RB"],
        [df["attempts"].fillna(0) + df["carries"].fillna(0),
         df["carries"].fillna(0) + df["targets"].fillna(0)],
        default=df["targets"].fillna(0),
    )
    df["win_tier"] = pd.cut(df["wins"], bins=WIN_TIER_BINS, labels=WIN_TIER_LABELS)
    return df


def section_composition(df: pd.DataFrame):
    print("\n" + "=" * 88)
    print("1. WHERE DO ELITE FINISHERS COME FROM?  (team wins of top-N positional finishers)")
    print("=" * 88)
    rows = []
    for pos in POSITIONS:
        sub = df[df["position"] == pos]
        for n in (5, 10):
            top = sub[sub["finish_rank"] <= n]
            for label in WIN_TIER_LABELS:
                share = 100.0 * (top["win_tier"] == label).mean()
                rows.append({"pos": pos, "topN": f"top-{n}", "win_tier": label,
                             "pct_of_finishers": share})
    comp = pd.DataFrame(rows).pivot_table(
        index=["pos", "topN"], columns="win_tier", values="pct_of_finishers"
    ).reindex(columns=WIN_TIER_LABELS)
    print(comp.to_string(float_format=lambda v: f"{v:4.0f}%"))

    print("\nMean / min team wins among top-10 finishers, by position:")
    for pos in POSITIONS:
        top = df[(df["position"] == pos) & (df["finish_rank"] <= 10)]
        print(f"  {pos}: mean {top['wins'].mean():4.1f} W, median {top['wins'].median():4.1f} W, "
              f"min {top['wins'].min():4.1f} W  (n={len(top)})")

    print("\nCan a top-10 RB come off a bad (<=6 win) team? Every instance, 2021-2025:")
    bad = df[(df["position"] == "RB") & (df["finish_rank"] <= 10) & (df["wins"] <= 6)]
    bad = bad.sort_values(["season_year", "finish_rank"])
    if bad.empty:
        print("  (none -- top-10 RBs never came from a <=6 win team)")
    else:
        for _, r in bad.iterrows():
            print(f"  {int(r['season_year'])}  RB{int(r['finish_rank']):>2}  {r['player_name']:<22} "
                  f"{r['team_abbr']:<3} {r['wins']:.0f} W, {r['pts']:.0f} pts")


def section_upside_curve(df: pd.DataFrame):
    print("\n" + "=" * 88)
    print("2. UPSIDE CURVE -- team LEAD player at each position: P(top-10 finish) & mean finish")
    print("=" * 88)
    pool = df[df["games_played"] >= MIN_GAMES].copy()
    # Each team's top scorer at the position that season = the "lead" (WR1/RB1/etc.)
    lead_idx = pool.groupby(["season_year", "team_abbr", "position"])["pts"].idxmax()
    leads = pool.loc[lead_idx].copy()
    leads["top10"] = (leads["finish_rank"] <= 10).astype(float)

    rows = []
    for pos in POSITIONS:
        sub = leads[leads["position"] == pos]
        for label in WIN_TIER_LABELS:
            t = sub[sub["win_tier"] == label]
            if len(t) == 0:
                continue
            rows.append({"pos": pos, "win_tier": label, "n_leads": len(t),
                         "pct_top10": 100.0 * t["top10"].mean(),
                         "mean_finish": t["finish_rank"].mean()})
    tab = pd.DataFrame(rows)
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.1f}"))

    print("\nUpside lift (good-team minus bad-team P(top-10) for the lead player):")
    for pos in POSITIONS:
        sub = leads[leads["position"] == pos]
        good = sub[sub["win_tier"] == "good (10+ W)"]["top10"].mean() * 100
        bad = sub[sub["win_tier"] == "bad (<=6 W)"]["top10"].mean() * 100
        print(f"  {pos}: {bad:4.0f}% -> {good:4.0f}%   (lift {good - bad:+4.0f} pts)")


def ols_coeffs(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def ols_fit(X: np.ndarray, y: np.ndarray):
    """Return (coeffs, R^2)."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    return beta, r2


def section_points_vs_wins(df: pd.DataFrame):
    """The user's question: is projected TEAM POINTS a more direct signal for
    fantasy production than wins? Compare, volume-controlled, per position."""
    print("\n" + "=" * 88)
    print("4. TEAM POINTS vs WINS as the environment signal (which predicts fantasy better?)")
    print("=" * 88)
    pool = df[(df["games_played"] >= MIN_GAMES) & (df["touches"] > 0)]
    rows = []
    for pos in POSITIONS:
        sub = pool[pool["position"] == pos]
        if len(sub) < 20:
            continue
        touches = sub["touches"].to_numpy(float)
        y = sub["pts"].to_numpy(float)
        ones = np.ones(len(sub))
        # Model A: touches + wins ; Model B: touches + points_for
        _, r2_w = ols_fit(np.column_stack([ones, touches, sub["wins"].to_numpy(float)]), y)
        beta_p, r2_p = ols_fit(np.column_stack([ones, touches, sub["points_for"].to_numpy(float)]), y)
        rows.append({"pos": pos, "n": len(sub),
                     "R2_touch+wins": r2_w, "R2_touch+points": r2_p,
                     "fpts_per_team_point": beta_p[2],
                     "fpts_per_+50_pts": beta_p[2] * 50})
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    # Team points ~ wins map, used to turn a 2026 win-total line into projected
    # team points (the only 2026 team signal we have is the win total).
    team = df[["team_abbr", "season_year", "wins", "points_for"]].drop_duplicates()
    beta, r2 = ols_fit(np.column_stack([np.ones(len(team)), team["wins"].to_numpy(float)]),
                       team["points_for"].to_numpy(float))
    print(f"\nWin-total -> projected team points map (2021-2025):")
    print(f"  points_for = {beta[0]:.1f} + {beta[1]:.1f} * wins   (R^2 = {r2:.2f})")
    print(f"  e.g. a 6-win team ~ {beta[0] + beta[1]*6:.0f} pts, "
          f"an 11-win team ~ {beta[0] + beta[1]*11:.0f} pts "
          f"(spread ~{beta[1]*5:.0f} pts over 5 wins).")


def section_volume_controlled(df: pd.DataFrame):
    print("\n" + "=" * 88)
    print("3. VOLUME-CONTROLLED UPSIDE -- extra fantasy points per win at EQUAL opportunity")
    print("=" * 88)
    print("Model per position:  season_pts ~ intercept + b*touches + c*wins")
    print("c = extra half-PPR points from +1 team win, holding touches/targets constant.\n")
    pool = df[(df["games_played"] >= MIN_GAMES) & (df["touches"] > 0)]
    rows = []
    for pos in POSITIONS:
        sub = pool[pool["position"] == pos]
        if len(sub) < 20:
            continue
        X = np.column_stack([np.ones(len(sub)), sub["touches"].to_numpy(float),
                             sub["wins"].to_numpy(float)])
        y = sub["pts"].to_numpy(float)
        _, b_touch, c_win = ols_coeffs(X, y)
        # Also: extra TDs per win at equal volume (why the points show up).
        Xt = X
        _, _, c_win_td = ols_coeffs(Xt, sub["total_tds"].to_numpy(float))
        rows.append({"pos": pos, "n": len(sub),
                     "pts_per_touch": b_touch,
                     "pts_per_win@equal_vol": c_win,
                     "pts_per_4wins": c_win * 4,
                     "tds_per_win@equal_vol": c_win_td})
    tab = pd.DataFrame(rows)
    print(tab.to_string(index=False, float_format=lambda v: f"{v:.2f}"))

    print("\nDescriptive check -- points per touch by win tier (efficiency rises with wins?):")
    for pos in POSITIONS:
        sub = pool[pool["position"] == pos].copy()
        sub["ppt"] = sub["pts"] / sub["touches"]
        means = sub.groupby("win_tier", observed=True)["ppt"].mean().reindex(WIN_TIER_LABELS)
        vals = "  ".join(f"{lbl.split()[0]}:{means[lbl]:.2f}" for lbl in WIN_TIER_LABELS if lbl in means)
        print(f"  {pos}: {vals}")


def main():
    df = load_data()
    n_team_seasons = df[["team_abbr", "season_year"]].drop_duplicates().shape[0]
    print(f"Sample: {len(df)} player-seasons across {n_team_seasons} team-seasons "
          f"({min(SEASONS)}-{max(SEASONS)}).")

    section_composition(df)
    section_upside_curve(df)
    section_volume_controlled(df)
    section_points_vs_wins(df)

    print("\n" + "=" * 88)
    print("TAKEAWAYS (decision rule: favor the higher-win player among similar projections?)")
    print("=" * 88)
    print("- Section 3's 'pts_per_4wins' is the direct answer: if it exceeds the projected-")
    print("  points gap between two similar players, prefer the higher-win team for upside.")
    print("- Section 1 shows whether elite finishes are gated by team quality (composition),")
    print("  and Section 2 shows how much a winning environment lifts a lead player's ceiling.")
    print("- Compare the gradient across positions: the steeper the lift/pts-per-win, the")
    print("  more team wins should tie-break your ranking at that position.")


if __name__ == "__main__":
    main()
