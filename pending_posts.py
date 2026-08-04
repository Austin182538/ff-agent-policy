"""
Blitz Culture -- Pending post queue (Phase 6 support)
----------------------------------------------------------
Windows Task Scheduler runs unattended -- there's no one there to answer an
input() prompt at 9:30am. During the semi-autonomous testing period
(roadmap Phase 6), scheduled runs use `orchestrator.py --queue`: the graphic
and caption get generated and parked here instead of published immediately.
A human reviews and approves/rejects each one with `review_pending.py`.

Record shape:
{
  "id": "20260731T183000-position",
  "queued_at": "2026-07-31T18:30:00Z",
  "decision": { ...the full content_brain decision dict... },
  "graphic": { "image_path": "...", "theme": "...", "variant": "...", "layout": "..." },
  "caption": "full caption text incl. hashtags",
}
"""
import json
import os
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PENDING_PATH = os.path.join(PROJECT_ROOT, "outputs", "pending_posts.json")
REJECTED_LOG_PATH = os.path.join(PROJECT_ROOT, "outputs", "rejected_posts.json")


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _save(path: str, items: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def load_pending() -> list:
    return _load(PENDING_PATH)


def add_pending(decision: dict, graphic: dict, caption: str) -> dict:
    now = datetime.now(timezone.utc)
    entry = {
        "id": f"{now.strftime('%Y%m%dT%H%M%S')}-{decision.get('chosen_slot', 'unknown')}",
        "queued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decision": decision,
        "graphic": graphic,
        "caption": caption,
    }
    items = load_pending()
    items.append(entry)
    _save(PENDING_PATH, items)
    return entry


def remove_pending(entry_id: str) -> dict:
    items = load_pending()
    match = next((i for i in items if i["id"] == entry_id), None)
    items = [i for i in items if i["id"] != entry_id]
    _save(PENDING_PATH, items)
    return match


def log_rejected(entry: dict, reason: str = "") -> None:
    rejected = _load(REJECTED_LOG_PATH)
    rejected.append({**entry, "rejected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "reason": reason})
    _save(REJECTED_LOG_PATH, rejected)
