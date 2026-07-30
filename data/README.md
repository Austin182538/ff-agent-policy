# data/

Small, manually-curated datasets that aren't available from a free API/MCP
server, refreshed by hand occasionally rather than on a schedule.

## vegas_win_totals.csv

Preseason team season win-total lines (Over/Under number of regular-season
wins) for 2022-2026. The Odds API does not carry this market for NFL (see
`app/integrations/odds_api_client.py` docstring), so these were sourced
directly from public sportsbook-odds writeups:

- 2022: actionnetwork.com, DraftKings opening lines (Aug 24, 2022)
- 2023: actionnetwork.com, DraftKings opening lines
- 2024: actionnetwork.com, FanDuel lines (as of Aug 20, 2024)
- 2025: dknetwork.draftkings.com (May 2025)
- 2026: wsn.com / pff.com (FanDuel-sourced), current as of Jul 2026 -- these
  are preseason lines and will keep moving until kickoff, so re-scrape/update
  closer to Week 1 if you want the true closing line.

Over/under prices (juice) were intentionally left blank where not confidently
sourced -- only the line itself is populated. Loaded into the
`team_season_win_totals` table by `scripts/seed_team_win_totals.py`.

To refresh a season, look up "<year> NFL win totals every team" and update
the corresponding rows.

## vegas_player_props_2026.csv

Season-long individual player prop lines (receiving/rushing/passing yards
and TDs) for the 2026 season, sourced from **all six** of fantasypoints.com's
season-prop articles (receiving yards, receiving TDs, rushing yards, rushing
TDs, passing yards, passing TDs -- themselves aggregating DraftKings/
FanDuel/BetMGM/Caesars/theScore/Bet365). The Odds API does not carry
season-long player props for NFL (only single-game weekly props once the
season starts), so -- same as team win totals -- this had to be manually
curated rather than pulled live.

Each `*_line` value is the midpoint between the "highest total where the
under is the play" and "lowest total where the over is the play" reported
across books, i.e. an approximation of the consensus line, not any single
book's exact number, and not fantasypoints' own "FP Projection" column
(their proprietary point estimate, not a market price). Rebuilt from scratch
on 2026-07-28 via `scripts/build_vegas_props_2026.py`, which fetches all six
articles in full and merges them by player -- this **replaced** an earlier,
much smaller snapshot that had only curated a "most market interest" subset
of the receiving/rushing-yards articles (~86 rows) and didn't have the TD or
passing articles at all. The full articles cover 115 unique players across
QB/RB/WR/TE (up from 76), including a real TD line for the large majority of
them -- so far fewer players fall back to the league-average TD-rate
estimate in `app/integrations/player_projection.py` than before.

QB passing props (pass_yards_line + pass_tds_line, all 25 starting-caliber
QBs) are now fully wired into `analysis/player_ranking_v1.py` via
`implied_passing_points()` -- interceptions aren't a market Vegas posts
either, so they're estimated from a league-average passing-yards-per-INT
rate (356, from 2021-2025 real-starter seasons), same "never a specific
player's own rate" rule as everywhere else. QBs without their own real
Vegas rushing line (i.e. not one of the current season's mobile-QB tier)
get a flat, position-wide "pocket passer" rushing baseline instead of zero
-- see `QB_POCKET_PASSER_RUSHING_BASELINE` in player_projection.py.

RB receiving props: fantasypoints.com doesn't track a receiving-yards market
for RBs at all (their receiving-yards article is WR/TE only), so Ashton
Jeanty's receiving line (400 yards, 2.5 TDs) remains a user-provided
sportsbook line, noted as such in that row's `source` column -- everyone
else without a listed rec_yards_line uses the flat RB-receiving baseline
(`compute_rb_receiving_baseline()` in player_ranking_v1.py).

This is a snapshot as of ~Jun-Jul 2026 and will drift from the closing lines
by kickoff -- re-run `scripts/build_vegas_props_2026.py` against updated
articles if you want a more current snapshot (update the URLs/tables in that
script first, since it's currently a point-in-time data dump, not a live
scraper).

## bettingpros_player_props_2026.csv  (PRIMARY season-prop source)

The earlier attempt to scrape BettingPros' rendered HTML dead-ended (the site
loads props via an XHR to a gated API, not in the page HTML). That API is now
wired up directly and is the **authoritative** season-prop source, replacing
fantasypoints.com as the primary feed. See
`app/integrations/bettingpros_client.py` for the endpoint/auth details and
`scripts/scrape_bettingpros_props.py` to refresh.

