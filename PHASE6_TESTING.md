# Phase 6 — Semi-Autonomous Testing Checklist

Goal: run the full pipeline (brain -> graphic -> caption -> queue) for about
a week with a human reviewing every post before it goes out, then remove the
approval gate once it's clean. Don't skip this — it's the cheapest place to
catch a bad pattern, before it's posted 20 times.

## Setup

1. `cd scheduling && .\setup_scheduled_tasks.ps1` (defaults to `-Mode Queue`,
   4 runs/day). This registers Task Scheduler jobs that call
   `orchestrator.py --queue` — nothing publishes without your approval.
2. A few times a day, run `venv\Scripts\python.exe review_pending.py` and
   approve/reject each queued post.

## What to check on every post before approving

- **Caption quality** — does it read like the voice described in
  `caption_system_prompt.txt` (confident, conversational, not corporate/
  robotic)? Any awkward phrasing, repeated sentence structure across posts,
  or hype-for-hype's-sake language?
- **Repeated content** — check `outputs/post_history.json` (or
  `review_pending.py`'s subject list): is the same player or content type
  showing up too often despite the variety rules in `content_history.py`?
  If so, the `NO_REPEAT_CONTENT_TYPE_WITHIN` / `NO_REPEAT_PLAYER_WITHIN`
  windows in that file may need widening.
- **Incorrect stats** — every number in the caption should trace back to
  `outputs/player_rankings_2026.csv`, `ranking_diff_report.csv`, or
  `market_gaps_2026.csv`. If a caption states something not in those files,
  that's a grounding failure in `caption_generator.py`'s prompt, not a data
  problem — flag it.
- **Hashtag issues** — right number (~12), relevant to the post, no
  duplicates, nothing that reads as spammy or off-brand.
- **Editorial judgment** — for `compare` / `value` / `movers` /
  `hypothetical` posts, is `content_brain.py`'s `reasoning` field actually a
  good call, or did it pick the least interesting eligible option?

## Rejecting a post

Use `review_pending.py`'s `[r]eject` option and jot a one-line reason —
these accumulate in `outputs/rejected_posts.json` so you can spot a pattern
(e.g. "movers posts keep citing stale diffs") instead of just remembering it.

## When to flip to full autonomy

Move to `-Mode Auto` (`.\setup_scheduled_tasks.ps1 -Mode Auto`) once, over
the trial window:

- You've approved the large majority of posts without edits.
- Rejections cluster around fixed bugs, not recurring judgment calls.
- No incorrect stat or repeated-content issue slipped through in the last
  ~2-3 days of review.

After switching, keep an eye on `outputs/orchestrator_failures.jsonl` and
`outputs/post_history.json` periodically — full autonomy removes the
pre-publish gate, not the need to check in.
