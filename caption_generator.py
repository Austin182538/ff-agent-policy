"""
Blitz Culture -- Caption generation (Phase 2)
------------------------------------------------
Turns a content decision (content_slot + params, as produced by
content_brain.py) into a posting-ready caption: a 2-4 paragraph LLM-written
body grounded in real ranking/diff/market-gap data, plus a deterministic
hashtag block and CTA appended in code (not left to the model).

Deliberately standalone -- does NOT import scripts/generate_ranking_graphic.py
or viz/, so caption generation never needs a headless-browser/Playwright
environment. It reads the same CSVs directly.

Usage:
    from caption_generator import generate_caption
    caption = generate_caption("position", {"position": "WR", "top": 10, "start": 1})
"""
import json
import os
import random
import re

import pandas as pd
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")
DIFF_CSV = os.path.join(PROJECT_ROOT, "outputs", "ranking_diff_report.csv")
GAPS_CSV = os.path.join(PROJECT_ROOT, "outputs", "market_gaps_2026.csv")
SLEEPER_ADP_CSV = os.path.join(PROJECT_ROOT, "data", "sleeper_adp_2026.csv")

CAPTION_MODEL = "claude-sonnet-4-6"

with open(os.path.join(PROJECT_ROOT, "caption_system_prompt.txt"), "r", encoding="utf-8") as f:
    CAPTION_SYSTEM_PROMPT = f.read()


# ---------------------------------------------------------------------------
# Static hashtag pool -- Phase 2 decision: no live scraping, ~30 curated tags.
# Selection below is deterministic code, not an LLM choice.
# ---------------------------------------------------------------------------
CORE_TAGS = [
    "#FantasyFootball", "#NFL", "#FantasyFootballAdvice", "#FFB",
    "#DynastyFootball", "#RedraftFantasy", "#FantasyFootball2026",
]
POSITION_TAGS = {
    "QB": ["#Quarterbacks", "#NFLQBs", "#QB1"],
    "RB": ["#RunningBacks", "#RB1", "#WorkhorseBack"],
    "WR": ["#WideReceivers", "#WR1", "#FantasyWR"],
    "TE": ["#TightEnds", "#TE1", "#FantasyTE"],
}
GENERAL_POOL = [
    "#FantasyFootballCommunity", "#WaiverWire", "#StartSitAdvice",
    "#FantasyFootballTips", "#DraftPrep", "#FantasyFootballRankings",
    "#NFLDraft", "#GridironGang", "#FootballAnalytics", "#SleeperPicks",
    "#ADP", "#ValueOverReplacement", "#FantasyManager", "#RosterConstruction",
    "#NFLStats", "#FantasyFootballNation",
]

assert len(CORE_TAGS) + sum(len(v) for v in POSITION_TAGS.values()) + len(GENERAL_POOL) >= 28