Why it's better than the fantasypoints scrape:

- **RB receiving yards** -- BettingPros posts a `total-receiving-yards` O/U for
  running backs (market 302), which fantasypoints does not. This closed the
  exact gap that was defaulting every pass-catching RB (Bijan, CMC, Achane...)
  to the flat league-average baseline. Bijan's real line (~575) now flows in.
- **Real reception counts** -- BettingPros posts a `total-receptions` O/U
  (market 330) for ~80 players. When present it's used *directly* for the
  0.5/catch scoring component instead of dividing yards by a league-average
  yards-per-catch, which had been over-counting catches for some roles (Bijan
  went from a derived ~81 receptions to a real 65.5).
- **Broader coverage** -- one refresh pulls 100+ receiving-yard lines, 59
  rushing-yard, 29 passing-yard, and the matching TD lines, all as a
  cross-book consensus (BettingPros "book id 0").

Each line is BettingPros' consensus number (their book id 0's main line). The
scraper upserts `player_season_prop_lines` matching existing rows by
*normalized name*, so it updates the same player row rather than duplicating
a fantasypoints-created one, and BettingPros values win for any market it
covers. Requires `BETTINGPROS_API_KEY` in `.env`.

The CSV also carries a `headshot_url` column (the fantasypros head-and-shoulders
cutout the API returns per player). `scripts/generate_ranking_graphic.py` joins
these by normalized name to draw the circular player photos in the ranking
graphics; players without a BettingPros line just fall back to the team logo.

### vegas_player_props_2026.csv (fantasypoints.com, secondary/legacy)

The fantasypoints.com scrape (below) still exists and its rows remain in
`player_season_prop_lines`, but BettingPros now overwrites them wherever it
has a line. Kept as a fallback for any player BettingPros doesn't cover and
because the line-movement monitor (`scrape_vegas_snapshot.py`) still uses it.

## External consensus rankings (ESPN, Sleeper, Yahoo)

`external_consensus_rankings` (see `app/models/market_models.py`) holds
rankings/ADP from platforms other than the primary FantasyPros-via-nflverse
source that the VOR/replacement calibration is built on
(`fantasy_consensus_rankings`, see historical_models.py). Kept in a
**separate table** deliberately -- that calibration curve was tuned
specifically against FantasyPros ECR history back to 2021, and there's no
equivalent multi-year history from these other platforms to re-derive it
against, so they're for side-by-side comparison (see
`analysis/multi_source_consensus_check.py`), not a drop-in replacement.

- **ESPN**: `app/integrations/espn_client.py` pulls a real, live, no-auth,
  undocumented-but-public endpoint (`lm-api-reads.fantasy.espn.com/.../
  leaguedefaults/3`) that returns ESPN's own expert draft rank (STANDARD/
  PPR/SUPERFLEX) plus real crowd-sourced ADP for every rostered-relevant
  player. Ingested via `scripts/ingest_espn_rankings.py`. ESPN has no native
  half-PPR rank category, so `PPR` (full PPR) is used as the closer analog
  to this league's 0.5-PPR scoring.
- **Sleeper**: investigated and **not integrated** -- their public API
  (`docs.sleeper.com`) is read-only and free, but only exposes rosters,
  drafts, matchups, and player metadata/trending-adds. There is no ADP or
  consensus-rank endpoint at all; third-party aggregators exist but aren't
  official Sleeper data.
- **Yahoo**: investigated and **not integrated** -- even purely public,
  read-only Yahoo Fantasy data requires a registered developer app (a
  consumer key/secret from developer.yahoo.com) and OAuth, which needs
  action from whoever owns this project (create an app, agree to Yahoo's
  API terms) before it could be pulled. Flag if you want this added and can
  provide credentials.

