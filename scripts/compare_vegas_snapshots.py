#!/usr/bin/env python3
"""
Diffs the two most recent player_prop_line_snapshots batches (see
scripts/scrape_vegas_snapshot.py) and converts each stat-line change into a
fantasy-point-equivalent swing, using this league's exact scoring (same
conversion as app/integrations/player_projection.py): yards/10, TDs x6
(rush/rec) or x4 (pass). This is the "daily monitor" half of the
headline-detection pipeline: run this after every scrape, and it tells you
whether anything actually needs a human look.

Two tiers:
  - NOTABLE (>= NOTABLE_THRESHOLD points): worth listing, usually just
    normal week-to-week market movement.
  - BIG (>= BIG_THRESHOLD points): flagged as "investigate this" -- exits
    with a nonzero status code so a scheduled task can alert on it, and
    prints a suggestion to run scripts/lookup_player_news.py for context.

Exits 0 if nothing crosses BIG_THRESHOLD ("safe to move on"), exits 1 if
something does ("flag to investigate why").

Run with the main app venv:
    venv\\Scripts\\python.exe scripts\\compare_vegas_snapshots.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from app.integrations.vegas_line_diff import diff_latest_two_snapshots

NOTABLE_THRESHOLD = 5.0
BIG_THRESHOLD = 12.0


def main():
    packed = diff_latest_two_snapshots(engine)
    if packed is None:
        print("Fewer than 2 snapshots exist yet -- run scripts/scrape_vegas_snapshot.py at least twice "
              "(on different occasions) before comparing.")
        sys.exit(0)

    result, older_ts, newer_ts = packed
    print(f"Comparing snapshot {older_ts} (older) -> {newer_ts} (newer)")

    if result.empty:
        print("No stat-line changes at all between these two snapshots.")
        sys.exit(0)

    result = result.sort_values("total_impact", key=lambda s: s.abs(), ascending=False)
    notable = result[result["total_impact"].abs() >= NOTABLE_THRESHOLD]
    big = result[result["total_impact"].abs() >= BIG_THRESHOLD]

    print(f"{len(result)} players had some line change; {len(notable)} notable (>= {NOTABLE_THRESHOLD} pts), "
          f"{len(big)} big (>= {BIG_THRESHOLD} pts).\n")

    if not notable.empty:
        print("=" * 100)
        print("NOTABLE MOVERS")
        print("=" * 100)
        print(notable.to_string(index=False, float_format=lambda x: f"{x:.1f}"))

    if not big.empty:
        print("\n" + "=" * 100)
        print("BIG MOVERS -- investigate why (try: venv\\Scripts\\python.exe scripts\\lookup_player_news.py \"<name>\")")
        print("=" * 100)
        print(big.to_string(index=False, float_format=lambda x: f"{x:.1f}"))
        sys.exit(1)
    else:
        print("\nNo big movers -- safe to move on.")
        sys.exit(0)


if __name__ == "__main__":
    main()
