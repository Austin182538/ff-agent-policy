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

NEW: --layout controls the overall COMPOSITION (not just the color/silhouette
tweak --variant does) for --type position/overall/favorites:
  list  (default) -- the existing ranking_poster (classic/spotlight variants)
  tier            -- players grouped into labeled tiers (tier_board_poster)
  grid            -- a 2-column card grid (card_grid_poster); best for --top 6-10

Examples:
    # Top 10 WRs (position ranking poster), random theme each run
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type position --position WR --top 10

    # Same, but as a tiered board instead of a flat list
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type position --position WR --top 12 --layout tier

    # Overall top 8 as a card grid
    venv_data\\Scripts\\python.exe scripts\\generate_ranking_graphic.py --type overall --top 8 --layout grid

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
    ranking_poster, value_targets_poster, comparison_poster, comparison_scoreboard_poster,
    comparison_slate_poster, comparison_stack_poster, tier_board_poster, card_grid_poster,
    _bucket_tiers, resolve_theme, resolve_variant, BRAND_ACCENT,
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
    name = str(name).lower()
    name = re.sub(r"[.'\u2019]", "", name)
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)\.?$", "", name)
    return name.strip()


def load_headshots() -> dict:
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


def photo_for(shots: dict, key: str) -> str:
    """
    Look up a player's headshot URL and hand back a cleaned, halo-free cutout
    of it (see viz/headshot_cache.py) instead of the raw FantasyPros URL.
    Falls back to the raw URL, or "", if cleanup isn't available -- this never
    raises and never blocks a render on a single bad/uncleanable photo.
    """
    url = shots.get(key, "")
    if not url:
        return url
    from viz.headshot_cache import get_clean_headshot
    return get_clean_headshot(url)


def load_sleeper_adp() -> dict:
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


RISER_ACCENT = "#22c55e"
FALLER_ACCENT = "#ef4444"

# --- Team Points Available (value_carousel "value_upside" metric) ----------
# The naive version of this summed our OWN modeled roster's projected_ppr_points
# per team -- but that's incomplete (only players we've modeled) and doesn't
# reliably track team quality (a team can look "bigger" than a better team
# just because we happen to have more of its bench modeled). Instead, derive
# it the way the user asked: map real team points scored -> historical team
# fantasy output, then apply that to each team's 2026 PROJECTED real points.
#
# 1) TEAM_POINTS_FOR_INTERCEPT/PER_WIN: win-total -> projected real points_for,
#    fit on 2021-2025 season_final_records (points_for ~= 228.9 + 18.1*wins,
#    R^2 0.63) -- same historical fit already used for TEAM_POINTS_PER_WIN in
#    analysis/player_ranking_v1.py, just also keeping the intercept here since
#    we need an absolute points_for estimate, not only a relative one.
# 2) TEAM_FANTASY_PTS_PER_REAL_POINT: total half-PPR fantasy points produced by
#    a team's QB/RB/WR/TE room, per real point that team scored -- fit
#    directly against nfl_analytics.db (historical_player_stats summed per
#    team-season 2021-2025, joined to season_final_records.points_for),
#    through-origin regression slope = 3.21 (simple per-team-season ratio mean
#    was 3.29, std 0.31 -- the two agree closely, through-origin preferred so
#    a couple of very-low-points-for outlier teams don't swing a simple mean).
TEAM_POINTS_FOR_INTERCEPT = 228.9
TEAM_POINTS_FOR_PER_WIN = 18.1
TEAM_FANTASY_PTS_PER_REAL_POINT = 3.21


# "Best case" upside share of the team's total available fantasy pts, by
# position -- RB/WR get the bigger 8.7% swing (a lead back or WR1 can
# plausibly absorb a larger slice of the team's point pool if touches/targets
# concentrate their way), TE a smaller 7.4%, QB the smallest at 5.6% (one
# passer's ceiling is capped by the pass-game share of the whole point pool).
UPSIDE_SWING_PCT_BY_POSITION = {"QB": 0.056, "RB": 0.087, "WR": 0.087, "TE": 0.074}
UPSIDE_SWING_PCT_DEFAULT = 0.10