## Headline-detection pipeline: Vegas line-movement monitor + news lookup

The long-term goal for this project is `headline -> ranking update -> graphic`.
This is the first, working piece: an automated monitor that watches Vegas
lines for meaningful movement and flags when something needs a human look,
plus a news lookup to help explain *why*.

**How it works:**

1. `scripts/scrape_vegas_snapshot.py` -- scrapes all six fantasypoints.com
   season-prop articles for real (server-rendered, no-JS-needed HTML tables
   confirmed via `app/integrations/fantasypoints_scraper.py`), and:
   - Appends one full batch of rows to `player_prop_line_snapshots`
     (append-only, timestamped, never overwritten -- this is what makes
     "diff now vs. last run" possible).
   - Upserts `player_season_prop_lines` (the "current" table the ranking
     pipeline reads), so a fresh scrape automatically flows into the next
     `analysis/player_ranking_v1.py` run with no extra step.
2. `scripts/compare_vegas_snapshots.py` -- diffs the two most recent
   snapshot batches, converts every line change into a fantasy-point
   equivalent (yards/10, TDs x6/x4 -- same conversion as
   `app/integrations/player_projection.py`), and flags anything crossing a
   threshold (12+ points by default) as a "big mover" worth investigating.
   Exits 0 ("safe to move on") if nothing crosses the threshold, exits 1 if
   something does.
3. `scripts/lookup_player_news.py "<name>"` -- pulls recent headlines from
   ESPN's public, no-auth NFL news feed
   (`app/integrations/espn_news_client.py`) and filters to ones mentioning
   that player, to help explain a flagged line move.
4. `scripts/run_vegas_monitor.ps1` -- runs steps 1+2 back to back and logs
   every run to `logs/vegas_monitor.log`. This is the single entry point a
   scheduled task should call.

**What this does NOT do yet:** it doesn't automatically re-run the full
ranking pipeline or generate a graphic when a big mover is flagged -- those
are the next two pipeline stages, deliberately built after confirming the
monitor itself works. It also doesn't yet cross-reference the news feed
automatically against flagged movers (`lookup_player_news.py` is a manual
follow-up step for now).

## manual_prop_overrides.csv (fill/override prop lines the scraper can't get)

A last-resort hand/agent-editable hook to inject or correct a prop line the
automated feeds get wrong or don't carry. **As of the BettingPros integration
this file is empty (header only)** -- BettingPros now supplies RB receiving
yards and real reception counts, so the original reason it existed (Bijan's
missing RB receiving line) is gone. Add a row only when you have a specific,
better number than the live feeds.

| column | meaning |
| --- | --- |
| `player_name` | must match the ranking pool's spelling (normalized, so `Jr.`/`III`/apostrophes don't matter) |
| `position` | optional; only needed when adding a player not already in the prop table |
| `rec_yards_line`, `rec_tds_line`, `rush_yards_line`, `rush_tds_line`, `pass_yards_line`, `pass_tds_line`, `receptions_line` | any you fill in; **blank cells are ignored** (the scraped value stays) |
| `source` | free-text audit trail |

Read by `load_player_props()` and applied **after** the scraped/BettingPros
lines, so a non-empty cell wins over everything. The auto-scrapers never touch
this file, so a manual correction survives every re-scrape. It's also where the
duplicate-spelling coalescing lives: `load_player_props()` merges
`James Cook`/`James Cook III` and smart-quote vs straight-apostrophe spellings
into one row (first non-null per line) so a stat split across two spellings
isn't dropped.

**Receptions:** a real season reception O/U (`receptions_line`, BettingPros
market 330) is now used directly for the 0.5/catch component when present. Only
players without a posted reception line still fall back to deriving catches from
the yards line via the league-average yards-per-catch.

## player_availability.csv (games-missed adjustment)

The hand/agent-editable hook for reacting to a suspension/injury headline. One
row per affected player:

