#!/usr/bin/env python3
"""
Side-by-side comparison of our model's rank, FantasyPros ECR (the sole input
to our VOR/replacement calibration), and ESPN's live default PPR rank + ADP.

This is a sanity-check / "how much does the consensus source matter" report,
NOT a re-ranking. It deliberately does not blend ESPN into the VOR model --
that calibration curve was built and tuned specifically against FantasyPros
ECR history (2021-2025), and there's no equivalent multi-year ESPN history in
this project to re-derive it against. Treat large our-rank vs. ESPN-rank
divergences the same way as FantasyPros divergences: worth a look, not
automatically a bug in either direction.

Yahoo isn't included -- their API requires a registered developer app
(consumer key/secret) even for public-only reads, which needs the user to
create one; Sleeper's public API has no ADP/consensus-rank endpoint at all
(only rosters, drafts, and player metadata) -- see data/README.md.

Run with the main app venv:
    venv\\Scripts\\python.exe analysis\\multi_source_consensus_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

from app.core.database import engine
from analysis.player_ranking_v1 import normalize_name

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
RANKING_SEASON = 2026


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    ours = pd.read_csv(os.path.join(OUTPUT_DIR, "player_rankings_2026.csv"))
    ours["merge_key"] = ours["player_name"].apply(normalize_name)

    espn = pd.read_sql(text("""
        SELECT player_name, position, rank AS espn_rank, adp AS espn_adp
        FROM external_consensus_rankings
        WHERE source = 'ESPN' AND season_year = :season
    """), engine, params={"season": RANKING_SEASON})
    espn["merge_key"] = espn["player_name"].apply(normalize_name)
    espn = espn.drop_duplicates("merge_key")

    merged = ours.merge(espn[["merge_key", "espn_rank", "espn_adp"]], on="merge_key", how="left")
    merged = merged[merged["position"].isin(["QB", "RB", "WR", "TE"])]

    matched = merged.dropna(subset=["espn_rank"])
    print("=" * 100)
    print(f"MULTI-SOURCE CONSENSUS CHECK -- {len(matched)} of {len(merged)} ranked players matched to ESPN")
    print("=" * 100)

    corr_fp = matched["our_rank"].corr(matched["ecr_overall_rank"], method="spearman")
    corr_espn = matched["our_rank"].corr(matched["espn_rank"], method="spearman")
    corr_fp_espn = matched["ecr_overall_rank"].corr(matched["espn_rank"], method="spearman")
    print(f"\nRank correlation (Spearman): our model vs FantasyPros ECR = {corr_fp:.3f}")
    print(f"Rank correlation (Spearman): our model vs ESPN            = {corr_espn:.3f}")
    print(f"Rank correlation (Spearman): FantasyPros ECR vs ESPN      = {corr_fp_espn:.3f}")

    matched = matched.copy()
    matched["espn_vs_fp_gap"] = matched["ecr_overall_rank"] - matched["espn_rank"]

    print("\nBiggest FantasyPros-vs-ESPN disagreements (both are 'the market', not us):")
    cols = ["player_name", "position", "our_rank", "ecr_overall_rank", "espn_rank", "espn_adp", "espn_vs_fp_gap"]
    print(matched.reindex(columns=cols).nlargest(8, "espn_vs_fp_gap").to_string(index=False, float_format=lambda x: f"{x:.1f}"))
    print()
    print(matched.reindex(columns=cols).nsmallest(8, "espn_vs_fp_gap").to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    out_path = os.path.join(OUTPUT_DIR, "multi_source_consensus_2026.csv")
    matched.reindex(columns=["player_name", "position", "team_abbr", "our_rank", "vor",
                              "ecr_overall_rank", "espn_rank", "espn_adp", "espn_vs_fp_gap"]).sort_values(
        "our_rank").to_csv(out_path, index=False)
    print(f"\nFull detail written to {out_path}")


if __name__ == "__main__":
    main()