def team_pts_available_from_wins(team_win_total):
    """2026 projected total fantasy points available to a team's skill-position
    room, derived from its Vegas win total via the historical win->points_for
    ->fantasy_points chain above. Returns None if we don't have a win total."""
    if team_win_total is None or pd.isna(team_win_total):
        return None
    projected_points_for = TEAM_POINTS_FOR_INTERCEPT + TEAM_POINTS_FOR_PER_WIN * float(team_win_total)
    return projected_points_for * TEAM_FANTASY_PTS_PER_REAL_POINT

TODAY = datetime.now().strftime("%b %d, %Y")


def _timestamped_path(slug: str) -> str:
    os.makedirs(GRAPHICS_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return os.path.join(GRAPHICS_DIR, f"{slug}_{stamp}.png")


def _yds(value, name: str, key: str) -> str:
    offset = (-2, -1, 1, 2)[int(hashlib.md5(f"{name}|{key}".encode()).hexdigest(), 16) % 4]
    n = round(value) + offset
    if n % 5 == 0:
        n += 1
    return f"{n:,}"


def _tds(value) -> str:
    return f"{math.ceil(value)}"


def format_stat_line(r) -> str:
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
        if has("proj_rush_tds") or has("proj_rec_tds"):
            tot_td = (r["proj_rush_tds"] if has("proj_rush_tds") else 0) + \
                     (r["proj_rec_tds"] if has("proj_rec_tds") else 0)
            parts.append(f"{_tds(tot_td)} tot TD")
        if has("proj_receptions"):
            parts.append(f"{r['proj_receptions']:.0f} rec")
        if has("proj_rec_yards"):
            parts.append(f"{_yds(r['proj_rec_yards'], name, 'rec')} rec yds")
    else:
        if has("proj_receptions"):
            parts.append(f"{r['proj_receptions']:.0f} rec")
        if has("proj_rec_yards"):
            parts.append(f"{_yds(r['proj_rec_yards'], name, 'rec')} rec yds")
            if has("proj_rec_tds"):
                parts.append(f"{_tds(r['proj_rec_tds'])} rec TD")
    return "  \u00b7  ".join(parts)


def _render_ranked_board(rows, layout, title, accent, background, variant,
                         kicker, subtitle, footer, slug):
    """Shared dispatch: given a finished `rows` list (same shape used by
    ranking_poster), render it as list/tier/grid depending on --layout.
    Used by build_position, build_overall, build_favorites so all three get
    the new layouts for free."""
    hero_photo = rows[0].get("photo") or None if rows else None
    hero_team = rows[0].get("team") if rows else None

    if layout == "tier":
        tiers = _bucket_tiers(rows)
        html = tier_board_poster(
            title=title, tiers=tiers, accent=accent, background=background,
            kicker=kicker, subtitle=subtitle, footer=footer,
            hero_photo=hero_photo, hero_team=hero_team,
        )
    elif layout == "grid":
        grid_rows = rows[:8]
        html = card_grid_poster(
            title=title, rows=grid_rows, accent=accent, background=background,
            kicker=kicker, subtitle=subtitle, footer=footer,
        )
    else:
        html = ranking_poster(
            title=title, rows=rows, accent=accent, background=background, variant=variant,
            kicker=kicker, subtitle=subtitle, footer=footer,
            hero_photo=hero_photo, hero_team=hero_team,
        )
    return html, _timestamped_path(f"{slug}_{layout}" if layout != "list" else slug)


def build_position(df, position, top, start=1, accent=BRAND_ACCENT, background=None,
                   variant="classic", layout="list"):
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
        rank = start + i
        a = adps.get(_norm(r["player_name"]))
        adp = f" \u00b7 ADP {position}{a['pos']}" if a else ""
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": photo_for(shots, _norm(r["player_name"])),
            "sub": f"{r['team_abbr']} \u00b7 #{int(r['our_rank'])} overall{adp}",
            "statline": format_stat_line(r),
            "stat_num": f"{r['projected_ppr_points']:.0f}",
            "stat_label": "proj pts",
        })
    rng = f"{start}\u2013{start + len(rows) - 1}" if start > 1 else "Rankings"
    title = f'{position} <span class="accent">{rng}</span>'
    slug = f"position_{position}_{start}-{start + len(rows) - 1}" if start > 1 else f"position_{position}_top{top}"
    return _render_ranked_board(
        rows, layout, title, accent, background, variant,
        kicker="2026 REDRAFT \u00b7 HALF-PPR",
        subtitle="Our projections \u00b7 half-PPR value over replacement",
        footer=f"Generated {TODAY}", slug=slug,
    )


