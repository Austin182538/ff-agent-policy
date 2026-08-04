"""HTML/CSS builders for the ranking graphics.

Everything here returns a full HTML document string sized to an exact canvas
(default 1080x1350, a 4:5 portrait that fits Instagram/X). viz/render.py turns
that into a PNG. Keeping the graphics as HTML/CSS (not a generative image
model) is deliberate: player names, ranks and stats render pixel-perfect every
time, which diffusion image models cannot do.

Fonts are Windows built-ins (Bahnschrift is a condensed, sporty DIN-style face
that ships with Windows 10/11) so there's no web-font network dependency.
"""

import base64 as _base64
import hashlib as _hashlib
import html as _html
import os as _os
import random as _random
import urllib.parse as _urlparse
from typing import List, Dict, Optional

from viz.teams import team_color, team_secondary, team_logo_url

CANVAS_W = 1080
CANVAS_H = 1350

# Tier board layout sizing (pixels)
HEADER_HEIGHT = 250
FOOTER_HEIGHT = 40
BOARD_MARGIN = 30

BOARD_MAX_HEIGHT = CANVAS_H - HEADER_HEIGHT - FOOTER_HEIGHT - BOARD_MARGIN

ROW_HEIGHT = 82
ROW_GAP = 6
TIER_HEADER_HEIGHT = 34
TIER_BLOCK_GAP = 10

# --- Shared "premium" finishing effects (grain + vignette) ------------------
# Two pointer-inert, full-canvas overlays every poster drops in for depth:
#   * a faint film grain (SVG fractal noise) kills the flat digital look;
#   * a soft vignette darkens the corners to funnel the eye to the content.
# Light is treated as coming from the top-left everywhere else (inset highlights
# on top edges, drop shadows cast down + slightly right) so the piece feels lit
# from one direction. _OVERLAYS is the markup; _FX_CSS the styles; both are
# injected verbatim into each template so the HTML stays standalone.
_GRAIN_SVG = (
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence "
    "type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E"
    "%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")"
)
_FX_CSS = (
    # a soft diagonal sheen sitting just BEHIND the content (z-index 1) -- a
    # translucent light/shadow streak rather than a repeating line weave,
    # which read as busy/messy moire at real render resolution
    # a soft, non-directional floor vignette behind the content -- no diagonal
    # streak (those read as a stray light bar across the page)
    ".texture{position:absolute;inset:0;pointer-events:none;z-index:1;opacity:0.9;"
    "background:radial-gradient(135% 95% at 50% 118%, rgba(0,0,0,0.30), transparent 58%);}"
    ".grain{position:absolute;inset:0;pointer-events:none;z-index:60;"
    f"background-image:{_GRAIN_SVG};background-size:300px 300px;"
    "opacity:0.05;mix-blend-mode:overlay;}"
    ".vignette{position:absolute;inset:0;pointer-events:none;z-index:55;"
    "background:radial-gradient(130% 95% at 50% 34%, transparent 55%, rgba(0,0,0,0.42) 100%);"
    "box-shadow:inset 0 0 160px 40px rgba(0,0,0,0.38);}"
)
_OVERLAYS = '<div class="texture"></div><div class="vignette"></div><div class="grain"></div>'

# --- Brand watermark (the Blitz Culture logo) --------------------------------
# Embedded as a base64 data URI (read once, cached) so every rendered HTML
# stays a single standalone file -- no separate image file for the headless
# browser to fetch, consistent with the no-web-font-dependency approach above.
_LOGO_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "assets", "blitz_culture_logo.png")
_logo_data_uri_cache: Optional[str] = None


def _logo_data_uri() -> str:
    global _logo_data_uri_cache
    if _logo_data_uri_cache is None:
        if _os.path.exists(_LOGO_PATH):
            with open(_LOGO_PATH, "rb") as f:
                encoded = _base64.b64encode(f.read()).decode("ascii")
            _logo_data_uri_cache = f"data:image/png;base64,{encoded}"
        else:
            _logo_data_uri_cache = ""
    return _logo_data_uri_cache


_WATERMARK_CSS = (
    ".bcwatermark{position:absolute;z-index:40;top:26px;right:26px;width:104px;height:104px;"
    "border-radius:22px;overflow:hidden;border:3px solid rgba(255,255,255,0.6);"
    "box-shadow:0 10px 22px -6px rgba(0,0,0,0.55);}"
    ".bcwatermark img{width:100%;height:100%;object-fit:cover;display:block;}"
)


def _watermark_html() -> str:
    """Small branded badge (top-right, rounded square) dropped onto every
    poster -- returns "" if the logo asset is missing so a fresh clone
    without viz/assets/blitz_culture_logo.png doesn't hard-fail renders."""
    uri = _logo_data_uri()
    if not uri:
        return ""
    return f'<div class="bcwatermark"><img src="{uri}" alt=""></div>'

# Brand theme: warm gold-amber accent on a near-black background (matches the
# app's lightning-bolt mark). {accent} is filled per-graphic (defaults to
# BRAND_ACCENT) and gets an 8-digit-hex alpha suffix for the soft background
# glows.
BRAND_ACCENT = "#f5a623"
_BG = (
    "radial-gradient(1200px 600px at 85% -10%, {accent}33, transparent 60%),"
    "radial-gradient(900px 500px at -12% 112%, {accent}18, transparent 55%),"
    "linear-gradient(160deg, #1a1c24 0%, #24262f 48%, #16171e 100%)"
)

# A palette of vibrant, distinct "skins". Each has an accent + a full-canvas
# background so no two re-renders of the set feel identical. resolve_theme()
# picks one (deterministically from a seed, or at random). The backgrounds
# deliberately vary their glow placement/angle and a couple add a faint diagonal
# band or second glow so it's layout variety, not just a hue swap.
THEMES: Dict[str, Dict[str, str]] = {
    "midnight_gold": {"accent": "#f5a623", "bg": _BG},
    "royal_blue": {"accent": "#5b8cff", "bg": (
        "radial-gradient(1100px 620px at 15% -12%, {accent}3a, transparent 60%),"
        "radial-gradient(760px 460px at 108% 108%, {accent}1a, transparent 55%),"
        "linear-gradient(155deg, #141b30 0%, #1e2b4a 55%, #10182c 100%)")},
    "emerald": {"accent": "#2dd4a7", "bg": (
        "radial-gradient(1000px 560px at 92% -6%, {accent}36, transparent 58%),"
        "linear-gradient(160deg, #112019 0%, #1a2d23 50%, #0e1913 100%)")},
    "crimson": {"accent": "#ff5470", "bg": (
        "radial-gradient(1100px 600px at 82% -10%, {accent}32, transparent 60%),"
        "radial-gradient(820px 520px at -10% 110%, {accent}1a, transparent 55%),"
        "linear-gradient(160deg, #201319 0%, #2b1a24 50%, #170e13 100%)")},
    "violet": {"accent": "#b17bff", "bg": (
        "radial-gradient(1000px 600px at 8% -8%, {accent}3a, transparent 60%),"
        "radial-gradient(820px 520px at 104% 112%, {accent}1e, transparent 55%),"
        "linear-gradient(160deg, #181324 0%, #221934 52%, #130d1c 100%)")},
    "cyber_teal": {"accent": "#22d3ee", "bg": (
        "linear-gradient(122deg, transparent 0 45%, {accent}16 45% 55%, transparent 55%),"
        "radial-gradient(1000px 560px at 88% -6%, {accent}30, transparent 58%),"
        "linear-gradient(160deg, #101d2b 0%, #17283b 55%, #0d1826 100%)")},
    "sunset": {"accent": "#ff8a3d", "bg": (
        "radial-gradient(1150px 660px at 50% -22%, {accent}38, transparent 62%),"
        "linear-gradient(160deg, #21150d 0%, #2c1b11 48%, #170d08 100%)")},
}

# Row/layout variants: two safe, CSS-only looks that change the silhouette of
# the whole poster (circular vs squared photos/chips, gradient direction, border
# treatment). Combined with the 7 themes this yields plenty of non-repeating
# recreations.
LAYOUT_VARIANTS = ("classic", "spotlight")


def resolve_theme(name: Optional[str] = None, seed: Optional[str] = None) -> Dict[str, str]:
    """Return a theme dict {name, accent, background}. Force one with `name`,
    reproduce one from any `seed` string (stable hash), else pick at random so
    each run varies."""
    keys = list(THEMES)
    if name and name in THEMES:
        key = name
    elif seed is not None:
        key = keys[int(_hashlib.md5(str(seed).encode()).hexdigest(), 16) % len(keys)]
    else:
        key = _random.choice(keys)
    t = THEMES[key]
    return {"name": key, "accent": t["accent"], "background": t["bg"].format(accent=t["accent"])}


def resolve_variant(name: Optional[str] = None, seed: Optional[str] = None) -> str:
    """Pick a layout variant (see LAYOUT_VARIANTS), same rules as resolve_theme."""
    if name in LAYOUT_VARIANTS:
        return name
    if seed is not None:
        return LAYOUT_VARIANTS[int(_hashlib.md5(("v" + str(seed)).encode()).hexdigest(), 16) % len(LAYOUT_VARIANTS)]
    return _random.choice(LAYOUT_VARIANTS)


def _esc(text: str) -> str:
    return _html.escape(str(text))


