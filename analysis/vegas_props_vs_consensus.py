#!/usr/bin/env python3
"""
How does Vegas' player-prop-implied production compare to public consensus
(ADP/ECR)? For every player with a real Vegas season prop line, this
compares the Vegas-implied PPR points against what their current ECR rank
alone would predict (using the same isotonic rank-to-points calibration
curve as the main ranking model). A big positive gap means Vegas is more
bullish than the drafting public; a big negative gap means Vegas is more
bearish.

Caveat carried over from analysis/player_ranking_v1.py: Vegas season props
assume a full healthy season, while ECR/ADP-implied production already
bakes in the field's expectation of missed games -- so Vegas numbers run
structurally a bit high in an apples-to-apples sense. That's fine for
*relative* comparisons (this script), since every player gets the same
treatment, but don't read the absolute point gap as pure calibration error.

A full historical backtest of "how accurate are preseason player props
against actual results" would need season-long prop lines for many past
seasons, which -- unlike team win totals -- aren't readily available for
free at scale (see data/README.md). Flagged as follow-up work rather than
attempted here with partial data.

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\vegas_props_vs_consensus.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from analysis.player_ranking_v1 import (
    build_ecr_calibration_curve, make_calibration_lookup, load_current_rankings,
    load_player_props, load_prior_season_stats, normalize_name,
    compute_rb_receiving_baseline_components, rb_receiving_points,
)
from app.integrations.player_projection import (
    implied_receiving_points, implied_rushing_points, implied_passing_points,
    QB_POCKET_PASSER_RUSHING_BASELINE,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    current = load_current_rankings().set_index("merge_key")
    props = load_player_props()
    prior_stats = load_prior_season_stats()  # team lookup only, not a scoring input
    calibrated_points = make_calibration_lookup(build_ecr_calibration_curve())
    rb_receiving_baseline = compute_rb_receiving_baseline_components()

    rows = []
    for merge_key, prop_row in props.iterrows():
        if merge_key not in current.index:
            continue
        player = current.loc[merge_key]
        position = player["position"]
        prior = prior_stats.loc[merge_key].to_dict() if merge_key in prior_stats.index else None

        vegas_points = None
        if position in ("WR", "TE") and pd.notna(prop_row.get("rec_yards_line")):
            vegas_points = implied_receiving_points(
                prop_row["rec_yards_line"],
                prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None,
                position,
            )["points"]
        elif position == "RB" and pd.notna(prop_row.get("rush_yards_line")):
            rush = implied_rushing_points(
                prop_row["rush_yards_line"],
                prop_row["rush_tds_line"] if pd.notna(prop_row.get("rush_tds_line")) else None,
            )
            if pd.notna(prop_row.get("rec_yards_line")):
                receiving_points = implied_receiving_points(
                    prop_row["rec_yards_line"],
                    prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None,
                    "RB",
                )["points"]
            else:
                receiving_points = rb_receiving_points(
                    rb_receiving_baseline,
                    prop_row["rec_tds_line"] if pd.notna(prop_row.get("rec_tds_line")) else None,
                    1.0,
                )
            vegas_points = rush["points"] + receiving_points
        elif position == "QB" and pd.notna(prop_row.get("pass_yards_line")) and pd.notna(prop_row.get("pass_tds_line")):
            passing = implied_passing_points(prop_row["pass_yards_line"], prop_row["pass_tds_line"])
            if pd.notna(prop_row.get("rush_yards_line")):
                rushing_points = implied_rushing_points(
                    prop_row["rush_yards_line"],
                    prop_row["rush_tds_line"] if pd.notna(prop_row.get("rush_tds_line")) else None,
                    position="QB",
                )["points"]
            else:
                rushing_points = QB_POCKET_PASSER_RUSHING_BASELINE
            vegas_points = passing["points"] + rushing_points

        if vegas_points is None:
            continue

        consensus_points = calibrated_points(position, player["ecr_position_rank"])
        team_abbr = prior["team_abbr"] if prior and prior.get("team_abbr") else player["team_abbr"]
        rows.append({
            "player_name": player["player_name"],
            "position": position,
            "team_abbr": team_abbr,
            "ecr_overall_rank": player["ecr_overall_rank"],
            "vegas_implied_points": vegas_points,
            "consensus_implied_points": consensus_points,
            "vegas_vs_consensus_gap": vegas_points - consensus_points,
        })

    result = pd.DataFrame(rows).sort_values("vegas_vs_consensus_gap", ascending=False)

    print("=" * 100)
    print("VEGAS-IMPLIED PROJECTION vs. CONSENSUS-RANK-IMPLIED PROJECTION")
    print("(positive gap = Vegas is more bullish than the field; negative = Vegas is more bearish)")
    print("=" * 100)
    print(f"\n{len(result)} players with both a Vegas prop line and an ECR rank.\n")

    print("Vegas is MORE BULLISH than consensus (top 10):")
    print(result.head(10).to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    print("\nVegas is MORE BEARISH than consensus (top 10):")
    print(result.tail(10).sort_values("vegas_vs_consensus_gap").to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    print(f"\nMean absolute gap: {result['vegas_vs_consensus_gap'].abs().mean():.1f} points "
          f"(median {result['vegas_vs_consensus_gap'].abs().median():.1f})")

    out_path = os.path.join(OUTPUT_DIR, "vegas_props_vs_consensus_2026.csv")
    result.to_csv(out_path, index=False)
    print(f"\nFull detail written to {out_path}")

    print("\nNote: a systematic historical backtest of prop accuracy (like the win-totals one) isn't")
    print("included here -- historical season-long player prop lines aren't freely available at scale.")
    print("This is flagged as follow-up work; see the module docstring for details.")


if __name__ == "__main__":
    main()
