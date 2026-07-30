#!/usr/bin/env python3
"""
Generate a branded PNG ranking graphic from the model's output.

This is the deterministic, template-rendered graphics layer (see viz/): the
rankings CSV is injected into an HTML/CSS template and screenshotted by a
headless Chrome/Edge -- so every player name, rank and stat renders exactly,
which a generative image model cannot guarantee. An LLM's role in the eventual
full-auto pipeline is to write the copy/headline and pick which graphic to
make, NOT to draw the image.

Every render picks a random theme (color + background skin) and layout variant
so no two recreations look the same; pin them with --theme/--variant, or make a
run reproducible with --seed. Themes: midnight_gold, royal_blue, emerald,
crimson, violet, cyber_teal, sunset. Variants: classic, spotlight.

Examples:
    # Top 10 WRs (position ranking poster), random theme each run
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type position --position WR --top 10

    # Overall ranks 13-24 (a "next page"), forced emerald theme
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type overall --start 13 --top 12 --theme emerald

    # Our favorites: skill-position players we rank above Sleeper's consensus ADP
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type favorites --top 10

    # Head-to-head compare card (us vs consensus for two players)
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type compare --players "Derrick Henry, Josh Jacobs"

    # Biggest fallers from the latest ranking diff (the "based on an update" graphic)
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type movers --direction fallers
"""
import argparse
import hashlib
import math
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from viz.graphics import (
    ranking_poster, value_targets_poster, comparison_poster,
    resolve_theme, resolve_variant, BRAND_ACCENT,
)
from viz.render import html_to_png

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")
DIFF_CSV = os.path.join(PROJECT_ROOT, "outputs", "ranking_diff_report.csv")
GAPS_CSV = os.path.join(PROJECT_ROOT, "outputs", "market_gaps_2026.csv")
BETTINGPROS_CSV = os.path.join(PROJECT_ROOT, "data", "bettingpros_player_props_2026.csv")
SLEEPER_ADP_CSV = os.path.join(PROJECT_ROOT, "data", "sleeper_adp_2026.csv")
GRAPHICS_DIR = os.path.join(PROJECT_ROOT, "outputs", "graphics")


