#!/usr/bin/env python3
"""
Generate the SAME head-to-head matchup in every available card style, so you
can open them side by side and pick which look to move forward with. Nothing
here changes the pipeline or the current default -- it's purely a visual
bake-off.

Styles rendered:
  scoreboard  -- the current default (light broadcast card)
  slate       -- new: premium DARK card, circular headshots, clean stat ledger
  arena       -- the existing "fighter" arena layout (dark, circular photos)

Usage (from the project root, with the venv):
  venv\\Scripts\\python.exe scripts\\preview_compare_styles.py --players "Ja'Marr Chase, Justin Jefferson"
  venv\\Scripts\\python.exe scripts\\preview_compare_styles.py            # uses the top two overall

Each style is written to outputs/graphics/preview_<style>_<a>_<b>.png
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from viz.render import html_to_png
import scripts.generate_ranking_graphic as gen

STYLES = ["scoreboard", "slate", "arena", "stack", "stack_light"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", default="", help='Two names, e.g. "Ja\'Marr Chase, Justin Jefferson"')
    ap.add_argument("--seed", default="preview", help="Pin the texture/look so all styles use the same seed")
    args = ap.parse_args()

    df = pd.read_csv(gen.RANKINGS_CSV)
    theme = gen.resolve_theme(None, args.seed)
    accent, background = theme["accent"], theme["background"]

    made = []
    for style in STYLES:
        html, _ = gen.build_compare(
            df, args.players, accent=accent, background=background,
            style=style, seed=args.seed,
        )
        # derive a clean filename from the two names in the matchup
        names = args.players if args.players else "top2"
        tag = names.replace(",", "_").replace(" ", "").replace("'", "")[:40] or "top2"
        out = os.path.join(gen.GRAPHICS_DIR, f"preview_{style}_{tag}.png")
        final = html_to_png(html, out)
        made.append(final)
        print(f"[{style:10s}] {final}")

    print("\nOpen these three and tell me which direction feels right "
          "(or which pieces from each). I'll refine that one.")
    for m in made:
        print("  " + m)


if __name__ == "__main__":
    main()
