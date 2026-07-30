#!/usr/bin/env python3
"""
Parse a Sleeper half-PPR projections+ADP export (pasted as raw text into
data/sleeper_raw_2026.txt) into a clean data/sleeper_adp_2026.csv.

Sleeper is the ADP source we actually draft against, so its ADP -- not the
FantasyPros ECR proxy we were using before -- is what the graphics compare our
ranks to. The raw export is one value per line in this repeating block:

    <short name>            e.g. "B. Robinson"   (sometimes appears twice, and
    <short name again>       may carry a "rookie-label" suffix or a "*"/status
    <POS> - <TEAM>(<BYE>)    line; we key off the "POS - TEAM(BYE)" line)
    <game info>              e.g. "Sun 12:00 PM@ PIT"   (skipped)
    PTS  ADP  rush:ATT YD TD  rec:REC TAR YD TD  pass:CMP ATT YD TD   (13 nums,
                                                    "-" where not applicable)

Sleeper only prints abbreviated first names ("B. Robinson"), so we resolve each
to the full name in outputs/player_rankings_2026.csv by matching on
(last name, position) and disambiguating with first initial + team. ADP overall
and position ranks are derived by sorting the parsed board by ADP.

    venv\\Scripts\\python.exe scripts\\parse_sleeper_adp.py
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_PATH = os.path.join(PROJECT_ROOT, "data", "sleeper_raw_2026.txt")
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "sleeper_adp_2026.csv")
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")

POS_RE = re.compile(r"^([A-Za-z][A-Za-z,]*)\s*-\s*([A-Z]{2,3})?\((\d+)\)$")
NUM_RE = re.compile(r"^-$|^\d+(?:\.\d+)?$")

# PTS, ADP, then rushing / receiving / passing components in export column order.
FIELDS = ["proj_pts", "adp", "rush_att", "rush_yd", "rush_td",
          "rec", "tar", "rec_yd", "rec_td", "cmp", "pass_att", "pass_yd", "pass_td"]


def _num(tok):
    return None if tok == "-" else float(tok)


def _last_token(name: str) -> str:
    """Lowercased final name token, punctuation stripped -- the join key.
    'A. St. Brown' -> 'brown', 'J. Smith-Njigba' -> 'smith-njigba'. A Jr/Sr/III
    style suffix is dropped first so our 'James Cook III' keys on 'cook'."""
    name = re.sub(r"rookie-label$", "", name).strip()
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name, flags=re.I)
    tok = name.split()[-1] if name.split() else name
    return re.sub(r"[.'\u2019]", "", tok).lower()


def parse_raw(path: str) -> list:
    lines = [l.rstrip("\n").strip() for l in open(path, encoding="utf-8")]
    players = []
    for i, line in enumerate(lines):
        m = POS_RE.match(line)
        if not m:
            continue
        position = m.group(1).split(",")[0]      # "DB,WR" -> "DB"; here always RB/WR/TE/QB
        team = m.group(2) or ""
        raw_name = re.sub(r"rookie-label$", "", lines[i - 1]).strip()

        nums = []
        j = i + 1
        while j < len(lines) and len(nums) < len(FIELDS):
            if NUM_RE.match(lines[j]):
                nums.append(lines[j])
            j += 1
        if len(nums) < len(FIELDS):
            print(f"  ! skipped {raw_name} ({position} {team}): only {len(nums)} values")
            continue

        rec = {"sleeper_name": raw_name, "position": position, "team": team}
        for k, tok in zip(FIELDS, nums):
            rec[k] = _num(tok)
        rec["last_token"] = _last_token(raw_name)
        rec["initial"] = re.sub(r"[^a-z]", "", raw_name[:1].lower())
        players.append(rec)
    return players


def resolve_names(players: list) -> None:
    """Fill each player's 'player_name' with the full name from our rankings
    (matched on last name + position, disambiguated by initial + team)."""
    ours = pd.read_csv(RANKINGS_CSV)
    ours["last_token"] = ours["player_name"].apply(_last_token)
    ours["initial"] = ours["player_name"].str[:1].str.lower()

    for p in players:
        cand = ours[(ours["last_token"] == p["last_token"]) & (ours["position"] == p["position"])]
        if len(cand) > 1:
            by_init = cand[cand["initial"] == p["initial"]]
            cand = by_init if len(by_init) else cand
        if len(cand) > 1 and p["team"]:
            by_team = cand[cand["team_abbr"] == p["team"]]
            cand = by_team if len(by_team) else cand
        p["player_name"] = cand.iloc[0]["player_name"] if len(cand) else ""
        if not len(cand):
            print(f"  ? no rankings match for {p['sleeper_name']} ({p['position']} {p['team']})")


def main():
    if not os.path.exists(RAW_PATH):
        raise SystemExit(f"{RAW_PATH} not found -- paste the Sleeper export there first.")
    players = parse_raw(RAW_PATH)
    print(f"Parsed {len(players)} players from the Sleeper export.")

    resolve_names(players)

    # ADP-board ranks (sorted by ADP), overall and within position.
    players.sort(key=lambda p: p["adp"] if p["adp"] is not None else 9999)
    pos_counter = {}
    for overall, p in enumerate(players, start=1):
        p["adp_overall_rank"] = overall
        pos_counter[p["position"]] = pos_counter.get(p["position"], 0) + 1
        p["adp_pos_rank"] = pos_counter[p["position"]]

    cols = (["player_name", "sleeper_name", "position", "team", "adp",
             "adp_overall_rank", "adp_pos_rank"] + FIELDS[:1] + FIELDS[2:])
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for p in players:
            w.writerow(p)

    matched = sum(1 for p in players if p["player_name"])
    print(f"Wrote {len(players)} rows ({matched} matched to rankings) -> {OUT_PATH}")
    for p in players:
        if p["sleeper_name"] in ("B. Robinson", "D. Henry", "J. Jacobs"):
            print(f"  {p['sleeper_name']:<14} -> {p['player_name']:<20} "
                  f"ADP {p['adp']}  (overall {p['adp_overall_rank']}, {p['position']}{p['adp_pos_rank']})")


if __name__ == "__main__":
    main()