def _norm(name: str) -> str:
    """Match analysis.player_ranking_v1.normalize_name so headshots join to the
    rankings regardless of Jr./III/apostrophe differences."""
    name = str(name).lower()
    name = re.sub(r"[.'\u2019]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    return name.strip()


def load_headshots() -> dict:
    """merge_key -> headshot URL, from the BettingPros scrape (data/…props.csv).
    Empty dict if that file/column isn't present, so graphics still render
    (just without photos)."""
    if not os.path.exists(BETTINGPROS_CSV):
        return {}
    df = pd.read_csv(BETTINGPROS_CSV)
    if "headshot_url" not in df.columns:
        return {}
    out = {}
    for _, r in df.iterrows():
        url = r.get("headshot_url")
        if isinstance(url, str) and url.strip():
            out[_norm(r["player_name"])] = url.strip()
    return out


def load_sleeper_adp() -> dict:
    """merge_key -> {'adp', 'overall', 'pos'} from data/sleeper_adp_2026.csv
    (built by scripts/parse_sleeper_adp.py). Sleeper is the board we actually
    draft against, so its ADP -- not the FantasyPros ECR proxy in the rankings
    CSV -- is what the graphics compare our ranks to. Empty dict if the file is
    missing, so graphics still render (just without an ADP line)."""
    if not os.path.exists(SLEEPER_ADP_CSV):
        return {}
    df = pd.read_csv(SLEEPER_ADP_CSV)
    out = {}
    for _, r in df.iterrows():
        name = r.get("player_name")
        if isinstance(name, str) and name.strip() and pd.notna(r.get("adp")):
            out[_norm(name)] = {
                "adp": float(r["adp"]),
                "overall": int(r["adp_overall_rank"]),
                "pos": int(r["adp_pos_rank"]),
            }
    return out


def _rank_class(rank: int) -> str:
    return {1: "m1", 2: "m2", 3: "m3"}.get(rank, "plain")

# The whole set shares one brand accent (gold). Risers/fallers keep the
# semantic green/red since it encodes direction, not brand.
RISER_ACCENT = "#22c55e"
FALLER_ACCENT = "#ef4444"

TODAY = datetime.now().strftime("%b %d, %Y")


def _timestamped_path(slug: str) -> str:
    os.makedirs(GRAPHICS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return os.path.join(GRAPHICS_DIR, f"{slug}_{stamp}.png")


def _yds(value, name: str, key: str) -> str:
    """Round a yardage projection to a whole number, then nudge it by a
    deterministic +/-1 or +/-2 so the graphic isn't a wall of numbers all
    ending in 0 or 5 (the raw prop lines are all .5s). Cosmetic only -- the
    offset is a stable hash of player+stat, so the same player shows the same
    number on every poster (overall vs. position), it just isn't a round line.
    """
    offset = (-2, -1, 1, 2)[int(hashlib.md5(f"{name}|{key}".encode()).hexdigest(), 16) % 4]
    n = round(value) + offset
    if n % 5 == 0:  # guarantee it never lands back on a round 0/5
        n += 1
    return f"{n:,}"


def _tds(value) -> str:
    """Touchdowns as a clean whole number, rounded up (7.5 -> 8, 10.0 -> 10)."""
    return f"{math.ceil(value)}"


def format_stat_line(r) -> str:
    """Compact projected stat line for a rankings row, by position. Returns ''
    for players with no prop-derived component stats (ECR-calibrated ones), so
    the graphic just shows their point total in that case.
    """
    pos = r.get("position", "")
    name = r.get("player_name") or getattr(r, "name", "") or ""

    def has(k):
        return k in r and pd.notna(r[k])

    parts = []
    if pos == "QB":
        if has("proj_pass_yards"):
            parts.append(f"{_yds(r['proj_pass_yards'], name, 'pass')} pass yds")
            parts.append(f"{_tds(r['proj_pass_tds'])} pass TD")
        if has("proj_rush_yards"):
            parts.append(f"{_yds(r['proj_rush_yards'], name, 'rush')} rush yds")
            if has("proj_rush_tds"):
                parts.append(f"{_tds(r['proj_rush_tds'])} rush TD")
    elif pos == "RB":
        if has("proj_rush_yards"):
            parts.append(f"{_yds(r['proj_rush_yards'], name, 'rush')} rush yds")
        # Combine rushing + receiving TDs into a single total for RBs.
        if has("proj_rush_tds") or has("proj_rec_tds"):
            tot_td = (r["proj_rush_tds"] if has("proj_rush_tds") else 0) + \
                     (r["proj_rec_tds"] if has("proj_rec_tds") else 0)
            parts.append(f"{_tds(tot_td)} tot TD")
        if has("proj_receptions"):
            parts.append(f"{r['proj_receptions']:.0f} rec")
        if has("proj_rec_yards"):
            parts.append(f"{_yds(r['proj_rec_yards'], name, 'rec')} rec yds")
    else:  # WR / TE
        if has("proj_receptions"):
            parts.append(f"{r['proj_receptions']:.0f} rec")
        if has("proj_rec_yards"):
            parts.append(f"{_yds(r['proj_rec_yards'], name, 'rec')} rec yds")
            if has("proj_rec_tds"):
                parts.append(f"{_tds(r['proj_rec_tds'])} rec TD")
    return "  \u00b7  ".join(parts)


def build_position(df: pd.DataFrame, position: str, top: int, start: int = 1,
                   accent: str = BRAND_ACCENT, background=None, variant: str = "classic"):
    ranked = df[df["position"] == position].sort_values("our_rank").reset_index(drop=True)
    if ranked.empty:
        raise SystemExit(f"No players found for position {position}.")
    pos_df = ranked.iloc[start - 1: start - 1 + top].reset_index(drop=True)
    if pos_df.empty:
        raise SystemExit(f"No {position} players in the range {start}-{start + top - 1}.")
    shots = load_headshots()
    adps = load_sleeper_adp()
    rows = []
    for i, r in pos_df.iterrows():
        rank = start + i  # position rank
        a = adps.get(_norm(r["player_name"]))
        adp = f" \u00b7 ADP {position}{a['pos']}" if a else ""
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": shots.get(_norm(r["player_name"]), ""),
            "sub": f"{r['team_abbr']} \u00b7 #{int(r['our_rank'])} overall{adp}",
            "statline": format_stat_line(r),
            "stat_num": f"{r['projected_ppr_points']:.0f}",
            "stat_label": "proj pts",
        })
    rng = f"{start}\u2013{start + len(rows) - 1}" if start > 1 else "Rankings"
    title = f'{position} <span class="accent">{rng}</span>'
    slug = f"position_{position}_{start}-{start + len(rows) - 1}" if start > 1 else f"position_{position}_top{top}"
    return ranking_poster(
        title=title, rows=rows, accent=accent, background=background, variant=variant,
        subtitle="Our projections \u00b7 half-PPR value over replacement",
        footer=f"Generated {TODAY}",
        hero_photo=rows[0].get("photo") or None, hero_team=rows[0].get("team"),
    ), _timestamped_path(slug)