| column | meaning |
| --- | --- |
| `player_name` | must match the ranking pool's name (same spelling as the props/consensus feeds) |
| `games_missed` | integer 0-17, how many of the 17 NFL games the player is expected to miss |
| `reason` | free text for the audit trail (e.g. "4-game PED suspension") |
| `source` | where you got it (e.g. "ESPN 2026-07-29") |

An empty file (header only) = no adjustments; every healthy player implicitly
has `games_missed = 0`. Kept as a standalone CSV (not the Vegas-prop tables) on
purpose: the auto-scraper never touches it, so a manual availability note
survives every scrape. Read live by `analysis/player_ranking_v1.py`
(`load_availability()`), so you just edit the file and re-run -- no re-seed step.

**The valuation math (why VOR scales, not points).** A player who will miss `G`
of 17 games keeps only `(17-G)/17` of his **value over replacement**, *not* that
fraction of his raw points. Derivation: over the season you get his output for
`17-G` games and a replacement-level fill-in (waiver/handcuff) for the `G` he
misses, so the value of rostering *him* over just rostering a replacement all
year is `(17-G)·(player_per_game - replacement_per_game) = base_VOR × (17-G)/17`.

Naively prorating **points** instead would compare a partial-season total
against a *full-season* replacement baseline and massively over-penalize a short
absence. Worked example (Bijan Robinson, 4 games missed):