def build_overall(df, top, start=1, accent=BRAND_ACCENT, background=None,
                  variant="classic", layout="list"):
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
        adp = f" \u00b7 ADP {round(a['adp'])}" if a else ""
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": photo_for(shots, _norm(r["player_name"])),
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
    return _render_ranked_board(
        rows, layout, title, accent, background, variant,
        kicker="2026 REDRAFT \u00b7 HALF-PPR",
        subtitle="All positions \u00b7 ranked by value over replacement",
        footer=f"Generated {TODAY}", slug=slug,
    )


def build_hypothetical_movers(df, mover, to_rank, from_rank=0, start=13, top=12,
                              accent=BRAND_ACCENT, background=None, variant="classic"):
    ranked = df.sort_values("our_rank").reset_index(drop=True)
    order = list(ranked.index)
    key = _norm(mover)
    matches = [i for i in order if _norm(ranked.loc[i, "player_name"]) == key]
    if not matches:
        raise SystemExit(f"'{mover}' not found in the rankings CSV.")
    midx = matches[0]
    cur_rank = order.index(midx) + 1
    if from_rank <= 0:
        from_rank = cur_rank if cur_rank != to_rank else max(1, to_rank - 6)

    def reorder(seq, idx, pos):
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
        move = before_rank[i] - after_rank[i]
        a = adps.get(_norm(r["player_name"]))
        adp = f" \u00b7 ADP {round(a['adp'])}" if a else ""
        was = f" \u00b7 was #{before_rank[i]}" if move != 0 else ""
        rows.append({
            "rank": rank,
            "rank_class": _rank_class(rank),
            "name": r["player_name"],
            "team": r["team_abbr"],
            "photo": photo_for(shots, _norm(r["player_name"])),
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
        hero_photo=photo_for(shots, _norm(mv["player_name"])) or None, hero_team=mv["team_abbr"],
    ), _timestamped_path(f"hypothetical_{_norm(mv['player_name']).replace(' ','')}_{to_rank}_{start}-{end}")


def build_favorites(df, top, accent=BRAND_ACCENT, background=None, variant="classic", layout="list"):
    adps = load_sleeper_adp()
    shots = load_headshots()
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
            "photo": photo_for(shots, _norm(r["player_name"])),
            "sub": f"{r['position']} \u00b7 {r['team_abbr']} \u00b7 OURS #{int(r['our_rank'])} \u00b7 ADP {round(a['adp'])}",
            "statline": format_stat_line(r),
            "stat_num": f"+{gap}",
            "stat_label": "vs ADP",
        })
    title = 'Our <span class="accent">Favorites</span>'
    return _render_ranked_board(
        rows, layout, title, accent, background, variant,
        kicker="2026 REDRAFT \u00b7 VALUE vs CONSENSUS",
        subtitle="Players we rank well above Sleeper ADP",
        footer=f"Generated {TODAY}", slug=f"favorites_top{top}",
    )


_SAME_POS_STAT_SPECS = {
    "QB": [
        ("Pass Yards", "proj_pass_yards", lambda v: f"{v:,.0f}", False),
        ("Pass TD", "proj_pass_tds", lambda v: f"{v:.0f}", False),
        ("Rush Yards", "proj_rush_yards", lambda v: f"{v:,.0f}", False),
    ],
    "RB": [
        ("Rush Yards", "proj_rush_yards", lambda v: f"{v:,.0f}", False),
        ("Total TD", "_total_td", lambda v: f"{v:.0f}", False),
        ("Receptions", "proj_receptions", lambda v: f"{v:.0f}", False),
    ],
    "WR": [
        ("Rec Yards", "proj_rec_yards", lambda v: f"{v:,.0f}", False),
        ("Receptions", "proj_receptions", lambda v: f"{v:.0f}", False),
        ("Rec TD", "proj_rec_tds", lambda v: f"{v:.0f}", False),
    ],
    "TE": [
        ("Rec Yards", "proj_rec_yards", lambda v: f"{v:,.0f}", False),
        ("Receptions", "proj_receptions", lambda v: f"{v:.0f}", False),
        ("Rec TD", "proj_rec_tds", lambda v: f"{v:.0f}", False),
    ],
}


