"""
Blitz Culture -- The Brain (Phase 3)
----------------------------------------
Decides (1) WHICH content type to post and (2) WHICH subject(s) it covers.
`designer_agent.py` / `system_prompt.txt` only ever solved half of that
problem (subject selection off a single incoming trigger) -- this module is
the missing piece: content-type selection, with hard variety/data rules
enforced in Python *before* any LLM call happens.

Pipeline:
  1. Python checks which of the 7 content types have the DATA they need
     (fresh diff report, non-empty market-gap report, a real news trigger,
     etc.) -- ineligible types are dropped, full stop, no LLM involved.
  2. Python applies variety rules from content_history.py (don't repeat a
     content type or a player too soon) -- with a guaranteed quiet-day
     fallback so overall/position/favorites are never ALL excluded at once.
  3. Deterministic, evergreen picks (position rotation, overall-window
     rotation, favorites) are decided in code -- no LLM call spent on a
     coin flip Python can already make correctly.
  4. Only when there's a genuine editorial decision (which mover story,
     which value gap, which head-to-head, which hypothetical) does this
     call Claude, and only with the pre-filtered eligible options + real
     candidate data -- the model can't invent a slot or a player.

Usage:
    from content_brain import run_brain
    decision = run_brain()
    # {"chosen_slot": "...", "subjects": [...], "params": {...},
    #  "reasoning": "...", "priority": "normal"}
"""
import json
import os
import re
from datetime import datetime, timezone

import pandas as pd
from anthropic import Anthropic
from dotenv import load_dotenv

import content_history as ch

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")
DIFF_CSV = os.path.join(PROJECT_ROOT, "outputs", "ranking_diff_report.csv")
GAPS_CSV = os.path.join(PROJECT_ROOT, "outputs", "market_gaps_2026.csv")
SLEEPER_ADP_CSV = os.path.join(PROJECT_ROOT, "data", "sleeper_adp_2026.csv")
HYPOTHETICAL_TRIGGERS = os.path.join(PROJECT_ROOT, "outputs", "hypothetical_triggers.json")

BRAIN_MODEL = "claude-sonnet-4-6"
POSITION_ROTATION = ["QB", "RB", "WR", "TE"]
OVERALL_START_ROTATION = [1, 13, 25]

# A "mover" or diff report older than this many hours is considered stale --
# don't post a "what changed" graphic off data from three days ago.
DIFF_FRESHNESS_HOURS = 48
MOVERS_VOR_HIGH_PRIORITY = 8.0   # abs vor_change above this => high priority

with open(os.path.join(PROJECT_ROOT, "brain_system_prompt.txt"), "r", encoding="utf-8") as f:
    BRAIN_SYSTEM_PROMPT = f.read()


