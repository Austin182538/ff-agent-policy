#!/usr/bin/env python3
"""
How accurate are Vegas preseason team win totals?

Joins data/vegas_win_totals.csv (via team_season_win_totals) against actual
final regular-season records (season_final_records, derived from nflverse
schedules) for each completed season, and reports league-wide + per-team
error metrics. This calibration number is used as a "how much to trust
Vegas" weight in analysis/player_ranking_v1.py.

Run with the main app venv (pure SQLite/pandas, no nflreadpy needed):
    venv\\Scripts\\python.exe analysis\\vegas_win_totals_accuracy.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")


def load_data() -> pd.DataFrame:
    query = text("""
        SELECT
            w.team_abbr, w.season_year, w.win_total_line,
            r.wins AS actual_wins, r.losses AS actual_losses, r.ties
        FROM team_season_win_totals w
        JOIN season_final_records r
          ON w.team_abbr = r.team_abbr AND w.season_year = r.season_year
        ORDER BY w.season_year, w.team_abbr
    """)
    return pd.read_sql(query, engine)


def main():
    df = load_data()
    if df.empty:
        print("No matched rows -- did you run scripts/seed_team_win_totals.py and "
              "scripts/ingest_historical_data.py?")
        return

    df["error"] = df["actual_wins"] - df["win_total_line"]
    df["abs_error"] = df["error"].abs()
    df["result"] = df["error"].apply(lambda e: "OVER" if e > 0 else ("UNDER" if e < 0 else "PUSH"))

    print("=" * 70)
    print("VEGAS PRESEASON WIN TOTAL ACCURACY (by season)")
    print("=" * 70)
    by_season = df.groupby("season_year").agg(
        teams=("team_abbr", "count"),
        mean_abs_error=("abs_error", "mean"),
        rmse=("error", lambda s: (s ** 2).mean() ** 0.5),
        pct_over=("result", lambda s: (s == "OVER").mean() * 100),
        pct_under=("result", lambda s: (s == "UNDER").mean() * 100),
        pct_push=("result", lambda s: (s == "PUSH").mean() * 100),
    ).round(2)
    print(by_season.to_string())

    print("\n" + "=" * 70)
    print("LEAGUE-WIDE SUMMARY (all completed seasons)")
    print("=" * 70)
    print(f"Teams graded:        {len(df)}")
    print(f"Mean absolute error: {df['abs_error'].mean():.2f} wins")
    print(f"RMSE:                {(df['error'] ** 2).mean() ** 0.5:.2f} wins")
    print(f"Over / Under / Push: {(df['result']=='OVER').mean()*100:.1f}% / "
          f"{(df['result']=='UNDER').mean()*100:.1f}% / {(df['result']=='PUSH').mean()*100:.1f}%")

    print("\nBiggest overs (team beat its win total by the most):")
    print(df.nlargest(5, "error")[["team_abbr", "season_year", "win_total_line", "actual_wins", "error"]]
          .to_string(index=False))

    print("\nBiggest unders (team missed its win total by the most):")
    print(df.nsmallest(5, "error")[["team_abbr", "season_year", "win_total_line", "actual_wins", "error"]]
          .to_string(index=False))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "vegas_win_totals_accuracy.csv")
    df.to_csv(out_path, index=False)
    print(f"\nFull detail written to {out_path}")


if __name__ == "__main__":
    main()