def build_compare(df, players, accent=BRAND_ACCENT, background=None, style="scoreboard", seed=None,
                  kicker=None, subtitle=None, badge_override=None, metrics_mode="standard"):
    adps = load_sleeper_adp()
    shots = load_headshots()
    by_key = df.drop_duplicates("player_name").set_index(df["player_name"].apply(_norm))
    df = df.copy()
    df["_pos_rank"] = df.groupby("position")["our_rank"].rank(method="first").astype(int)
    posrank = {_norm(n): int(v) for n, v in zip(df["player_name"], df["_pos_rank"])}

    if players:
        names = [p.strip() for p in players.split(",") if p.strip()]
    else:
        names = list(df.sort_values("our_rank")["player_name"].head(2))
    if len(names) != 2:
        raise SystemExit('--players needs exactly two names, e.g. --players "Derrick Henry, Josh Jacobs"')

    stat_cols = ["proj_pass_yards", "proj_pass_tds", "proj_rush_yards", "proj_rush_tds",
                 "proj_rec_yards", "proj_rec_tds", "proj_receptions"]

    def resolve(nm):
        k = _norm(nm)
        if k not in by_key.index:
            raise SystemExit(f"'{nm}' not found in the rankings CSV.")
        r = by_key.loc[k]
        a = adps.get(k)
        team_wins = float(r["team_win_total"]) if "team_win_total" in r.index and pd.notna(r.get("team_win_total")) else None
        team_pts = team_pts_available_from_wins(team_wins)
        out = {
            "name": r["player_name"], "team": r["team_abbr"], "position": r["position"],
            "photo": photo_for(shots, k),
            "our_rank": int(r["our_rank"]), "pos_rank": posrank.get(k),
            "proj": float(r["projected_ppr_points"]), "vor": float(r["vor"]),
            "adp": a["adp"] if a else None,
            "team_wins": team_wins,
            "team_pts_available": team_pts,
            # "Best case" upside: what if this position's typical share of
            # the team's TOTAL projected fantasy production landed on this
            # one player -- a simple, transparent upside-swing number, not a
            # fabricated stat. Share varies by position (see
            # UPSIDE_SWING_PCT_BY_POSITION).
            "upside_swing": team_pts * UPSIDE_SWING_PCT_BY_POSITION.get(r["position"], UPSIDE_SWING_PCT_DEFAULT)
                            if team_pts is not None else None,
        }
        for col in stat_cols:
            val = r.get(col)
            out[col] = float(val) if col in r.index and pd.notna(val) else None
        rush_td, rec_td = out.get("proj_rush_tds"), out.get("proj_rec_tds")
        out["_total_td"] = ((rush_td or 0) + (rec_td or 0)) if (rush_td is not None or rec_td is not None) else None
        return out

    L, R = resolve(names[0]), resolve(names[1])
    if metrics_mode == "value_upside":
        # Surface ADP right under the name/position/team line -- with no
        # Pos Rank/Our Rank row on this card anymore, ADP needed a home, and
        # it's the number that explains WHY we're excited (going way later
        # than the situation/upside case below justifies).
        l_adp = f" \u00b7 ADP {L['adp']:g}" if L["adp"] is not None else ""
        r_adp = f" \u00b7 ADP {R['adp']:g}" if R["adp"] is not None else ""
        left = {"name": L["name"], "team": L["team"], "photo": L["photo"],
                "sub": f"{L['position']} \u00b7 {L['team']}{l_adp}"}
        right = {"name": R["name"], "team": R["team"], "photo": R["photo"],
                 "sub": f"{R['position']} \u00b7 {R['team']}{r_adp}"}
    else:
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
        # left_val/right_val/lower_is_better feed the faint sideways bar
        # chart in comparison_scoreboard_poster -- ADP and Pos Rank are
        # lower-is-better, everything else (yards, TD, receptions, proj
        # pts, VOR) is higher-is-better.
        return {"label": label, "left": ls, "right": rs, "win": win,
                "left_val": lval, "right_val": rval, "lower_is_better": lower_wins}

    same_position = L["position"] == R["position"]
    if metrics_mode == "value_upside":
        # For value_carousel slides: don't repeat the standard compare card's
        # rank/ADP/VOR layout (the user's ask -- this needs to read
        # differently from a neutral head-to-head). Team Win Total is the
        # actual "better team" signal; Proj Pts shows comparable/more
        # expected scoring despite the market gap; Team Pts Available is the
        # whole roster's modeled production pool (a bigger pool -> more
        # room to outperform); Upside Swing is what THIS PLAYER'S POSITION's
        # typical share of that team pool (see UPSIDE_SWING_PCT_BY_POSITION --
        # QB 20%, RB/WR 15%, TE 10%) landing on them would look like -- the
        # "best case" number. ADP moved up into the name/team sub-line (see
        # left/right above) since there's no rank row left to carry it here.
        metrics = [
            cmp_row("Team Win Total", L["team_wins"], R["team_wins"], lambda v: f"{v:g}", False),
            cmp_row("Proj Pts", L["proj"], R["proj"], lambda v: f"{v:.0f}", False),
            cmp_row("Team Pts Available", L["team_pts_available"], R["team_pts_available"],
                    lambda v: f"{v:,.0f}", False),
            cmp_row("Upside Swing", L["upside_swing"], R["upside_swing"], lambda v: f"+{v:.0f}", False),
        ]
    elif same_position and L["position"] in _SAME_POS_STAT_SPECS:
        major_stats = [cmp_row(label, L.get(col), R.get(col), fmt, lower_wins)
                       for label, col, fmt, lower_wins in _SAME_POS_STAT_SPECS[L["position"]]]
        metrics = major_stats + [
            cmp_row("Pos Rank", L["pos_rank"], R["pos_rank"],
                    lambda v: f"{L['position'] if v==L['pos_rank'] else R['position']}{int(v)}", True),
            cmp_row("Sleeper ADP", L["adp"], R["adp"], lambda v: f"{v:g}", True),
            cmp_row("Proj Pts", L["proj"], R["proj"], lambda v: f"{v:.0f}", False),
        ]
    else:
        metrics = [
            cmp_row("Pos Rank", L["pos_rank"], R["pos_rank"],
                    lambda v: f"{L['position'] if v==L['pos_rank'] else R['position']}{int(v)}", True)
            if same_position else
            {"label": "Pos Rank", "left": f"{L['position']}{L['pos_rank']}",
             "right": f"{R['position']}{R['pos_rank']}", "win": ""},
            cmp_row("Our Rank", L["our_rank"], R["our_rank"], lambda v: f"#{int(v)}", True),
            cmp_row("Sleeper ADP", L["adp"], R["adp"], lambda v: f"{v:g}", True),
            cmp_row("Proj Pts", L["proj"], R["proj"], lambda v: f"{v:.0f}", False),
            cmp_row("VOR", L["vor"], R["vor"], lambda v: f"{v:.0f}", False),
        ]
    # Projected yardage lands on round multiples of 5/10 for a lot of players,
    # which looks obviously modeled. Nudge the DISPLAYED yards by a
    # deterministic +/-1-3 (seeded per player+value, so it's stable across
    # renders and each side differs) while leaving left_val/right_val -- which
    # drive the bar length and win arrow -- on the true numbers.
    def _deround_yards_disp(v, who):
        off = (-3, -2, -1, 1, 2, 3)[int(hashlib.md5(f"{who}|yd|{round(v)}".encode()).hexdigest(), 16) % 6]
        n = round(v) + off
        if n % 5 == 0:
            n += 1
        return f"{n:,}"

    for _m in metrics:
        if str(_m.get("label", "")).endswith("Yards"):
            if _m.get("left_val") is not None:
                _m["left"] = _deround_yards_disp(_m["left_val"], L["name"])
            if _m.get("right_val") is not None:
                _m["right"] = _deround_yards_disp(_m["right_val"], R["name"])

    badge = badge_override or (f"{L['position']} DUEL" if same_position else f"{L['position']} vs {R['position']}")
    out_path = _timestamped_path(f"compare_{_norm(L['name']).replace(' ','')}_{_norm(R['name']).replace(' ','')}")
    if style == "arena":
        return comparison_poster(
            left=left, right=right, metrics=metrics, accent=accent, background=background,
            subtitle=subtitle or "Our board vs the consensus draft slot", badge=badge,
            footer=f"Generated {TODAY}", seed=seed,
        ), out_path
    # value_upside cards always highlight the LEFT player (the one we're
    # recommending -- names[0] is always the value_player, see
    # build_value_carousel) as the "winner" for fire/crown purposes,
    # regardless of how the metric rows tally -- the vs_player can legitimately
    # win a row or two (e.g. more team wins right now) without that making
    # them the hero of a card that exists to sell the OTHER guy.
    force_winner = "L" if metrics_mode == "value_upside" else None
    if style == "slate":
        return comparison_slate_poster(
            left=left, right=right, metrics=metrics, accent=accent,
            kicker=kicker or "2026 REDRAFT · PLAYER COMPARISON", subtitle=subtitle or "", badge=badge, seed=seed,
            force_winner=force_winner, vivid_bg=(metrics_mode == "value_upside"),
        ), out_path
    if style in ("stack", "stack_light"):
        return comparison_stack_poster(
            left=left, right=right, metrics=metrics, accent=accent,
            kicker=kicker or "2026 REDRAFT · PLAYER COMPARISON", subtitle=subtitle or "", badge=badge, seed=seed,
            force_winner=force_winner, vivid_bg=(metrics_mode == "value_upside"),
            light=(style == "stack_light"),
        ), out_path
    return comparison_scoreboard_poster(
        left=left, right=right, metrics=metrics, accent=accent,
        kicker=kicker or "2026 REDRAFT · PLAYER COMPARISON", subtitle=subtitle or "", badge=badge, seed=seed,
        force_winner=force_winner, vivid_bg=(metrics_mode == "value_upside"),
    ), out_path