def _norm(name: str) -> str:
    name = str(name).lower()
    name = re.sub(r"[.'’]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    return name.strip()


def _file_age_hours(path: str) -> float:
    if not os.path.exists(path):
        return float("inf")
    return (datetime.now().timestamp() - os.path.getmtime(path)) / 3600.0


def _load_sleeper_adp() -> dict:
    if not os.path.exists(SLEEPER_ADP_CSV):
        return {}
    df = pd.read_csv(SLEEPER_ADP_CSV)
    out = {}
    for _, r in df.iterrows():
        name = r.get("player_name")
        if isinstance(name, str) and name.strip() and pd.notna(r.get("adp")):
            out[_norm(name)] = {"adp": float(r["adp"]), "overall": int(r["adp_overall_rank"])}
    return out


# ---------------------------------------------------------------------------
# Deterministic evergreen subject selection -- no LLM call needed.
# ---------------------------------------------------------------------------
def next_position() -> str:
    last = ch.last_position_posted()
    if last not in POSITION_ROTATION:
        return POSITION_ROTATION[0]
    return POSITION_ROTATION[(POSITION_ROTATION.index(last) + 1) % len(POSITION_ROTATION)]


def next_overall_start() -> int:
    last = ch.last_overall_start_posted()
    if last not in OVERALL_START_ROTATION:
        return OVERALL_START_ROTATION[0]
    return OVERALL_START_ROTATION[(OVERALL_START_ROTATION.index(last) + 1) % len(OVERALL_START_ROTATION)]


# ---------------------------------------------------------------------------
# Step 1+2: eligibility (data requirements) + variety filtering
# ---------------------------------------------------------------------------
def _eligible_evergreen() -> list:
    """overall / position / favorites -- the quiet-day guarantee. Never all
    excluded at once even if all three were used recently."""
    options = []
    types_data_ok = []

    if os.path.exists(RANKINGS_CSV):
        types_data_ok.append("overall")
        types_data_ok.append("position")
    if os.path.exists(RANKINGS_CSV) and os.path.exists(SLEEPER_ADP_CSV):
        types_data_ok.append("favorites")

    not_recent = [t for t in types_data_ok if not ch.content_type_recently_used(t)]
    if not_recent:
        eligible_types = not_recent
    elif types_data_ok:
        # Quiet-day fallback: every evergreen type was used recently AND
        # nothing else is eligible -- allow the least-recently-used one
        # anyway rather than posting nothing.
        def last_used_index(t):
            rec = ch.last_content_slot_of_type(t)
            return rec["timestamp"] if rec else ""
        eligible_types = [min(types_data_ok, key=last_used_index)]
    else:
        eligible_types = []

    for t in eligible_types:
        if t == "overall":
            options.append({
                "content_slot": "overall",
                "candidates": {"start": next_overall_start(), "top": 12},
                "priority_hint": "normal",
                "_deterministic_params": {"start": next_overall_start(), "top": 12},
                "_deterministic_subjects": [],
            })
        elif t == "position":
            pos = next_position()
            options.append({
                "content_slot": "position",
                "candidates": {"position": pos, "top": 10},
                "priority_hint": "normal",
                "_deterministic_params": {"position": pos, "top": 10, "start": 1},
                "_deterministic_subjects": [],
            })
        elif t == "favorites":
            options.append({
                "content_slot": "favorites",
                "candidates": {"top": 10},
                "priority_hint": "normal",
                "_deterministic_params": {"top": 10},
                "_deterministic_subjects": [],
            })
    return options


def _eligible_movers() -> dict:
    if ch.content_type_recently_used("movers"):
        return None
    if not os.path.exists(DIFF_CSV):
        return None
    if _file_age_hours(DIFF_CSV) > DIFF_FRESHNESS_HOURS:
        return None  # stale diff -- don't post "what changed" off old data
    diff = pd.read_csv(DIFF_CSV)
    if "vor_change" not in diff.columns:
        return None
    diff = diff[diff["vor_change"].abs() > 0.05]
    diff = diff[~diff["player_name"].apply(lambda n: ch.player_recently_featured(n))]
    if diff.empty:
        return None
    risers = diff.sort_values("vor_change", ascending=False).head(5)
    fallers = diff.sort_values("vor_change", ascending=True).head(5)
    max_abs_change = diff["vor_change"].abs().max()
    return {
        "content_slot": "movers",
        "candidates": {
            "risers": [{"name": r["player_name"], "vor_change": round(float(r["vor_change"]), 1),
                        "old_rank": int(r["our_rank_old"]), "new_rank": int(r["our_rank_new"])}
                       for _, r in risers.iterrows()],
            "fallers": [{"name": r["player_name"], "vor_change": round(float(r["vor_change"]), 1),
                         "old_rank": int(r["our_rank_old"]), "new_rank": int(r["our_rank_new"])}
                        for _, r in fallers.iterrows()],
        },
        "priority_hint": "high" if max_abs_change >= MOVERS_VOR_HIGH_PRIORITY else "normal",
    }


def _eligible_value() -> dict:
    if ch.content_type_recently_used("value"):
        return None
    if not os.path.exists(GAPS_CSV):
        return None
    gaps = pd.read_csv(GAPS_CSV)
    if gaps.empty:
        return None
    gaps = gaps[~gaps["value_player"].apply(lambda n: ch.player_recently_featured(n))]
    if gaps.empty:
        return None
    top = gaps.head(8)
    return {
        "content_slot": "value",
        "candidates": {"gaps": [
            {"value_player": r["value_player"], "position": r["position"],
             "vs_player": r["vs_player"], "win_gap": round(float(r["win_gap"]), 1),
             "adp_gap": round(float(r["adp_gap"]), 1)}
            for _, r in top.iterrows()
        ]},
        "priority_hint": "normal",
    }


def _eligible_value_carousel() -> dict:
    """The 6-slide carousel (summary + 5 individual comparisons) needs 5
    WHOLE pairs, not just 1 gap row, so it has its own tighter data bar than
    _eligible_value(). It also shares the same underlying market_gaps data
    as "value" -- if we just posted a plain "value" post recently, skip the
    carousel too for a few more posts so the same steals don't show up
    twice in different formats back-to-back."""
    if ch.content_type_recently_used("value_carousel"):
        return None
    if ch.content_type_recently_used("value", within=2):
        return None
    if not os.path.exists(GAPS_CSV):
        return None
    gaps = pd.read_csv(GAPS_CSV)
    if gaps.empty:
        return None
    gaps = gaps[~gaps["value_player"].apply(lambda n: ch.player_recently_featured(n))]
    gaps = gaps[~gaps["vs_player"].apply(lambda n: ch.player_recently_featured(n))]
    if len(gaps) < 5:
        return None  # not enough fresh pairs for a full 6-slide carousel
    top = gaps.head(5)
    return {
        "content_slot": "value_carousel",
        "candidates": {"gaps": [
            {"value_player": r["value_player"], "position": r["position"],
             "vs_player": r["vs_player"], "win_gap": round(float(r["win_gap"]), 1),
             "adp_gap": round(float(r["adp_gap"]), 1)}
            for _, r in top.iterrows()
        ]},
        "priority_hint": "normal",
    }


def _eligible_compare() -> dict:
    if ch.content_type_recently_used("compare"):
        return None
    if not os.path.exists(RANKINGS_CSV):
        return None
    df = pd.read_csv(RANKINGS_CSV)
    adps = _load_sleeper_adp()
    candidates = []
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = df[df["position"] == pos].sort_values("our_rank").head(8)
        for _, r in sub.iterrows():
            if ch.player_recently_featured(r["player_name"]):
                continue
            a = adps.get(_norm(r["player_name"]))
            candidates.append({
                "name": r["player_name"], "position": pos, "our_rank": int(r["our_rank"]),
                "vor": round(float(r["vor"]), 1), "adp": a["adp"] if a else None,
            })
    if len(candidates) < 2:
        return None
    return {
        "content_slot": "compare",
        "candidates": {"players": candidates},
        "priority_hint": "normal",
    }


def _eligible_hypothetical() -> dict:
    if ch.content_type_recently_used("hypothetical"):
        return None
    if not os.path.exists(HYPOTHETICAL_TRIGGERS):
        return None
    with open(HYPOTHETICAL_TRIGGERS, "r", encoding="utf-8") as f:
        try:
            triggers = json.load(f)
        except json.JSONDecodeError:
            return None
    pending = [t for t in triggers if not t.get("used") and not ch.player_recently_featured(t.get("mover", ""))]
    if not pending:
        return None
    return {
        "content_slot": "hypothetical",
        "candidates": {"pending_triggers": pending},
        "priority_hint": "high",
    }


def build_eligible_options() -> list:
    """The full set the brain is allowed to choose from this run. Order:
    editorial/newsworthy options first (so the LLM sees them prominently),
    evergreen fallback last."""
    options = []
    for fn in (_eligible_hypothetical, _eligible_movers, _eligible_value_carousel,
              _eligible_value, _eligible_compare):
        opt = fn()
        if opt:
            options.append(opt)
    options.extend(_eligible_evergreen())
    return options


# ---------------------------------------------------------------------------
# Step 3/4: decide -- deterministic if ONLY evergreen is eligible, else LLM
# ---------------------------------------------------------------------------
def _parse_llm_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def _call_llm(eligible_options: list) -> dict:
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    payload = {
        "eligible_options": [
            {"content_slot": o["content_slot"], "candidates": o["candidates"],
             "priority_hint": o["priority_hint"]}
            for o in eligible_options
        ],
        "recent_history": ch.recent(5),
    }
    response = client.messages.create(
        model=BRAIN_MODEL,
        max_tokens=1000,
        system=BRAIN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    decision = _parse_llm_json(response.content[0].text)

    valid_slots = {o["content_slot"] for o in eligible_options}
    if decision.get("chosen_slot") not in valid_slots:
        raise ValueError(f"Brain chose an ineligible slot: {decision.get('chosen_slot')!r} "
                          f"not in {valid_slots}")
    return decision


def run_brain() -> dict:
    """Returns {"chosen_slot", "subjects", "params", "reasoning", "priority"}."""
    eligible = build_eligible_options()
    if not eligible:
        return {
            "chosen_slot": None, "subjects": [], "params": {},
            "reasoning": "No content types are eligible -- missing outputs/player_rankings_2026.csv? "
                         "Run analysis/player_ranking_v1.py first.",
            "priority": "normal",
        }

    editorial = [o for o in eligible if o["content_slot"] not in ("overall", "position", "favorites")]

    # Pure evergreen, single-option case: no editorial call needed at all.
    if not editorial and len(eligible) == 1:
        only = eligible[0]
        return {
            "chosen_slot": only["content_slot"],
            "subjects": only.get("_deterministic_subjects", []),
            "params": only.get("_deterministic_params", {}),
            "reasoning": "No editorial or high-priority content eligible this run -- "
                         "deterministic evergreen rotation (no LLM call).",
            "priority": "normal",
        }

    # Multiple evergreen options but no editorial content -- still let
    # Python decide (rotation is a coin-flip Python can make correctly) by
    # picking the one whose content type was used longest ago.
    if not editorial:
        def staleness(o):
            rec = ch.last_content_slot_of_type(o["content_slot"])
            return rec["timestamp"] if rec else ""
        chosen = min(eligible, key=staleness)
        return {
            "chosen_slot": chosen["content_slot"],
            "subjects": chosen.get("_deterministic_subjects", []),
            "params": chosen.get("_deterministic_params", {}),
            "reasoning": "Multiple evergreen options eligible, no editorial content -- "
                         "picked the least-recently-used evergreen slot (no LLM call).",
            "priority": "normal",
        }

    # A genuine editorial decision exists -- call Claude with the
    # pre-filtered, data-grounded options.
    return _call_llm(eligible)


if __name__ == "__main__":
    decision = run_brain()
    print(json.dumps(decision, indent=2))