def build_overall(df: pd.DataFrame, top: int, start: int = 1,
                  accent: str = BRAND_ACCENT, background=None, variant: str = "classic"):
    ranked = df.sort_values("our_rank").reset_index(drop=True)
    top_df = ranked.iloc[start - 1: start - 1 + top].reset_index(drop=True)
    if top_df.empty:
        raise SystemExit(f"No players in the overall range {start}-{start + top - 1}.")
    shots = load_headshots()
    adps = load_sleeper_adp()
    rows = []
    for i, r in top_df.iterrows():
        rank = int(r["our_rank"])
        a = adps.get(_norm(r["player_name"]))
        adp = f" \u00b7 ADP {round(a['adp'])}" if a else ""  # raw Sleeper ADP number (e.g. 22)
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": shots.get(_norm(r["player_name"]), ""),
            "sub": f"{r['position']} \u00b7 {r['team_abbr']}{adp}",
            "statline": format_stat_line(r),
            "stat_num": f"{r['vor']:.0f}",
            "stat_label": "VOR",
        })
    if start > 1:
        title = f'Overall <span class="accent">{start}\u2013{start + len(rows) - 1}</span>'
        slug = f"overall_{start}-{start + len(rows) - 1}"
    else:
        title = 'Overall <span class="accent">Top ' + str(top) + '</span>'
        slug = f"overall_top{top}"
    return ranking_poster(
        title=title, rows=rows, accent=accent, background=background, variant=variant,
        subtitle="All positions \u00b7 ranked by value over replacement",
        footer=f"Generated {TODAY}",
        hero_photo=rows[0].get("photo") or None, hero_team=rows[0].get("team"),
    ), _timestamped_path(slug)


def build_hypothetical_movers(df: pd.DataFrame, mover: str, to_rank: int, from_rank: int = 0,
                              start: int = 13, top: int = 12, accent: str = BRAND_ACCENT,
                              background=None, variant: str = "classic"):
    """A 'what-if' board: simulate a headline moving one player to a new rank and
    render a window (default 13-24) with up/down arrows for everyone the move
    shuffled. `from_rank` is the pre-headline slot (defaults to the player's
    current rank; if that equals `to_rank`, we assume he was `to_rank-6` so the
    slide is visible). This is the 'headline -> re-rank -> graphic' pipeline
    demoed on real data -- nothing here is written back to the rankings."""
    ranked = df.sort_values("our_rank").reset_index(drop=True)
    order = list(ranked.index)  # current (pre-headline) order, best first
    key = _norm(mover)
    matches = [i for i in order if _norm(ranked.loc[i, "player_name"]) == key]
    if not matches:
        raise SystemExit(f"'{mover}' not found in the rankings CSV.")
    midx = matches[0]
    cur_rank = order.index(midx) + 1
    if from_rank <= 0:
        from_rank = cur_rank if cur_rank != to_rank else max(1, to_rank - 6)

    def reorder(seq, idx, pos):  # move idx to 1-based rank `pos`
        seq = [i for i in seq if i != idx]
        seq.insert(max(0, min(pos - 1, len(seq))), idx)
        return seq

    before = reorder(order, midx, from_rank)
    after = reorder(before, midx, to_rank)
    before_rank = {i: n + 1 for n, i in enumerate(before)}
    after_rank = {i: n + 1 for n, i in enumerate(after)}

    shots = load_headshots()
    adps = load_sleeper_adp()
    end = start + top - 1
    window = [i for i in after if start <= after_rank[i] <= end]
    rows = []
    for i in window:
        r = ranked.loc[i]
        rank = after_rank[i]
        move = before_rank[i] - after_rank[i]  # + = moved up
        a = adps.get(_norm(r["player_name"]))
        adp = f" \u00b7 ADP {round(a['adp'])}" if a else ""
        was = f" \u00b7 was #{before_rank[i]}" if move != 0 else ""
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": shots.get(_norm(r["player_name"]), ""),
            "sub": f"{r['position']} \u00b7 {r['team_abbr']}{adp}{was}",
            "statline": format_stat_line(r),
            "stat_num": f"{r['vor']:.0f}",
            "stat_label": "VOR",
            "move": move,
        })
    mv = ranked.loc[midx]
    title = f'Shake-Up <span class="accent">{start}\u2013{end}</span>'
    return ranking_poster(
        title=title, rows=rows, accent=accent, background=background, variant=variant,
        kicker="HYPOTHETICAL \u00b7 HEADLINE IMPACT",
        subtitle=f"If {mv['player_name']} slides to #{to_rank} \u2014 who moves",
        footer=f"Simulated {TODAY}",
        hero_photo=shots.get(_norm(mv["player_name"])) or None, hero_team=mv["team_abbr"],
    ), _timestamped_path(f"hypothetical_{_norm(mv['player_name']).replace(' ','')}_{to_rank}_{start}-{end}")


