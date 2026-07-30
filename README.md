# Fantasy Football Rankings & Graphics Engine (2026)

A data-driven redraft ranking system for **12-team half-PPR** leagues that turns
Vegas markets and historical outcomes into a value-over-replacement (VOR) board,
then renders that board into sleek, broadcast-quality PNG graphics. It's built to
**adapt to headlines**: re-run the model, diff the ranks, and auto-generate a
"what changed" graphic.

Scoring: 0.5 pt/reception, 1 pt / 10 yds, 6 pt rush/rec TD, **4 pt pass TD, -2 pt
INT**. Lineup assumed: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX (RB/WR/TE). No K/DST.

---

## How it works (the pipeline)

```
        ingest / scrape                    model                         render
  ┌───────────────────────┐      ┌────────────────────────┐     ┌────────────────────┐
  nflverse history         │      │ analysis/              │     │ scripts/           │
  Odds API + BettingPros   ├────► │  player_ranking_v1.py  ├───► │  generate_ranking_ │
  FantasyPoints scraper    │  DB  │  → player_rankings.csv │ CSV │  graphic.py        │
  ESPN rankings/news       │      │ ranking_diff_report.py │     │  (viz/ templates)  │
  Sleeper ADP (parsed)     │      │ market_gaps.py         │     │  → outputs/graphics│
  └───────────────────────┘      └────────────────────────┘     └────────────────────┘
```

1. **Ingest** raw data into `nfl_analytics.db` (SQLite).
2. **Project** each player's points from Vegas player props (the baseline), convert
   to half-PPR, and rank by **VOR** (points above a replacement-level player).
3. **Render** any slice of the board (overall, by position, favorites, head-to-head,
   movers, hypothetical shake-ups) to a 1080×1350 PNG via headless Chrome/Edge.

---

## Quick start

Two virtualenvs are used: `venv` (model/DB) and `venv_data` (graphics/scrape deps).

```powershell
# 1. (Re)build the rankings from the DB  ->  outputs/player_rankings_2026.csv
venv\Scripts\python.exe analysis\player_ranking_v1.py

# 2. Make graphics (random theme/variant each run; pin with --theme/--variant/--seed)
venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type overall --top 12
venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type position --position RB --top 12
venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type favorites --top 10
venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type compare --players "Derrick Henry, Josh Jacobs"
venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type hypothetical --mover "Josh Allen" --to 17 --from 11 --start 13 --top 12
```

Graphic types: `overall`, `position`, `favorites`, `compare`, `movers`, `value`,
`hypothetical`. Themes: `midnight_gold, royal_blue, emerald, crimson, violet,
cyber_teal, sunset`. Variants: `classic, spotlight`.

### Refreshing data (headlines / new lines)

```powershell
venv\Scripts\python.exe scripts\scrape_bettingpros_props.py     # season-long player props
venv\Scripts\python.exe scripts\scrape_vegas_snapshot.py        # FantasyPoints prop snapshot
venv\Scripts\python.exe scripts\ingest_espn_rankings.py         # ESPN consensus
venv\Scripts\python.exe scripts\parse_sleeper_adp.py            # Sleeper ADP -> data/sleeper_adp_2026.csv
venv\Scripts\python.exe analysis\ranking_diff_report.py         # diff vs last run -> movers graphic input
```

---

## Repository layout

```
analysis/     the model + all methodology/research scripts (the "why")
  player_ranking_v1.py        ← the ranking model (VOR, replacement, env tie-breaker)
  ranking_diff_report.py      ← rank changes between runs (feeds the "movers" graphic)
  market_gaps.py              ← "value targets" (feeds the value graphic)
  adp_divergence_report.py    ← our board vs Sleeper ADP vs ESPN, rank-based
  wins_vs_fantasy_finish.py   ← calibrated the team-environment coefficients
  wins_vs_production.py, qb_premium_historical_check.py,
  preseason_expectation_bias_check.py, multi_source_consensus_check.py,
  adp_vs_vegas_and_actuals.py, vegas_props_vs_consensus.py,
  vegas_win_totals_accuracy.py   ← research that justified specific design choices
viz/          graphics engine (HTML/CSS -> PNG)
  graphics.py   templates, themes, layout variants, all the "premium" styling
  teams.py      per-team primary + secondary colors and logos
  render.py     headless Chrome/Edge screenshotter
scripts/      ingestion + scraping + the graphic generator
app/          only the pieces the pipeline imports:
  core/ (config + SQLAlchemy engine), models/ (ORM tables), integrations/
  (nflverse, Odds API, BettingPros, FantasyPoints, ESPN, news, projections)
data/         inputs (Vegas props, Sleeper ADP, win totals, overrides) + README.md (data dictionary)
outputs/      player_rankings_2026.csv, analysis CSVs, graphics/, history/ (rank snapshots)
nfl_analytics.db   SQLite store for all ingested data
```

> The original FastAPI web API + dashboard (`app/api`, `app/services`, `app/schemas`,
> `frontend/`, `alembic/`) was removed — this repo is now the rankings + graphics
> pipeline only. `app/core`, `app/models` and `app/integrations` remain because the
> model and scrapers import them.

---