- healthy: 221.9 pts, VOR 71.4, **rank 10**
- games-missed VOR (this method): `71.4 × 13/17 = 54.6` -> **rank 14** (a 4-spot
  drop, still a firm RB1 -- the elite 13 games outweigh a replacement's 4)
- naive points proration (wrong): `221.9 × 13/17 - 150.4 = 19.3` VOR -> ~rank 35

`projected_ppr_points` is deliberately left at the healthy full-season figure (a
talent/role signal); the `games_missed` column is carried into the output CSV so
the lower VOR is self-explanatory. A whole-season absence (`games_missed = 17`)
drives VOR to ~0, i.e. down to replacement level -- correct for a redraft league.

**Caveat -- don't double-count.** Vegas season-long totals already price in some
injury probability. Use this override for a *fresh* event the market hasn't
absorbed yet (a just-announced suspension), not to re-penalize a line that has
already moved to reflect the news. Timing isn't modeled either: missing weeks
1-4 and missing the fantasy-playoff weeks 15-17 are scored identically here.

## Ranking diff report (Phase 2: what actually changed, and why)

`analysis/ranking_diff_report.py` is the bridge between "a Vegas line moved"
and "here's what changed in the rankings" -- the thing an eventual
ranking-change graphic would be built from.

**How it fits with the monitor above:** `analysis/player_ranking_v1.py` now
archives a full, timestamped copy of every run to `outputs/history/`
(never overwritten -- the "live" `outputs/player_rankings_2026.csv` is still
also written, unchanged, for anything that reads "the current rankings").
The diff report compares the two most recent archives by default, or two
specific ones via `--old`/`--new`.

**The intended workflow when the monitor flags a big mover:**

1. `scripts/run_vegas_monitor.ps1` (or its two scripts individually) flags a
   big mover.
2. `venv\Scripts\python.exe scripts\lookup_player_news.py "<name>"` -- find
   out why (this is the "a little bit of intuition" step -- the tools give
   you the raw signal and headlines, not a fully automated verdict on what
   to do about it).
3. Decide how to react and update the data accordingly (e.g., correct a
   prop line by hand if the market hasn't caught up yet, or just let the
   next scheduled scrape pick up the market's own adjustment).
4. Re-run `analysis/player_ranking_v1.py` -- it archives automatically.
5. `venv\Scripts\python.exe analysis\ranking_diff_report.py` -- shows every
   player whose rank or VOR changed, cross-referenced against:
   - Any real Vegas line change for that player in the same window (the
     "why," pulled from `player_prop_line_snapshots`).
   - Any `games_missed` availability change (the "why" for a move that has no
     Vegas line change and zero points change -- see player_availability.csv).
   - Recent ESPN headlines for the biggest movers (best-effort).

**A real bug this surfaced and fixed:** raw rank position is a bad "who
moved" signal on its own. When one player's value drops a lot, every player
below them in the global sort mechanically shifts up by exactly one rank
slot -- with zero real change of their own. An early version of this report
listed dozens of these as "risers." Fixed by requiring a genuine `vor_change`
(not just `rank_change`) to appear in the risers/fallers lists. `vor_change`
(rather than `points_change`) is the right signal because it also catches a
games-missed availability move, which changes VOR without changing raw points.
Verified two ways: a synthetic "Derrick Henry season-ending injury" test
(cratered his Vegas rushing line -> one real mover, no renumbering false
positives), and a "Bijan 4-game absence" test (games_missed 0->4 -> Bijan
correctly flagged as the biggest faller, rank 10 -> 14, VOR -16.8, +0.0 pts,
with the cause reported as the availability change, not a phantom line move).

**Known gap (the "possibly more data" the user flagged):** the "why" lookup
only checks that *specific player's* own Vegas line and news. A real
headline often should ripple to teammates too (e.g., a starting RB's injury
should bump his backup's expected workload) -- that redistribution isn't
modeled yet; it currently requires a human to manually update the backup's
line too before re-running. Team win-total changes also aren't
snapshotted/diffed yet the way player prop lines are, so a team-context-driven
shift (new OC hired, coach fired mid-season) wouldn't show up in the "why"
even though it would show up in the points_change itself.

**Scheduling on Windows (Task Scheduler), every few hours:**

1. Open Task Scheduler -> **Create Task** (not "Basic Task", so you get
   the full trigger options).
2. **General tab**: name it (e.g. "NFL Vegas Line Monitor"). Check "Run
   whether user is logged on or not" if you want it to run even when
   you're not at the machine.
3. **Triggers tab** -> **New** -> "On a schedule" -> "Daily", set a start
   time, then check "Repeat task every" -> **4 hours** (or whatever
   interval you want) **for a duration of 1 day**. This gives you a
   recurring every-N-hours run without a separate cron-style tool.
4. **Actions tab** -> **New** -> "Start a program":
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\Users\aucooper\Documents\LRN bootcamp day 2\cursor-test\scripts\run_vegas_monitor.ps1"`
   - Start in: `C:\Users\aucooper\Documents\LRN bootcamp day 2\cursor-test`
5. Save. Check `logs\vegas_monitor.log` after the first couple of runs to
   confirm it's working, and check the task's "Last Run Result" in Task
   Scheduler -- a nonzero result means a big mover was flagged last run.

This is intentionally a plain scheduled script, not tied to Cursor-specific
infrastructure, so it can run on any machine (including a separate always-on
one) independent of whether Cursor itself is open.

## Graphics (Phase 3: branded PNGs from the rankings)

`scripts/generate_ranking_graphic.py` turns the model output into shareable,
branded PNG graphics (see the `viz/` package). Output goes to
`outputs/graphics/` (gitignored -- regenerate any time).

**Why template rendering, not an AI image model.** These graphics are
data-first: exact player names, ranks, team logos and stats. Generative image
models (DALL-E, Imagen, Midjourney, etc.) garble text and hallucinate
names/logos, so they're the wrong tool. Instead we inject the data into an
HTML/CSS template (`viz/graphics.py`) and screenshot it with a headless
Chrome/Edge (`viz/render.py`). Result: pixel-perfect text every time, real
team logos pulled live from ESPN's CDN, consistent branding, `$0`/image, fully
deterministic. **No extra dependency to install** -- it uses the Chrome or Edge
already on the machine (`--screenshot` CLI mode), rendered at 2x for retina
sharpness (1080x1350 canvas -> 2160x2700 PNG).

**Where an LLM *does* fit (and where it doesn't).** Claude's API cannot produce
images at all -- it's text+vision. Its real role in the eventual full-auto
pipeline is the *copy and decisioning*: writing the caption/headline for a post
("Bijan tumbles to RB14 after a 4-game suspension -- still an RB1 for the 13 he
plays") and choosing *which* graphic to make from an update. That's a text task
that slots in right before the render step. Architecture:

```
ranking update (diff report)
  -> [optional] LLM writes the caption + picks the graphic
  -> data injected into HTML/CSS template
  -> headless browser screenshots it -> PNG
```

**Graphic types (all render to outputs/graphics/):**

| command | what it makes |
| --- | --- |
| `--type position --position WR --top 10` | positional Top-N poster (per-position accent color) |
| `--type overall --top 12` | overall Top-N by VOR, all positions |
| `--type movers --direction fallers` | "what changed since last run" card, built from `outputs/ranking_diff_report.csv` (run `ranking_diff_report.py` first) |

Run with the analysis venv (same one as the ranking):
`venv_data\Scripts\python.exe scripts\generate_ranking_graphic.py --type overall --top 12`.
The `movers` graphic is the one that closes the headline->rerank->graphic loop:
a suspension/injury updates `player_availability.csv` -> re-run the ranking ->
run the diff report -> render the movers card showing exactly who moved and why.

**Not yet built (next step for full automation):** a single orchestrator that
chains monitor -> diff -> (LLM caption) -> render, plus optionally auto-posting.
The pieces all exist and are individually runnable; they just aren't stitched
into one scheduled command yet.

## Team wins vs production (win-environment multiplier calibration)

`analysis/wins_vs_production.py` measures how team wins actually relate to
player production, across 160 team-seasons (2021-2025, the 17-game era so win
totals are on one scale). This was to replace a guessed flat "+3% per win"
multiplier in the ranking model with something data-grounded.

**Finding -- it is emphatically not 1:1, and not uniform across stats.**
Per +1 win above average, production changes by:

| stat | % per win | | stat | % per win |
| --- | --- | --- | --- | --- |
| passing yards | +2.1% | | passing TDs | +5.7% |
| rushing yards | +2.0% | | rushing TDs | +6.0% |
| receptions | +1.1% | | receiving TDs | +5.9% |
| receiving yards | +2.3% | | points scored | +4.7% |

**TDs scale with wins ~3x harder than yards** (~6%/win vs ~2%/win), and
receptions barely move. Winning teams don't gain more *yards* (losing teams
throw for garbage-time yardage) -- they convert more *touchdowns* (leads,
red-zone trips, more possessions). By position group, fantasy points move QB
+4.1%/win, WR +3.4%, RB +3.0%, TE +1.3% (TE only weakly win-tied, r~0.13).

**What changed in the model.** An earlier version scaled BASELINE points by a
per-position *win* multiplier. That was superseded by the points-based
tie-breaker described in the next section (calibrated on team points, applied
once at the VOR level for every player). The old baseline multiplier was
removed so team environment is handled in exactly one place.

## Wins vs fantasy CEILING (upside / tie-break analysis)

`analysis/wins_vs_fantasy_finish.py` answers the upside question behind the
draft rule "if two players project within ~5-15 pts but one is on a team with
~4 more wins, favor the higher-win player." It looks at *actual* finishes
2021-2025 three ways. Key results:

- **Extra points per win at EQUAL opportunity** (regress season pts on
  touches + wins): QB **+5.9/win (~23.5 per 4 wins)**, RB +1.9 (~7.7/4W),
  WR +1.8 (~7.3/4W), TE +1.0 (~3.8/4W). This is the direct tie-break number:
  +4 wins is worth ~8 RB points of upside, so it flips a decision when two RBs
  are within ~5-8 projected pts, but NOT when they're 15 apart. For QB it's
  huge (~23 pts), so wins should heavily tie-break QBs.
- **Elite finishes are win-gated very differently by position.** Share of
  top-10 finishers from good (10+ win) teams: QB 74%, WR 56%, TE 50%, RB 44%.
  Lead-player P(top-10) lift from bad->good team: QB +59pts (2%->62%),
  WR +29, RB +27, TE +18. QB upside basically requires a good team; RB/TE
  upside is the least win-dependent.
- **Yes, a top-10 RB can come off a bad team** -- but it's rare (~1/yr) and
  always a volume monster: Josh Jacobs (2022, LV, 6W, RB3), Derrick Henry
  (2023, TEN, 6W, RB8), Alvin Kamara (2024, NO, 5W, RB10), Chase Brown
  (2025, CIN, 6W, RB8). RB upside is driven by workload, not team quality.
- **Why:** consistent with `wins_vs_production.py` -- wins buy touchdowns, not
  touches. So the same volume converts to more fantasy points on winning teams
  (pts/touch rises with wins), and the effect is biggest for TD-dependent
  positions (QB >> WR ~ RB > TE).

**Wired into the ranking model as the team-environment tie-breaker.**
`player_ranking_v1.py` now applies a position-scaled favorability adjustment
directly to VOR (`team_env_adj` column), replacing the old baseline win
multiplier. Design:

- **Calibrated on projected team POINTS, not wins** (points is a tighter
  predictor -- volume-controlled R^2 rises for every position when swapping
  wins -> points_for). `ENV_FPTS_PER_TEAM_POINT` = extra half-PPR pts per +1
  projected team point at equal opportunity: QB 0.345, RB 0.125, WR 0.100,
  TE 0.057 -- so the tie-break is strongest at QB, weakest at TE, exactly the
  increasing-by-position gradient we found.
- **Projected team points come from the win-total line** (`points_for ~=
  228.9 + 18.1*wins`), since no season point-total market is posted for 2026.
- **Applied to VOR, never multiplied into the Vegas lines**, so it's an upside
  tie-breaker, not a re-projection -- it favors the better-environment player
  when two are close, without overriding a real projection gap.
- **Dampened + capped** (`ENV_STRENGTH=0.6`, `ENV_CAP_WINS=4.0`) because Vegas
  medians already price most of a good offense's production; this adds only the
  residual ceiling premium. Set `ENV_STRENGTH=1.0` for the full measured effect.

Observed effect (2026 board): Josh Allen (BUF) +6.8 VOR, Henry (BAL) +3.8,
Nacua (LAR) +3.1; weak environments penalized -- Jeanty (LV) -3.0, McBride
(ARI, TE) -2.6. It flipped only near-ties (e.g. Smith-Njigba past Taylor, Cook
past Jeanty), leaving clear separations intact.

## Market-gap finder (value = similar projection, cheaper, better team)

`analysis/market_gaps.py` scans the ranking output for the specific
inefficiency worth drafting into: two same-position players with **close Vegas
projections**, where one is going **meaningfully later in ADP** *and* is on a
team projected for **more wins** (better scoring environment -> more ceiling).
The market (ADP/ECR) tends to under-price the environment edge, so that later
player is the value.

For each pair (expensive A vs cheaper B) it requires: both Vegas-projected,
`|proj gap| <= --proj` (default 15 pts), `adp_gap >= --adp-gap` (default 3
picks later), `win_gap >= --win-gap` (default 1 win). Each candidate is kept
with its strongest comparison and ranked by a transparent score that weights
the win edge heavily and caps the ADP contribution (so genuine environment
plays beat pure deep sleepers, not the other way around). Writes
`outputs/market_gaps_2026.csv`.

Example hits (2026): Courtland Sutton (DEN, 9.5W) over Jaylen Waddle (MIA,
4.5W) -- identical projection, ~39 picks cheaper; Matthew Stafford (LAR, 11.5W)
over Jayden Daniels (WAS, 7.5W) -- same projection, +4 wins, ~49 cheaper. This
is the draft-time complement to the in-model `team_env_adj` tie-breaker: the
model nudges rankings, this tool names the specific "draft B over A" spots.

## games_played (historical_player_stats)

Added so analyses can exclude injury/benching-shortened seasons instead of
letting a handful of low-snap-count outliers skew averages (see
`analysis/preseason_expectation_bias_check.py`). Computed as the count of
distinct weeks nflreadpy has a real stat line for that player/season --
confirmed nflreadpy only emits a weekly row for games actually played (no
zero-stat placeholder rows for missed games), so this is a reliable proxy
without needing a separate "games played" data source.