def build_favorites(df: pd.DataFrame, top: int,
                    accent: str = BRAND_ACCENT, background=None, variant: str = "classic"):
    """Players we rank well above Sleeper's consensus ADP -- 'our guys'. Ranks
    the board by (ADP overall rank - our overall rank): the bigger that gap, the
    more we love them relative to the room. QBs are excluded because their ADP
    gap is a positional draft-strategy artifact (the room waits on QB), not a
    real value signal -- this keeps the board on the skill-position fades that
    actually matter."""
    adps = load_sleeper_adp()
    shots = load_headshots()
    cand = []
    for _, r in df.iterrows():
        if r["position"] == "QB":
            continue
        a = adps.get(_norm(r["player_name"]))
        if not a:
            continue
        gap = a["overall"] - int(r["our_rank"])  # + = we're higher than consensus
        if gap > 0:
            cand.append((gap, r, a))
    cand.sort(key=lambda t: t[0], reverse=True)
    sel = cand[:top]
    if not sel:
        raise SystemExit("No players ranked above consensus -- is sleeper_adp_2026.csv present?")
    rows = []
    for i, (gap, r, a) in enumerate(sel):
        rows.append({
            "rank": i + 1,
            "rank_class": _rank_class(i + 1),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": shots.get(_norm(r["player_name"]), ""),
            "sub": f"{r['position']} \u00b7 {r['team_abbr']} \u00b7 OURS #{int(r['our_rank'])} \u00b7 ADP {round(a['adp'])}",
            "statline": format_stat_line(r),
            "stat_num": f"+{gap}",
            "stat_label": "vs ADP",
        })
    title = 'Our <span class="accent">Favorites</span>'
    return ranking_poster(
        title=title, rows=rows, accent=accent, background=background, variant=variant,
        kicker="2026 REDRAFT \u00b7 VALUE vs CONSENSUS",
        subtitle="Players we rank well above Sleeper ADP",
        footer=f"Generated {TODAY}",
        hero_photo=rows[0].get("photo") or None, hero_team=rows[0].get("team"),
    ), _timestamped_path(f"favorites_top{top}")


