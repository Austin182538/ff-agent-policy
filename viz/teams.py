"""NFL team branding: primary colors + ESPN CDN logo URLs.

Logos are pulled live from ESPN's public CDN at render time (the headless
browser is online), so we don't vendor any image assets. Colors are each
team's primary brand color, used for the per-row accent stripe in graphics.
"""

# Our standard team abbreviations -> primary brand color (hex).
TEAM_COLORS = {
    "ARI": "#97233F", "ATL": "#A71930", "BAL": "#241773", "BUF": "#00338D",
    "CAR": "#0085CA", "CHI": "#0B162A", "CIN": "#FB4F14", "CLE": "#311D00",
    "DAL": "#041E42", "DEN": "#FB4F14", "DET": "#0076B6", "GB":  "#203731",
    "HOU": "#03202F", "IND": "#002C5F", "JAX": "#006778", "KC":  "#E31837",
    "LV":  "#000000", "LAC": "#0080C6", "LAR": "#003594", "MIA": "#008E97",
    "MIN": "#4F2683", "NE":  "#002244", "NO":  "#D3BC8D", "NYG": "#0B2265",
    "NYJ": "#125740", "PHI": "#004C54", "PIT": "#FFB612", "SF":  "#AA0000",
    "SEA": "#69BE28", "TB":  "#D50A0A", "TEN": "#4B92DB", "WAS": "#5A1414",
}

# Each team's SECONDARY brand color -- the "other" color in its identity. In
# graphics the primary drives the border/accent and the secondary washes the
# main panel, so every row/card reads as that team's two-tone kit (e.g. Packers
# = green border, gold wash). Picked to be recognizable and to still show up as
# a tint on a dark background (silver/white secondaries are nudged darker).
TEAM_COLORS_SECONDARY = {
    "ARI": "#000000", "ATL": "#000000", "BAL": "#9E7C0C", "BUF": "#C60C30",
    "CAR": "#101820", "CHI": "#C83803", "CIN": "#000000", "CLE": "#FF3C00",
    "DAL": "#869397", "DEN": "#002244", "DET": "#B0B7BC", "GB":  "#FFB612",
    "HOU": "#A71930", "IND": "#A2AAAD", "JAX": "#D7A22A", "KC":  "#FFB81C",
    "LV":  "#A5ACAF", "LAC": "#FFC20E", "LAR": "#FFA300", "MIA": "#FC4C02",
    "MIN": "#FFC62F", "NE":  "#C60C30", "NO":  "#101820", "NYG": "#A71930",
    "NYJ": "#101820", "PHI": "#A5ACAF", "PIT": "#101820", "SF":  "#B3995D",
    "SEA": "#002244", "TB":  "#FF7900", "TEN": "#0C2340", "WAS": "#FFB612",
}


# ESPN's logo CDN uses lowercase codes that mostly match ours; the few that
# differ are mapped here.
_ESPN_LOGO_ABBR = {"WAS": "wsh"}


def team_color(abbr: str, default: str = "#334155") -> str:
    return TEAM_COLORS.get((abbr or "").upper(), default)


def team_secondary(abbr: str, default: str = "#1b2230") -> str:
    """The team's secondary color (see TEAM_COLORS_SECONDARY). Falls back to a
    neutral dark slate so unknown teams still render cleanly."""
    return TEAM_COLORS_SECONDARY.get((abbr or "").upper(), default)


def team_colors(abbr: str) -> tuple:
    """(primary, secondary) for a team -- primary for borders/accents, secondary
    for the panel wash."""
    return team_color(abbr), team_secondary(abbr)


def team_logo_url(abbr: str) -> str:
    abbr = (abbr or "").upper()
    code = _ESPN_LOGO_ABBR.get(abbr, abbr.lower())
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{code}.png"
