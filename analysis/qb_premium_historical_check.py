#!/usr/bin/env python3
"""
Has an early (top-5/top-10) QB pick ever actually paid off, historically?

Two separate, concrete questions:

1. Has the market EVER drafted a QB that early? (best-ever preseason ECR
   rank achieved by a QB, per season, 2021-2025)
2. Even in a QB's best-case / ceiling season, did the marginal value
   (points above replacement) beat the best-case RB or WR season that
   same year? This uses ACTUAL final-season points, not projections --
   it's a clean test of "would the QB premium bet have paid off," using
   what actually happened rather than what a model predicted.

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\qb_premium_historical_check.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine
from analysis.player_ranking_v1 import build_actual_finish_curve, make_calibration_lookup, compute_flex_adjusted_replacement_ranks

SEASONS = (2021, 2022, 2023, 2024, 2025)
# Flex-simulated replacement ranks, computed the same way player_ranking_v1.py
# does it (not hardcoded), so this stays correct if the flex simulation ever
# shifts. See player_ranking_v1.py's compute_flex_adjusted_replacement_ranks.
_actual_finish_curve = build_actual_finish_curve()
_actual_finish_lookup = make_calibration_lookup(_actual_finish_curve, rank_col="actual_rank")
REPLACEMENT_RANK = compute_flex_adjusted_replacement_ranks(_actual_finish_lookup)


def main():
    print("=" * 100)
    print("QUESTION 1: Has the market EVER drafted a QB inside the top 10 overall picks?")
    print("=" * 100)
    seasons_clause = ",".join(str(y) for y in SEASONS)
    best_qb_adp = pd.read_sql(text(f"""
        SELECT season_year, player_name, ecr_overall_rank
        FROM fantasy_consensus_rankings
        WHERE position = 'QB' AND season_year IN ({seasons_clause})
        ORDER BY season_year, ecr_overall_rank
    """), engine)
    best_per_season = best_qb_adp.loc[best_qb_adp.groupby("season_year")["ecr_overall_rank"].idxmin()]
    print(best_per_season.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    print(f"\nBest QB ADP/ECR ever recorded across 2021-2025: {best_qb_adp['ecr_overall_rank'].min():.1f} overall")
    print("(For reference: see analysis/player_ranking_v1.py's current QB placement for 2026 --")
    print("if it's earlier than the real market has ever gone, that's a live tension with this")
    print("finding worth re-examining, not something this script resolves on its own.)")

    print("\n" + "=" * 100)
    print("QUESTION 2: Using ACTUAL final points, did any QB's best season beat the best RB/WR season")
    print("in points-above-replacement (VOR) that same year?")
    print("=" * 100)

    rows = []
    for season in SEASONS:
        for pos in ["QB", "RB", "WR"]:
            df = pd.read_sql(text(f"""
                SELECT player_name, fantasy_points_half_ppr
                FROM historical_player_stats
                WHERE season_year = {season} AND week = 0 AND position = '{pos}'
                ORDER BY fantasy_points_half_ppr DESC
            """), engine)
            if len(df) < REPLACEMENT_RANK[pos]:
                continue
            top_player = df.iloc[0]
            replacement = df.iloc[REPLACEMENT_RANK[pos] - 1]["fantasy_points_half_ppr"]
            vor = top_player["fantasy_points_half_ppr"] - replacement
            rows.append({
                "season": season, "position": pos, "best_player": top_player["player_name"],
                "actual_points": top_player["fantasy_points_half_ppr"], "replacement_points": replacement,
                "actual_vor": vor,
            })

    result = pd.DataFrame(rows)
    pivot = result.pivot(index="season", columns="position", values="actual_vor")
    print("\nActual ceiling VOR by season and position (bigger = more marginal value that year):")
    print(pivot.to_string(float_format=lambda x: f"{x:.1f}"))

    print("\nWho was the ceiling player each year:")
    print(result[["season", "position", "best_player", "actual_points", "actual_vor"]].to_string(
        index=False, float_format=lambda x: f"{x:.1f}"))

    qb_wins = (pivot["QB"] > pivot[["RB", "WR"]].max(axis=1)).sum()
    print(f"\nIn {qb_wins} of {len(pivot)} seasons, the QB ceiling outcome beat BOTH the RB and WR ceiling outcome.")
    print(f"Average ceiling VOR across {SEASONS[0]}-{SEASONS[-1]}: "
          f"QB={pivot['QB'].mean():.1f}, RB={pivot['RB'].mean():.1f}, WR={pivot['WR'].mean():.1f}")


if __name__ == "__main__":
    main()
