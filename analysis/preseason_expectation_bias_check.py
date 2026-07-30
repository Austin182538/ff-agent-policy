#!/usr/bin/env python3
"""
Tests whether preseason expectations (ECR rank -- our best available proxy
for "what the fantasy market/consensus expected") are systematically biased
vs. actual outcomes, and how much of any gap is explained by missed games
(injuries, benchings) vs. genuine over-optimism -- the user's stated
intuition for excluding low-game-count seasons.

IMPORTANT SCOPE NOTE: this is NOT a Vegas-vs-actual backtest. True
season-long historical Vegas player prop lines (the actual ask) are not
freely available anywhere -- confirmed via research: PropLine's historical
archive only starts April 2026 (doesn't reach back to past seasons at all),
and SportsDataIO's historical betting/props warehouse requires contacting
their sales team (enterprise pricing, not something obtainable in this
session). If a paid historical props feed is ever added, this script's
season-by-season / games-played-filtered structure could be reused directly
against it. In the meantime, this uses preseason ECR rank -- an average of
expert redraft rankings, not a Vegas line -- as the best real, freely
available stand-in for "preseason expectation." All points are half-PPR
(fantasy_points_half_ppr), matching this league's exact scoring.

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\preseason_expectation_bias_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine

SEASONS = (2021, 2022, 2023, 2024, 2025)
POSITIONS = ["QB", "RB", "WR", "TE"]
MIN_GAMES = 10  # ~60% of a season -- excludes players who missed most of it


def load_data():
    seasons_clause = ",".join(str(y) for y in SEASONS)
    query = text(f"""
        SELECT c.player_name, c.position, c.season_year, c.ecr_position_rank, c.ecr_overall_rank,
               s.fantasy_points_half_ppr AS actual_points, s.games_played
        FROM fantasy_consensus_rankings c
        JOIN historical_player_stats s
          ON s.player_name = c.player_name AND s.season_year = c.season_year AND s.week = 0
        WHERE c.season_year IN ({seasons_clause}) AND c.position IN ('QB','RB','WR','TE')
    """)
    return pd.read_sql(query, engine)


def main():
    df = load_data()
    if "games_played" not in df.columns or df["games_played"].isna().all():
        print("games_played column not populated -- falling back to a points>0 proxy for 'played meaningfully'.")
        df["games_played"] = None

    tiers = [(1, 5, "Top 5"), (1, 12, "Top 12"), (1, 24, "Top 24"), (1, 36, "Top 36")]

    print("=" * 100)
    print("PRESEASON ECR-RANK EXPECTATION vs ACTUAL OUTCOME -- ALL PLAYERS (no games-played filter)")
    print("(For each tier, this compares the ACTUAL final rank achieved by players drafted in that")
    print(" preseason tier against the tier itself -- i.e. do top-12 preseason picks actually finish top-12?)")
    print("=" * 100)
    for lo, hi, label in tiers:
        for pos in POSITIONS:
            sub = df[(df["position"] == pos) & (df["ecr_position_rank"] >= lo) & (df["ecr_position_rank"] <= hi)]
            if sub.empty:
                continue
            sub = sub.copy()
            sub["actual_rank"] = df[df["position"] == pos].groupby("season_year")["actual_points"].rank(
                ascending=False, method="first").reindex(sub.index)
            hit_rate = (sub["actual_rank"] <= hi).mean()
            print(f"  {pos} {label:8s}: n={len(sub):3d}  avg actual rank={sub['actual_rank'].mean():5.1f}  "
                  f"avg actual points={sub['actual_points'].mean():6.1f}  "
                  f"% who actually finished in that tier={hit_rate*100:4.1f}%  "
                  f"avg games played={sub['games_played'].mean() if sub['games_played'].notna().any() else float('nan'):.1f}")

    print("\n" + "=" * 100)
    print(f"SAME ANALYSIS, EXCLUDING SEASONS WITH < {MIN_GAMES} GAMES PLAYED (removes injury/benching outliers)")
    print("=" * 100)
    if df["games_played"].notna().any():
        df_filtered = df[df["games_played"] >= MIN_GAMES]
        excluded_pct = 1 - len(df_filtered) / len(df)
        print(f"Excluded {excluded_pct*100:.1f}% of player-seasons for playing fewer than {MIN_GAMES} games.\n")
        for lo, hi, label in tiers:
            for pos in POSITIONS:
                sub = df_filtered[(df_filtered["position"] == pos) & (df_filtered["ecr_position_rank"] >= lo)
                                   & (df_filtered["ecr_position_rank"] <= hi)]
                if sub.empty:
                    continue
                sub = sub.copy()
                sub["actual_rank"] = df[df["position"] == pos].groupby("season_year")["actual_points"].rank(
                    ascending=False, method="first").reindex(sub.index)
                hit_rate = (sub["actual_rank"] <= hi).mean()
                print(f"  {pos} {label:8s}: n={len(sub):3d}  avg actual rank={sub['actual_rank'].mean():5.1f}  "
                      f"avg actual points={sub['actual_points'].mean():6.1f}  "
                      f"% who actually finished in that tier={hit_rate*100:4.1f}%")
    else:
        print("games_played not available in historical_player_stats -- see data ingestion.")

    print("\n" + "=" * 100)
    print("YEAR-BY-YEAR: preseason Top-12 WR/RB avg actual points (half-PPR), all vs 10+ games only")
    print("=" * 100)
    for pos in ["RB", "WR"]:
        print(f"\n{pos}:")
        for season in SEASONS:
            sub_all = df[(df["position"] == pos) & (df["season_year"] == season) & (df["ecr_position_rank"] <= 12)]
            sub_filtered = sub_all[sub_all["games_played"] >= MIN_GAMES] if sub_all["games_played"].notna().any() else sub_all
            print(f"  {season}: all n={len(sub_all):2d} avg={sub_all['actual_points'].mean():6.1f} pts   |   "
                  f"10+ games n={len(sub_filtered):2d} avg={sub_filtered['actual_points'].mean():6.1f} pts   "
                  f"(gap from removing injured/limited players: "
                  f"{sub_filtered['actual_points'].mean() - sub_all['actual_points'].mean():+.1f} pts)")


if __name__ == "__main__":
    main()