## Methodology — how we got here (play-by-play)

Each decision below is backed by a script in `analysis/` if you want to reproduce it.

1. **Vegas props as the projection baseline.** Player points come from season-long
   over/unders (passing/rushing/receiving yards, TDs, receptions) converted to
   half-PPR — not from our own guesses or last year's stats. Prop lines are the
   market's best estimate of volume/efficiency. `build_vegas_props_2026.py`,
   `scrape_bettingpros_props.py`.

2. **No player self-history.** A player's own prior-season fantasy points are **not**
   an input. This stopped rookies from being penalized for having no history and
   stopped veterans from being anchored to a stale year. See the header notes in
   `player_ranking_v1.py`.

3. **Value Over Replacement (VOR).** Players are ranked by projected points minus a
   **replacement-level** baseline at their position, so positions are comparable.

4. **Replacement level from real outcomes, flex-simulated.** The baseline is the
   actual season finish (2021–25) of the last startable player, with the 12 FLEX
   slots simulated from who'd really win them — not an ADP-rank curve (which bakes
   in bust/breakout noise). `build_actual_finish_curve`, `compute_flex_adjusted_replacement_ranks`.

5. **Elite injuries scale VOR, not raw points.** A player expected to miss *G* games
   keeps `(17−G)/17` of his **VOR** (the missed weeks are backfilled at replacement
   level), instead of naively prorating his point total — which would massively
   over-penalize a short absence. `data/player_availability.csv` drives it.

6. **Team-environment tie-breaker in points space.** A small, capped premium/penalty
   on VOR for players in strong/weak scoring environments, scaled per position by how
   much fantasy points actually move with team points. We use **projected team points**
   (from the win total) because it predicts fantasy finish better than wins —
   confirmed in `wins_vs_fantasy_finish.py` (R² improves QB/RB/WR/TE when swapping
   wins → points_for).

7. **Streaming-adjusted replacement for QB & TE** *(latest model change)*. Because
   almost nobody rosters a second QB or TE, quality options are always on waivers and
   a manager who waits can **stream near-starter production for free**. So the baseline
   you draft *above* is a low-end starter, not the last starter: QB replacement was
   moved to ~QB9 (~296 pts) and TE to ~TE10 (~131 pts). This collapsed QB/TE VOR to
   roughly what the market already prices, so the board stopped overvaluing them (Allen
   #11→#17, the mid-QB/TE tiers slid down; scarce elite TEs stayed near the top).
   Constant `STREAMING_REPLACEMENT_RANK` in `player_ranking_v1.py`.

8. **ADP source = Sleeper.** Graphics compare our ranks to **Sleeper ADP** (parsed by
   `parse_sleeper_adp.py` into `data/sleeper_adp_2026.csv`), which is the board we
   actually draft against — not the FantasyPros ECR proxy that seeds calibration.
   `adp_divergence_report.py` classifies gaps as genuine market fades vs. our outliers.

---

## Graphics design system

All posters auto-inherit a shared "premium" look (baked into `viz/graphics.py`, no
per-run flags needed):

- **Depth:** soft drop shadows, inset top-edge highlights + bottom occlusion (light
  from top-left), a team-color bloom behind the hero headshot.
- **Type:** carved 3D titles (dark stroke + stacked extrude shadow), text shadows on
  names for legibility over busy washes.
- **Hierarchy:** the #1 row is a spotlight — bigger headshot/rank/stat + an accent glow
  frame. Headshot/rank sizes auto-scale to the row count so circles always fit the bar.
- **Color:** lifted (non-black) backgrounds per theme, a faint transparent crosshatch
  texture, film grain + vignette overlays. Each row is washed in the **more vibrant of
  the team's two colors** (49ers → red, Packers → gold) with the other color as the
  thin edge stripe (`teams.py` holds both colors; vibrance picked by chroma).
- **Head-to-head:** an "arena" with a team-color split, glowing hero cutouts, an accent
  VS medallion, winner-highlighted metric rows, and a verdict tally.

---

## Changelog (this build)

- **Model:** added streaming-adjusted replacement for QB/TE (`STREAMING_REPLACEMENT_RANK`)
  so QBs/TEs are valued against a waiver/streaming baseline instead of the last starter.
- **Graphics — depth & polish:** grain + vignette overlays, top-left lighting, inset
  cards, hero bloom, carved 3D titles, legibility text shadows.
- **Graphics — hierarchy:** #1 spotlight row; headshot/rank chips auto-size to the
  number of rows (fixes circles overflowing dense boards).
- **Graphics — color:** two colors per team with the vibrant one as the main wash;
  lifted backgrounds + subtle background texture for more color/energy.
- **Graphics — head-to-head:** full redesign (arena split, VS medallion, winner glow,
  verdict bar) with dark-team legibility handling.
- **New graphic type `hypothetical`:** simulate a headline moving a player to a new rank
  and render any window with up/down movement arrows (the headline → re-rank → graphic
  demo).
- **Cleanup:** removed the unused FastAPI web app + dashboard, one-off Clay-projection
  imports, diagnostics, and stale outputs; kept the ingestion/scrape/model/graphics
  pipeline and the `analysis/` methodology scripts.
```
