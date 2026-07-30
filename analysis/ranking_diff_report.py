#!/usr/bin/env python3
"""
Compares two archived ranking runs (outputs/history/player_rankings_2026_*.csv,
written by analysis/player_ranking_v1.py every run) and reports exactly how
the rankings changed: rank/VOR/points movement per player, cross-referenced
against (a) any real Vegas line change for that player in the same window
(app/integrations/vegas_line_diff.py) and (b) recent ESPN news for the
biggest movers -- this is the bridge between "a headline moved a Vegas line"
and "here's what actually changed in the rankings," which is what an
eventual ranking-change graphic would be built from.

Defaults to the two most recent archived runs. Pass explicit paths to
compare specific runs instead (e.g. a "before" run saved right before you
manually reacted to a big-mover flag, vs. "after" once you've updated the
data and re-run the rankings):

    venv\\Scripts\\python.exe analysis\\ranking_diff_report.py
    venv\\Scripts\\python.exe analysis\\ranking_diff_report.py --old outputs/history/player_rankings_2026_<ts1>.csv --new outputs/history/player_rankings_2026_<ts2>.csv

Run with the main app venv (needs the DB for the Vegas-line and news
cross-references; falls back to a plain ranking diff without them if the DB
piece fails):
    venv\\Scripts\\python.exe analysis\\ranking_diff_report.py
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs", "history")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")

NEWS_LOOKUP_TOP_N = 5  # only spend API calls on the very biggest movers


def find_two_most_recent_archives() -> tuple:
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "player_rankings_*.csv")))
    if len(files) < 2:
        raise SystemExit(
            f"Need at least 2 archived runs in {HISTORY_DIR} to diff -- found {len(files)}. "
            "Run analysis/player_ranking_v1.py at least twice (it archives automatically every run)."
        )
    return files[-2], files[-1]


def load_prop_line_causes() -> pd.DataFrame:
    """Best-effort: which players had a real Vegas line change between the
    two most recent scrape snapshots? Used to explain movers whose ranking
    changed because THEIR OWN inputs moved (vs. everyone else's VOR shifting
    around them, or a rank-based ECR change with no Vegas line at all).
    """
    try:
        from app.core.database import engine
        from app.integrations.vegas_line_diff import diff_latest_two_snapshots
        packed = diff_latest_two_snapshots(engine)
        if packed is None:
            return pd.DataFrame(columns=["player_name", "changes"])
        diff_df, _, _ = packed
        return diff_df[["player_name", "changes"]]
    except Exception as e:
        print(f"(Could not load Vegas line-change context: {e})")
        return pd.DataFrame(columns=["player_name", "changes"])


def attach_news(player_names: list) -> dict:
    """Best-effort: recent ESPN headlines per player, only for the players
    passed in (keep this small -- NEWS_LOOKUP_TOP_N callers)."""
    news_by_player = {}
    try:
        from app.integrations.espn_news_client import fetch_recent_news, find_news_for_player, summarize_article
        articles = fetch_recent_news(limit=50)
        for name in player_names:
            matches = find_news_for_player(name, articles=articles)
            if matches:
                news_by_player[name] = [summarize_article(a) for a in matches[:2]]
    except Exception as e:
        print(f"(Could not load news context: {e})")
    return news_by_player


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", help="Path to the 'before' ranking CSV")
    parser.add_argument("--new", help="Path to the 'after' ranking CSV")
    args = parser.parse_args()

    if args.old and args.new:
        old_path, new_path = args.old, args.new
    else:
        old_path, new_path = find_two_most_recent_archives()

    print(f"Comparing:\n  OLD: {old_path}\n  NEW: {new_path}\n")

    old = pd.read_csv(old_path)
    new = pd.read_csv(new_path)

    # games_missed was added later; older archives won't have it. Default to 0
    # so the availability diff still works against a pre-feature "before" run.
    for df_ in (old, new):
        if "games_missed" not in df_.columns:
            df_["games_missed"] = 0.0

    merged = new.merge(
        old[["player_name", "our_rank", "vor", "projected_ppr_points", "games_missed", "projection_source"]],
        on="player_name", how="outer", suffixes=("_new", "_old"), indicator=True,
    )

    new_players = merged[merged["_merge"] == "left_only"]
    dropped_players = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"].copy()

    both["rank_change"] = both["our_rank_old"] - both["our_rank_new"]  # positive = moved UP (better rank)
    both["points_change"] = both["projected_ppr_points_new"] - both["projected_ppr_points_old"]
    both["vor_change"] = both["vor_new"] - both["vor_old"]
    both["games_missed_change"] = both["games_missed_new"] - both["games_missed_old"]
    both["source_changed"] = both["projection_source_new"] != both["projection_source_old"]

    moved = both[(both["rank_change"] != 0) | (both["vor_change"].abs() > 0.05)]
    print(f"{len(both)} players present in both runs; {len(moved)} had any rank or points change.")
    if not new_players.empty:
        print(f"{len(new_players)} players newly appeared: {', '.join(new_players['player_name'].head(10))}"
              f"{' ...' if len(new_players) > 10 else ''}")
    if not dropped_players.empty:
        print(f"{len(dropped_players)} players dropped out: {', '.join(dropped_players['player_name'].head(10))}"
              f"{' ...' if len(dropped_players) > 10 else ''}")

    if moved.empty:
        print("\nNo ranking movement between these two runs.")
        return

    causes = load_prop_line_causes()
    moved = moved.merge(causes, on="player_name", how="left")

    # Rank alone is a bad "who actually moved" signal: when one player's
    # value drops a lot, EVERY player below them mechanically shifts up by
    # exactly 1 rank slot from pure renumbering, with zero real change of
    # their own -- that's noise, not a headline-worthy riser. Real movers are
    # defined by their OWN VOR changing -- whether from a points input (Vegas
    # line, team win total, ECR calibration) OR a games-missed availability
    # adjustment, which moves VOR without moving raw points. So filter on
    # vor_change, not points_change (which would miss availability-only moves).
    real_movement = moved[moved["vor_change"].abs() > 0.05]
    risers = real_movement[real_movement["vor_change"] > 0].sort_values("vor_change", ascending=False).head(15)
    fallers = real_movement[real_movement["vor_change"] < 0].sort_values("vor_change", ascending=True).head(15)

    renumbering_only = len(moved) - len(real_movement)
    if renumbering_only > 0:
        print(f"({renumbering_only} additional players shifted by exactly the renumbering effect from the "
              f"movers below -- zero real points change of their own, omitted from the lists below.)")

    top_movers_for_news = pd.concat([risers.head(NEWS_LOOKUP_TOP_N), fallers.head(NEWS_LOOKUP_TOP_N)])["player_name"].tolist()
    news_by_player = attach_news(top_movers_for_news)

    def _print_movers(df, title):
        print("\n" + "=" * 100)
        print(title)
        print("=" * 100)
        for _, r in df.iterrows():
            if r["rank_change"] == 0 and abs(r["vor_change"]) < 0.05:
                continue
            # A games-missed change moves VOR without moving raw points and
            # won't show in the Vegas line-diff, so surface it explicitly.
            if abs(r["games_missed_change"]) > 0.01:
                cause = (f"availability change: games missed {r['games_missed_old']:.0f} -> "
                         f"{r['games_missed_new']:.0f} (VOR scaled by remaining games)")
            elif pd.notna(r["changes"]):
                cause = r["changes"]
            else:
                cause = "no direct Vegas line change found -- likely driven by ECR/consensus movement or other players shifting around them"
            source_note = " [projection source changed]" if r["source_changed"] else ""
            print(f"\n{r['player_name']} ({r['position']}, {r['team_abbr']}): "
                  f"rank {int(r['our_rank_old'])} -> {int(r['our_rank_new'])} ({r['rank_change']:+.0f}), "
                  f"VOR {r['vor_change']:+.1f}, {r['points_change']:+.1f} pts{source_note}")
            print(f"  Why: {cause}")
            if r["player_name"] in news_by_player:
                for headline in news_by_player[r["player_name"]]:
                    print(f"  News: {headline}")

    _print_movers(risers, "BIGGEST RISERS")
    _print_movers(fallers, "BIGGEST FALLERS")

    out_path = os.path.join(OUTPUT_DIR, "ranking_diff_report.csv")
    moved.sort_values("rank_change", key=lambda s: s.abs(), ascending=False).to_csv(out_path, index=False)
    print(f"\nFull diff written to {out_path}")


if __name__ == "__main__":
    main()
