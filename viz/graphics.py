"""HTML/CSS builders for the ranking graphics.

Everything here returns a full HTML document string sized to an exact canvas
(default 1080x1350, a 4:5 portrait that fits Instagram/X). viz/render.py turns
that into a PNG. Keeping the graphics as HTML/CSS (not a generative image
model) is deliberate: player names, ranks and stats render pixel-perfect every
time, which diffusion image models cannot do.

Fonts are Windows built-ins (Bahnschrift is a condensed, sporty DIN-style face
that ships with Windows 10/11) so there's no web-font network dependency.
"""

import hashlib as _hashlib
import html as _html
import random as _random
from typing import List, Dict, Optional

from viz.teams import team_color, team_secondary, team_logo_url

CANVAS_W = 1080
CANVAS_H = 1350

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
    # faint crosshatch weave sitting just BEHIND the content (z-index 1) to add
    # texture to the lifted background without muddying the rows
    ".texture{position:absolute;inset:0;pointer-events:none;z-index:1;opacity:0.75;"
    "background-image:repeating-linear-gradient(135deg, rgba(255,255,255,0.032) 0 1px, transparent 1px 26px),"
    "repeating-linear-gradient(45deg, rgba(255,255,255,0.020) 0 1px, transparent 1px 26px);}"
    ".grain{position:absolute;inset:0;pointer-events:none;z-index:60;"
    f"background-image:{_GRAIN_SVG};background-size:300px 300px;"
    "opacity:0.05;mix-blend-mode:overlay;}"
    ".vignette{position:absolute;inset:0;pointer-events:none;z-index:55;"
    "background:radial-gradient(130% 95% at 50% 34%, transparent 55%, rgba(0,0,0,0.42) 100%);"
    "box-shadow:inset 0 0 160px 40px rgba(0,0,0,0.38);}"
)
_OVERLAYS = '<div class="texture"></div><div class="vignette"></div><div class="grain"></div>'

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


def _value_row_html(row: Dict) -> str:
    """row keys: value_name, value_team, value_sub, statline, vs_text, win_badge, adp_badge."""
    team = row.get("value_team", "")
    accent = team_color(team)
    logo = team_logo_url(team) if team else ""
    logo_html = f'<img class="logo" src="{logo}" alt="">' if logo else ""
    statline = row.get("statline", "")
    statline_html = f'<div class="vstat">{_esc(statline)}</div>' if statline else ""
    return f"""
      <div class="vrow" style="--accent:{accent}">
        {logo_html}
        <div class="vmeta">
          <div class="vname">{_esc(row.get('value_name',''))}</div>
          <div class="vsub">{_esc(row.get('value_sub',''))}</div>
          {statline_html}
          <div class="vs">{_esc(row.get('vs_text',''))}</div>
        </div>
        <div class="badges">
          <div class="badge win">{_esc(row.get('win_badge',''))}</div>
          <div class="badge adp">{_esc(row.get('adp_badge',''))}</div>
        </div>
      </div>"""


