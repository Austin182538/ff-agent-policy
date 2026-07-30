"""
ESPN's public, no-auth-required NFL news feed
(site.api.espn.com/apis/site/v2/sports/football/nfl/news) -- the "trusted
news source accessible via API" half of the headline-detection pipeline
(the other half is the Vegas line-movement monitor in
scripts/scrape_vegas_snapshot.py + scripts/compare_vegas_snapshots.py).

Same undocumented-but-public ESPN API family already used for rankings/ADP
in app/integrations/espn_client.py. Each article's `categories` list
includes structured `type: "athlete"` entries with a clean player name --
much more reliable for player matching than searching headline text alone,
since NFL headlines often use last names or nicknames.
"""

from typing import Any, Dict, List, Optional

import requests

NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news"


def fetch_recent_news(limit: int = 50) -> List[Dict[str, Any]]:
    """Returns raw ESPN article dicts (headline, description, published,
    categories, ...), most recent first."""
    resp = requests.get(NEWS_URL, params={"limit": limit}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("articles", [])


def _athlete_names(article: Dict[str, Any]) -> List[str]:
    return [
        c["description"] for c in article.get("categories", [])
        if c.get("type") == "athlete" and c.get("description")
    ]


def find_news_for_player(player_name: str, articles: Optional[List[Dict[str, Any]]] = None,
                          limit: int = 50) -> List[Dict[str, Any]]:
    """Matches on the structured athlete category first (reliable, exact
    full-name match), falling back to a substring search of the last name
    in headline/description (catches articles that mention a player only
    in passing -- e.g. "impacts Jordan Love" -- without tagging him as a
    primary athlete category).
    """
    if articles is None:
        articles = fetch_recent_news(limit=limit)

    last_name = player_name.strip().split()[-1]
    matches = []
    for article in articles:
        athlete_names = _athlete_names(article)
        if any(player_name.lower() == a.lower() for a in athlete_names):
            matches.append(article)
            continue
        haystack = f"{article.get('headline', '')} {article.get('description', '')}".lower()
        if last_name.lower() in haystack:
            matches.append(article)
    return matches


def summarize_article(article: Dict[str, Any]) -> str:
    published = article.get("published", "")[:10]
    return f"[{published}] {article.get('headline', '')} -- {article.get('description', '')}"