def _norm(name: str) -> str:
    name = str(name).lower()
    name = re.sub(r"[.'’]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    return name.strip()


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


def build_hashtags(positions: list = None, player_names: list = None, count: int = 12) -> str:
    """Deterministically assemble the hashtag block: core tags + relevant
    position tags + a player-name tag per subject + a random sample from the
    general pool to fill out to `count`."""
    tags = list(CORE_TAGS)
    for pos in positions or []:
        tags.extend(POSITION_TAGS.get(pos.upper(), []))
    for name in player_names or []:
        slug = re.sub(r"[^A-Za-z]", "", name)
        if slug:
            tags.append(f"#{slug}")
    # de-dupe, preserve order
    seen = set()
    tags = [t for t in tags if not (t.lower() in seen or seen.add(t.lower()))]
    if len(tags) < count:
        pool = [t for t in GENERAL_POOL if t not in tags]
        random.shuffle(pool)
        tags.extend(pool[: count - len(tags)])
    return " ".join(tags[:count])


# ---------------------------------------------------------------------------
# Per-content-type data extraction -- pulls REAL numbers for the caption,
# mirroring what the graphic itself shows so the caption can't drift from it.
# ---------------------------------------------------------------------------
def _rankings_df() -> pd.DataFrame:
    if not os.path.exists(RANKINGS_CSV):
        raise FileNotFoundError(f"{RANKINGS_CSV} not found -- run analysis/player_ranking_v1.py first.")
    return pd.read_csv(RANKINGS_CSV)


def extract_data(content_slot: str, params: dict) -> dict:
    adps = _load_sleeper_adp()

    if content_slot == "overall":
        df = _rankings_df().sort_values("our_rank").reset_index(drop=True)
        top, start = params.get("top", 12), params.get("start", 1)
        sl = df.iloc[start - 1: start - 1 + top]
        return {"players": [
            {"name": r["player_name"], "position": r["position"], "rank": int(r["our_rank"]),
             "vor": round(float(r["vor"]), 1), "proj_pts": round(float(r["projected_ppr_points"]), 1),
             "adp": adps.get(_norm(r["player_name"]), {}).get("adp")}
            for _, r in sl.iterrows()
        ], "range": f"{start}-{start + len(sl) - 1}"}

    if content_slot == "position":
        df = _rankings_df()
        pos = params.get("position", "WR").upper()
        ranked = df[df["position"] == pos].sort_values("our_rank").reset_index(drop=True)
        top, start = params.get("top", 10), params.get("start", 1)
        sl = ranked.iloc[start - 1: start - 1 + top]
        return {"position": pos, "players": [
            {"name": r["player_name"], "team": r["team_abbr"], "pos_rank": start + i,
             "overall_rank": int(r["our_rank"]), "vor": round(float(r["vor"]), 1),
             "proj_pts": round(float(r["projected_ppr_points"]), 1),
             "adp": adps.get(_norm(r["player_name"]), {}).get("adp")}
            for i, (_, r) in enumerate(sl.iterrows())
        ]}

    if content_slot == "favorites":
        df = _rankings_df()
        cand = []
        for _, r in df.iterrows():
            if r["position"] == "QB":
                continue
            a = adps.get(_norm(r["player_name"]))
            if not a:
                continue
            gap = a["overall"] - int(r["our_rank"])
            if gap > 0:
                cand.append((gap, r, a))
        cand.sort(key=lambda t: t[0], reverse=True)
        top = params.get("top", 10)
        return {"players": [
            {"name": r["player_name"], "position": r["position"], "our_rank": int(r["our_rank"]),
             "adp": a["adp"], "adp_gap": gap, "proj_pts": round(float(r["projected_ppr_points"]), 1)}
            for gap, r, a in cand[:top]
        ]}

    if content_slot == "compare":
        df = _rankings_df()
        by_key = df.drop_duplicates("player_name").set_index(df["player_name"].apply(_norm))
        names = params.get("players", [])
        out = []
        for nm in names:
            k = _norm(nm)
            if k not in by_key.index:
                continue
            r = by_key.loc[k]
            a = adps.get(k)
            out.append({"name": r["player_name"], "position": r["position"], "team": r["team_abbr"],
                        "our_rank": int(r["our_rank"]), "vor": round(float(r["vor"]), 1),
                        "proj_pts": round(float(r["projected_ppr_points"]), 1),
                        "adp": a["adp"] if a else None})
        return {"players": out}

    if content_slot == "movers":
        if not os.path.exists(DIFF_CSV):
            return {"movers": []}
        diff = pd.read_csv(DIFF_CSV)
        diff = diff[diff["vor_change"].abs() > 0.05]
        direction = params.get("direction", "fallers")
        top = params.get("top", 5)
        sl = diff.sort_values("vor_change", ascending=(direction == "fallers")).head(top)
        return {"direction": direction, "movers": [
            {"name": r["player_name"], "position": r.get("position", ""),
             "old_rank": int(r["our_rank_old"]), "new_rank": int(r["our_rank_new"]),
             "rank_change": int(r["rank_change"]), "vor_change": round(float(r["vor_change"]), 1)}
            for _, r in sl.iterrows()
        ]}

    if content_slot in ("value", "value_carousel"):
        if not os.path.exists(GAPS_CSV):
            return {"gaps": []}
        gaps = pd.read_csv(GAPS_CSV)
        top = params.get("top", 5)
        sl = gaps.head(top)
        return {"gaps": [
            {"value_player": r["value_player"], "position": r["position"], "value_team": r["value_team"],
             "value_proj": round(float(r["value_proj"]), 1), "vs_player": r["vs_player"],
             "vs_proj": round(float(r["vs_proj"]), 1), "win_gap": round(float(r["win_gap"]), 1),
             "adp_gap": round(float(r["adp_gap"]), 1)}
            for _, r in sl.iterrows()
        ]}

    if content_slot == "hypothetical":
        df = _rankings_df()
        mover = params.get("mover", "")
        k = _norm(mover)
        ranked = df.sort_values("our_rank").reset_index(drop=True)
        match = ranked[ranked["player_name"].apply(_norm) == k]
        current_rank = int(match.iloc[0]["our_rank"]) if not match.empty else None
        return {
            "mover": mover, "current_rank": current_rank,
            "to_rank": params.get("to_rank"), "from_rank": params.get("from_rank"),
            "trigger_headline": params.get("trigger_headline", ""),
        }

    raise ValueError(f"Unknown content_slot: {content_slot}")


def _strip_em_dashes(text: str) -> str:
    """Hard rule, not just a prompt request -- models reach for em dashes
    out of habit even when told not to, so enforce it in code too. Swap
    any em dash (with its surrounding spacing) for a comma; simple and
    reliably grammatical rather than trying to guess a sentence break."""
    text = re.sub(r"\s*—\s*", ", ", text)
    text = re.sub(r",\s*,", ",", text)  # collapse if a comma already preceded it
    return text


def generate_caption(content_slot: str, params: dict, graphic_title: str = "",
                     hashtag_count: int = 12) -> dict:
    """Returns {"body": str, "hashtags": str, "full_caption": str}."""
    data = extract_data(content_slot, params)

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    user_payload = {"content_slot": content_slot, "data": data, "graphic_title": graphic_title}
    response = client.messages.create(
        model=CAPTION_MODEL,
        max_tokens=700,
        system=CAPTION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(user_payload)}],
    )
    body = _strip_em_dashes(response.content[0].text.strip())

    positions = []
    player_names = []
    if content_slot == "position":
        positions = [data.get("position")]
    for p in data.get("players", []):
        player_names.append(p["name"])
    for m in data.get("movers", []):
        player_names.append(m["name"])
    for g in data.get("gaps", []):
        player_names.append(g["value_player"])
    if data.get("mover"):
        player_names.append(data["mover"])

    hashtags = build_hashtags(positions=positions, player_names=player_names[:3], count=hashtag_count)
    full_caption = f"{body}\n\n{hashtags}"
    return {"body": body, "hashtags": hashtags, "full_caption": full_caption}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True,
                        choices=["overall", "position", "favorites", "compare", "movers", "value", "hypothetical"])
    parser.add_argument("--position", default="WR")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--players", default="", help='"Derrick Henry, Josh Jacobs"')
    parser.add_argument("--direction", default="fallers")
    parser.add_argument("--mover", default="")
    parser.add_argument("--to", dest="to_rank", type=int, default=None)
    parser.add_argument("--from", dest="from_rank", type=int, default=None)
    args = parser.parse_args()

    params = {"position": args.position, "top": args.top, "start": args.start,
              "players": [p.strip() for p in args.players.split(",") if p.strip()],
              "direction": args.direction, "mover": args.mover,
              "to_rank": args.to_rank, "from_rank": args.from_rank}
    result = generate_caption(args.type, params)
    print(result["full_caption"])
