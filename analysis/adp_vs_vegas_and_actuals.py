#!/usr/bin/env python3
"""
Two related questions:

1. How accurate is preseason ADP/ECR at predicting that season's actual
   fantasy finish? (historical backtest, 2021-2025)
2. For the upcoming 2026 season, how does current ADP line up with each
   player's team's Vegas win-total environment? (early signal for the
   ranking model -- e.g. a well-drafted player on a suddenly-weak-projected
   team, or a value pick on a team Vegas expects to be much better)

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\adp_vs_vegas_and_actuals.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def historical_adp_vs_actual() -> pd.DataFrame:
    query = text("""
        SELECT
            c.player_name, c.position, c.team_abbr, c.season_year,
            c.ecr_overall_rank, c.ecr_position_rank,
            s.fantasy_points_ppr AS actual_ppr_points
        FROM fantasy_consensus_rankings c
        JOIN historical_player_stats s
          ON s.player_name = c.player_name AND s.season_year = c.season_year AND s.week = 0
        WHERE c.season_year < 2026
    """)
    return pd.read_sql(query, engine)


def current_adp_vs_team_environment() -> pd.DataFrame:
    query = text("""
        SELECT
            c.player_name, c.position, c.team_abbr,
            c.ecr_overall_rank, c.ecr_position_rank,
            w.win_total_line
        FROM fantasy_consensus_rankings c
        LEFT JOIN team_season_win_totals w
          ON w.team_abbr = c.team_abbr AND w.season_year = 2026
        WHERE c.season_year = 2026
        ORDER BY c.ecr_overall_rank ASC
    """)
    return pd.read_sql(query, engine)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("PART 1: HISTORICAL ADP/ECR ACCURACY, 2021-2025")
    print("=" * 70)
    df = historical_adp_vs_actual()
    if df.empty:
        print("No matched rows -- did you run scripts/ingest_historical_data.py?")
        return

    df["actual_position_rank"] = df.groupby(["season_year", "position"])["actual_ppr_points"].rank(
        ascending=False, method="first"
    )
    df["rank_miss"] = df["actual_position_rank"] - df["ecr_position_rank"]

    print("\nSpearman rank correlation (preseason ECR position rank vs actual season-end "
          "position rank) by position -- closer to -1.0 is better (low preseason rank number "
          "should mean high final points):")
    corr_rows = []
    for pos, group in df.groupby("position"):
        if len(group) < 10:
            continue
        corr = group["ecr_position_rank"].corr(group["actual_position_rank"], method="spearman")
        corr_rows.append({"position": pos, "n": len(group), "spearman_corr": round(corr, 3)})
    corr_df = pd.DataFrame(corr_rows).sort_values("position")
    print(corr_df.to_string(index=False))

    print("\nBiggest historical 'busts' (top-24 preseason ECR at position, "
          "worst actual finish relative to that rank):")
    busts = df[df["ecr_position_rank"] <= 24].nlargest(10, "rank_miss")[
        ["player_name", "position", "season_year", "ecr_position_rank", "actual_position_rank", "rank_miss"]
    ]
    print(busts.to_string(index=False))

    print("\nBiggest historical 'steals' (drafted outside top-60 overall, "
          "finished as a top-24-at-position player):")
    steals = df[(df["ecr_overall_rank"] > 60) & (df["actual_position_rank"] <= 24)].nsmallest(
        10, "rank_miss"
    )[["player_name", "position", "season_year", "ecr_overall_rank", "actual_position_rank", "rank_miss"]]
    print(steals.to_string(index=False))

    df.to_csv(os.path.join(OUTPUT_DIR, "adp_vs_actual_historical.csv"), index=False)

    print("\n" + "=" * 70)
    print("PART 2: 2026 CURRENT ADP vs TEAM WIN-TOTAL ENVIRONMENT (top 40 overall)")
    print("=" * 70)
    current = current_adp_vs_team_environment()
    if current.empty:
        print("No 2026 rankings found -- did you run scripts/ingest_historical_data.py "
              "and scripts/seed_team_win_totals.py?")
        return

    top40 = current.head(40).copy()
    league_avg_win_total = current.drop_duplicates("team_abbr")["win_total_line"].mean()
    top40["team_win_total_vs_league_avg"] = top40["win_total_line"] - league_avg_win_total
    print(top40.to_string(index=False))
    print(f"\n(League-average 2026 win total across teams with a drafted player: "
          f"{league_avg_win_total:.2f})")

    current.to_csv(os.path.join(OUTPUT_DIR, "adp_vs_team_environment_2026.csv"), index=False)
    print(f"\nFull detail written to outputs/adp_vs_actual_historical.csv and "
          f"outputs/adp_vs_team_environment_2026.csv")


if __name__ == "__main__":
    main()
