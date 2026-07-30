"""
Shared logic for comparing two Vegas prop-line snapshots and expressing the
difference in fantasy points. Used by both scripts/compare_vegas_snapshots.py
(the standalone line-movement monitor) and analysis/ranking_diff_report.py
(to explain *why* a player's ranking moved -- did their own inputs change?).
"""

from typing import Optional

import pandas as pd
from sqlalchemy import text

# yards-per-point / per-TD conversion, matching app/integrations/player_projection.py
YARDS_DIVISOR = {"rec_yards_line": 10.0, "rush_yards_line": 10.0, "pass_yards_line": 25.0}
TD_POINTS = {"rec_tds_line": 6.0, "rush_tds_line": 6.0, "pass_tds_line": 4.0}
STAT_FIELDS = list(YARDS_DIVISOR) + list(TD_POINTS)


def point_impact(field: str, delta: float) -> float:
    if field in YARDS_DIVISOR:
        return delta / YARDS_DIVISOR[field]
    return delta * TD_POINTS[field]


def load_last_two_snapshot_timestamps(engine, limit: int = 2) -> list:
    return pd.read_sql(text(
        f"SELECT DISTINCT scraped_at FROM player_prop_line_snapshots ORDER BY scraped_at DESC LIMIT {limit}"
    ), engine)["scraped_at"].tolist()


def load_snapshot(engine, scraped_at) -> pd.DataFrame:
    cols = ", ".join(STAT_FIELDS)
    return pd.read_sql(text(
        f"SELECT player_name, position, {cols} FROM player_prop_line_snapshots WHERE scraped_at = :ts"
    ), engine, params={"ts": scraped_at})


def diff_snapshots(newer: pd.DataFrame, older: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per player with ANY stat-line change: player_name,
    position, total_impact (points), changes (human-readable string).
    Players with no change in any field are omitted entirely.
    """
    merged = newer.merge(older, on="player_name", how="inner", suffixes=("_new", "_old"))

    rows = []
    for _, r in merged.iterrows():
        total_impact = 0.0
        changes = []
        for field in STAT_FIELDS:
            new_val, old_val = r[f"{field}_new"], r[f"{field}_old"]
            if pd.isna(new_val) or pd.isna(old_val):
                continue
            delta = new_val - old_val
            if abs(delta) < 1e-6:
                continue
            impact = point_impact(field, delta)
            total_impact += impact
            changes.append(f"{field.replace('_line', '')} {old_val:+.1f}->{new_val:+.1f} ({impact:+.1f} pts)")
        if changes:
            rows.append({
                "player_name": r["player_name"],
                "position": r.get("position_new") or r.get("position_old"),
                "total_impact": total_impact,
                "changes": "; ".join(changes),
            })
    return pd.DataFrame(rows)


def diff_latest_two_snapshots(engine) -> Optional[tuple]:
    """Returns (diff_df, older_ts, newer_ts), or None if fewer than 2
    snapshots exist yet."""
    timestamps = load_last_two_snapshot_timestamps(engine)
    if len(timestamps) < 2:
        return None
    newer_ts, older_ts = timestamps[0], timestamps[1]
    newer = load_snapshot(engine, newer_ts)
    older = load_snapshot(engine, older_ts)
    return diff_snapshots(newer, older), older_ts, newer_ts