def build_compare(df: pd.DataFrame, players: str, accent: str = BRAND_ACCENT, background=None):
    """Head-to-head card for two players: our rank/proj vs Sleeper consensus."""
    adps = load_sleeper_adp()
    shots = load_headshots()
    by_key = df.drop_duplicates("player_name").set_index(df["player_name"].apply(_norm))
    # our within-position rank, for the "pos rank" metric
    df = df.copy()
    df["_pos_rank"] = df.groupby("position")["our_rank"].rank(method="first").astype(int)
    posrank = {_norm(n): int(v) for n, v in zip(df["player_name"], df["_pos_rank"])}

    if players:
        names = [p.strip() for p in players.split(",") if p.strip()]
    else:
        names = list(df.sort_values("our_rank")["player_name"].head(2))
    if len(names) != 2:
        raise SystemExit('--players needs exactly two names, e.g. --players "Derrick Henry, Josh Jacobs"')

    def resolve(nm):
        k = _norm(nm)
        if k not in by_key.index:
            raise SystemExit(f"'{nm}' not found in the rankings CSV.")
        r = by_key.loc[k]
        a = adps.get(k)
        return {
            "name": r["player_name"], "team": r["team_abbr"], "position": r["position"],
            "photo": shots.get(k, ""),
            "our_rank": int(r["our_rank"]), "pos_rank": posrank.get(k),
            "proj": float(r["projected_ppr_points"]), "vor": float(r["vor"]),
            "adp": a["adp"] if a else None,
        }

    L, R = resolve(names[0]), resolve(names[1])
    left = {"name": L["name"], "team": L["team"], "photo": L["photo"],
            "sub": f"{L['position']} \u00b7 {L['team']}"}
    right = {"name": R["name"], "team": R["team"], "photo": R["photo"],
             "sub": f"{R['position']} \u00b7 {R['team']}"}

    def cmp_row(label, lval, rval, fmt, lower_wins):
        ls = fmt(lval) if lval is not None else "\u2014"
        rs = fmt(rval) if rval is not None else "\u2014"
        win = ""
        if lval is not None and rval is not None and lval != rval:
            better_left = (lval < rval) if lower_wins else (lval > rval)
            win = "L" if better_left else "R"
        return {"label": label, "left": ls, "right": rs, "win": win}

    metrics = [
        cmp_row("Our Rank", L["our_rank"], R["our_rank"], lambda v: f"#{int(v)}", True),
        cmp_row("Pos Rank", L["pos_rank"], R["pos_rank"],
                lambda v: f"{L['position'] if v==L['pos_rank'] else R['position']}{int(v)}", True)
        if L["position"] == R["position"] else
        {"label": "Pos Rank", "left": f"{L['position']}{L['pos_rank']}",
         "right": f"{R['position']}{R['pos_rank']}", "win": ""},
        cmp_row("Sleeper ADP", L["adp"], R["adp"], lambda v: f"{v:g}", True),
        cmp_row("Proj Pts", L["proj"], R["proj"], lambda v: f"{v:.0f}", False),
        cmp_row("VOR", L["vor"], R["vor"], lambda v: f"{v:.0f}", False),
    ]
    badge = f"{L['position']} DUEL" if L["position"] == R["position"] else f"{L['position']} vs {R['position']}"
    return comparison_poster(
        left=left, right=right, metrics=metrics, accent=accent, background=background,
        subtitle="Our board vs the consensus draft slot", badge=badge,
        footer=f"Generated {TODAY}",
    ), _timestamped_path(f"compare_{_norm(L['name']).replace(' ','')}_{_norm(R['name']).replace(' ','')}")


def build_movers(direction: str, top: int):
    if not os.path.exists(DIFF_CSV):
        raise SystemExit(
            f"{DIFF_CSV} not found. Run analysis/ranking_diff_report.py first "
            "(it writes the diff CSV the movers graphic is built from)."
        )
    diff = pd.read_csv(DIFF_CSV)
    if "vor_change" not in diff.columns:
        raise SystemExit("Diff CSV has no vor_change column -- re-run ranking_diff_report.py.")
    diff = diff[diff["vor_change"].abs() > 0.05]
    if direction == "risers":
        sel = diff.sort_values("vor_change", ascending=False).head(top)
        accent, title, arrow = RISER_ACCENT, 'Biggest <span class="accent">Risers</span>', "\u25b2"
    else:
        sel = diff.sort_values("vor_change", ascending=True).head(top)
        accent, title, arrow = FALLER_ACCENT, 'Biggest <span class="accent">Fallers</span>', "\u25bc"
    if sel.empty:
        raise SystemExit("No movers in the latest diff.")

    shots = load_headshots()
    rows = []
    for _, r in sel.iterrows():
        rank_change = int(r["rank_change"])
        rows.append({
            "rank": arrow,
            "name": r["player_name"],
            "team": r.get("team_abbr", ""),
            "photo": shots.get(_norm(r["player_name"]), ""),
            "sub": f"{r.get('position','')} \u00b7 #{int(r['our_rank_old'])} \u2192 #{int(r['our_rank_new'])} ({rank_change:+d})",
            "stat_num": f"{r['vor_change']:+.1f}",
            "stat_label": "VOR \u0394",
            "accent": accent,
        })
    return ranking_poster(
        title=title, rows=rows, accent=accent,
        kicker="2026 REDRAFT \u00b7 RANKING UPDATE",
        subtitle="What changed since the last run",
        footer=f"Updated {TODAY}",
    ), _timestamped_path(f"movers_{direction}")


