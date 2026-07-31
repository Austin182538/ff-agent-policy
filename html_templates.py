"""
Blitz Culture — HTML/CSS Graphic Templates
--------------------------------------------
Each function returns a full HTML document string for one guided layout
variant. These are intentionally NOT freeform — the design agent picks
one of these functions and fills it with content, rather than writing
arbitrary HTML from scratch. This keeps every post on-brand while still
giving real layout variety.

Fonts are embedded via @font-face pointing at local files so rendering
works fully offline once you've downloaded them once.
"""

import os

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# file:// URLs so the headless browser can load local font files
ANTON_PATH = "file:///" + os.path.join(FONT_DIR, "Anton-Regular.ttf").replace("\\", "/")
INTER_PATH = "file:///" + os.path.join(FONT_DIR, "Inter-Regular.ttf").replace("\\", "/")
INTER_BOLD_PATH = "file:///" + os.path.join(FONT_DIR, "Inter-Bold.ttf").replace("\\", "/")

BASE_STYLE = f"""
@font-face {{ font-family: 'Anton'; src: url('{ANTON_PATH}'); }}
@font-face {{ font-family: 'Inter'; src: url('{INTER_PATH}'); font-weight: 400; }}
@font-face {{ font-family: 'Inter'; src: url('{INTER_BOLD_PATH}'); font-weight: 700; }}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  width: 1080px; height: 1350px;
  background: linear-gradient(160deg, #1A1A18 0%, #232320 100%);
  font-family: 'Inter', sans-serif;
  color: #F5F0E6;
  position: relative;
  overflow: hidden;
}}
.accent-bar {{ position: absolute; top: 0; left: 0; width: 100%; height: 14px;
  background: linear-gradient(90deg, #EF9F27, #FAC775); }}
.wordmark {{ position: absolute; top: 50px; left: 60px;
  font-family: 'Inter'; font-weight: 700; font-size: 30px;
  letter-spacing: 3px; color: #EF9F27; }}
.headline {{ position: absolute; top: 105px; left: 60px; right: 60px;
  font-family: 'Anton'; font-size: 68px; line-height: 1.05;
  text-transform: uppercase; color: #FFFFFF; }}
.underline {{ position: absolute; width: 160px; height: 6px; background: #EF9F27; }}
"""


def _wrap(body_html: str) -> str:
    return f"<html><head><style>{BASE_STYLE}</style></head><body>{body_html}</body></html>"


def ranking_card_clean_list(title: str, rows: list[dict]) -> str:
    """Guided variant 1: simple vertical list, good for 5-10 ranked items."""
    row_html = ""
    for r in rows[:10]:
        row_html += f"""
        <div style="display:flex; justify-content:space-between; align-items:center;
                    background:#2C2C2A; border-radius:10px; padding:22px 30px; margin-bottom:14px;">
          <span style="font-family:'Inter'; font-weight:700; font-size:38px;">{r['label']}</span>
          <span style="font-family:'Inter'; font-size:30px; color:#FAC775;">{r['value']}</span>
        </div>"""
    body = f"""
    <div class="accent-bar"></div>
    <div class="wordmark">BLITZ CULTURE</div>
    <div class="headline">{title}</div>
    <div class="underline" style="top:195px; left:60px;"></div>
    <div style="position:absolute; top:260px; left:60px; right:60px;">{row_html}</div>
    """
    return _wrap(body)


def ranking_card_podium(title: str, rows: list[dict]) -> str:
    """Guided variant 2: top 3 get big emphasized cards, rest listed smaller below."""
    top3 = rows[:3]
    rest = rows[3:8]
    podium_html = "<div style='position:absolute; top:250px; left:60px; right:60px; display:flex; gap:20px;'>"
    for i, r in enumerate(top3):
        size = 130 if i == 0 else 100
        podium_html += f"""
        <div style="flex:1; background:linear-gradient(160deg,#2C2C2A,#232320);
                    border:2px solid #EF9F27; border-radius:16px; padding:24px; text-align:center;">
          <div style="font-family:'Anton'; font-size:{size}px; color:#EF9F27;">#{i+1}</div>
          <div style="font-family:'Inter'; font-weight:700; font-size:30px; margin-top:8px;">{r['label']}</div>
          <div style="font-family:'Inter'; font-size:22px; color:#FAC775; margin-top:6px;">{r['value']}</div>
        </div>"""
    podium_html += "</div>"

    rest_html = ""
    y_offset = 560
    for r in rest:
        rest_html += f"""
        <div style="display:flex; justify-content:space-between;
                    padding:16px 10px; border-bottom:1px solid #333;">
          <span style="font-family:'Inter'; font-size:30px;">{r['label']}</span>
          <span style="font-family:'Inter'; font-size:24px; color:#FAC775;">{r['value']}</span>
        </div>"""

    body = f"""
    <div class="accent-bar"></div>
    <div class="wordmark">BLITZ CULTURE</div>
    <div class="headline">{title}</div>
    <div class="underline" style="top:195px; left:60px;"></div>
    {podium_html}
    <div style="position:absolute; top:{y_offset}px; left:60px; right:60px;">{rest_html}</div>
    """
    return _wrap(body)


def player_spotlight_bold(title: str, player: str, stats: list[dict]) -> str:
    """Guided variant: big player name, few large stat callouts. Good for hype/injury."""
    stat_html = ""
    for s in stats[:3]:
        stat_html += f"""
        <div style="margin-bottom:36px;">
          <div style="font-family:'Inter'; font-size:26px; color:#FAC775; text-transform:uppercase; letter-spacing:2px;">{s['label']}</div>
          <div style="font-family:'Inter'; font-weight:700; font-size:44px; margin-top:4px;">{s['value']}</div>
        </div>"""
    body = f"""
    <div class="accent-bar"></div>
    <div class="wordmark">BLITZ CULTURE</div>
    <div class="headline">{title}</div>
    <div class="underline" style="top:195px; left:60px;"></div>
    <div style="position:absolute; top:270px; left:60px; right:60px;
                font-family:'Anton'; font-size:88px; color:#EF9F27; text-transform:uppercase; line-height:1;">
      {player}
    </div>
    <div style="position:absolute; top:440px; left:60px; right:60px;">{stat_html}</div>
    """
    return _wrap(body)


def odds_card_line_move(title: str, rows: list[dict]) -> str:
    """Guided variant: line-movement rows with arrow-style before/after."""
    row_html = ""
    for r in rows[:6]:
        row_html += f"""
        <div style="margin-bottom:30px; padding-bottom:24px; border-bottom:1px solid #333;">
          <div style="font-family:'Inter'; font-size:28px; text-transform:uppercase; color:#FAC775;">{r['label']}</div>
          <div style="font-family:'Anton'; font-size:50px; margin-top:6px;">{r['value']}</div>
        </div>"""
    body = f"""
    <div class="accent-bar"></div>
    <div class="wordmark">BLITZ CULTURE</div>
    <div class="headline">{title}</div>
    <div class="underline" style="top:195px; left:60px;"></div>
    <div style="position:absolute; top:270px; left:60px; right:60px;">{row_html}</div>
    """
    return _wrap(body)


# Registry mapping (post_type, variant) -> function, used by the designer agent
LAYOUTS = {
    ("ranking_card", "clean_list"): ranking_card_clean_list,
    ("ranking_card", "podium"): ranking_card_podium,
    ("player_spotlight", "bold"): player_spotlight_bold,
    ("odds_card", "line_move"): odds_card_line_move,
}
