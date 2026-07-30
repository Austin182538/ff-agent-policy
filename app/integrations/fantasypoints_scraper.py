"""
Automated scraper for fantasypoints.com's season-long NFL player prop
articles. These are plain, server-rendered HTML tables (confirmed via a
direct plain-`requests` fetch -- no JS rendering needed), one `<table>` per
article, first row is a header row, one column each for the "FP Projection"
(fantasypoints' own point estimate -- NOT used, see note below) and the
book-derived "Highest Total (bet under)" / "Lowest Total (bet over)"
columns whose midpoint is this project's consensus-line convention.

Six articles cover receiving yards/TDs, rushing yards/TDs, and passing
yards/TDs -- the same six manually read and transcribed into
data/vegas_player_props_2026.csv earlier this project (see
scripts/build_vegas_props_2026.py). This module automates that same pull so
it can run unattended on a schedule (scripts/scrape_vegas_snapshot.py).

Note on "FP Projection": that column is fantasypoints' own proprietary
point projection, not a market price -- deliberately not scraped, to stay
consistent with using only real sportsbook lines throughout this project.
"""

import re
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# (url, stat_line_field_name) -- stat_line_field_name matches the columns on
# PlayerSeasonPropLine / PlayerPropLineSnapshot.
ARTICLES: List[Tuple[str, str]] = [
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-receiving-yards", "rec_yards_line"),
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-receiving-touchdowns", "rec_tds_line"),
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-rushing-yards", "rush_yards_line"),
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-rushing-touchdowns", "rush_tds_line"),
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-passing-yards", "pass_yards_line"),
    ("https://www.fantasypoints.com/nfl/articles/2026/nfl-player-props-passing-touchdowns", "pass_tds_line"),
]

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _first_number(cell_text: str) -> Optional[float]:
    """'1375.5 (-114, FD)' -> 1375.5. Returns None if no number found (a
    handful of rows have no line posted at all for that book/market yet)."""
    match = _NUMBER_RE.search(cell_text.replace(",", ""))
    return float(match.group()) if match else None


def fetch_prop_table(url: str) -> List[Tuple[str, Optional[float], Optional[float]]]:
    """Returns [(player_name, highest_total_under, lowest_total_over), ...]
    for one fantasypoints.com prop article. Raises requests.HTTPError on a
    non-200 response, and ValueError if the page structure doesn't match
    what's expected (so a silent site redesign doesn't produce garbage
    data -- fail loudly instead).
    """
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError(f"No <table> found on {url} -- site structure may have changed.")

    rows = tables[0].find_all("tr")
    if len(rows) < 2:
        raise ValueError(f"Table on {url} has too few rows ({len(rows)}) -- site structure may have changed.")

    header_cells = [td.get_text(strip=True).lower() for td in rows[0].find_all("td")]
    try:
        name_idx = 0  # player name is always the first column
        highest_idx = next(i for i, h in enumerate(header_cells) if "highest" in h)
        lowest_idx = next(i for i, h in enumerate(header_cells) if "lowest" in h)
    except StopIteration:
        raise ValueError(f"Expected 'Highest Total'/'Lowest Total' columns not found on {url}: {header_cells}")

    results = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if len(cells) <= max(highest_idx, lowest_idx):
            continue
        name = cells[name_idx].get_text(strip=True)
        if not name:
            continue
        highest = _first_number(cells[highest_idx].get_text(strip=True))
        lowest = _first_number(cells[lowest_idx].get_text(strip=True))
        results.append((name, highest, lowest))
    return results


def scrape_all_prop_lines() -> Dict[str, Dict[str, Optional[float]]]:
    """Fetches all six articles and merges them by player name (as scraped
    -- NOT yet normalized/matched against our DB; that's the caller's job,
    since name normalization needs the merge_key logic already living in
    analysis/player_ranking_v1.py and importing analysis/ into app/
    integrations/ would invert this project's dependency direction).

    Returns {player_name: {"rec_yards_line": ..., "rec_tds_line": ..., ...}}
    with the midpoint of (highest, lowest) already computed per line.
    """
    merged: Dict[str, Dict[str, Optional[float]]] = {}
    for url, field in ARTICLES:
        for name, highest, lowest in fetch_prop_table(url):
            if highest is None or lowest is None:
                line = highest if highest is not None else lowest
            else:
                line = round((highest + lowest) / 2, 1)
            merged.setdefault(name, {})[field] = line
    return merged