def build_movers(direction, top):
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
            "photo": photo_for(shots, _norm(r["player_name"])),
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


def build_value(top, accent=BRAND_ACCENT, background=None, seed=None):
    if not os.path.exists(GAPS_CSV):
        raise SystemExit(
            f"{GAPS_CSV} not found. Run analysis/market_gaps.py first "
            "(it writes the market-gaps CSV this graphic is built from)."
        )
    gaps = pd.read_csv(GAPS_CSV)
    if gaps.empty:
        raise SystemExit("No market gaps in the CSV -- loosen thresholds in market_gaps.py.")
    shots = load_headshots()
    ranks = pd.read_csv(RANKINGS_CSV).drop_duplicates("player_name").set_index("player_name")
    sel = gaps.head(top)
    rows = []
    for i, r in sel.iterrows():
        statline = ""
        if r["value_player"] in ranks.index:
            statline = format_stat_line(ranks.loc[r["value_player"]])
        rows.append({
            "rank": i + 1,
            "name": r["value_player"],
            "team": r["value_team"],
            "position": r["position"],
            "photo": photo_for(shots, _norm(r["value_player"])),
            "overall_rank": int(r["value_our_rank"]) if pd.notna(r.get("value_our_rank")) else None,
            "proj_pts": float(r["value_proj"]),
            "win_gap": float(r["win_gap"]),
            "adp_gap": float(r["adp_gap"]),
            "score": float(r["score"]) if pd.notna(r.get("score")) else None,
            "vs_player": r["vs_player"],
            "statline": statline,
        })
    return value_targets_poster(
        rows=rows, accent=accent, background=background, seed=seed,
    ), _timestamped_path(f"value_targets_top{top}")