def value_targets_poster(
    rows: List[Dict],
    title: str = 'Market <span class="accent">Value Targets</span>',
    kicker: str = "2026 REDRAFT \u00b7 MARKET GAPS",
    subtitle: str = "Similar projection \u00b7 cheaper ADP \u00b7 better team",
    accent: str = BRAND_ACCENT,
    footer: str = "",
    badge: str = "2026",
) -> str:
    rows_html = "\n".join(_value_row_html(r) for r in rows)
    footer_html = _esc(footer) if footer else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{
    font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc;
    background:{_BG.format(accent=accent)};
    padding:48px 52px 34px 52px; display:flex; flex-direction:column;
    position:relative;
  }}
  {_FX_CSS}
  .topbar, .list, .footer {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .kicker {{ font-family:"Bahnschrift","Segoe UI",sans-serif; font-weight:600;
             letter-spacing:4px; font-size:22px; color:{accent}; text-transform:uppercase; }}
  .badge-yr {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:26px;
               color:#0a0f1f; background:{accent}; border-radius:10px; padding:6px 14px;
               letter-spacing:2px; }}
  .title {{ font-family:"Bahnschrift Condensed","Bahnschrift","Arial Narrow",sans-serif;
            font-weight:700; font-size:82px; line-height:0.92; text-transform:uppercase;
            letter-spacing:1px; margin-top:6px;
            -webkit-text-stroke:1.5px rgba(0,0,0,0.38); paint-order:stroke fill;
            text-shadow:0 1px 0 rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.26),
              0 5px 0 rgba(0,0,0,0.16), 0 10px 20px rgba(0,0,0,0.6); }}
  .title .accent {{ color:{accent}; }}
  .subtitle {{ color:#94a3b8; font-size:21px; margin-top:6px; text-shadow:0 1px 3px rgba(0,0,0,0.6); }}
  .list {{ margin-top:22px; display:flex; flex-direction:column; gap:10px;
           flex:1; justify-content:center; }}
  .vrow {{ display:flex; align-items:center; gap:18px;
    background:linear-gradient(90deg, rgba(255,255,255,0.09), rgba(255,255,255,0.03));
    border-left:7px solid var(--accent); border-radius:14px; padding:0 22px;
    flex:1 1 0; min-height:0; max-height:150px; overflow:hidden; }}
  .logo {{ width:52px; height:52px; object-fit:contain; flex:0 0 auto; }}
  .vmeta {{ flex:1; min-width:0; }}
  .vname {{ font-size:32px; font-weight:700; white-space:nowrap; overflow:hidden;
            text-overflow:ellipsis; }}
  .vsub {{ font-size:16px; color:#93a4bd; letter-spacing:1px; text-transform:uppercase;
           margin-top:1px; }}
  .vstat {{ font-size:17px; color:{accent}; font-weight:600; margin-top:4px;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .vs {{ font-size:17px; color:#cbd5e1; margin-top:3px; }}
  .vs::before {{ content:"vs "; color:#93a4bd; font-weight:700; }}
  .badges {{ display:flex; flex-direction:column; gap:8px; flex:0 0 auto; align-items:flex-end; }}
  .badge {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:24px;
            padding:6px 14px; border-radius:10px; min-width:132px; text-align:center; }}
  .badge.win {{ background:rgba(34,197,94,0.16); color:#4ade80; border:1px solid rgba(34,197,94,0.45); }}
  .badge.adp {{ background:rgba(56,189,248,0.16); color:#38bdf8; border:1px solid rgba(56,189,248,0.45); }}
  .footer {{ margin-top:18px; color:#64748b; font-size:15px;
             display:flex; justify-content:space-between; }}
</style></head>
<body>
  {_OVERLAYS}
  <div class="topbar">
    <div>
      <div class="kicker">{_esc(kicker)}</div>
      <div class="title">{title}</div>
      <div class="subtitle">{_esc(subtitle)}</div>
    </div>
    <div class="badge-yr">{_esc(badge)}</div>
  </div>
  <div class="list">
    {rows_html}
  </div>
  <div class="footer"><span>{footer_html}</span><span>data-driven \u00b7 our projections</span></div>
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
      inset 0 0 0 2px rgba(255,255,255,0.10); }}
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
  .avatar {{ position:relative; flex:0 0 auto; width:{av}px; height:{av}px; }}
  .avatar .shot {{ width:{av}px; height:{av}px; border-radius:50%; object-fit:cover;
    object-position:center 10%; background:#20242c;
    border:3px solid var(--accent);
    box-shadow:0 0 16px -3px var(--accent), 0 10px 16px -8px rgba(0,0,0,0.85); }}
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
  body.spot .avatar .shot {{ border-radius:15px; }}
  body.spot .avatar .logo {{ right:-7px; bottom:-6px; }}
  body.spot .name {{ letter-spacing:0.6px; }}
  body.spot .stat-num {{ color:var(--accent-l); text-shadow:0 0 18px var(--accent), 0 2px 6px rgba(0,0,0,0.6); }}
</style></head>
<body class="{body_class}">
  {_OVERLAYS}
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
        shot = f'<div class="cshot-wrap"><img class="cshot" src="{photo}" alt="">{logo_html}</div>'
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

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; overflow:hidden; }}
  body {{ font-family:"Segoe UI", Arial, sans-serif; color:#f8fafc; background:{bg};
    padding:44px 50px 30px 50px; display:flex; flex-direction:column; position:relative;
    --lc-tint:{lc_tint}; --rc-tint:{rc_tint}; --lc-lean:{lc_lean}; --rc-lean:{rc_lean};
    --lc-bord:{lc_bord}; --rc-bord:{rc_bord}; }}
  {_FX_CSS}
  .topbar, .arena, .metrics, .verdict, .footer {{ position:relative; z-index:2; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:24px; }}
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
  .cshot-wrap {{ position:relative; z-index:1; width:208px; height:208px; }}
  .cshot {{ width:208px; height:208px; border-radius:50%; object-fit:cover; object-position:center 8%;
    background:#20242c; border:5px solid var(--pc);
    box-shadow:0 0 52px -8px var(--pc), 0 26px 40px -14px rgba(0,0,0,0.85); }}
  .cshot-wrap.nophoto {{ display:flex; align-items:center; justify-content:center;
    border-radius:50%; border:5px solid var(--pc); background:#141821;
    box-shadow:0 26px 40px -14px rgba(0,0,0,0.85); }}
  .clogo {{ position:absolute; z-index:2; bottom:0; right:-6px; width:66px; height:66px; object-fit:contain;
    filter:drop-shadow(0 3px 4px rgba(0,0,0,0.8)); }}
  .clogo.big {{ position:static; width:104px; height:104px; }}
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
  .cval {{ font-family:"Bahnschrift",sans-serif; font-weight:700; font-size:36px; color:#717d8f;
    text-shadow:0 1px 3px rgba(0,0,0,0.5); }}
  .cval:first-child {{ text-align:left; }}
  .cval:last-child {{ text-align:right; }}
  .cval.win {{ color:var(--pcl); font-size:50px;
    text-shadow:0 0 26px var(--pcl), 0 0 10px var(--pcl), 0 2px 6px rgba(0,0,0,0.7); }}
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
  {_OVERLAYS}
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
  <div class="footer"><span>{_esc(footer) if footer else ''}</span><span>data-driven \u00b7 our projections</span></div>
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
    total_rows = sum(len(t["rows"]) for t in tiers)
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
    box-shadow:0 0 40px -4px var(--hero-accent), 0 20px 30px -12px rgba(0,0,0,0.85); }}
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
  .avatar {{ position:relative; flex:0 0 auto; width:{av}px; height:{av}px; }}
  .avatar .shot {{ width:{av}px; height:{av}px; border-radius:50%; object-fit:cover; object-position:center 10%;
    background:#20242c; border:2px solid var(--accent); box-shadow:0 0 12px -3px var(--accent); }}
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
  .cphoto-wrap {{ position:relative; width:132px; height:132px; margin-top:6px; }}
  .cphoto {{ width:132px; height:132px; border-radius:18px; object-fit:cover; object-position:center 10%;
    background:#20242c; border:3px solid var(--accent);
    box-shadow:0 0 20px -4px var(--accent), 0 12px 20px -10px rgba(0,0,0,0.85); }}
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
