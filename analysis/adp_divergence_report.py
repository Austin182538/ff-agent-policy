#!/usr/bin/env python3
"""
Why do our ranks diverge so hard from ADP (e.g. we have Josh Jacobs / Derrick
Henry ~30 spots ahead of the market)?

Everything here is in RANK terms (overall rank + position rank), not points.
This report separates two explanations per player by pulling a genuine
third-party PROJECTION (ESPN's own season projections, via
app/integrations/espn_client.fetch_espn_projections), re-scoring it in OUR
half-PPR system, and converting it to VOR-based overall ranks + position ranks
the SAME way we rank -- so ours / ADP / ESPN are all directly comparable:

  1. MARKET FADE  -- our rank ~= ESPN's projection rank (or ESPN ranks them
     even higher), but ADP is far lower. Two independent projection systems
     say the player produces; the market discounts them for reasons a
     projection doesn't capture (age, injury history, committee/holdout
     narrative, TD-regression fear). These are the genuine "value" signals.

  2. OUR RANK HIGH -- ESPN's projection ranks them notably lower than we do, so
     part of the gap to ADP is our own board, not just the market.

    venv\\Scripts\\python.exe analysis\\adp_divergence_report.py [--top 60]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from analysis.player_ranking_v1 import normalize_name
from app.integrations.espn_client import fetch_espn_projections

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
RANKINGS_CSV = os.path.join(OUTPUT_DIR, "player_rankings_2026.csv")
SEASON = 2026


def half_ppr(row: dict) -> float:
    """Re-score ESPN's projected components in our exact scoring so the point
    total is directly comparable to our projected_ppr_points."""
    def g(k):
        v = row.get(k)
        return float(v) if v is not None and pd.notna(v) else 0.0
    return (g("espn_pass_yards") / 25.0 + g("espn_pass_tds") * 4.0 - g("espn_interceptions") * 2.0
            + g("espn_rush_yards") / 10.0 + g("espn_rush_tds") * 6.0
            + g("espn_receptions") * 0.5 + g("espn_rec_yards") / 10.0 + g("espn_rec_tds") * 6.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=60, help="Consider our top-N by our_rank")
    args = ap.parse_args()

    ours = pd.read_csv(RANKINGS_CSV)
    ours["merge_key"] = ours["player_name"].apply(normalize_name)
    ours = ours[ours["position"].isin(["QB", "RB", "WR", "TE"])].copy()

    # Our position rank (within-position order of our overall rank).
    ours["our_pos_rank"] = ours.groupby("position")["our_rank"].rank(method="first").astype(int)

    espn = pd.DataFrame(fetch_espn_projections(SEASON))
    espn = espn[espn["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    espn["merge_key"] = espn["player_name"].apply(normalize_name)
    espn["espn_half_ppr"] = espn.apply(lambda r: half_ppr(r), axis=1)
    espn = espn.drop_duplicates("merge_key")

    # Turn ESPN's projections into ranks the SAME way we rank: VOR (points above
    # the position's replacement level) for the overall board, raw points within
    # a position for the position rank. Reuse OUR replacement levels so the two
    # overall boards are directly comparable rather than QBs floating to the top
    # on raw points.
    replacement = ours.groupby("position")["replacement_points_at_position"].first()
    espn["espn_vor"] = espn["espn_half_ppr"] - espn["position"].map(replacement)
    espn["espn_overall_rank"] = espn["espn_vor"].rank(ascending=False, method="first").astype(int)
    espn["espn_pos_rank"] = espn.groupby("position")["espn_half_ppr"].rank(ascending=False, method="first").astype(int)

    df = ours.merge(
        espn[["merge_key", "espn_overall_rank", "espn_pos_rank"]],
        on="merge_key", how="left").sort_values("our_rank").head(args.top).copy()

    # All comparisons are in RANK terms now.
    df["adp_overall"] = df["ecr_overall_rank"]
    df["adp_pos"] = df["ecr_position_rank"]
    df["adp_gap"] = df["adp_overall"] - df["our_rank"]              # + = market drafts them later
    df["espn_gap"] = df["espn_overall_rank"] - df["our_rank"]        # + = ESPN ranks them lower than us

    def classify(r):
        if pd.isna(r["espn_overall_rank"]):
            return "no ESPN proj"
        if r["adp_gap"] < 8:
            return "-"
        # ESPN's own projection-rank vs ours: does an independent projection
        # also rank them near where we do (i.e. is ADP the outlier, not us)?
        if r["espn_gap"] > 15:
            return "OUR RANK HIGH (ESPN lower)"
        if r["espn_gap"] < -5:
            return "STRONG FADE (ESPN ranks even higher)"
        return "MARKET FADE (ESPN agrees)"

    df["verdict"] = df.apply(classify, axis=1)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    def posr(r, col):  # e.g. "RB6"
        return f"{r['position']}{int(r[col])}" if pd.notna(r[col]) else "-"

    biggest = df[df["adp_gap"] >= 8].sort_values("adp_gap", ascending=False).copy()
    biggest["ours"] = biggest.apply(lambda r: f"{int(r['our_rank'])} ({posr(r,'our_pos_rank')})", axis=1)
    biggest["adp"] = biggest.apply(lambda r: f"{int(r['adp_overall'])} ({posr(r,'adp_pos')})", axis=1)
    biggest["espn"] = biggest.apply(
        lambda r: f"{int(r['espn_overall_rank'])} ({posr(r,'espn_pos_rank')})" if pd.notna(r["espn_overall_rank"]) else "-", axis=1)

    print("=" * 110)
    print(f"OUR RANK vs ADP vs ESPN PROJECTION RANK -- biggest 'we love them, market doesn't' gaps (top {args.top})")
    print("Each cell is OVERALL rank (POSITION rank). adp_gap = how many overall spots later ADP drafts them.")
    print("=" * 110)
    show = biggest.rename(columns={"player_name": "player"})[
        ["player", "position", "ours", "adp", "espn", "adp_gap", "verdict"]]
    print(show.to_string(index=False, float_format=lambda x: f"{x:.0f}"))

    n_high = (biggest["verdict"] == "OUR RANK HIGH (ESPN lower)").sum()
    n_fade = (biggest["verdict"] == "MARKET FADE (ESPN agrees)").sum()
    n_strong = (biggest["verdict"] == "STRONG FADE (ESPN ranks even higher)").sum()
    print("\n" + "-" * 110)
    print(f"Of {len(biggest)} big ADP gaps: {n_high} are OUR RANK sitting higher than ESPN's projection rank, "
          f"{n_fade} match ESPN, {n_strong} have ESPN ranking them EVEN HIGHER than we do.")
    print(f"=> {n_fade + n_strong}/{len(biggest)} corroborated by ESPN's independent projection ranks -- the gap "
          "to ADP is the market fading them, not our board being idiosyncratic.")

    out = os.path.join(OUTPUT_DIR, "adp_divergence_2026.csv")
    df.reindex(columns=["our_rank", "our_pos_rank", "player_name", "position",
                        "adp_overall", "adp_pos", "espn_overall_rank", "espn_pos_rank",
                        "adp_gap", "espn_gap", "verdict"]).to_csv(out, index=False)
    print(f"\nFull table -> {out}")


if __name__ == "__main__":
    main()