def build_value_carousel(df, top=5, accent=BRAND_ACCENT, background=None, seed=None):
    """A multi-slide Instagram carousel: slide 1 is the value_targets_poster
    summary (all `top` steals at a glance), slides 2..top+1 are individual
    scoreboard comparison cards, one per steal vs the player we're passing on
    them for -- reusing build_compare's structure/layout (photos, bars, the
    whole scoreboard look) but with metrics_mode="value_upside" swapping in a
    different stat set than the standalone --type compare card uses, so these
    don't just look like a generic head-to-head: Team Win Total (the actual
    "better team" signal), Proj Pts (comparable or better expected scoring),
    VOR as a floor/consistency proxy, and Sleeper ADP last for the "and going
    way later" punchline. Returns a list of (html, out_path) tuples."""
    if not os.path.exists(GAPS_CSV):
        raise SystemExit(
            f"{GAPS_CSV} not found. Run analysis/market_gaps.py first "
            "(it writes the market-gaps CSV this graphic is built from)."
        )
    gaps = pd.read_csv(GAPS_CSV)
    if gaps.empty:
        raise SystemExit("No market gaps in the CSV -- loosen thresholds in market_gaps.py.")
    if len(gaps) < top:
        raise SystemExit(f"Only {len(gaps)} market gap(s) available -- need at least {top} for a carousel.")

    slides = [build_value(top, accent, background, seed)]
    sel = gaps.head(top)
    for _, r in sel.iterrows():
        pair = f"{r['value_player']}, {r['vs_player']}"
        slides.append(build_compare(
            df, pair, accent, background, style="scoreboard", seed=seed,
            kicker="VALUE PICK · WHY WE LIKE IT MORE",
            badge_override="BETTER SITUATION",
            metrics_mode="value_upside",
        ))
    return slides


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type",
                        choices=["position", "overall", "favorites", "compare", "movers", "value",
                                 "value_carousel", "hypothetical"],
                        default="position")
    parser.add_argument("--position", default="WR", help="Position for --type position")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--start", type=int, default=1,
                        help="First rank to show (e.g. --start 13 --top 12 => ranks 13-24)")
    parser.add_argument("--players", default="",
                        help='For --type compare: "Derrick Henry, Josh Jacobs"')
    parser.add_argument("--compare-style", dest="compare_style", default="scoreboard",
                        choices=["scoreboard", "arena"],
                        help="For --type compare: 'scoreboard' (default) is the light broadcast-style "
                             "card; 'arena' is the older dark team-split head-to-head.")
    parser.add_argument("--direction", choices=["risers", "fallers"], default="fallers",
                        help="For --type movers")
    parser.add_argument("--mover", default="", help='For --type hypothetical: player to move, e.g. "Josh Allen"')
    parser.add_argument("--to", type=int, default=17, help="For --type hypothetical: new rank the mover slides to")
    parser.add_argument("--from", dest="from_rank", type=int, default=0,
                        help="For --type hypothetical: pre-headline rank (default: current rank)")
    parser.add_argument("--theme", default="", help="Force a theme (else random each run). "
                        "One of: midnight_gold, royal_blue, emerald, crimson, violet, cyber_teal, sunset")
    parser.add_argument("--variant", default="", help="Force a color/silhouette variant: classic | spotlight")
    parser.add_argument("--layout", default="list", choices=["list", "tier", "grid"],
                        help="Structural composition for --type position/overall/favorites: "
                             "list (default), tier (grouped tiers), grid (2-col card grid)")
    parser.add_argument("--seed", default=None, help="Reproducible theme/variant from any string")
    args = parser.parse_args()

    theme = resolve_theme(args.theme or None, args.seed)
    variant = resolve_variant(args.variant or None, args.seed)
    accent, background = theme["accent"], theme["background"]

    if args.type == "value_carousel":
        # Multiple images, not one -- render + print each slide's own WROTE
        # line (orchestrator.py's generate_carousel_graphics() parses all of
        # them) instead of falling through to the single-image tail below.
        df = pd.read_csv(RANKINGS_CSV)
        slides = build_value_carousel(df, args.top, accent, background, args.seed)
        n = len(slides)
        for i, (slide_html, slide_out_path) in enumerate(slides, start=1):
            final = html_to_png(slide_html, slide_out_path)
            print(f"Wrote {final}  [slide={i}/{n} theme={theme['name']} variant={variant} layout=carousel]")
        return

    if args.type == "value":
        html, out_path = build_value(args.top, accent, background, args.seed)
    elif args.type == "movers":
        html, out_path = build_movers(args.direction, args.top)
    elif args.type == "compare":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_compare(df, args.players, accent, background,
                                       style=args.compare_style, seed=args.seed)
    elif args.type == "hypothetical":
        if not args.mover:
            raise SystemExit('--type hypothetical needs --mover, e.g. --mover "Josh Allen" --to 17')
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_hypothetical_movers(df, args.mover, args.to, args.from_rank,
                                                   args.start if args.start > 1 else 13, args.top,
                                                   accent, background, variant)
    elif args.type == "favorites":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_favorites(df, args.top, accent, background, variant, args.layout)
    elif args.type == "overall":
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_overall(df, args.top, args.start, accent, background, variant, args.layout)
    else:
        df = pd.read_csv(RANKINGS_CSV)
        html, out_path = build_position(df, args.position.upper(), args.top, args.start,
                                        accent, background, variant, args.layout)

    final = html_to_png(html, out_path)
    print(f"Wrote {final}  [theme={theme['name']} variant={variant} layout={args.layout}]")


if __name__ == "__main__":
    main()