def _lighten(hex_color: str, t: float = 0.55) -> str:
    """Mix a color toward white by fraction t (0..1). Dark team colors (Ravens
    navy, Bears navy, Raiders black...) are illegible as text on the dark
    canvas, so winner values/labels use a lightened tint for readability while
    the true saturated color is kept for the glow behind them."""
    h = (hex_color or "#94a3b8").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 148, 163, 184
    r = int(r + (255 - r) * t)
    g = int(g + (255 - g) * t)
    b = int(b + (255 - b) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _chroma(hex_color: str) -> float:
    """0..1 'vibrance' proxy = (max-min)/255 of the RGB channels. Used to pick
    the punchier of a team's two colors for the main row wash (e.g. 49ers red
    over gold, Packers gold over dark green)."""
    h = (hex_color or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0.0
    return (max(r, g, b) - min(r, g, b)) / 255.0


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB -> rgba(r,g,b,a). Used to tint each row with its team color
    without needing CSS color-mix (keeps rendering identical on Edge/Chrome)."""
    h = (hex_color or "#334155").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 51, 65, 85
    return f"rgba({r},{g},{b},{alpha})"


# Top-3 get a metallic medal badge; everyone else a subtle dark chip.
_MEDAL_CLASS = {1: "m1", 2: "m2", 3: "m3"}


def _avatar_html(photo: str, logo: str) -> str:
    """Circular player headshot with the team logo as an overlapping badge.
    Falls back to just the team logo (centered, larger) when no photo exists."""
    if photo:
        logo_badge = f'<img class="logo" src="{logo}" alt="">' if logo else ""
        return (f'<div class="avatar"><img class="shot" src="{photo}" alt="">'
                f'{logo_badge}</div>')
    if logo:
        return f'<div class="avatar nophoto"><img class="logo" src="{logo}" alt=""></div>'
    return '<div class="avatar nophoto"></div>'


def _row_html(row: Dict) -> str:
    """row keys: rank, rank_class, name, team, sub, statline, stat_num,
    stat_label, photo(optional), accent(optional)."""
    team = row.get("team", "")
    # Two-tone team identity: the MORE VIBRANT of the team's two colors washes
    # the main panel (49ers -> red, Packers -> gold), and the other color is the
    # thin edge stripe. A row can override with its own accent (risers/fallers
    # green/red), which then drives both.
    override = row.get("accent")
    primary, secondary = team_color(team), team_secondary(team)
    vibrant, other = (secondary, primary) if _chroma(secondary) > _chroma(primary) else (primary, secondary)
    accent = override or vibrant      # avatar ring / statline / spotlight glow / stat
    edge = override or other          # thin border-left stripe (the second color)
    accent_l = _lighten(accent)       # legible team-colored stat numbers (spotlight)
    wash_hex = override or vibrant
    team_tint = _hex_to_rgba(wash_hex, 0.82)
    team_fade = _hex_to_rgba(wash_hex, 0.15)
    logo = team_logo_url(team) if team else ""
    stat_num = row.get("stat_num", "")
    stat_label = row.get("stat_label", "")
    stat_html = ""
    if stat_num != "":
        stat_html = (
            f'<div class="stat"><div class="stat-num">{_esc(stat_num)}</div>'
            f'<div class="stat-label">{_esc(stat_label)}</div></div>'
        )
    statline = row.get("statline", "")
    statline_html = f'<div class="statline">{_esc(statline)}</div>' if statline else ""
    rank_class = row.get("rank_class", "plain")
    # Optional movement chip (hypothetical/movers boards): row["move"] = spots
    # moved up (+) / down (-) / 0 for unchanged.
    move = row.get("move")
    delta_html = ""
    if move is not None:
        if move > 0:
            delta_html = f'<div class="delta up">\u25b2{int(move)}</div>'
        elif move < 0:
            delta_html = f'<div class="delta down">\u25bc{abs(int(move))}</div>'
        else:
            delta_html = '<div class="delta flat">\u2013</div>'
    return f"""
      <div class="row" style="--accent:{accent};--accent-l:{accent_l};--edge:{edge};--team:{team_tint};--team-fade:{team_fade}">
        <div class="rank {rank_class}">{_esc(row.get('rank', ''))}</div>
        {delta_html}
        {_avatar_html(row.get('photo', ''), logo)}
        <div class="meta">
          <div class="name">{_esc(row.get('name', ''))}</div>
          <div class="sub">{_esc(row.get('sub', ''))}</div>
          {statline_html}
        </div>
        {stat_html}
      </div>"""


# Dark-canvas counterpart to BG_PATTERNS (see further down) -- same texture
# shapes, but tinted white instead of navy so they read on value_targets_poster's
# near-black background instead of disappearing into it. Keyed identically so
# resolve_bg_pattern()'s picked name works against either dict.
BG_PATTERNS_DARK: Dict[str, str] = {
    "orbit": ("radial-gradient(150px 150px at 25% 30%, rgba(255,255,255,0.28), transparent 70%) 0 0/220px 220px,"
              "radial-gradient(100px 100px at 74% 68%, rgba(255,255,255,0.20), transparent 70%) 0 0/220px 220px"),
    "halo": ("radial-gradient(circle at 30% 35%, transparent 34%, rgba(255,255,255,0.26) 40%, transparent 50%) 0 0/210px 210px,"
             "radial-gradient(circle at 74% 72%, transparent 24%, rgba(255,255,255,0.19) 30%, transparent 40%) 0 0/210px 210px"),
    "spark": ("radial-gradient(8px 8px at center, rgba(255,255,255,0.34) 62%, transparent 100%) 0 0/30px 30px,"
              "radial-gradient(5px 5px at 50% 50%, rgba(255,255,255,0.26) 62%, transparent 100%) 15px 15px/30px 30px"),
    "drift": ("linear-gradient(120deg, transparent 22%, rgba(255,255,255,0.24) 40%, rgba(255,255,255,0.24) 48%, transparent 66%) 0 0/220px 220px,"
              "linear-gradient(120deg, transparent 4%, rgba(255,255,255,0.16) 16%, rgba(255,255,255,0.16) 22%, transparent 34%) 60px 60px/220px 220px"),
    "mesh": ("radial-gradient(46px 46px at 0% 0%, rgba(255,255,255,0.24), transparent 70%) 0 0/120px 120px,"
             "radial-gradient(46px 46px at 100% 50%, rgba(255,255,255,0.24), transparent 70%) 0 0/120px 120px,"
             "radial-gradient(46px 46px at 0% 100%, rgba(255,255,255,0.24), transparent 70%) 0 0/120px 120px"),
}


def _steal_row_html(row: Dict, gauge_pct: float, featured: bool = False, name_fs: int = 38) -> str:
    """One "value target" card: a big team-framed headshot (with a fire aura
    behind the top steal, echoing the versus card's winner treatment), a
    large name that fills the row, a steal-strength gauge bar (sized off the
    market_gaps composite score so it actually tracks the card's rank order),
    the vs-player callout + this player's own projected stat line underneath
    it, and proj-pts/win/ADP numbers on the right.

    row keys: name, team, position, photo, overall_rank, proj_pts, win_gap,
    adp_gap, vs_player, statline, rank (1-based position in this steal list)."""
    team = row.get("team", "")
    vivid, other = _vivid_pair(team, BRAND_ACCENT)
    logo = team_logo_url(team) if team else ""
    photo = row.get("photo", "")
    if photo:
        img_html = f'<img class="vphoto" src="{photo}" alt="">'
    elif logo:
        img_html = f'<div class="vphoto nophoto"><img class="vbiglogo" src="{logo}" alt=""></div>'
    else:
        img_html = '<div class="vphoto nophoto"></div>'
    badge_plate = f'<div class="vbadgeplate"><img class="vbadge" src="{logo}" alt=""></div>' if (logo and photo) else ""
    fire_html = (f'<svg class="vfire" viewBox="0 0 24 24" fill="{vivid}">{_FIRE_PATH}</svg>'
                 if featured else "")

    overall_rank = row.get("overall_rank")
    meta_bits = [b for b in [row.get("position", ""), team,
                             f"#{int(overall_rank)} overall" if overall_rank else ""] if b]
    meta_line = " \u00b7 ".join(meta_bits)
    proj_pts = row.get("proj_pts")
    proj_html = (f'<div class="vproj"><div class="vproj-num">{proj_pts:.0f}</div>'
                 f'<div class="vproj-label">Proj Pts</div></div>') if proj_pts is not None else ""
    win_gap = row.get("win_gap")
    adp_gap = row.get("adp_gap")
    win_pill = f'<div class="vpill wins">+{win_gap:.0f} WINS</div>' if win_gap is not None else ""
    adp_pill = f'<div class="vpill adp">{adp_gap:.0f} PICKS LATER</div>' if adp_gap is not None else ""

    rank_chip = f'<div class="vrank-chip">#{row.get("rank", "")} STEAL</div>'
    featured_cls = " featured" if featured else ""
    vs_player = row.get("vs_player", "")
    gauge_label = f"Steal Score vs {_esc(vs_player)}" if vs_player else "Steal Score"
    statline = row.get("statline", "")
    statline_html = f'<div class="vstatline">{_esc(statline)}</div>' if statline else ""

    # Auto-fit the name to ONE line: with no browser to measure glyphs, shrink
    # the font for longer names off character count so "Amon-Ra St. Brown" or
    # "Christian McCaffrey" fit cleanly instead of clipping to an ellipsis. The
    # name owns the full info column (~470px), condensed bold ~0.52*fs per char.
    name = str(row.get("name", ""))
    fit_fs = min(name_fs, int(400 / (max(len(name), 1) * 0.56)))
    fit_fs = max(fit_fs, 22)

    return f"""
      <div class="vcard{featured_cls}" style="--pc:{vivid};--pc2:{other};--pcg:{_hex_to_rgba(vivid, 0.55)}">
        <div class="vphotowrap">{fire_html}<div class="vbackdrop"></div>{img_html}{badge_plate}</div>
        <div class="vdivider"></div>
        <div class="vinfo">
          <div class="vname" style="font-size:{fit_fs}px">{_esc(name)}</div>
          <div class="vmeta-row">{rank_chip}<span class="vmeta-line">{_esc(meta_line)}</span></div>
          <div class="vgauge-wrap">
            <div class="vgauge-label">{gauge_label}</div>
            <div class="vgauge-track"><div class="vgauge-fill" style="width:{gauge_pct}%"><span class="vgauge-cap"></span></div></div>
          </div>
          {statline_html}
        </div>
        <div class="vdivider"></div>
        <div class="vstats">
          {proj_html}
          <div class="vpill-col">{win_pill}{adp_pill}</div>
        </div>
      </div>"""


def value_targets_poster(
    rows: List[Dict],
    title: str = 'Market <span class="accent">Value Targets</span>',
    kicker: str = "2026 REDRAFT \u00b7 MARKET GAPS",
    subtitle: str = "Similar Projection \u00b7 Cheaper ADP \u00b7 Better Team",
    accent: str = BRAND_ACCENT,
    badge: str = "2026",
    background: Optional[str] = None,
    pattern: Optional[str] = None,
    seed: Optional[str] = None,
) -> str:
    """row keys (see _steal_row_html): name, team, position, photo,
    overall_rank, proj_pts, win_gap, adp_gap, vs_player, statline, score.
    `background` overrides the theme's color wash entirely (pass a
    resolve_theme() background for THEME variety); `pattern`/`seed` pick the
    TEXTURE layered underneath it (see BG_PATTERNS_DARK) the same way
    comparison_scoreboard_poster does, so repeated value posts don't all
    look identical. The gauge bar is sized off each row's `score` (the same
    composite value the rows are already ranked/sorted by), not the raw ADP
    gap, so the bar length actually tracks the #1/#2/#3... order instead of
    occasionally showing a bigger bar on a lower-ranked card."""
    n = max(len(rows), 1)
    photo_sz = 172 if n <= 4 else (150 if n <= 5 else 130)
    # A fixed width-estimate heuristic for a single-line, ellipsis-truncated
    # name kept clipping real names (no browser here to measure actual glyph
    # widths against the stats column's real size) -- so instead of guessing
    # a font size that's supposed to always fit one line, the name now WRAPS
    # onto up to 2 lines (see .vname's -webkit-line-clamp below) at one
    # consistent, generous size. That fits "David Montgomery"-length names
    # without shrinking or clipping anything.
    name_fs = 44 if n <= 4 else (38 if n <= 5 else 32)

    scores = [r.get("score") if r.get("score") is not None else (r.get("adp_gap") or 0) for r in rows]
    max_score = max(scores) if scores else 1
    max_score = max_score or 1

    rows_html = "\n".join(
        _steal_row_html(
            r,
            round(min(100.0, 100.0 * ((r.get("score") if r.get("score") is not None else (r.get("adp_gap") or 0)) / max_score)), 1),
            featured=(i == 0),
            name_fs=name_fs,
        )
        for i, r in enumerate(rows)
    )
    # top steal's team colour feeds the mesh blobs when that texture comes up
    _top_team = rows[0].get("team", "") if rows else ""
    _tc1, _tc2 = _vivid_pair(_top_team, accent)
    bg_pattern_css = _resolve_skin_css(seed, "value", dark=True, c1=_tc1, c2=_tc2)
    bg = background or _BG.format(accent=accent)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{
    font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc;
    background:{bg};
    padding:48px 52px 18px 52px; display:flex; flex-direction:column;
    position:relative;
  }}
  .pattern {{ position:absolute; inset:0; pointer-events:none; z-index:1; {bg_pattern_css} }}
  {_FX_CSS}
  {_WATERMARK_CSS}
  .topbar, .list {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:600;
             letter-spacing:4px; font-size:22px; color:{accent}; text-transform:uppercase; }}
  .badge-yr {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px;
               color:#0a0f1f; background:{accent}; border-radius:10px; padding:6px 14px;
               letter-spacing:2px; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
            font-weight:700; font-size:82px; line-height:0.92; text-transform:uppercase;
            letter-spacing:1px; margin-top:10px;
            -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
            text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26),
              0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:21px; margin-top:8px; text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .rule {{ height:2px; width:120px; margin-top:16px;
    background:linear-gradient(90deg, {accent}, transparent); border-radius:2px; }}
  .list {{ margin-top:30px; display:flex; flex-direction:column; gap:18px;
           flex:1; justify-content:center; padding-bottom:26px; }}
  .vcard {{ position:relative; display:flex; align-items:center; gap:22px;
    background:linear-gradient(120deg, var(--pcg), rgba(255,255,255,0.055) 55%, rgba(255,255,255,0.02));
    border:1px solid rgba(255,255,255,0.1); border-radius:24px;
    padding:16px 30px 16px 24px; flex:1 1 0; min-height:0; max-height:250px; overflow:hidden;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.12), inset 3px 0 0 var(--pc),
      0 18px 34px -18px rgba(0,0,0,0.9), 0 4px 14px -10px var(--pcg); }}
  .vcard.featured {{ max-height:270px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.16), inset 4px 0 0 var(--pc), 0 0 0 1.5px var(--pcg),
      0 22px 40px -16px rgba(0,0,0,0.95), 0 6px 20px -10px var(--pcg); }}
  .vdivider {{ align-self:stretch; width:1px; margin:10px 0;
    background:linear-gradient(180deg, transparent, rgba(255,255,255,0.16) 20%, rgba(255,255,255,0.16) 80%, transparent); }}
  .vphotowrap {{ position:relative; width:{photo_sz}px; height:{photo_sz}px; flex:0 0 auto;
    overflow:hidden; border-radius:20px; }}
  .vfire {{ position:absolute; z-index:-1; top:50%; left:50%; width:230%; height:230%;
    transform:translate(-50%,-50%); opacity:0.55; filter:blur(14px); }}
  .vbackdrop {{ position:absolute; inset:-6% -6% -6% -6%; border-radius:24px; z-index:0;
    transform:rotate(4deg); background:linear-gradient(135deg, var(--pc), var(--pc2));
    box-shadow:0 14px 26px -16px rgba(0,0,0,0.7); }}
  .vphoto {{ position:relative; z-index:1; width:100%; height:100%; border-radius:20px; object-fit:cover;
    object-position:center 10%; background:#20242c; border:4px solid var(--pc);
    box-shadow:0 0 24px -4px var(--pc), 0 16px 26px -12px rgba(0,0,0,0.85);
    transform:scale(1.12); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%); }}
  .vphoto.nophoto {{ display:flex; align-items:center; justify-content:center; transform:none; }}
  .vbiglogo {{ width:64%; height:64%; object-fit:contain; }}
  .vbadgeplate {{ position:absolute; z-index:2; right:-10px; bottom:-10px; width:46px; height:46px; border-radius:50%;
    background:radial-gradient(circle at 34% 28%, #ffffff, #e2e8f0 75%); display:flex; align-items:center;
    justify-content:center; box-shadow:0 0 0 3px rgba(255,255,255,0.6), 0 6px 14px -6px rgba(0,0,0,0.6); }}
  .vbadge {{ width:30px; height:30px; object-fit:contain; }}
  .vinfo {{ flex:1; min-width:0; display:flex; flex-direction:column; gap:6px; justify-content:center; }}
  .vname {{ font-size:{name_fs}px; font-weight:800; text-shadow:0 2px 6px rgba(0,0,0,0.6);
            line-height:1.02; letter-spacing:0.3px; width:100%; min-width:0;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .vmeta-row {{ display:flex; align-items:center; gap:12px; min-width:0; }}
  .vrank-chip {{ font-family:"Bahnschrift",sans-serif; font-weight:800; font-size:14px; color:#0a0f1f;
    background:linear-gradient(135deg, var(--pc2), var(--pc)); border-radius:8px; padding:4px 11px;
    letter-spacing:1.2px; flex:0 0 auto; white-space:nowrap;
    box-shadow:0 0 0 1px rgba(255,255,255,0.35) inset, 0 4px 10px -5px rgba(0,0,0,0.7); }}
  .vmeta-line {{ font-size:15px; color:#9fb0c8; letter-spacing:1.2px; text-transform:uppercase;
                 font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .vgauge-wrap {{ margin-top:2px; max-width:420px; }}
  .vgauge-label {{ font-size:14px; color:#f1f5f9; font-weight:800; letter-spacing:0.6px;
                   text-transform:uppercase; margin-bottom:4px; white-space:nowrap; overflow:hidden;
                   text-overflow:ellipsis; text-shadow:0 1px 4px rgba(0,0,0,0.7); }}
  .vgauge-track {{ width:100%; height:10px; border-radius:6px; background:rgba(255,255,255,0.08);
                    box-shadow:inset 0 1px 3px rgba(0,0,0,0.5); overflow:visible; position:relative; }}
  .vgauge-fill {{ height:100%; border-radius:6px; position:relative; overflow:hidden;
                   background:linear-gradient(90deg, var(--pc2), var(--pc));
                   box-shadow:0 0 10px -1px var(--pcg); }}
  .vgauge-cap {{ position:absolute; right:0; top:-2px; width:14px; height:14px; border-radius:50%;
                  background:#ffffff; box-shadow:0 0 0 3px var(--pc), 0 0 10px -1px var(--pcg); }}
  .vstatline {{ font-size:17px; color:{accent}; font-weight:700; margin-top:4px; min-width:0; width:100%;
                line-height:1.25; max-width:440px;
                display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; }}
  .vstats {{ flex:0 0 auto; display:flex; flex-direction:row; align-items:center; gap:20px; }}
  .vproj {{ text-align:right; }}
  .vproj-num {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:72px; color:#fff;
                text-shadow:0 2px 12px rgba(0,0,0,0.55); line-height:1; }}
  .vproj-label {{ font-size:13px; color:#a8b6cc; letter-spacing:1.4px; text-transform:uppercase; }}
  .vpill-col {{ display:flex; flex-direction:column; gap:10px; }}
  .vpill {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:20px; padding:9px 18px 9px 15px;
            border-radius:10px; white-space:nowrap; text-align:center; display:flex; align-items:center;
            gap:8px; box-shadow:inset 0 1px 0 rgba(255,255,255,0.12); }}
  .vpill::before {{ content:""; width:7px; height:7px; border-radius:50%; flex:0 0 auto; }}
  .vpill.wins {{ background:rgba(34,197,94,0.16); color:#4ade80; border:1px solid rgba(34,197,94,0.45); }}
  .vpill.wins::before {{ background:#4ade80; box-shadow:0 0 6px #4ade80; }}
  .vpill.adp {{ background:rgba(56,189,248,0.16); color:#38bdf8; border:1px solid rgba(56,189,248,0.45); }}
  .vpill.adp::before {{ background:#38bdf8; box-shadow:0 0 6px #38bdf8; }}
</style></head>
<body>
  {_OVERLAYS}
  <div class="pattern"></div>
  {_watermark_html()}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      <div class="subtitle">{_esc(subtitle)}</div>
      <div class="rule"></div>
    </div>
    <div class="badge-yr">{_esc(badge)}</div>
  </div>
  <div class="list">
    {rows_html}
  </div>
</body></html>"""


def ranking_poster(
    title: str,
    rows: List[Dict],
    kicker: str = "2026 REDRAFT \u00b7 HALF-PPR",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    footer: str = "",
    badge: str = "2026",
    hero_photo: Optional[str] = None,
    hero_team: Optional[str] = None,
    background: Optional[str] = None,
    variant: str = "classic",
) -> str:
    rows_html = "\n".join(_row_html(r) for r in rows)
    subtitle_html = f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    footer_html = _esc(footer) if footer else ""
    bg = background or _BG.format(accent=accent)
    body_class = "spot" if variant == "spotlight" else ""

    # Size the headshot circle + rank chip to the number of rows so they always
    # fit the bar height (denser boards -> smaller circles); #1's spotlight row
    # is taller, so its elements scale up a notch.
    n = len(rows)
    av = 84 if n <= 8 else (76 if n <= 10 else (66 if n <= 12 else 56))
    rk = round(av * 0.76)
    lg = round(av * 0.46)          # team-logo badge on the headshot
    nolg = round(av * 0.72)        # logo when there's no headshot
    av1, rk1 = av + 12, rk + 6     # #1 spotlight sizes
    rkf, rkf1 = round(rk * 0.5), round(rk1 * 0.5)  # rank font sizes

    # Header right side: a big circular headshot of the #1 player (with team
    # glow + logo badge + year chip) when we have a photo; otherwise the plain
    # year badge as before.
    if hero_photo:
        hero_accent = team_color(hero_team) if hero_team else accent
        hero_logo = team_logo_url(hero_team) if hero_team else ""
        hero_logo_html = f'<img class="hlogo" src="{hero_logo}" alt="">' if hero_logo else ""
        header_right = (
            f'<div class="hero" style="--hero-accent:{hero_accent}">'
            f'<img class="hshot" src="{hero_photo}" alt="">{hero_logo_html}'
            f'<div class="yrchip">{_esc(badge)}</div></div>'
        )
    else:
        header_right = f'<div class="badge">{_esc(badge)}</div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{
    font-family:"Segoe UI", Arial, sans-serif;
    color:#f8fafc;
    background:{bg};
    padding:44px 50px 30px 50px;
    display:flex; flex-direction:column;
    position:relative;
  }}
  {_FX_CSS}
  {_WATERMARK_CSS}
  .topbar, .list, .footer {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
  .kicker {{
    font-family:"Bahnschrift","Segoe UI",sans-serif;
    font-weight:600; letter-spacing:4px; font-size:22px;
    color:{accent}; text-transform:uppercase;
  }}
  .badge {{
    font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px;
    color:#0a0f1f; background:{accent}; border-radius:10px; padding:6px 14px;
    letter-spacing:2px;
  }}
  .hero {{ position:relative; flex:0 0 auto; width:168px; height:168px; }}
  /* soft team-color bloom behind the hero so it glows off the background */
  .hero::before {{ content:""; position:absolute; inset:-22px; border-radius:50%;
    background:radial-gradient(circle at 50% 42%, var(--hero-accent), transparent 68%);
    filter:blur(16px); opacity:0.6; z-index:0; }}
  .hero .hshot {{ position:relative; z-index:1;
    width:168px; height:168px; border-radius:50%; object-fit:cover;
    object-position:center 10%; background:#20242c;
    border:4px solid var(--hero-accent);
    box-shadow:0 0 46px -4px var(--hero-accent), 0 22px 34px -12px rgba(0,0,0,0.85),
      inset 0 0 0 7px var(--hero-accent);
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 80%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 80%, transparent 100%); }}
  .hero .hlogo {{ position:absolute; z-index:2; left:-6px; bottom:2px; width:56px; height:56px;
    object-fit:contain; filter:drop-shadow(0 3px 4px rgba(0,0,0,0.8)); }}
  .hero .yrchip {{ position:absolute; z-index:2; right:-6px; top:2px;
    font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:20px;
    color:#0a0f1f; background:{accent}; border-radius:8px; padding:3px 10px;
    letter-spacing:1px; box-shadow:0 3px 10px rgba(0,0,0,0.5); }}
  .title {{
    font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
    font-weight:700; font-size:82px; line-height:0.9; text-transform:uppercase;
    letter-spacing:1px; margin-top:6px;
    /* carved 3D look: dark stroke behind the fill + a stacked extrude shadow
       (light from top-left, so the extrude falls down) */
    -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
    text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26),
      0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6);
  }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:21px; margin-top:6px; letter-spacing:0.5px;
    text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .list {{ margin-top:18px; display:flex; flex-direction:column; gap:9px;
           flex:1; justify-content:center; }}
  .row {{
    display:flex; align-items:center; gap:16px;
    background:linear-gradient(90deg, var(--team) 0%, var(--team-fade) 34%, rgba(16,18,24,0.5) 60%, rgba(12,13,17,0.24) 100%);
    border:1px solid rgba(255,255,255,0.07);
    border-left:6px solid var(--edge);
    border-radius:16px; padding:0 22px 0 16px;
    flex:1 1 0; min-height:0; max-height:120px; overflow:hidden;
    /* light from top-left: bright inset on the top edge, occlusion at the
       bottom, plus a soft drop shadow so rows read as inset cards */
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08),
      inset 0 -14px 22px -18px rgba(0,0,0,0.9),
      0 12px 24px -14px rgba(0,0,0,0.9);
  }}
  /* #1 gets a spotlight: bigger, brighter, an accent glow frame -- so the eye
     lands on the top entry first (broken tie vs. the rest of the list). */
  .list .row:first-child {{
    flex-grow:1.42;
    background:linear-gradient(90deg, var(--team) 0%, var(--team-fade) 40%, rgba(18,20,26,0.55) 66%, rgba(12,13,17,0.28) 100%);
    border-color:rgba(255,255,255,0.14);
    box-shadow: 0 0 0 1.5px var(--accent), 0 0 36px -6px var(--accent),
      inset 0 1px 0 rgba(255,255,255,0.14), 0 18px 30px -14px rgba(0,0,0,0.92);
  }}
  .list .row:first-child .name {{ font-size:36px; }}
  .list .row:first-child .avatar {{ width:{av1}px; height:{av1}px; }}
  .list .row:first-child .avatar .shot {{ width:{av1}px; height:{av1}px; }}
  .list .row:first-child .rank {{ width:{rk1}px; height:{rk1}px; font-size:{rkf1}px; }}
  .list .row:first-child .stat-num {{ font-size:40px; }}
  .rank {{
    position:relative; flex:0 0 auto; width:{rk}px; height:{rk}px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif;
    font-weight:700; font-size:{rkf}px; color:#e8edf5;
    background:rgba(255,255,255,0.06); border:2px solid rgba(255,255,255,0.16);
  }}
  .rank.m1 {{ background:linear-gradient(145deg,#ffe9a8,#f0a91c); color:#3d2800;
    border:none; box-shadow:0 0 22px -2px rgba(245,169,28,0.8); }}
  .rank.m2 {{ background:linear-gradient(145deg,#f4f6f8,#aab2bd); color:#20262e;
    border:none; box-shadow:0 0 16px -4px rgba(200,210,220,0.6); }}
  .rank.m3 {{ background:linear-gradient(145deg,#f0b483,#a85a1e); color:#2a1400;
    border:none; box-shadow:0 0 16px -4px rgba(190,110,40,0.6); }}
  .delta {{ flex:0 0 auto; min-width:52px; text-align:center;
    font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:21px;
    padding:5px 8px; border-radius:9px; letter-spacing:0.5px;
    box-shadow:0 4px 10px -4px rgba(0,0,0,0.7); }}
  .delta.up {{ color:#4ade80; background:rgba(34,197,94,0.16); border:1px solid rgba(34,197,94,0.5);
    text-shadow:0 0 12px rgba(34,197,94,0.6); }}
  .delta.down {{ color:#f87171; background:rgba(239,68,68,0.16); border:1px solid rgba(239,68,68,0.5);
    text-shadow:0 0 12px rgba(239,68,68,0.6); }}
  .delta.flat {{ color:#8f9db0; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); }}
  .avatar {{ position:relative; flex:0 0 auto; width:{av}px; height:{av}px;
    overflow:hidden; border-radius:50%; }}
  .avatar .shot {{ width:{av}px; height:{av}px; border-radius:50%; object-fit:cover;
    object-position:center 10%; background:#20242c;
    border:3px solid var(--accent);
    box-shadow:0 0 16px -3px var(--accent), 0 10px 16px -8px rgba(0,0,0,0.85);
    transform:scale(1.12); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%); }}
  .avatar .logo {{ position:absolute; right:-6px; bottom:-4px; width:{lg}px; height:{lg}px;
    object-fit:contain; filter:drop-shadow(0 1px 2px rgba(0,0,0,0.7)); }}
  .avatar.nophoto {{ display:flex; align-items:center; justify-content:center; }}
  .avatar.nophoto .logo {{ position:static; width:{nolg}px; height:{nolg}px; }}
  .meta {{ flex:1; min-width:0; }}
  .name {{ font-size:31px; font-weight:700; letter-spacing:0.3px; line-height:1.08;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
           text-shadow:0 2px 5px rgba(0,0,0,0.7); }}
  .sub {{ font-size:16px; color:#c4cfde; margin-top:1px; letter-spacing:1px;
          line-height:1.15; text-transform:uppercase; text-shadow:0 1px 3px rgba(0,0,0,0.7); }}
  .statline {{ font-size:16px; color:{accent}; font-weight:600; margin-top:2px;
               line-height:1.15; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
               text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .stat {{ text-align:right; min-width:104px; flex:0 0 auto; }}
  .stat-num {{ font-family:"Bahnschrift",sans-serif; font-weight:700;
               font-size:34px; color:#ffffff; text-shadow:0 2px 8px rgba(0,0,0,0.5); }}
  .stat-label {{ font-size:13px; color:#8896ad; letter-spacing:1.5px;
                 text-transform:uppercase; }}
  .footer {{ margin-top:16px; color:#64748b; font-size:15px; letter-spacing:0.5px;
             display:flex; justify-content:space-between; }}

  /* ---- "spotlight" variant: squared glassy rows + squared photos/chips, a
     stronger team wash and a heavier accent bar. Same data, different silhouette. */
  body.spot .row {{
    background:linear-gradient(90deg, var(--team) 0%, var(--team-fade) 38%, rgba(12,13,17,0.34) 62%, rgba(12,13,17,0.10) 100%);
    border:1px solid rgba(255,255,255,0.05);
    border-left:8px solid var(--edge);
    border-radius:10px;
  }}
  body.spot .rank {{ border-radius:13px; background:rgba(255,255,255,0.05);
    box-shadow:inset 0 0 0 1px rgba(255,255,255,0.10); }}
  body.spot .avatar {{ border-radius:15px; }}
  body.spot .avatar .shot {{ border-radius:15px; }}
  body.spot .avatar .logo {{ right:-7px; bottom:-6px; }}
  body.spot .name {{ letter-spacing:0.6px; }}
  body.spot .stat-num {{ color:var(--accent-l); text-shadow:0 0 18px var(--accent), 0 2px 6px rgba(0,0,0,0.6); }}
</style></head>
<body class="{body_class}">
  {_OVERLAYS}
  {_watermark_html()}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      {subtitle_html}
    </div>
    {header_right}
  </div>
  <div class="list">
    {rows_html}
  </div>
  <div class="footer"><span>{footer_html}</span><span>data-driven \u00b7 our projections</span></div>
</body></html>"""


def _cmp_side(p: Dict, side: str) -> str:
    """One fighter panel (big glowing headshot + name + sub) for the compare
    card. side is 'l' or 'r'. Two-tone: primary rims the photo/border, secondary
    is available via --pc2. A blurred team bloom sits behind the cutout so the
    player lifts off the arena instead of sitting flat on it."""
    team = p.get("team", "")
    color, color2 = team_color(team), team_secondary(team)
    logo = team_logo_url(team) if team else ""
    photo = p.get("photo", "")
    if photo:
        logo_html = f'<img class="clogo" src="{logo}" alt="">' if logo else ""
        # logo is a sibling of (not inside) the clipping .cshot-wrap so it isn't
        # cut off by the wrap's overflow:hidden
        shot = (f'<div class="cshot-holder"><div class="cshot-wrap">'
                f'<img class="cshot" src="{photo}" alt=""></div>{logo_html}</div>')
    else:
        logo_html = f'<img class="clogo big" src="{logo}" alt="">' if logo else ""
        shot = f'<div class="cshot-wrap nophoto">{logo_html}</div>'
    return (f'<div class="fighter {side}" style="--pc:{color};--pc2:{color2}">'
            f'{shot}'
            f'<div class="cname">{_esc(p.get("name",""))}</div>'
            f'<div class="csub">{_esc(p.get("sub",""))}</div>'
            f'</div>')


def comparison_poster(
    left: Dict,
    right: Dict,
    metrics: List[Dict],
    title: str = 'Head to <span class="accent">Head</span>',
    kicker: str = "2026 REDRAFT \u00b7 US vs CONSENSUS",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    footer: str = "",
    badge: str = "VS",
    background: Optional[str] = None,
    seed: Optional[str] = None,
) -> str:
    """Two-player head-to-head "arena" card. `metrics` is a list of
    {label, left, right, win} where win is 'L', 'R' or ''. The winning side's
    value is enlarged and glows in that player's team color, the row leans a
    team-tinted gradient toward the winner, and a verdict bar tallies the
    categories. Built to POP: team-split arena, blurred hero blooms, an accent
    VS medallion, grain + vignette."""
    bg = background or _BG.format(accent=accent)
    subtitle_html = f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    lc, rc = team_color(left.get("team", "")), team_color(right.get("team", ""))
    # Lightened tints so winner values/labels stay legible even for dark teams
    # (the true saturated color is kept for the glow).
    lcl, rcl = _lighten(lc), _lighten(rc)

    metric_rows = []
    lw = rw = 0
    for m in metrics:
        win = m.get("win", "")
        lcls = "cval win" if win == "L" else "cval"
        rcls = "cval win" if win == "R" else "cval"
        rowcls = "mrow winL" if win == "L" else ("mrow winR" if win == "R" else "mrow")
        if win == "L":
            lw += 1
        elif win == "R":
            rw += 1
        larw = f'<span class="arw" style="color:{lcl}">\u25c0</span>' if win == "L" else ""
        rarw = f'<span class="arw" style="color:{rcl}">\u25b6</span>' if win == "R" else ""
        metric_rows.append(
            f'<div class="{rowcls}">'
            f'<div class="{lcls}" style="--pc:{lc};--pcl:{lcl}">{_esc(m.get("left",""))}</div>'
            f'<div class="mlabel">{larw}{_esc(m.get("label",""))}{rarw}</div>'
            f'<div class="{rcls}" style="--pc:{rc};--pcl:{rcl}">{_esc(m.get("right",""))}</div>'
            f'</div>')
    metric_html = "\n".join(metric_rows)

    # Verdict bar: who wins more categories, tinted to the leader's team color.
    if lw > rw:
        verdict = (f'<span class="lead" style="--lead:{lcl}">{_esc(left.get("name",""))}</span>'
                   f'<span class="vtxt">takes it</span><span class="score">{lw}\u2013{rw}</span>')
    elif rw > lw:
        verdict = (f'<span class="lead" style="--lead:{rcl}">{_esc(right.get("name",""))}</span>'
                   f'<span class="vtxt">takes it</span><span class="score">{rw}\u2013{lw}</span>')
    else:
        verdict = f'<span class="vtxt">Dead heat</span><span class="score">{lw}\u2013{rw}</span>'

    # Team-color tints for the arena diagonal split and the winner row lean.
    lc_tint, rc_tint = _hex_to_rgba(lc, 0.22), _hex_to_rgba(rc, 0.22)
    lc_lean, rc_lean = _hex_to_rgba(lc, 0.20), _hex_to_rgba(rc, 0.20)
    lc_bord, rc_bord = _hex_to_rgba(lc, 0.55), _hex_to_rgba(rc, 0.55)
    # gradient-mesh texture (client pick for this card), team-coloured
    mesh_css = _mesh_props(lc, rc, dark=True)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc; background:{bg};
    padding:44px 50px 30px 50px; display:flex; flex-direction:column; position:relative;
    --lc-tint:{lc_tint}; --rc-tint:{rc_tint}; --lc-lean:{lc_lean}; --rc-lean:{rc_lean};
    --lc-bord:{lc_bord}; --rc-bord:{rc_bord}; }}
  .pattern {{ position:absolute; inset:0; pointer-events:none; z-index:0; {mesh_css} }}
  {_FX_CSS}
  {_WATERMARK_CSS}
  .topbar, .arena, .metrics, .verdict, .footer {{ position:relative; z-index:2; }}
  /* padding-right keeps the badge clear of the top-right watermark logo */
  .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:24px;
    padding-right:132px; }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:600;
    letter-spacing:4px; font-size:22px; color:{accent}; text-transform:uppercase; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
    font-weight:700; font-size:80px; line-height:0.9; text-transform:uppercase;
    letter-spacing:1px; margin-top:6px;
    -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
    text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26),
      0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:21px; margin-top:6px; text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .badge {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px;
    color:#0a0f1f; background:{accent}; border-radius:12px; padding:7px 16px; letter-spacing:2px;
    box-shadow:0 8px 20px -6px rgba(0,0,0,0.6); }}

  .arena {{ margin-top:24px; position:relative; display:grid; grid-template-columns:1fr 1fr;
    border-radius:22px; overflow:hidden; border:1px solid rgba(255,255,255,0.08);
    background:
      linear-gradient(103deg, var(--lc-tint) 0%, var(--lc-tint) 38%, transparent 48%,
        transparent 52%, var(--rc-tint) 62%, var(--rc-tint) 100%),
      linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.012));
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 22px 44px -22px rgba(0,0,0,0.9); }}
  .fighter {{ position:relative; display:flex; flex-direction:column; align-items:center;
    text-align:center; padding:32px 18px 24px; }}
  .fighter.l {{ border-top:5px solid var(--pc); }}
  .fighter.r {{ border-top:5px solid var(--pc); }}
  .fighter::before {{ content:""; position:absolute; top:26px; left:50%; transform:translateX(-50%);
    width:220px; height:220px; border-radius:50%;
    background:radial-gradient(circle, var(--pc), transparent 66%); filter:blur(22px); opacity:0.5; z-index:0; }}
  .cshot-holder {{ position:relative; z-index:1; width:208px; height:208px; }}
  .cshot-wrap {{ position:relative; z-index:1; width:208px; height:208px; overflow:hidden; border-radius:50%; }}
  .cshot {{ width:208px; height:208px; border-radius:50%; object-fit:cover; object-position:center 8%;
    background:#20242c; border:5px solid var(--pc);
    box-shadow:0 0 52px -8px var(--pc), 0 26px 40px -14px rgba(0,0,0,0.85);
    transform:scale(1.12); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%); }}
  .cshot-wrap.nophoto {{ display:flex; align-items:center; justify-content:center;
    border-radius:50%; border:5px solid var(--pc); background:#141821;
    box-shadow:0 26px 40px -14px rgba(0,0,0,0.85); }}
  /* team logo on a clean white plate, sitting on the photo's lower-right rim
     (outside the clipping wrap so it's never cut off) */
  .clogo {{ position:absolute; z-index:3; bottom:-6px; right:-6px; width:70px; height:70px; border-radius:50%;
    background:#fff; padding:11px; object-fit:contain;
    box-shadow:0 0 0 3px var(--pc), 0 8px 16px -5px rgba(0,0,0,0.75); }}
  .clogo.big {{ position:static; width:104px; height:104px; background:none; padding:0; box-shadow:none;
    border-radius:0; }}
  .cname {{ position:relative; z-index:1; font-size:39px; font-weight:800; margin-top:16px; line-height:1.0;
    text-shadow:0 2px 6px rgba(0,0,0,0.7); -webkit-text-stroke:0.75px rgba(0,0,0,0.32); paint-order:stroke fill; }}
  .csub {{ position:relative; z-index:1; font-size:16px; color:#c4cfde; margin-top:6px; letter-spacing:1px;
    text-transform:uppercase; text-shadow:0 1px 3px rgba(0,0,0,0.7); }}
  .vs {{ position:absolute; left:50%; top:132px; transform:translate(-50%,-50%) rotate(-8deg); z-index:5;
    font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:700; font-size:36px;
    color:#0a0f1f; width:94px; height:94px; border-radius:50%;
    background:radial-gradient(circle at 38% 30%, rgba(255,255,255,0.65), transparent 45%), {accent};
    border:3px solid rgba(255,255,255,0.85);
    display:flex; align-items:center; justify-content:center;
    box-shadow:0 0 40px -2px {accent}, 0 12px 26px rgba(0,0,0,0.6); }}

  .metrics {{ margin-top:20px; display:flex; flex-direction:column; gap:9px; flex:1; justify-content:center; }}
  .mrow {{ position:relative; display:grid; grid-template-columns:1fr 210px 1fr; align-items:center;
    background:linear-gradient(90deg, rgba(255,255,255,0.05), rgba(255,255,255,0.025), rgba(255,255,255,0.05));
    border:1px solid rgba(255,255,255,0.06); border-radius:14px; padding:12px 26px;
    flex:1 1 0; min-height:0; max-height:110px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 10px 20px -14px rgba(0,0,0,0.85); }}
  .mrow.winL {{ background:linear-gradient(90deg, var(--lc-lean) 0%, rgba(255,255,255,0.02) 55%, rgba(255,255,255,0.02) 100%);
    border-color:var(--lc-bord); }}
  .mrow.winR {{ background:linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.02) 45%, var(--rc-lean) 100%);
    border-color:var(--rc-bord); }}
  .cval {{ font-family:"Bahnschrift",sans-serif; font-weight:800; font-size:42px; color:#dbe3ee;
    text-shadow:0 2px 5px rgba(0,0,0,0.7); }}
  .cval:first-child {{ text-align:left; }}
  .cval:last-child {{ text-align:right; }}
  .cval.win {{ color:var(--pcl); font-size:56px;
    -webkit-text-stroke:1.5px rgba(0,0,0,0.45); paint-order:stroke fill;
    text-shadow:0 0 24px var(--pcl), 0 2px 6px rgba(0,0,0,0.8); }}
  .mlabel {{ text-align:center; font-size:15px; color:#b3bece; letter-spacing:2px;
    text-transform:uppercase; font-weight:700; display:flex; align-items:center; justify-content:center; gap:9px; }}
  .arw {{ font-size:17px; line-height:1; filter:drop-shadow(0 0 6px currentColor); }}
  .verdict {{ margin-top:14px; display:flex; align-items:center; justify-content:center; gap:12px;
    font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px; letter-spacing:1px;
    background:linear-gradient(90deg, transparent, rgba(255,255,255,0.055), transparent);
    padding:12px; border-radius:12px; text-transform:uppercase; }}
  .verdict .lead {{ color:var(--lead); text-shadow:0 0 20px var(--lead); }}
  .verdict .vtxt {{ color:#9fb0c3; font-size:20px; letter-spacing:2px; }}
  .verdict .score {{ color:#e8edf5; font-size:24px;
    background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.12);
    border-radius:9px; padding:2px 12px; }}
  .footer {{ margin-top:14px; color:#64748b; font-size:15px; display:flex; justify-content:space-between; }}
</style></head>
<body>
  <div class="pattern"></div>
  {_OVERLAYS}
  {_watermark_html()}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      {subtitle_html}
    </div>
    <div class="badge">{_esc(badge)}</div>
  </div>
  <div class="arena">
    {_cmp_side(left, 'l')}
    {_cmp_side(right, 'r')}
    <div class="vs">VS</div>
  </div>
  <div class="metrics">
    {metric_html}
  </div>
  <div class="verdict">{verdict}</div>
</body></html>"""


# Clean monoline SVG icon paths (24x24 viewBox, stroke-only) per metric label
# -- replaces an earlier emoji-glyph version that read as tacky. Keyed by the
# exact label strings build_compare() passes today; anything unrecognized
# falls back to a generic bar-chart icon rather than erroring.
_SCOREBOARD_ICON_PATHS = {
    "Our Rank": ('<path d="M6 3h12v3a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5V3z"/>'
                 '<path d="M9 16.5h6v2H9z"/><path d="M8 21h8"/>'
                 '<path d="M4.5 4.5H6V6a3.2 3.2 0 0 1-3.2 3.2"/>'
                 '<path d="M19.5 4.5H18V6a3.2 3.2 0 0 0 3.2 3.2"/>'),
    "Pos Rank": ('<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="4.6"/>'
                 '<circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>'),
    "Sleeper ADP": ('<polyline points="3,16.5 9,10.5 13,14.5 21,6.5"/>'
                    '<polyline points="15,6.5 21,6.5 21,12.5"/>'),
    "Proj Pts": ('<ellipse cx="12" cy="12" rx="9.4" ry="6"/>'
                 '<line x1="5" y1="12" x2="19" y2="12"/>'
                 '<line x1="9" y1="9.6" x2="9" y2="14.4"/>'
                 '<line x1="12" y1="9" x2="12" y2="15"/>'
                 '<line x1="15" y1="9.6" x2="15" y2="14.4"/>'),
    "VOR": ('<path d="M12 3.2l2.63 5.9 6.37.63-4.8 4.36 1.4 6.31L12 16.98l-5.6 3.42 '
            '1.4-6.31-4.8-4.36 6.37-.63z"/>'),
    # Same-position major-stat comparisons (build_compare uses these instead
    # of Our Rank/Pos Rank/ADP/Proj/VOR when both players share a position).
    "Pass Yards": ('<line x1="3" y1="12" x2="21" y2="12"/><line x1="6" y1="9" x2="6" y2="15"/>'
                   '<line x1="12" y1="9" x2="12" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/>'),
    "Rush Yards": ('<line x1="3" y1="12" x2="21" y2="12"/><line x1="6" y1="9" x2="6" y2="15"/>'
                   '<line x1="12" y1="9" x2="12" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/>'),
    "Rec Yards": ('<line x1="3" y1="12" x2="21" y2="12"/><line x1="6" y1="9" x2="6" y2="15"/>'
                  '<line x1="12" y1="9" x2="12" y2="15"/><line x1="18" y1="9" x2="18" y2="15"/>'),
    "Pass TD": '<path d="M6 3v18"/><path d="M6 4h11l-3 4 3 4H6"/>',
    "Rush TD": '<path d="M6 3v18"/><path d="M6 4h11l-3 4 3 4H6"/>',
    "Rec TD": '<path d="M6 3v18"/><path d="M6 4h11l-3 4 3 4H6"/>',
    "Total TD": '<path d="M6 3v18"/><path d="M6 4h11l-3 4 3 4H6"/>',
    "Receptions": ('<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="4.6"/>'
                   '<circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>'),
}
_SCOREBOARD_ICON_DEFAULT = ('<line x1="5" y1="19" x2="5" y2="10"/>'
                            '<line x1="12" y1="19" x2="12" y2="6"/>'
                            '<line x1="19" y1="19" x2="19" y2="13"/>')


def _scoreboard_icon_svg(label: str, color: str) -> str:
    path = _SCOREBOARD_ICON_PATHS.get(label, _SCOREBOARD_ICON_DEFAULT)
    return (f'<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="{color}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{path}</svg>')


# Background TEXTURE variety (separate from the accent-color THEMES above) --
# picked at random per render (or reproducibly via a seed) so head-to-head
# posts don't all look identical. Each is a CSS background-image string;
# comparison_scoreboard_poster layers the chosen one under the color blooms.
BG_PATTERNS: Dict[str, str] = {
    "orbit": ("radial-gradient(150px 150px at 25% 30%, rgba(15,23,42,0.48), transparent 70%) 0 0/220px 220px,"
              "radial-gradient(100px 100px at 74% 68%, rgba(15,23,42,0.36), transparent 70%) 0 0/220px 220px"),
    "halo": ("radial-gradient(circle at 30% 35%, transparent 34%, rgba(15,23,42,0.44) 40%, transparent 50%) 0 0/210px 210px,"
             "radial-gradient(circle at 74% 72%, transparent 24%, rgba(15,23,42,0.32) 30%, transparent 40%) 0 0/210px 210px"),
    "spark": ("radial-gradient(8px 8px at center, rgba(15,23,42,0.55) 62%, transparent 100%) 0 0/30px 30px,"
              "radial-gradient(5px 5px at 50% 50%, rgba(15,23,42,0.42) 62%, transparent 100%) 15px 15px/30px 30px"),
    "drift": ("linear-gradient(120deg, transparent 22%, rgba(15,23,42,0.42) 40%, rgba(15,23,42,0.42) 48%, transparent 66%) 0 0/220px 220px,"
              "linear-gradient(120deg, transparent 4%, rgba(15,23,42,0.28) 16%, rgba(15,23,42,0.28) 22%, transparent 34%) 60px 60px/220px 220px"),
    "mesh": ("radial-gradient(46px 46px at 0% 0%, rgba(15,23,42,0.40), transparent 70%) 0 0/120px 120px,"
             "radial-gradient(46px 46px at 100% 50%, rgba(15,23,42,0.40), transparent 70%) 0 0/120px 120px,"
             "radial-gradient(46px 46px at 0% 100%, rgba(15,23,42,0.40), transparent 70%) 0 0/120px 120px"),
}
BG_PATTERN_NAMES = list(BG_PATTERNS)


def resolve_bg_pattern(name: Optional[str] = None, seed: Optional[str] = None) -> str:
    """Pick a background texture (see BG_PATTERNS): force one with `name`,
    reproduce one from any `seed` string, else pick at random -- same rules
    as resolve_theme/resolve_variant so a --seed pins the whole look."""
    if name and name in BG_PATTERNS:
        return name
    if seed is not None:
        return BG_PATTERN_NAMES[int(_hashlib.md5(("bg" + str(seed)).encode()).hexdigest(), 16)
                                 % len(BG_PATTERN_NAMES)]
    return _random.choice(BG_PATTERN_NAMES)


# --- Organic background "skins" ----------------------------------------------
# Repeating LINE patterns (weave/field/stripes) read as cheap and busy at print
# scale -- the eye follows the lines instead of the content. Premier sports
# graphics use ORGANIC texture instead: fine paper/sand grain, soft painted
# plaster, marbled swirl, low-poly prism facets. We generate these procedurally
# as inline SVG data URIs -- feTurbulence fractal noise for the paint/sand/
# plaster/marble looks, and a hand-built triangulated mesh for the prisms. All
# are tinted (navy on the light head-to-head canvas, white on the dark
# value-targets canvas) and kept at low alpha so they enrich the surface
# WITHOUT ever sitting on top of a number or hurting legibility.

def _svg_bg(svg: str) -> str:
    """Compact + URL-encode an SVG string into a CSS url() background value."""
    svg = " ".join(svg.split())
    return 'url("data:image/svg+xml,' + _urlparse.quote(svg, safe="") + '")'


def _noise_props(base_freq: float, octaves: int, opacity: float, rgb: tuple,
                 ttype: str = "fractalNoise") -> str:
    """A tinted fractal-noise texture (paint / sand / plaster / marble depending
    on frequency + type). feTurbulence makes the organic field; feColorMatrix
    turns its luminance into an alpha mask; a flood of the tint colour is
    composited through that mask -- so the result is a single-hue organic grain
    whose peak opacity is `opacity` (kept low so it never blocks text).

    Rendered ONCE at full canvas size and drawn no-repeat/cover -- a small
    repeating tile stamped the same blob across the canvas in a grid ("copied
    and pasted"); one full-canvas instance is a single continuous field with no
    seams."""
    r, g, b = rgb
    W, H = CANVAS_W, CANVAS_H
    lum = "0.42 0.42 0.16 0 0"

    def _layer(fid: str, bf: str, oct_: int, op: float, ttyp: str) -> str:
        return (
            f"<filter id='{fid}' x='0' y='0' width='100%' height='100%'>"
            f"<feTurbulence type='{ttyp}' baseFrequency='{bf}' numOctaves='{oct_}' result='t'/>"
            f"<feColorMatrix in='t' type='matrix' values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 {lum}' result='a'/>"
            f"<feComponentTransfer in='a' result='m'><feFuncA type='linear' slope='{op}' intercept='0'/>"
            f"</feComponentTransfer>"
            f"<feFlood flood-color='rgb({r},{g},{b})' result='c'/>"
            f"<feComposite in='c' in2='m' operator='in'/></filter>"
        )

    # a richer stack: the main organic field (soft clouds/marble/paint) PLUS a
    # fine, high-frequency grain layered over it -- the grain adds crisp
    # tooth/fidelity so the surface reads as premium plaster/paper rather than a
    # soft low-detail blob
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}'>"
        + _layer("n", str(base_freq), max(octaves, 4), opacity, ttype)
        + _layer("fine", "0.85", 2, opacity * 0.5, "fractalNoise")
        + f"<rect width='100%' height='100%' filter='url(#n)'/>"
        + f"<rect width='100%' height='100%' filter='url(#fine)'/>"
        + "</svg>"
    )
    return f"background-image:{_svg_bg(svg)}; background-size:cover; background-repeat:no-repeat;"


def _lowpoly_props(seed: str, rgb: tuple, a_lo: float = 0.02, a_hi: float = 0.08) -> str:
    """A low-poly prism mesh: a jittered point grid split into triangles, each
    facet flooded with the tint at a seeded, varied alpha so light seems to
    catch the facets. Non-repeating, sized to cover the whole canvas."""
    r, g, b = rgb
    W, H = CANVAS_W, CANVAS_H
    cols, rows = 7, 10
    cw, ch = W / cols, H / rows

    def _jit(key: str, amp: float) -> float:
        h = int(_hashlib.md5(f"{seed}-{key}".encode()).hexdigest(), 16)
        return (h % 1000 / 1000.0 - 0.5) * amp

    pts = {}
    for i in range(cols + 1):
        for j in range(rows + 1):
            x = i * cw + (_jit(f"x{i}-{j}", cw * 0.7) if 0 < i < cols else 0)
            y = j * ch + (_jit(f"y{i}-{j}", ch * 0.7) if 0 < j < rows else 0)
            pts[(i, j)] = (round(x, 1), round(y, 1))

    tris = []
    for i in range(cols):
        for j in range(rows):
            a, bb, c, d = pts[(i, j)], pts[(i + 1, j)], pts[(i, j + 1)], pts[(i + 1, j + 1)]
            for tri, key in (((a, bb, c), f"t1-{i}-{j}"), ((bb, d, c), f"t2-{i}-{j}")):
                hh = int(_hashlib.md5((seed + key).encode()).hexdigest(), 16)
                # base seeded alpha, plus a gentle light-from-top-left lean so
                # adjacent facets differ enough to read as beveled glass, not a
                # flat field of same-colour triangles
                cx = sum(p[0] for p in tri) / 3.0
                cy = sum(p[1] for p in tri) / 3.0
                light = 1.0 - 0.45 * ((cx / W) * 0.5 + (cy / H) * 0.5)  # brighter (lower alpha) toward top-left
                al = (a_lo + (hh % 1000 / 1000.0) * (a_hi - a_lo)) * light
                poly = " ".join(f"{x},{y}" for x, y in tri)
                tris.append(f"<polygon points='{poly}' fill='rgb({r},{g},{b})' fill-opacity='{al:.3f}'/>")

    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' "
           f"viewBox='0 0 {W} {H}'>" + "".join(tris) + "</svg>")
    return f"background-image:{_svg_bg(svg)}; background-size:cover; background-repeat:no-repeat;"


def _mesh_props(c1: str, c2: str, dark: bool) -> str:
    """Gradient-mesh: soft blobs of the two team/accent colours plus a neutral
    pool. Smooth, modern, no noise -- reads clean and premium."""
    a = 0.20 if dark else 0.16
    ink = "255,255,255" if dark else "15,23,42"
    return (
        "background-image:"
        f"radial-gradient(circle at 20% 24%, {_hex_to_rgba(c1, a)}, transparent 48%),"
        f"radial-gradient(circle at 82% 74%, {_hex_to_rgba(c2, a)}, transparent 48%),"
        f"radial-gradient(circle at 64% 40%, rgba({ink},{a*0.35:.3f}), transparent 52%);"
        " background-size:cover; background-repeat:no-repeat;"
    )


def _carbon_props(dark: bool) -> str:
    """Carbon-fibre weave: a fine 2-direction twill."""
    ink = "255,255,255" if dark else "15,23,42"
    a = 0.05
    return (
        "background-image:"
        f"repeating-linear-gradient(45deg, rgba({ink},{a}) 0 2px, transparent 2px 5px),"
        f"repeating-linear-gradient(-45deg, rgba({ink},{a}) 0 2px, transparent 2px 5px);"
        " background-size:10px 10px; background-repeat:repeat;"
    )


def _brushed_props(dark: bool) -> str:
    """Brushed metal: fine vertical grain + a soft diagonal sheen."""
    ink = "255,255,255" if dark else "15,23,42"
    a = 0.05 if dark else 0.045
    return (
        "background-image:"
        f"linear-gradient(115deg, rgba({ink},{a*1.5:.3f}) 0%, transparent 44%),"
        f"repeating-linear-gradient(90deg, rgba({ink},{a}) 0 1px, transparent 1px 3px);"
        " background-size:cover, 4px 100%; background-repeat:no-repeat, repeat;"
    )


# The client-approved texture set (from the sampler): 1 prisms, 2 gradient
# mesh, 3 carbon fibre, 6 plaster, 9 brushed metal. Each card rotates through
# these per seed so repeated posts vary; `salt` offsets the pick so different
# card FORMATS don't land on the same texture for the same seed.
_TEXTURE_KEYS = ["prisms", "mesh", "carbon", "plaster", "brushed"]


def _resolve_skin_css(seed: Optional[str], salt: str, dark: bool,
                      c1: Optional[str] = None, c2: Optional[str] = None) -> str:
    """Pick one approved texture for this card (see _TEXTURE_KEYS). `dark`
    tints white on the dark cards, navy on the light one. `c1`/`c2` are the
    two accent colours the gradient-mesh blobs use (fall back to BRAND_ACCENT)."""
    rgb = (255, 255, 255) if dark else (15, 23, 42)
    c1 = c1 or BRAND_ACCENT
    c2 = c2 or c1
    if seed is not None:
        idx = int(_hashlib.md5((salt + "tex" + str(seed)).encode()).hexdigest(), 16) % len(_TEXTURE_KEYS)
        pseed = _hashlib.md5((salt + "poly" + str(seed)).encode()).hexdigest()[:12]
    else:
        idx = _random.randrange(len(_TEXTURE_KEYS))
        pseed = f"{_random.random()}"
    key = _TEXTURE_KEYS[idx]
    if key == "mesh":
        return _mesh_props(c1, c2, dark)
    if key == "carbon":
        return _carbon_props(dark)
    if key == "brushed":
        return _brushed_props(dark)
    if key == "plaster":
        return _noise_props(0.011, 5, 0.20 if dark else 0.28, rgb)
    return _lowpoly_props(pseed, rgb, a_lo=0.025, a_hi=0.11 if dark else 0.12)


def _vivid_wash_css(seed: Optional[str] = None) -> str:
    """A big randomized-hue color wash for comparison_scoreboard_poster's
    vivid_bg mode: picks a hue (any color, seeded/reproducible like the other
    resolve_* helpers), a lightness that's sometimes darker/sometimes
    brighter, an opacity in a tasteful-but-visible range, and a diagonal
    angle/position -- so no two "value_upside" cards land on the same look,
    while staying subtle enough not to fight the team-color blooms or the
    text legibility on top of it."""
    if seed is not None:
        h = int(_hashlib.md5(("wash-h" + str(seed)).encode()).hexdigest(), 16) % 360
        l_bucket = int(_hashlib.md5(("wash-l" + str(seed)).encode()).hexdigest(), 16) % 100
        a_bucket = int(_hashlib.md5(("wash-a" + str(seed)).encode()).hexdigest(), 16) % 100
        ang_bucket = int(_hashlib.md5(("wash-ang" + str(seed)).encode()).hexdigest(), 16) % 360
    else:
        h = _random.randint(0, 359)
        l_bucket = _random.randint(0, 99)
        a_bucket = _random.randint(0, 99)
        ang_bucket = _random.randint(0, 359)
    lightness = 32 + (l_bucket / 99.0) * 30       # 32-62% -- sometimes darker, sometimes lighter
    opacity = 0.10 + (a_bucket / 99.0) * 0.14      # 0.10-0.24 -- vibrant but not overpowering
    hue2 = (h + 40) % 360                          # a near-analogous second stop for a richer gradient
    return (
        f"linear-gradient({ang_bucket}deg, "
        f"hsla({h}, 78%, {lightness:.0f}%, {opacity:.2f}) 0%, "
        f"hsla({hue2}, 70%, {lightness + 8:.0f}%, {opacity * 0.55:.2f}) 45%, "
        f"transparent 85%)"
    )


def _scoreboard_base_css(seed: Optional[str] = None) -> str:
    """Randomizes how LIGHT the scoreboard card's base canvas is (separate
    from _vivid_wash_css's color hue) -- the original card was always the
    same near-white gradient no matter what. A wider light-to-medium-gray
    range looked "low quality" and hurt legibility (the whole card is
    designed dark-text-on-light), so this stays in a narrow, always-bright
    band: just enough variety that repeated cards don't look identical, never
    dim/muddy."""
    if seed is not None:
        t_bucket = int(_hashlib.md5(("wash-tone" + str(seed)).encode()).hexdigest(), 16) % 100
    else:
        t_bucket = _random.randint(0, 99)
    top_l = 92 - (t_bucket / 99.0) * 8     # 84-92% lightness for the brightest stop
    mid_l = min(99, top_l + 7)
    bot_l = max(80, top_l - 8)

    def _gray(pct: float) -> str:
        v = round(255 * pct / 100)
        return f"#{v:02x}{v:02x}{v:02x}"

    return f"linear-gradient(160deg, {_gray(top_l)} 0%, {_gray(mid_l)} 45%, {_gray(bot_l)} 100%)"


def _scoreboard_bar_pcts(lval, rval, lower_is_better: bool = False, max_pct: float = 85.0) -> tuple:
    """Faint sideways-bar-chart widths (as a % of each side's cell) for a
    stat row: whichever side is actually better -- accounting for
    lower_is_better (ADP, Pos Rank) vs higher_is_better (yards, TD, VOR,
    proj pts, etc.) -- gets the full max_pct bar, and the other side's bar
    is scaled down by how much worse it is. Returns (0, 0) if either value
    is missing so no bar renders for "--" rows."""
    if lval is None or rval is None:
        return (0, 0)
    try:
        lval, rval = float(lval), float(rval)
    except (TypeError, ValueError):
        return (0, 0)
    if lower_is_better:
        a = (1.0 / lval) if lval > 0 else 0.0
        b = (1.0 / rval) if rval > 0 else 0.0
    else:
        a, b = max(lval, 0.0), max(rval, 0.0)
    mx = max(a, b)
    if mx <= 0:
        return (0, 0)
    return (round(max_pct * a / mx, 1), round(max_pct * b / mx, 1))


def _vivid_pair(team: str, accent: str) -> tuple:
    """Pick the punchier of a team's two colors for the main pop (glow, name,
    winner value) and keep the other as a secondary accent stripe -- same
    "more vibrant color leads" logic ranking_poster uses per-row."""
    pc, sc = team_color(team), team_secondary(team)
    if not pc:
        return accent, accent
    if not sc:
        return pc, pc
    return (pc, sc) if _chroma(pc) >= _chroma(sc) else (sc, pc)


# A simple, recognizable flame silhouette -- rendered large, blurred, and
# faint behind the overall-winner's photo (see comparison_scoreboard_poster).
_FIRE_PATH = ('<path d="M12 2c-2.6 3.4-5.4 6.2-5.4 10.4a5.4 5.4 0 0 0 10.8 0c0-1.8-.7-3.4-1.7-4.6'
              '.3 1.7-.9 2.7-1.8 2.2-1-.6-1.1-2-.3-3.4C14.6 4.7 13.4 3.2 12 2z"/>')

# A simple 3-peak crown, propped at a jaunty angle on the winner's frame
# border (see comparison_scoreboard_poster / .scrown).
_CROWN_PATH = ('<path d="M2 8.5 6 12 9.5 4 12 10 14.5 4 18 12 22 8.5 20 18H4z"/>'
               '<rect x="4" y="18" width="16" height="2.4" rx="1"/>')


def _scoreboard_side(p: Dict, side: str, accent: str, is_winner: bool = False) -> str:
    """One player block for the scoreboard card: a big carved name (team-
    colored, glowing) with a two-tone underline, a rotated team-gradient
    backdrop card peeking out behind a large rounded-rectangle headshot
    frame (kills the bare-white blank space behind the head), a big logo
    badge on a white plate for contrast, and -- if this side wins more
    stat rows overall -- a large, faint team-color flame silhouette behind
    the whole photo. side is 'l'/'r' so everything aligns outward toward
    the canvas edges, mirrored toward the center VS medal."""
    team = p.get("team", "")
    vivid, other = _vivid_pair(team, accent)
    logo = team_logo_url(team) if team else ""
    photo = p.get("photo", "")
    align = "left" if side == "l" else "right"
    tilt = "-3deg" if side == "l" else "3deg"
    if photo:
        img_html = f'<img class="sshot" src="{photo}" alt="">'
    else:
        img_html = f'<img class="sshot slogo" src="{logo}" alt="">' if logo else '<div class="sshot sblank"></div>'
    logo_badge = (f'<div class="sbadge-plate"><img class="sbadge" src="{logo}" alt=""></div>'
                  if (logo and photo) else "")
    fire_html = (f'<svg class="sfire" viewBox="0 0 24 24" fill="{vivid}">{_FIRE_PATH}</svg>'
                 if is_winner else "")
    crown_html = (f'<svg class="scrown {side}" viewBox="0 0 24 21" fill="url(#crownGrad)" '
                  f'stroke="#ffffff" stroke-width="1" stroke-linejoin="round">'
                  f'<defs><linearGradient id="crownGrad" x1="0" y1="0" x2="0" y2="1">'
                  f'<stop offset="0%" stop-color="#ffe27a"/><stop offset="100%" stop-color="#f2a92e"/>'
                  f'</linearGradient></defs>{_CROWN_PATH}</svg>' if is_winner else "")
    return (
        f'<div class="splayer {side}" style="--pc:{vivid};--pc2:{other};'
        f'--pcg:{_hex_to_rgba(vivid, 0.4)};--tilt:{tilt}">'
        f'<div class="sname-block" style="text-align:{align}">'
        f'<div class="sname">{_esc(p.get("name",""))}</div>'
        f'<div class="sdash"><span class="d1"></span><span class="d2"></span></div>'
        f'<div class="ssub">{_esc(p.get("sub",""))}</div>'
        f'</div>'
        f'<div class="sphoto">{fire_html}<div class="sbackdrop"></div>'
        f'<div class="sframe">{img_html}</div>{logo_badge}{crown_html}</div>'
        f'</div>'
    )


def comparison_scoreboard_poster(
    left: Dict,
    right: Dict,
    metrics: List[Dict],
    title: str = 'HEAD <span class="accent">TO</span> HEAD',
    kicker: str = "PLAYER COMPARISON",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    badge: str = "",
    pattern: Optional[str] = None,
    seed: Optional[str] = None,
    force_winner: Optional[str] = None,
    vivid_bg: bool = False,
) -> str:
    """Bold, saturated head-to-head scoreboard card: team-color canvas
    blooms + a randomized background texture, carved 3D title, glowing
    rounded-rectangle photo frames (colorful team-gradient fill, not bare
    white) with team logo badges, a big radiant VS medallion, and icon+label
    stat rows tinted toward whichever player wins each one -- content runs
    to the bottom edge of the canvas (no verdict bar/footer eating the last
    stretch of the poster). `metrics` is the same shape comparison_poster
    takes: a list of {label, left, right, win} where win is 'L', 'R' or ''.
    `badge`/`subtitle` render as the centered line under the title (badge
    takes priority). `pattern` forces a background texture (see
    BG_PATTERNS); leave it None (the default) for a random one each call, or
    pass `seed` for a reproducible pick -- this is what gives repeated
    head-to-head posts visual variety instead of all looking identical."""
    lvivid, lother = _vivid_pair(left.get("team", ""), accent)
    rvivid, rother = _vivid_pair(right.get("team", ""), accent)
    sub_line = badge or subtitle
    # Approved texture, rotated per seed -- distinct salt per format ('val' vs
    # 'std') so the value and standard head-to-heads don't land on the same
    # texture for a given seed; mesh blobs pick up the two team colours.
    bg_pattern_css = _resolve_skin_css(seed, "val" if vivid_bg else "std", dark=False,
                                       c1=lvivid, c2=rvivid)
    # Two DISTINCT clean canvases (no more muddy full-canvas hue wash): the
    # standard head-to-head reads cool broadcast-gray; the value head-to-head
    # reads a warm ivory "spotlight" so it's instantly a different series.
    if vivid_bg:
        base_bg_css = "linear-gradient(160deg, #f7f2ea 0%, #fffdf9 46%, #f2ebe1 100%)"
    else:
        base_bg_css = "linear-gradient(160deg, #eef1f5 0%, #ffffff 46%, #e8ecf1 100%)"

    l_bloom, r_bloom = _hex_to_rgba(lvivid, 0.16), _hex_to_rgba(rvivid, 0.16)
    l_bord, r_bord = _hex_to_rgba(lvivid, 0.62), _hex_to_rgba(rvivid, 0.62)
    l_style_base = f'--pc:{lvivid};--pc2:{lother};--pcg:{_hex_to_rgba(lvivid, 0.4)}'
    r_style_base = f'--pc:{rvivid};--pc2:{rother};--pcg:{_hex_to_rgba(rvivid, 0.4)}'

    metric_rows = []
    lw = rw = 0
    for m in metrics:
        win = m.get("win", "")
        if win == "L":
            lw += 1
        elif win == "R":
            rw += 1
        rowcls = "srow winL" if win == "L" else ("srow winR" if win == "R" else "srow")
        # Both sides always show their own team color now -- "win" just adds
        # a stronger glow, it no longer decides whether a number gets color.
        lcls = "sval win" if win == "L" else "sval"
        rcls = "sval win" if win == "R" else "sval"
        larw = f'<span class="arw" style="color:{lvivid}">\u25c0</span>' if win == "L" else ""
        rarw = f'<span class="arw" style="color:{rvivid}">\u25b6</span>' if win == "R" else ""
        icon_svg = _scoreboard_icon_svg(m.get("label", ""), accent)

        l_pct, r_pct = _scoreboard_bar_pcts(m.get("left_val"), m.get("right_val"), m.get("lower_is_better", False))
        l_bar = (f'<div class="sbar" style="width:{l_pct}%;'
                 f'background:linear-gradient(to left, {_hex_to_rgba(lvivid, 0.62)}, {_hex_to_rgba(lvivid, 0.16)})">'
                 f'</div>') if l_pct > 0 else ""
        r_bar = (f'<div class="sbar" style="width:{r_pct}%;'
                 f'background:linear-gradient(to right, {_hex_to_rgba(rvivid, 0.62)}, {_hex_to_rgba(rvivid, 0.16)})">'
                 f'</div>') if r_pct > 0 else ""

        metric_rows.append(
            f'<div class="{rowcls}">'
            f'<div class="scell l">{l_bar}<div class="{lcls}" style="{l_style_base}">{_esc(m.get("left",""))}</div></div>'
            f'<div class="smid"><div class="sicon">{icon_svg}</div>'
            f'<div class="slabel">{larw}{_esc(m.get("label",""))}{rarw}</div></div>'
            f'<div class="scell r">{r_bar}<div class="{rcls}" style="{r_style_base}">{_esc(m.get("right",""))}</div></div>'
            f'</div>')
    metric_html = "\n".join(metric_rows)
    if force_winner in ("L", "R"):
        # Some callers (value_carousel) always want the SAME side highlighted
        # as the "winner" (fire aura + crown) regardless of how the metric
        # rows tally -- that's the player being recommended, not whoever
        # happens to win more individual stat rows on this specific card.
        l_is_winner, r_is_winner = force_winner == "L", force_winner == "R"
    else:
        l_is_winner, r_is_winner = lw > rw, rw > lw

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:#0f172a;
    background:
      radial-gradient(900px 620px at 6% -8%, {l_bloom}, transparent 55%),
      radial-gradient(900px 620px at 94% 2%, {r_bloom}, transparent 55%),
      {base_bg_css};
    padding:22px 40px 0px 40px; display:flex; flex-direction:column; position:relative; }}
  .pattern {{ position:absolute; inset:0; pointer-events:none; z-index:1; {bg_pattern_css} }}
  .texture {{ position:absolute; inset:0; pointer-events:none; z-index:1; opacity:0.85;
    background:radial-gradient(140% 100% at 50% 116%, rgba(15,23,42,0.12), transparent 55%); }}
  .grain {{ position:absolute; inset:0; pointer-events:none; z-index:60;
    background-image:{_GRAIN_SVG}; background-size:300px 300px; opacity:0.035; mix-blend-mode:multiply; }}
  .vignette {{ position:absolute; inset:0; pointer-events:none; z-index:55;
    box-shadow:inset 0 0 180px 30px rgba(15,23,42,0.10); }}
  .flagbar, .kickerrow, .title, .subline, .matchup, .metrics {{
    position:relative; z-index:2; }}

  .flagbar {{ position:absolute; top:22px; left:40px; display:flex; gap:5px; z-index:3; }}
  .flagbar span {{ display:block; width:36px; height:10px; border-radius:3px; }}
  .flagbar span:nth-child(1) {{ background:#0f172a; }}
  .flagbar span:nth-child(2) {{ background:{lvivid}; }}
  .flagbar span:nth-child(3) {{ background:{rvivid}; width:22px; }}

  .kickerrow {{ display:flex; align-items:center; justify-content:center; gap:14px; margin-top:12px; }}
  .kickerrow .line {{ height:2px; width:80px; background:linear-gradient(90deg, transparent, {accent}); }}
  .kickerrow .line.r {{ background:linear-gradient(90deg, {accent}, transparent); }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:700; letter-spacing:7px;
    font-size:20px; color:{accent}; text-transform:uppercase; white-space:nowrap; }}

  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
    font-weight:800; font-size:84px; line-height:0.9; text-transform:uppercase;
    letter-spacing:1px; text-align:center; margin-top:2px; color:#0f172a;
    -webkit-text-stroke:1.5px rgba(15,23,42,0.12); paint-order:stroke fill;
    text-shadow:0 2px 0 rgba(15,23,42,0.10), 0 5px 0 rgba(15,23,42,0.06), 0 14px 26px rgba(15,23,42,0.18); }}
  .title .accent {{ color:{accent}; text-shadow:0 2px 0 rgba(15,23,42,0.14), 0 14px 30px {_hex_to_rgba(accent, 0.35)}; }}
  .subline {{ text-align:center; font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:22px;
    letter-spacing:6px; text-transform:uppercase; color:{accent}; margin-top:3px; }}

  .matchup {{ margin-top:14px; position:relative; display:grid; grid-template-columns:1fr 1fr;
    align-items:end; gap:14px; }}
  .splayer {{ position:relative; display:flex; flex-direction:column; gap:10px; }}
  .splayer.l {{ align-items:flex-start; }}
  .splayer.r {{ align-items:flex-end; }}
  .sname-block {{ width:100%; min-height:78px; }}
  .sname {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800;
    font-size:56px; line-height:1.0; color:var(--pc); text-transform:uppercase;
    text-shadow:0 1px 0 rgba(15,23,42,0.18), 0 10px 22px var(--pcg); }}
  .sdash {{ display:flex; gap:4px; margin:9px 0; }}
  .splayer.r .sdash {{ justify-content:flex-end; }}
  .sdash .d1 {{ height:5px; width:56px; border-radius:3px;
    background:linear-gradient(90deg, var(--pc), var(--pc2)); }}
  .splayer.r .sdash .d1 {{ background:linear-gradient(270deg, var(--pc), var(--pc2)); }}
  .sdash .d2 {{ height:5px; width:14px; border-radius:3px; background:rgba(15,23,42,0.16); }}
  .ssub {{ font-size:15px; color:#475569; letter-spacing:1.5px; text-transform:uppercase; font-weight:700; }}
  .sphoto {{ position:relative; width:72%; }}
  .sfire {{ position:absolute; z-index:-1; top:50%; left:50%; width:240%; height:240%;
    transform:translate(-50%,-50%); opacity:0.55; filter:blur(14px); }}
  .sbackdrop {{ position:absolute; inset:-3% -3% -3% -3%; border-radius:30px; z-index:0;
    transform:rotate(var(--tilt)); background:linear-gradient(135deg, var(--pc), var(--pc2));
    box-shadow:0 16px 32px -18px rgba(15,23,42,0.4); }}
  .sframe {{ width:100%; aspect-ratio:1/1; border-radius:28px; overflow:hidden; position:relative; z-index:1;
    background:linear-gradient(135deg, var(--pc), var(--pc2)); border:5px solid var(--pc);
    box-shadow:0 0 50px -10px var(--pc), 0 22px 38px -18px rgba(15,23,42,0.4); }}
  .sshot {{ width:100%; height:100%; object-fit:cover; object-position:center 10%; display:block;
    transform:scale(1.05); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 84%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 84%, transparent 100%); }}
  .sshot.slogo {{ object-fit:contain; padding:50px; transform:none; -webkit-mask-image:none; mask-image:none; }}
  .sshot.sblank {{ width:100%; height:100%; transform:none; -webkit-mask-image:none; mask-image:none; }}
  .sbadge-plate {{ position:absolute; z-index:2; bottom:-14px; right:-14px; width:118px; height:118px;
    border-radius:50%; background:#ffffff; border:4px solid var(--pc);
    display:flex; align-items:center; justify-content:center;
    box-shadow:0 10px 20px -6px rgba(15,23,42,0.4); }}
  .splayer.r .sbadge-plate {{ right:auto; left:-14px; }}
  .sbadge {{ width:80px; height:80px; object-fit:contain; }}

  .scrown {{ position:absolute; z-index:3; top:-22px; width:72px; height:auto;
    filter:drop-shadow(0 6px 10px rgba(15,23,42,0.5)); }}
  .scrown.l {{ left:14%; transform:rotate(-16deg); }}
  .scrown.r {{ right:14%; transform:rotate(16deg); }}

  .vs {{ position:absolute; left:50%; top:310px; transform:translate(-50%,-50%) rotate(-6deg); z-index:5;
    font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:38px;
    color:#0a0f1f; width:112px; height:112px; border-radius:50%;
    background:radial-gradient(circle at 36% 30%, rgba(255,255,255,0.85), transparent 46%), {accent};
    border:5px solid #ffffff; display:flex; align-items:center; justify-content:center;
    box-shadow:0 0 0 6px {_hex_to_rgba(accent, 0.18)}, 0 0 0 8px rgba(15,23,42,0.08),
      0 0 44px -4px {accent}, 0 16px 30px -12px rgba(15,23,42,0.5); }}
  .vs::before {{ content:""; position:absolute; inset:-15px; border-radius:50%;
    border:2px dashed {_hex_to_rgba(accent, 0.35)}; }}

  .metrics {{ margin-top:34px; display:flex; flex-direction:column; gap:14px; flex:1; justify-content:center;
    padding-bottom:22px; }}
  .srow {{ display:grid; grid-template-columns:1fr 150px 1fr; align-items:center;
    background:rgba(255,255,255,0.28); border:4px solid rgba(15,23,42,0.22); border-radius:22px; padding:10px 26px;
    flex:1 1 0; min-height:0; max-height:150px; overflow:hidden;
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.5); }}
  .srow.winL {{ border-color:{l_bord}; background:linear-gradient(90deg, {_hex_to_rgba(lvivid, 0.10)}, rgba(255,255,255,0.28) 55%); }}
  .srow.winR {{ border-color:{r_bord}; background:linear-gradient(270deg, {_hex_to_rgba(rvivid, 0.10)}, rgba(255,255,255,0.28) 55%); }}
  .scell {{ position:relative; height:100%; display:flex; align-items:center; }}
  .scell.l {{ justify-content:flex-start; }}
  .scell.r {{ justify-content:flex-end; }}
  .sbar {{ position:absolute; top:-8px; bottom:-8px; z-index:0; border-radius:999px; }}
  .scell.l .sbar {{ right:0; border-radius:999px 0 0 999px; }}
  .scell.r .sbar {{ left:0; border-radius:0 999px 999px 0; }}
  .sval {{ position:relative; z-index:1; font-family:"Bahnschrift",sans-serif; font-weight:800;
    font-size:56px; color:var(--pc);
    -webkit-text-stroke:2.5px var(--pc2); paint-order:stroke fill;
    text-shadow:0 1px 2px rgba(15,23,42,0.15); }}
  .sval.win {{ text-shadow:0 0 20px var(--pcg), 0 1px 2px rgba(15,23,42,0.15); }}
  .smid {{ display:flex; flex-direction:column; align-items:center; gap:5px; min-height:0; }}
  .sicon {{ width:48px; height:48px; flex:0 0 auto; border-radius:50%;
    background:radial-gradient(circle at 34% 28%, #ffffff, #f1f5f9 70%); border:3px solid {accent};
    display:flex; align-items:center; justify-content:center;
    box-shadow:0 0 0 3px rgba(255,255,255,0.85), 0 6px 14px -8px rgba(15,23,42,0.35); }}
  .sicon svg {{ width:24px; height:24px; }}
  .slabel {{ font-size:11px; font-weight:800; letter-spacing:0.6px; text-transform:uppercase;
    color:#1f2937; text-align:center; line-height:1.15; max-width:146px; white-space:normal;
    word-break:break-word; -webkit-text-stroke:2px rgba(255,255,255,0.9); paint-order:stroke fill;
    display:flex; align-items:center; justify-content:center; gap:4px; flex:0 0 auto; }}
  .arw {{ font-size:11px; line-height:1; -webkit-text-stroke:1.5px rgba(255,255,255,0.9); paint-order:stroke fill; }}
  {_WATERMARK_CSS}
</style></head>
<body>
  <div class="pattern"></div>
  <div class="texture"></div><div class="vignette"></div><div class="grain"></div>
  {_watermark_html()}
  <div class="flagbar"><span></span><span></span><span></span></div>
  <div class="kickerrow"><div class="line"></div><div class="kicker">{_esc(kicker)}</div><div class="line r"></div></div>
  <div class="title">{title}</div>
  {f'<div class="subline">{_esc(sub_line)}</div>' if sub_line else ''}
  <div class="matchup">
    {_scoreboard_side(left, 'l', accent, is_winner=l_is_winner)}
    {_scoreboard_side(right, 'r', accent, is_winner=r_is_winner)}
    <div class="vs">VS</div>
  </div>
  <div class="metrics">
    {metric_html}
  </div>
</body></html>"""


"""
Append everything below to the END of viz/graphics.py (after comparison_poster).
These add two new, structurally distinct layouts alongside ranking_poster's
classic/spotlight silhouettes:

  - tier_board_poster: players grouped into labeled tiers with a divider
    between groups, instead of one continuous numbered list.
  - card_grid_poster: a 2-column grid of player "cards" (bigger photos, more
    visual weight per player) instead of stacked rows.

Both reuse the same theme system (THEMES / resolve_theme / _BG), the same
_FX_CSS/_OVERLAYS finishing effects, and the same team_color/team_secondary/
team_logo_url helpers already imported at the top of graphics.py -- so a
--theme flag colors these exactly like ranking_poster does.
"""


def _bucket_tiers(rows: List[Dict], sizes=(1, 3, 4, 6, 8)) -> List[Dict]:
    """Group a flat, already-ranked rows list into tiers of increasing size
    (a tight #1-only top tier, then progressively looser groups) and label
    them Tier 1, Tier 2, ... This is what turns build_overall/build_position's
    normal `rows` list into the `tiers` shape tier_board_poster expects --
    no change needed to how rows themselves are built."""
    tiers = []
    i = 0
    tier_num = 1
    while i < len(rows):
        size = sizes[min(tier_num - 1, len(sizes) - 1)]
        chunk = rows[i:i + size]
        if not chunk:
            break
        tiers.append({"label": f"Tier {tier_num}", "rows": chunk})
        i += size
        tier_num += 1
    return tiers


def _tier_header_html(label: str, accent: str, count: int) -> str:
    return (
        f'<div class="tier-head" style="--accent:{accent}">'
        f'<div class="tier-label">{_esc(label)}</div>'
        f'<div class="tier-line"></div>'
        f'<div class="tier-count">{count}</div>'
        f'</div>'
    )


def _fit_tiers_to_height(tiers):
    """Return a copy of tiers that fits within the board height."""

    fitted = []
    used = 0

    for tier in tiers:
        new_rows = []

        # Account for tier header
        needed = TIER_HEADER_HEIGHT
        if fitted:
            needed += TIER_BLOCK_GAP

        if used + needed > BOARD_MAX_HEIGHT:
            break

        used += needed

        for row in tier["rows"]:
            row_height = ROW_HEIGHT
            if new_rows:
                row_height += ROW_GAP

            if used + row_height > BOARD_MAX_HEIGHT:
                break

            new_rows.append(row)
            used += row_height

        if new_rows:
            fitted.append({
                "label": tier["label"],
                "rows": new_rows,
            })

        if len(new_rows) < len(tier["rows"]):
            break

    return fitted

def tier_board_poster(
    title: str,
    tiers: List[Dict],
    kicker: str = "2026 REDRAFT \u00b7 HALF-PPR",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    footer: str = "",
    badge: str = "2026",
    background: Optional[str] = None,
    hero_photo: Optional[str] = None,
    hero_team: Optional[str] = None,
) -> str:
    """Players grouped into visual tiers (Tier 1, Tier 2, ...) with a labeled
    divider between groups, instead of one continuous numbered list.
    `tiers` = [{"label": str, "rows": [row dicts, same shape as ranking_poster
    rows]}, ...]. This is a genuinely different read than ranking_poster: the
    eye processes it in chunks (matches how analysts actually talk about
    rankings -- "he's a Tier 2 RB") rather than scanning one long list.
    """

    # Count rows before fitting
    original_rows = sum(len(t["rows"]) for t in tiers)

    # Remove rows that won't fit on the canvas
    tiers = _fit_tiers_to_height(tiers)

    # Count rows after fitting
    visible_rows = sum(len(t["rows"]) for t in tiers)

    # Existing sizing logic now uses only visible rows
    total_rows = visible_rows

    av = 68 if total_rows <= 10 else (58 if total_rows <= 14 else 48)
    rk = round(av * 0.7)
    lg = round(av * 0.46)
    nolg = round(av * 0.72)
    rkf = round(rk * 0.5)
    blocks = []
    for tier in tiers:
        rows_html = "".join(_row_html(r) for r in tier["rows"])
        header = _tier_header_html(tier["label"], accent, len(tier["rows"]))
        blocks.append(f'<div class="tier-block">{header}<div class="tier-rows">{rows_html}</div></div>')
    blocks_html = "\n".join(blocks)

    subtitle_html = f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    bg = background or _BG.format(accent=accent)

    if hero_photo:
        hero_accent = team_color(hero_team) if hero_team else accent
        hero_logo = team_logo_url(hero_team) if hero_team else ""
        hero_logo_html = f'<img class="hlogo" src="{hero_logo}" alt="">' if hero_logo else ""
        header_right = (
            f'<div class="hero" style="--hero-accent:{hero_accent}">'
            f'<img class="hshot" src="{hero_photo}" alt="">{hero_logo_html}'
            f'<div class="yrchip">{_esc(badge)}</div></div>'
        )
    else:
        header_right = f'<div class="badge">{_esc(badge)}</div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{
    font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc; background:{bg};
    padding:44px 50px 30px 50px; display:flex; flex-direction:column; position:relative;
  }}
  {_FX_CSS}
  {_WATERMARK_CSS}
  .topbar, .board, .footer {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:600;
    letter-spacing:4px; font-size:22px; color:{accent}; text-transform:uppercase; }}
  .badge {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px;
    color:#0a0f1f; background:{accent}; border-radius:10px; padding:6px 14px; letter-spacing:2px; }}
  .hero {{ position:relative; flex:0 0 auto; width:150px; height:150px; }}
  .hero::before {{ content:""; position:absolute; inset:-20px; border-radius:50%;
    background:radial-gradient(circle at 50% 42%, var(--hero-accent), transparent 68%);
    filter:blur(16px); opacity:0.6; z-index:0; }}
  .hero .hshot {{ position:relative; z-index:1; width:150px; height:150px; border-radius:50%;
    object-fit:cover; object-position:center 10%; background:#20242c; border:4px solid var(--hero-accent);
    box-shadow:0 0 40px -4px var(--hero-accent), 0 20px 30px -12px rgba(0,0,0,0.85),
      inset 0 0 0 7px var(--hero-accent);
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 80%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 80%, transparent 100%); }}
  .hero .hlogo {{ position:absolute; z-index:2; left:-6px; bottom:2px; width:48px; height:48px;
    object-fit:contain; filter:drop-shadow(0 3px 4px rgba(0,0,0,0.8)); }}
  .hero .yrchip {{ position:absolute; z-index:2; right:-6px; top:2px;
    font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:18px; color:#0a0f1f;
    background:{accent}; border-radius:8px; padding:3px 9px; letter-spacing:1px; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
    font-weight:700; font-size:74px; line-height:0.9; text-transform:uppercase; letter-spacing:1px;
    margin-top:6px; -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
    text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26), 0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:20px; margin-top:6px; text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .board {{ margin-top:16px; display:flex; flex-direction:column; gap:14px; flex:1; overflow:hidden; }}
  .tier-block {{ display:flex; flex-direction:column; gap:6px; }}
  .tier-head {{ display:flex; align-items:center; gap:12px; }}
  .tier-label {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:20px;
    color:var(--accent); letter-spacing:2px; text-transform:uppercase; white-space:nowrap; }}
  .tier-line {{ flex:1; height:2px; background:linear-gradient(90deg, var(--accent), transparent); opacity:0.55; }}
  .tier-count {{ font-family:"Bahnschrift",sans-serif; font-size:14px; color:#8896ad;
    border:1px solid rgba(255,255,255,0.14); border-radius:8px; padding:2px 8px; }}
  .tier-rows {{ display:flex; flex-direction:column; gap:6px; }}
  .row {{ display:flex; align-items:center; gap:14px;
    background:linear-gradient(90deg, var(--team) 0%, var(--team-fade) 34%, rgba(16,18,24,0.5) 60%, rgba(12,13,17,0.24) 100%);
    border:1px solid rgba(255,255,255,0.07); border-left:5px solid var(--edge); border-radius:13px;
    padding:8px 18px; min-height:0;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), inset 0 -10px 16px -14px rgba(0,0,0,0.9),
      0 10px 18px -12px rgba(0,0,0,0.85); }}
  .rank {{ position:relative; flex:0 0 auto; width:{rk}px; height:{rk}px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:700; font-size:{rkf}px;
    color:#e8edf5; background:rgba(255,255,255,0.06); border:2px solid rgba(255,255,255,0.16); }}
  .rank.m1 {{ background:linear-gradient(145deg,#ffe9a8,#f0a91c); color:#3d2800; border:none;
    box-shadow:0 0 18px -2px rgba(245,169,28,0.8); }}
  .rank.m2 {{ background:linear-gradient(145deg,#f4f6f8,#aab2bd); color:#20262e; border:none; }}
  .rank.m3 {{ background:linear-gradient(145deg,#f0b483,#a85a1e); color:#2a1400; border:none; }}
  .delta {{ flex:0 0 auto; min-width:44px; text-align:center; font-family:"Bahnschrift",sans-serif;
    font-weight:700; font-size:16px; padding:3px 6px; border-radius:7px; }}
  .delta.up {{ color:#4ade80; background:rgba(34,197,94,0.16); border:1px solid rgba(34,197,94,0.5); }}
  .delta.down {{ color:#f87171; background:rgba(239,68,68,0.16); border:1px solid rgba(239,68,68,0.5); }}
  .delta.flat {{ color:#8f9db0; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); }}
  .avatar {{ position:relative; flex:0 0 auto; width:{av}px; height:{av}px;
    overflow:hidden; border-radius:50%; }}
  .avatar .shot {{ width:{av}px; height:{av}px; border-radius:50%; object-fit:cover; object-position:center 10%;
    background:#20242c; border:2px solid var(--accent); box-shadow:0 0 12px -3px var(--accent);
    transform:scale(1.12); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%); }}
  .avatar .logo {{ position:absolute; right:-5px; bottom:-3px; width:{lg}px; height:{lg}px; object-fit:contain;
    filter:drop-shadow(0 1px 2px rgba(0,0,0,0.7)); }}
  .avatar.nophoto {{ display:flex; align-items:center; justify-content:center; }}
  .avatar.nophoto .logo {{ position:static; width:{nolg}px; height:{nolg}px; }}
  .meta {{ flex:1; min-width:0; }}
  .name {{ font-size:24px; font-weight:700; letter-spacing:0.2px; line-height:1.05;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-shadow:0 2px 5px rgba(0,0,0,0.7); }}
  .sub {{ font-size:13px; color:#c4cfde; margin-top:1px; letter-spacing:0.6px; line-height:1.1;
    text-transform:uppercase; text-shadow:0 1px 3px rgba(0,0,0,0.7); }}
  .statline {{ font-size:12px; color:{accent}; font-weight:600; margin-top:1px; }}
  .stat {{ text-align:right; min-width:80px; flex:0 0 auto; }}
  .stat-num {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:24px; color:#ffffff;
    text-shadow:0 2px 8px rgba(0,0,0,0.5); }}
  .stat-label {{ font-size:11px; color:#8896ad; letter-spacing:1.2px; text-transform:uppercase; }}
  .footer {{ margin-top:14px; color:#64748b; font-size:15px; letter-spacing:0.5px;
    display:flex; justify-content:space-between; }}
</style></head>
<body>
  {_OVERLAYS}
  {_watermark_html()}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      {subtitle_html}
    </div>
    {header_right}
  </div>
  <div class="board">
    {blocks_html}
  </div>
  <div class="footer"><span>{_esc(footer) if footer else ''}</span><span>data-driven \u00b7 our projections</span></div>
</body></html>"""


def _card_html(row: Dict) -> str:
    team = row.get("team", "")
    override = row.get("accent")
    primary, secondary = team_color(team), team_secondary(team)
    vibrant, other = (secondary, primary) if _chroma(secondary) > _chroma(primary) else (primary, secondary)
    accent = override or vibrant
    logo = team_logo_url(team) if team else ""
    photo = row.get("photo", "")
    if photo:
        img_html = f'<img class="cphoto" src="{photo}" alt="">'
        logo_badge = f'<img class="clogo" src="{logo}" alt="">' if logo else ""
    else:
        img_html = f'<div class="cphoto nophoto"><img class="cbiglogo" src="{logo}" alt=""></div>' if logo else '<div class="cphoto nophoto"></div>'
        logo_badge = ""
    stat_num = row.get("stat_num", "")
    stat_label = row.get("stat_label", "")
    stat_html = ""
    if stat_num != "":
        stat_html = (f'<div class="cstat"><span class="cstat-num">{_esc(stat_num)}</span>'
                     f'<span class="cstat-label">{_esc(stat_label)}</span></div>')
    return f"""
      <div class="card" style="--accent:{accent}">
        <div class="crank">{_esc(row.get('rank', ''))}</div>
        <div class="cphoto-wrap">{img_html}{logo_badge}</div>
        <div class="cname">{_esc(row.get('name', ''))}</div>
        <div class="csub">{_esc(row.get('sub', ''))}</div>
        {stat_html}
      </div>"""


def card_grid_poster(
    title: str,
    rows: List[Dict],
    columns: int = 2,
    kicker: str = "2026 REDRAFT \u00b7 HALF-PPR",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    footer: str = "",
    badge: str = "2026",
    background: Optional[str] = None,
) -> str:
    """A grid of player "cards" instead of stacked rows -- bigger photos, more
    visual weight per player. Best for shorter lists (6-10 players); a 2D grid
    silhouette reads completely differently from ranking_poster's vertical list
    or tier_board_poster's grouped blocks."""
    cards_html = "\n".join(_card_html(r) for r in rows)
    subtitle_html = f'<div class="subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    bg = background or _BG.format(accent=accent)

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc; background:{bg};
    padding:44px 50px 34px 50px; display:flex; flex-direction:column; position:relative; }}
  {_FX_CSS}
  {_WATERMARK_CSS}
  .topbar, .grid, .footer {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:600;
    letter-spacing:4px; font-size:22px; color:{accent}; text-transform:uppercase; }}
  .badge {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px; color:#0a0f1f;
    background:{accent}; border-radius:10px; padding:6px 14px; letter-spacing:2px; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
    font-weight:700; font-size:78px; line-height:0.9; text-transform:uppercase; letter-spacing:1px;
    margin-top:6px; -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
    text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26), 0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:20px; margin-top:6px; text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .grid {{ margin-top:22px; flex:1; display:grid; grid-template-columns:repeat({columns}, 1fr);
    gap:18px; align-content:center; }}
  .card {{ position:relative; display:flex; flex-direction:column; align-items:center; text-align:center;
    background:linear-gradient(160deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
    border:1px solid rgba(255,255,255,0.08); border-top:5px solid var(--accent); border-radius:20px;
    padding:22px 16px 18px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.08), 0 16px 30px -16px rgba(0,0,0,0.9); }}
  .crank {{ position:absolute; top:12px; left:14px; font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif;
    font-weight:700; font-size:22px; color:var(--accent); }}
  .cphoto-wrap {{ position:relative; width:132px; height:132px; margin-top:6px;
    overflow:hidden; border-radius:18px; }}
  .cphoto {{ width:132px; height:132px; border-radius:18px; object-fit:cover; object-position:center 10%;
    background:#20242c; border:3px solid var(--accent);
    box-shadow:0 0 20px -4px var(--accent), 0 12px 20px -10px rgba(0,0,0,0.85);
    transform:scale(1.12); transform-origin:center;
    -webkit-mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 40%, #000 82%, transparent 100%); }}
  .cphoto.nophoto {{ display:flex; align-items:center; justify-content:center; }}
  .cbiglogo {{ width:88px; height:88px; object-fit:contain; }}
  .clogo {{ position:absolute; right:-8px; bottom:-8px; width:44px; height:44px; object-fit:contain;
    filter:drop-shadow(0 2px 4px rgba(0,0,0,0.8)); }}
  .cname {{ font-size:24px; font-weight:700; margin-top:12px; line-height:1.05;
    text-shadow:0 2px 5px rgba(0,0,0,0.7); }}
  .csub {{ font-size:13px; color:#c4cfde; margin-top:3px; letter-spacing:0.8px; text-transform:uppercase; }}
  .cstat {{ margin-top:10px; display:flex; flex-direction:column; align-items:center; }}
  .cstat-num {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:30px; color:#fff;
    text-shadow:0 2px 8px rgba(0,0,0,0.5); }}
  .cstat-label {{ font-size:11px; color:#8896ad; letter-spacing:1.4px; text-transform:uppercase; }}
  .footer {{ margin-top:18px; color:#64748b; font-size:15px; display:flex; justify-content:space-between; }}
</style></head>
<body>
  {_OVERLAYS}
  {_watermark_html()}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      {subtitle_html}
    </div>
    <div class="badge">{_esc(badge)}</div>
  </div>
  <div class="grid">
    {cards_html}
  </div>
  <div class="footer"><span>{_esc(footer) if footer else ''}</span><span>data-driven \u00b7 our projections</span></div>
</body></html>"""


# =============================================================================
# ALTERNATIVE HEAD-TO-HEAD STYLE: "slate"
# A premium DARK card (borrowing the clean, modern language of
# value_targets_poster, which the client liked): dark canvas + generated
# organic texture, big circular team-ringed headshots, condensed white names,
# a slim VS, and a clean stat ledger -- each stat is one row with the label
# centered between two large team-colored numbers over a thin two-sided bar.
# Takes the SAME (left, right, metrics, ...) inputs as
# comparison_scoreboard_poster so it is a drop-in alternative; the current
# scoreboard card is left completely untouched.
# =============================================================================

def _slate_side(p: Dict, side: str, accent: str, is_winner: bool = False) -> str:
    team = p.get("team", "")
    vivid, other = _vivid_pair(team, accent)
    logo = team_logo_url(team) if team else ""
    photo = p.get("photo", "")
    align = "left" if side == "l" else "right"
    if photo:
        img_html = f'<img class="qshot" src="{photo}" alt="">'
    else:
        img_html = f'<img class="qshot qlogo" src="{logo}" alt="">' if logo else '<div class="qshot qblank"></div>'
    logo_badge = f'<div class="qbadge"><img src="{logo}" alt=""></div>' if (logo and photo) else ""
    crown = (f'<svg class="qcrown" viewBox="0 0 24 21" fill="url(#cg)" stroke="#fff" stroke-width="1" '
             f'stroke-linejoin="round"><defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0%" stop-color="#ffe27a"/><stop offset="100%" stop-color="#f2a92e"/>'
             f'</linearGradient></defs>{_CROWN_PATH}</svg>' if is_winner else "")
    return (
        f'<div class="qplayer {side}" style="--pc:{vivid};--pc2:{other};--pcg:{_hex_to_rgba(vivid, 0.5)}">'
        f'<div class="qphoto">{crown}<div class="qring"></div>{img_html}{logo_badge}</div>'
        f'<div class="qname" style="text-align:{align}">{_esc(p.get("name",""))}</div>'
        f'<div class="qsub" style="text-align:{align}">{_esc(p.get("sub",""))}</div>'
        f'</div>'
    )


def comparison_slate_poster(
    left: Dict,
    right: Dict,
    metrics: List[Dict],
    title: str = 'HEAD <span class="accent">TO</span> HEAD',
    kicker: str = "PLAYER COMPARISON",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    badge: str = "",
    pattern: Optional[str] = None,
    seed: Optional[str] = None,
    force_winner: Optional[str] = None,
    vivid_bg: bool = False,
) -> str:
    """Dark 'slate' alternative to comparison_scoreboard_poster (same inputs)."""
    lvivid, lother = _vivid_pair(left.get("team", ""), accent)
    rvivid, rother = _vivid_pair(right.get("team", ""), accent)
    sub_line = badge or subtitle
    skin = _resolve_skin_css(seed, "slate", dark=True, c1=lvivid, c2=rvivid)
    bg = _BG.format(accent=accent)

    rows = []
    lw = rw = 0
    for m in metrics:
        win = m.get("win", "")
        if win == "L":
            lw += 1
        elif win == "R":
            rw += 1
        lcls = "qval win" if win == "L" else "qval"
        rcls = "qval win" if win == "R" else "qval"
        icon = _scoreboard_icon_svg(m.get("label", ""), accent)
        # cap bar length so the bars stay in the central region of each side
        # (anchored toward the middle) rather than stretching to the far edges
        l_pct, r_pct = _scoreboard_bar_pcts(m.get("left_val"), m.get("right_val"),
                                            m.get("lower_is_better", False), max_pct=58.0)
        l_bar = (f'<span class="qbar l" style="width:{l_pct}%;background:linear-gradient(to left,'
                 f'{_hex_to_rgba(lvivid, 0.9)},{_hex_to_rgba(lvivid, 0.2)})"></span>') if l_pct > 0 else ""
        r_bar = (f'<span class="qbar r" style="width:{r_pct}%;background:linear-gradient(to right,'
                 f'{_hex_to_rgba(rvivid, 0.9)},{_hex_to_rgba(rvivid, 0.2)})"></span>') if r_pct > 0 else ""
        rows.append(
            f'<div class="qrow">'
            f'<div class="qside l">{l_bar}<span class="{lcls}" style="color:{lvivid}">{_esc(m.get("left",""))}</span></div>'
            f'<div class="qmid"><span class="qicon">{icon}</span>'
            f'<span class="qlabel">{_esc(m.get("label",""))}</span></div>'
            f'<div class="qside r">{r_bar}<span class="{rcls}" style="color:{rvivid}">{_esc(m.get("right",""))}</span></div>'
            f'</div>'
        )
    rows_html = "\n".join(rows)
    if force_winner in ("L", "R"):
        l_is_winner, r_is_winner = force_winner == "L", force_winner == "R"
    else:
        l_is_winner, r_is_winner = lw > rw, rw > lw

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc; background:{bg};
    padding:44px 52px 30px 52px; display:flex; flex-direction:column; position:relative; }}
  .pattern {{ position:absolute; inset:0; pointer-events:none; z-index:1; {skin} }}
  .floor {{ position:absolute; inset:0; pointer-events:none; z-index:1;
    background:radial-gradient(150% 80% at 50% 120%, rgba(0,0,0,0.42), transparent 60%); }}
  {_WATERMARK_CSS}
  .top, .matchup, .ledger {{ position:relative; z-index:2; }}
  .top {{ text-align:center; }}
  .krow {{ display:flex; align-items:center; justify-content:center; gap:14px; }}
  .krow .ln {{ height:2px; width:74px; background:linear-gradient(90deg, transparent, {accent}); }}
  .krow .ln.r {{ background:linear-gradient(90deg, {accent}, transparent); }}
  .kicker {{ font-family:"Bahnschrift",sans-serif; font-weight:700; letter-spacing:7px; font-size:19px;
    color:{accent}; text-transform:uppercase; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:86px;
    line-height:0.92; text-transform:uppercase; letter-spacing:1px; margin-top:4px; color:#f8fafc;
    text-shadow:0 3px 0 rgba(0,0,0,0.35), 0 16px 30px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; text-shadow:0 0 34px {_hex_to_rgba(accent, 0.5)}; }}
  .subline {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:20px; letter-spacing:6px;
    text-transform:uppercase; color:{accent}; margin-top:4px; }}

  .matchup {{ margin-top:26px; display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:12px; }}
  .qplayer {{ display:flex; flex-direction:column; align-items:center; gap:12px; }}
  .qphoto {{ position:relative; width:190px; height:190px; }}
  .qring {{ position:absolute; inset:-9px; border-radius:50%;
    background:conic-gradient(from 210deg, var(--pc), var(--pc2), var(--pc));
    filter:drop-shadow(0 0 22px var(--pcg)); }}
  .qshot {{ position:relative; z-index:1; width:190px; height:190px; border-radius:50%; object-fit:cover;
    object-position:center 12%; background:#0f1218; border:6px solid #0f1218;
    box-shadow:0 18px 34px -16px rgba(0,0,0,0.9);
    -webkit-mask-image:radial-gradient(circle at 50% 42%, #000 78%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 42%, #000 78%, transparent 100%); }}
  .qshot.qlogo {{ object-fit:contain; padding:44px; -webkit-mask-image:none; mask-image:none; }}
  .qshot.qblank {{ -webkit-mask-image:none; mask-image:none; }}
  .qbadge {{ position:absolute; z-index:2; right:2px; bottom:2px; width:60px; height:60px; border-radius:50%;
    background:#fff; display:flex; align-items:center; justify-content:center;
    box-shadow:0 8px 18px -6px rgba(0,0,0,0.7); }}
  .qbadge img {{ width:42px; height:42px; object-fit:contain; }}
  .qcrown {{ position:absolute; z-index:3; top:-26px; left:50%; transform:translateX(-50%) rotate(-6deg);
    width:66px; filter:drop-shadow(0 6px 10px rgba(0,0,0,0.6)); }}
  .qname {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:46px;
    line-height:0.98; text-transform:uppercase; color:#f8fafc; width:100%;
    text-shadow:0 2px 10px rgba(0,0,0,0.6); }}
  .qsub {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:16px; letter-spacing:2px;
    text-transform:uppercase; color:#93a2bd; width:100%; }}
  .qvs {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:34px;
    color:#0a0f1f; width:96px; height:96px; border-radius:50%; display:flex; align-items:center;
    justify-content:center; background:radial-gradient(circle at 36% 30%, #fff, {accent} 70%);
    box-shadow:0 0 0 6px {_hex_to_rgba(accent, 0.16)}, 0 0 40px -4px {accent}; }}

  .ledger {{ margin-top:30px; display:flex; flex-direction:column; gap:14px; flex:1; justify-content:center; }}
  .qrow {{ display:grid; grid-template-columns:1fr 210px 1fr; align-items:center;
    background:rgba(255,255,255,0.045); border:1px solid rgba(255,255,255,0.09); border-radius:18px;
    padding:12px 26px; flex:1 1 0; min-height:0; max-height:150px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,0.06); }}
  .qside {{ position:relative; height:100%; display:flex; align-items:center; }}
  .qside.l {{ justify-content:flex-start; }}
  .qside.r {{ justify-content:flex-end; }}
  .qbar {{ position:absolute; top:50%; transform:translateY(-50%); height:82%; z-index:0; border-radius:14px; opacity:0.7; }}
  .qbar.l {{ right:0; border-radius:14px 0 0 14px; }}
  .qbar.r {{ left:0; border-radius:0 14px 14px 0; }}
  .qval {{ position:relative; z-index:1; font-family:"Bahnschrift",sans-serif; font-weight:800; font-size:60px;
    text-shadow:0 2px 10px rgba(0,0,0,0.6); }}
  .qval.win {{ text-shadow:0 0 22px var(--pcg), 0 2px 10px rgba(0,0,0,0.6); }}
  .qmid {{ display:flex; flex-direction:column; align-items:center; gap:7px; }}
  .qicon {{ width:56px; height:56px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:radial-gradient(circle at 34% 28%, #2a2e39, #171a21 70%); border:2px solid {accent};
    box-shadow:0 0 18px -4px {_hex_to_rgba(accent, 0.6)}; }}
  .qicon svg {{ width:28px; height:28px; }} .qicon svg * {{ stroke:{accent}; }}
  .qlabel {{ font-size:12px; font-weight:800; letter-spacing:1px; text-transform:uppercase; color:#c3cfe2;
    text-align:center; line-height:1.15; max-width:200px; }}
</style></head>
<body>
  <div class="pattern"></div><div class="floor"></div>
  {_watermark_html()}
  <div class="top">
    <div class="krow"><span class="ln"></span><span class="kicker">{_esc(kicker)}</span><span class="ln r"></span></div>
    <div class="title">{title}</div>
    {f'<div class="subline">{_esc(sub_line)}</div>' if sub_line else ''}
  </div>
  <div class="matchup">
    {_slate_side(left, 'l', accent, is_winner=l_is_winner)}
    <div class="qvs">VS</div>
    {_slate_side(right, 'r', accent, is_winner=r_is_winner)}
  </div>
  <div class="ledger">
    {rows_html}
  </div>
</body></html>"""


# =============================================================================
# ALTERNATIVE HEAD-TO-HEAD STYLE: "stack" (tug-of-war infographic)
# Each metric is a full-width lane: the two values flank a single split bar
# whose meeting point shows who leads and by how much (a tug-of-war). Reads as
# a clean modern infographic -- structurally different from the scoreboard's
# icon rows, the slate's ledger, and the arena's split. Comes in dark and
# light so it doubles as two distinct looks. Same inputs as the other
# comparison_* posters.
# =============================================================================

def _tug_shares(lv, rv, lower: bool) -> tuple:
    if lv is None or rv is None:
        return (50.0, 50.0)
    a, b = float(lv), float(rv)
    if lower:  # smaller-is-better -> invert so the better side pulls harder
        a = (1.0 / a) if a else 0.0
        b = (1.0 / b) if b else 0.0
    t = a + b
    if t <= 0:
        return (50.0, 50.0)
    la = max(10.0, min(90.0, 100.0 * a / t))  # keep a visible sliver either way
    return (round(la, 1), round(100.0 - la, 1))


def _stack_player(p: Dict, side: str, accent: str, is_winner: bool = False) -> str:
    team = p.get("team", "")
    vivid, other = _vivid_pair(team, accent)
    logo = team_logo_url(team) if team else ""
    photo = p.get("photo", "")
    align = "flex-start" if side == "l" else "flex-end"
    talign = "left" if side == "l" else "right"
    if photo:
        img = f'<img class="kshot" src="{photo}" alt="">'
    else:
        img = f'<img class="kshot klogo" src="{logo}" alt="">' if logo else '<div class="kshot kblank"></div>'
    badge = f'<div class="kbadge"><img src="{logo}" alt=""></div>' if (logo and photo) else ""
    crown = (f'<svg class="kcrown" viewBox="0 0 24 21" fill="#f2b834" stroke="#fff" stroke-width="1" '
             f'stroke-linejoin="round">{_CROWN_PATH}</svg>' if is_winner else "")
    return (
        f'<div class="kplayer" style="--pc:{vivid};--pc2:{other};--pcg:{_hex_to_rgba(vivid, 0.5)};'
        f'align-items:{align};text-align:{talign}">'
        f'<div class="kphoto">{crown}<div class="kring"></div>{img}{badge}</div>'
        f'<div class="kname">{_esc(p.get("name",""))}</div>'
        f'<div class="ksub">{_esc(p.get("sub",""))}</div>'
        f'</div>'
    )


def comparison_stack_poster(
    left: Dict,
    right: Dict,
    metrics: List[Dict],
    title: str = 'HEAD <span class="accent">TO</span> HEAD',
    kicker: str = "PLAYER COMPARISON",
    subtitle: str = "",
    accent: str = BRAND_ACCENT,
    badge: str = "",
    pattern: Optional[str] = None,
    seed: Optional[str] = None,
    force_winner: Optional[str] = None,
    vivid_bg: bool = False,
    light: bool = False,
) -> str:
    lvivid, lother = _vivid_pair(left.get("team", ""), accent)
    rvivid, rother = _vivid_pair(right.get("team", ""), accent)
    sub_line = badge or subtitle
    dark = not light
    skin = _resolve_skin_css(seed, "stack" + ("L" if light else "D"), dark=dark, c1=lvivid, c2=rvivid)
    if light:
        canvas = "linear-gradient(160deg,#eef1f5 0%,#ffffff 46%,#e8ecf1 100%)"
        ink, ink2, lab = "#0f172a", "#5b6a82", "#334155"
        track = "rgba(15,23,42,0.09)"
        rowbg = "rgba(255,255,255,0.55)"; rowbd = "rgba(15,23,42,0.10)"
        floor = "radial-gradient(140% 100% at 50% 116%, rgba(15,23,42,0.10), transparent 55%)"
    else:
        canvas = _BG.format(accent=accent)
        ink, ink2, lab = "#f8fafc", "#93a2bd", "#c3cfe2"
        track = "rgba(255,255,255,0.10)"
        rowbg = "rgba(255,255,255,0.045)"; rowbd = "rgba(255,255,255,0.09)"
        floor = "radial-gradient(150% 85% at 50% 120%, rgba(0,0,0,0.42), transparent 60%)"

    l_bloom, r_bloom = _hex_to_rgba(lvivid, 0.16), _hex_to_rgba(rvivid, 0.16)

    lw = rw = 0
    body_rows = []
    for m in metrics:
        win = m.get("win", "")
        if win == "L":
            lw += 1
        elif win == "R":
            rw += 1
        ls, rs = _tug_shares(m.get("left_val"), m.get("right_val"), m.get("lower_is_better", False))
        lcls = "kval win" if win == "L" else "kval"
        rcls = "kval win" if win == "R" else "kval"
        icon = _scoreboard_icon_svg(m.get("label", ""), accent)
        body_rows.append(
            f'<div class="krow">'
            f'<div class="{lcls}" style="color:{lvivid}">{_esc(m.get("left",""))}</div>'
            f'<div class="ktug">'
            f'<div class="klabelrow"><span class="kicon">{icon}</span>'
            f'<span class="klabel">{_esc(m.get("label",""))}</span></div>'
            f'<div class="ktrack">'
            f'<span class="kfill l" style="width:{ls}%;background:linear-gradient(90deg,{_hex_to_rgba(lvivid,0.35)},{lvivid})"></span>'
            f'<span class="kfill r" style="width:{rs}%;background:linear-gradient(90deg,{rvivid},{_hex_to_rgba(rvivid,0.35)})"></span>'
            f'<span class="kseam" style="left:{ls}%"></span>'
            f'</div></div>'
            f'<div class="{rcls}" style="color:{rvivid}">{_esc(m.get("right",""))}</div>'
            f'</div>'
        )
    rows_html = "\n".join(body_rows)
    if force_winner in ("L", "R"):
        l_is_winner, r_is_winner = force_winner == "L", force_winner == "R"
    else:
        l_is_winner, r_is_winner = lw > rw, rw > lw

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:{ink};
    background:radial-gradient(900px 620px at 6% -8%, {l_bloom}, transparent 55%),
      radial-gradient(900px 620px at 94% 2%, {r_bloom}, transparent 55%), {canvas};
    padding:44px 54px 34px 54px; display:flex; flex-direction:column; position:relative; }}
  .pattern {{ position:absolute; inset:0; pointer-events:none; z-index:1; {skin} }}
  .floor {{ position:absolute; inset:0; pointer-events:none; z-index:1; background:{floor}; }}
  {_WATERMARK_CSS}
  .top, .duo, .lanes {{ position:relative; z-index:2; }}
  .top {{ text-align:center; }}
  .krow2 {{ display:flex; align-items:center; justify-content:center; gap:14px; }}
  .krow2 .ln {{ height:2px; width:74px; background:linear-gradient(90deg, transparent, {accent}); }}
  .krow2 .ln.r {{ background:linear-gradient(90deg, {accent}, transparent); }}
  .kicker {{ font-family:"Bahnschrift",sans-serif; font-weight:700; letter-spacing:7px; font-size:19px;
    color:{accent}; text-transform:uppercase; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:82px;
    line-height:0.92; text-transform:uppercase; letter-spacing:1px; margin-top:4px; color:{ink}; }}
  .title .accent {{ color:{accent}; }}
  .subline {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:20px; letter-spacing:6px;
    text-transform:uppercase; color:{accent}; margin-top:4px; }}

  .duo {{ margin-top:22px; display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:14px; }}
  .kplayer {{ display:flex; flex-direction:column; gap:10px; }}
  .kphoto {{ position:relative; width:150px; height:150px; }}
  .kring {{ position:absolute; inset:-8px; border-radius:50%;
    background:conic-gradient(from 210deg, var(--pc), var(--pc2), var(--pc)); filter:drop-shadow(0 0 18px var(--pcg)); }}
  .kshot {{ position:relative; z-index:1; width:150px; height:150px; border-radius:50%; object-fit:cover;
    object-position:center 12%; background:#0f1218; border:5px solid #0f1218;
    -webkit-mask-image:radial-gradient(circle at 50% 42%, #000 78%, transparent 100%);
    mask-image:radial-gradient(circle at 50% 42%, #000 78%, transparent 100%); }}
  .kshot.klogo {{ object-fit:contain; padding:34px; -webkit-mask-image:none; mask-image:none; }}
  .kbadge {{ position:absolute; z-index:2; right:0; bottom:0; width:52px; height:52px; border-radius:50%;
    background:#fff; display:flex; align-items:center; justify-content:center; box-shadow:0 6px 14px -5px rgba(0,0,0,0.7); }}
  .kbadge img {{ width:36px; height:36px; object-fit:contain; }}
  .kcrown {{ position:absolute; z-index:3; top:-22px; left:50%; transform:translateX(-50%) rotate(-6deg); width:56px;
    filter:drop-shadow(0 5px 8px rgba(0,0,0,0.5)); }}
  .kname {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:40px;
    line-height:0.98; text-transform:uppercase; color:{ink}; width:100%; }}
  .ksub {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:15px; letter-spacing:2px;
    text-transform:uppercase; color:{ink2}; width:100%; }}
  .kvs {{ font-family:"Bahnschrift Condensed","Bahnschrift",sans-serif; font-weight:800; font-size:30px;
    color:#0a0f1f; width:84px; height:84px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:radial-gradient(circle at 36% 30%, #fff, {accent} 70%); box-shadow:0 0 34px -4px {accent}; }}

  .lanes {{ margin-top:26px; display:flex; flex-direction:column; gap:14px; flex:1; justify-content:center; }}
  .krow {{ display:grid; grid-template-columns:150px 1fr 150px; align-items:center; gap:20px;
    background:{rowbg}; border:1px solid {rowbd}; border-radius:16px; padding:14px 26px;
    flex:1 1 0; min-height:0; max-height:150px; }}
  .kval {{ font-family:"Bahnschrift",sans-serif; font-weight:800; font-size:52px; }}
  .krow > .kval:first-child {{ text-align:left; }}
  .krow > .kval:last-child {{ text-align:right; }}
  .kval.win {{ font-size:62px; }}
  .ktug {{ display:flex; flex-direction:column; align-items:center; gap:10px; }}
  .klabelrow {{ display:flex; align-items:center; gap:9px; }}
  .kicon {{ width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center;
    background:{"rgba(255,255,255,0.9)" if light else "rgba(255,255,255,0.10)"}; border:2px solid {accent}; }}
  .kicon svg {{ width:18px; height:18px; }} .kicon svg * {{ stroke:{accent}; }}
  .klabel {{ font-size:13px; font-weight:800; letter-spacing:1.4px; text-transform:uppercase; color:{lab}; }}
  .ktrack {{ position:relative; width:100%; height:18px; border-radius:999px; background:{track}; overflow:hidden;
    box-shadow:inset 0 1px 2px rgba(0,0,0,0.25); }}
  .kfill {{ position:absolute; top:0; height:100%; }}
  .kfill.l {{ left:0; }} .kfill.r {{ right:0; }}
  .kseam {{ position:absolute; top:-3px; bottom:-3px; width:4px; transform:translateX(-2px);
    background:{ink}; border-radius:2px; box-shadow:0 0 6px rgba(0,0,0,0.4); z-index:2; }}
</style></head>
<body>
  <div class="pattern"></div><div class="floor"></div>
  {_watermark_html()}
  <div class="top">
    <div class="krow2"><span class="ln"></span><span class="kicker">{_esc(kicker)}</span><span class="ln r"></span></div>
    <div class="title">{title}</div>
    {f'<div class="subline">{_esc(sub_line)}</div>' if sub_line else ''}
  </div>
  <div class="duo">
    {_stack_player(left, 'l', accent, is_winner=l_is_winner)}
    <div class="kvs">VS</div>
    {_stack_player(right, 'r', accent, is_winner=r_is_winner)}
  </div>
  <div class="lanes">
    {rows_html}
  </div>
</body></html>"""
