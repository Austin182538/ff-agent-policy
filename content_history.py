"""
Blitz Culture -- Post history + variety enforcement
-----------------------------------------------------
Gives the brain (content_brain.py) memory. Every successful post gets logged
here so future runs can avoid repeating the same content type or the same
player too soon.

This is Python-enforced (not LLM-enforced) on purpose -- see the roadmap:
variety is a hard rule, not a suggestion the model might ignore.

Record shape written per post:
{
  "timestamp": "2026-07-31T18:05:00Z",
  "content_slot": "position",              # one of the 7 content types
  "featured_players": ["Ja'Marr Chase"],   # primary subject(s), [] if none
  "parameters": {"position": "WR", "top": 10},
  "layout": "list",
  "theme": "midnight_gold",
  "caption_hook": "first line/hook of the caption, for quick scanning",
  "image_path": "outputs/graphics/position_WR_top10_20260731T180500.png",
  "image_paths": null,                     # carousel posts only: all slide paths, in order
  "ig_media_id": "17895..."                # null until publish confirms
}
"""
import json
import os
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(PROJECT_ROOT, "outputs", "post_history.json")

# Variety windows -- tune here, not scattered through the brain logic.
NO_REPEAT_CONTENT_TYPE_WITHIN = 3   # don't pick the same content type two+ times in the last N posts
NO_REPEAT_PLAYER_WITHIN = 5         # don't feature the same player as a subject in the last N posts


def load_history() -> list:
    if not os.path.exists(HISTORY_PATH):
        return []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def save_history(history: list) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def log_post(content_slot: str, featured_players: list, parameters: dict,
             layout: str = "", theme: str = "", caption_hook: str = "",
             image_path: str = "", ig_media_id: str = None,
             image_paths: list = None) -> dict:
    """Append a completed post to history and persist it. Returns the record.

    `image_paths` (plural) is for carousel posts (multiple slides) -- pass a
    list and `image_path` (singular) is filled in as the first slide for any
    older code/log-scanning that only looks at the singular field. Regular
    single-image posts just pass `image_path` as before; `image_paths` stays
    None."""
    record = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content_slot": content_slot,
        "featured_players": featured_players or [],
        "parameters": parameters or {},
        "layout": layout,
        "theme": theme,
        "caption_hook": caption_hook,
        "image_path": image_path or (image_paths[0] if image_paths else ""),
        "image_paths": image_paths,
        "ig_media_id": ig_media_id,
    }
    history = load_history()
    history.append(record)
    save_history(history)
    return record


def recent(n: int) -> list:
    """Most recent n posts, newest last (same order as storage)."""
    history = load_history()
    return history[-n:] if n > 0 else []


def content_type_recently_used(content_slot: str, within: int = NO_REPEAT_CONTENT_TYPE_WITHIN) -> bool:
    return any(p.get("content_slot") == content_slot for p in recent(within))


def player_recently_featured(player_name: str, within: int = NO_REPEAT_PLAYER_WITHIN) -> bool:
    key = player_name.strip().lower()
    for p in recent(within):
        if any(key == fp.strip().lower() for fp in p.get("featured_players", [])):
            return True
    return False


def any_players_recently_featured(player_names: list, within: int = NO_REPEAT_PLAYER_WITHIN) -> bool:
    return any(player_recently_featured(name, within) for name in player_names)


def last_content_slot_of_type(content_slot: str):
    """Most recent post record matching a content type, or None."""
    for p in reversed(load_history()):
        if p.get("content_slot") == content_slot:
            return p
    return None


def last_position_posted():
    """The `position` param of the most recent `position`-type post, or None."""
    rec = last_content_slot_of_type("position")
    if not rec:
        return None
    return rec.get("parameters", {}).get("position")


def last_overall_start_posted():
    rec = last_content_slot_of_type("overall")
    if not rec:
        return None
    return rec.get("parameters", {}).get("start", 1)
