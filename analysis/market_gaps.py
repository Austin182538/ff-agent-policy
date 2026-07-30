#!/usr/bin/env python3
"""
Market-gap finder: where is a player a VALUE because the market underrates his
environment?

The spot we're hunting (per the draft logic): two same-position players with
close Vegas-implied projections, but one is (a) going meaningfully later in ADP
AND (b) on a team projected for more wins (a better scoring environment ->
more ceiling). That player is the buy: similar expected production, cheaper
cost, better upside. The market (ADP/ECR) tends to under-price the team-
environment edge, which is exactly the inefficiency the ranking model's
team_env_adj is built on -- this tool makes those pairs explicit.

For every qualifying pair (expensive A vs cheaper B), we require:
  - both projected from real Vegas prop lines (apples-to-apples),
  - |proj_pts(A) - proj_pts(B)| <= PROJ_THRESHOLD  (close production),
  - adp_gap = ecr_rank(B) - ecr_rank(A) >= ADP_GAP  (B is cheaper / later),
  - win_gap = wins(B) - wins(A) >= WIN_GAP           (B has the better team).

Run with the analysis venv (after a ranking run):
  venv_data\\Scripts\\python.exe analysis\\market_gaps.py
  venv_data\\Scripts\\python.exe analysis\\market_gaps.py --proj 10 --adp-gap 5 --win-gap 2
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")
OUT_CSV = os.path.join(PROJECT_ROOT, "outputs", "market_gaps_2026.csv")

POSITIONS = ["QB", "RB", "WR", "TE"]

# Scoring weights for how attractive a gap is (all transparent/tunable).
# ADP picks and wins live on very different scales (an ADP gap can be 70+, a win
# gap maxes ~7), so raw addition lets deep sleepers swamp the true environment-
# edge spots. We therefore weight wins heavily and CAP the ADP contribution
# (ADP_SCORE_CAP) -- past that, "very cheap" has diminishing marginal signal --
# so a genuine win/environment edge competes with a big price discount.
#   +4 per extra projected win, +1 per ADP pick of discount (capped),
#   +0.2 per proj pt that B projects ABOVE A (negative if below).
W_ADP, W_WIN, W_PROJ = 1.0, 4.0, 0.2
ADP_SCORE_CAP = 40.0


def load_rankings() -> pd.DataFrame:
    df = pd.read_csv(RANKINGS_CSV)
    df = df[df["projection_source"] == "vegas_prop"]
    df = df[df["ecr_overall_rank"].notna() & df["team_win_total"].notna()
            & df["projected_ppr_points"].notna()]
    return df


def find_gaps(df: pd.DataFrame, proj_threshold: float, adp_gap: float,
              win_gap: float, ecr_cap: float) -> pd.DataFrame:
    df = df[df["ecr_overall_rank"] <= ecr_cap]
    rows = []
    for pos in POSITIONS:
        sub = df[df["position"] == pos]
        recs = sub.to_dict("records")
        for a in recs:            # A = the more expensive (earlier ADP) player
            for b in recs:        # B = the potential value (later ADP, better team)
                if a["player_name"] == b["player_name"]:
                    continue
                gap_adp = b["ecr_overall_rank"] - a["ecr_overall_rank"]
                gap_win = b["team_win_total"] - a["team_win_total"]
                proj_diff = b["projected_ppr_points"] - a["projected_ppr_points"]
                if gap_adp < adp_gap or gap_win < win_gap or abs(proj_diff) > proj_threshold:
                    continue
                score = (W_ADP * min(gap_adp, ADP_SCORE_CAP)
                         + W_WIN * gap_win + W_PROJ * proj_diff)
                rows.append({
                    "position": pos,
                    "value_player": b["player_name"], "value_team": b["team_abbr"],
                    "value_adp": b["ecr_overall_rank"], "value_wins": b["team_win_total"],
                    "value_proj": b["projected_ppr_points"], "value_our_rank": b["our_rank"],
                    "vs_player": a["player_name"], "vs_team": a["team_abbr"],
                    "vs_adp": a["ecr_overall_rank"], "vs_wins": a["team_win_total"],
                    "vs_proj": a["projected_ppr_points"],
                    "adp_gap": gap_adp, "win_gap": gap_win, "proj_diff": proj_diff,
                    "score": score,
                })
    gaps = pd.DataFrame(rows)
    if gaps.empty:
        return gaps
    # Keep each value player's single strongest comparison, then rank by score.
    gaps = gaps.sort_values("score", ascending=False).drop_duplicates("value_player")
    return gaps.reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proj", type=float, default=15.0, help="Max projected-points gap")
    parser.add_argument("--adp-gap", type=float, default=3.0, help="Min ADP (ECR) positions later")
    parser.add_argument("--win-gap", type=float, default=1.0, help="Min extra projected wins")
    parser.add_argument("--ecr-cap", type=float, default=150.0, help="Only consider ECR <= this")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    df = load_rankings()
    gaps = find_gaps(df, args.proj, args.adp_gap, args.win_gap, args.ecr_cap)

    print("=" * 96)
    print("MARKET GAPS -- similar Vegas projection, cheaper ADP, BETTER team (more wins)")
    print(f"(|proj gap| <= {args.proj:.0f} pts, >= {args.adp_gap:.0f} picks later in ADP, "
          f">= {args.win_gap:.0f} more wins)")
    print("=" * 96)
    if gaps.empty:
        print("No qualifying gaps at these thresholds -- try loosening (--proj / --adp-gap / --win-gap).")
        return

    for _, r in gaps.head(args.top).iterrows():
        proj_note = (f"projects {r['proj_diff']:+.0f} pts vs him"
                     if abs(r["proj_diff"]) >= 1 else "same projection")
        print(f"\n{r['position']}  VALUE: {r['value_player']} ({r['value_team']}, "
              f"{r['value_wins']:.1f} W)  vs  {r['vs_player']} ({r['vs_team']}, {r['vs_wins']:.1f} W)")
        print(f"   ~{r['adp_gap']:.0f} picks CHEAPER in ADP "
              f"(ADP {r['value_adp']:.0f} vs {r['vs_adp']:.0f}), "
              f"+{r['win_gap']:.0f} more projected wins, {proj_note} "
              f"({r['value_proj']:.0f} vs {r['vs_proj']:.0f} pts).")

    gaps.to_csv(OUT_CSV, index=False)
    print(f"\n{len(gaps)} value players found. Full table -> {OUT_CSV}")


if __name__ == "__main__":
    main()