def build_value(top: int):
    if not os.path.exists(GAPS_CSV):
        raise SystemExit(
            f"{GAPS_CSV} not found. Run analysis/market_gaps.py first "
            "(it writes the market-gaps CSV this graphic is built from)."
        )
    gaps = pd.read_csv(GAPS_CSV)
    if gaps.empty:
        raise SystemExit("No market gaps in the CSV -- loosen thresholds in market_gaps.py.")
    # Pull each value player's projected stat components from the rankings CSV
    # (the market-gaps CSV only carries the point total, not the stat line).
    ranks = pd.read_csv(RANKINGS_CSV).drop_duplicates("player_name").set_index("player_name")
    sel = gaps.head(top)
    rows = []
    for _, r in sel.iterrows():
        statline = ""
        if r["value_player"] in ranks.index:
            statline = format_stat_line(ranks.loc[r["value_player"]])
        rows.append({
            "value_name": r["value_player"],
            "value_team": r["value_team"],
            "value_sub": f"{r['position']} \u00b7 {r['value_team']} \u00b7 {r['value_proj']:.0f} proj pts",
            "statline": statline,
            "vs_text": f"{r['vs_player']} ({r['vs_team']}, {r['vs_proj']:.0f} pts)",
            "win_badge": f"+{r['win_gap']:.0f} WINS",
            "adp_badge": f"{r['adp_gap']:.0f} PICKS \u2193",
        })
    return value_targets_poster(rows=rows, footer=f"Generated {TODAY}"), _timestamped_path(f"value_targets_top{top}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type",
                        choices=["position", "overall", "favorites", "compare", "movers", "value",
                                 "hypothetical"],
                        default="position")
    parser.add_argument("--position", default="WR", help="Position for --type position")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--start", type=int, default=1,
                        help="First rank to show (e.g. --start 13 --top 12 => ranks 13-24)")
    parser.add_argument("--players", default="",
                        help='For --type compare: "Derrick Henry, Josh Jacobs"')
    parser.add_argument("--direction", choices=["risers", "fallers"], default="fallers",
                        help="For --type movers")
    parser.add_argument("--mover", default="", help='For --type hypothetical: player to move, e.g. "Josh Allen"')
    parser.add_argument("--to", type=int, default=17, help="For --type hypothetical: new rank the mover slides to")
    parser.add_argument("--from", dest="from_rank", type=int, default=0,
                        help="For --type hypothetical: pre-headline rank (default: current rank)")
    parser.add_argument("--theme", default="", help="Force a theme (else random each run). "
                        "One of: midnight_gold, royal_blue, emerald, crimson, violet, cyber_teal, sunset")
    parser.add_argument("--variant", default="", help="Force a layout variant: classic | spotlight")
    parser.add_argument("--seed", default=None, help="Reproducible theme/variant from any string")
    args = parser.parse_args()

    theme = resolve_theme(args.theme or None, args.seed)
    variant = resolve_variant(args.variant or None, args.seed)
    accent, background = theme["accent"], theme["background"]

    if args.type == "value":
        html, out_path = build_value(args.top)
    elif args.type == "movers":
        html, out_path = build_movers(args.direction, args.top)
    elif args.type == "compare":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_compare(df, args.players, accent, background)
    elif args.type == "hypothetical":
        if not args.mover:
            raise SystemExit('--type hypothetical needs --mover, e.g. --mover "Josh Allen" --to 17')
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_hypothetical_movers(df, args.mover, args.to, args.from_rank,
                                                   args.start if args.start > 1 else 13, args.top,
                                                   accent, background, variant)
    elif args.type == "favorites":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_favorites(df, args.top, accent, background, variant)
    elif args.type == "overall":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_overall(df, args.top, args.start, accent, background, variant)
    else:
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_position(df, args.position.upper(), args.top, args.start,
                                        accent, background, variant)

    final = html_to_png(html, out_path)
    print(f"Wrote {final}  [theme={theme['name']} variant={variant}]")


if __name__ == "__main__":
    main()
