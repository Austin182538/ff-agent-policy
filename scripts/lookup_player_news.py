#!/usr/bin/env python3
"""
Quick CLI to pull recent ESPN NFL news for a specific player -- meant to be
run right after scripts/compare_vegas_snapshots.py flags a BIG mover, to
find the "why" before deciding whether/how to react.

Usage:
    venv\\Scripts\\python.exe scripts\\lookup_player_news.py "Derrick Henry"
    venv\\Scripts\\python.exe scripts\\lookup_player_news.py --all   (dumps recent NFL headlines, no filter)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.integrations.espn_news_client import fetch_recent_news, find_news_for_player, summarize_article


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--all":
        articles = fetch_recent_news(limit=50)
        print(f"{len(articles)} recent NFL headlines:\n")
        for a in articles:
            print(summarize_article(a))
        return

    player_name = " ".join(sys.argv[1:])
    matches = find_news_for_player(player_name)
    if not matches:
        print(f"No recent ESPN headlines mention '{player_name}' (checked the last 50 NFL articles).")
        return

    print(f"{len(matches)} recent headline(s) mentioning '{player_name}':\n")
    for a in matches:
        print(summarize_article(a))


if __name__ == "__main__":
    main()
