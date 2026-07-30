"""
Minimal FantasyPros news stub. Not a priority for this pass -- this exists so
app/models/news_models.NewsItem has a real (if unused) fetch path, without
building a scheduled ingestion pipeline yet.

Get a free (non-commercial/prototyping) key at
https://www.fantasypros.com/api-data/ and set FANTASYPROS_API_KEY in .env to
enable this; otherwise it no-ops.
"""

from typing import Any, Dict, List, Optional
import logging
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.fantasypros.com/public/v2/json"


def fetch_fantasypros_news(limit: int = 25, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns a list of raw FantasyPros news items, or [] if no API key is configured."""
    if not settings.fantasypros_api_key:
        logger.info("FANTASYPROS_API_KEY not set -- skipping news fetch (this is expected for now).")
        return []

    params: Dict[str, Any] = {"limit": limit}
    if category:
        params["category"] = category

    response = requests.get(
        f"{BASE_URL}/nfl/news",
        headers={"x-api-key": settings.fantasypros_api_key},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("items", [])
