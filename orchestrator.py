"""
Blitz Culture -- Orchestrator (Phase 4)
--------------------------------------------
The one master script Task Scheduler will eventually call. Per run:

  1. (Optional) refresh the ranking board if it's stale.
  2. Run the brain (content_brain.run_brain()) to decide WHAT to post.
  3. Generate the graphic (scripts/generate_ranking_graphic.py).
  4. Generate the caption (caption_generator.generate_caption()).
  5. Upload the image to a public URL (image_hosting.publish_image()).
  6. Publish to Instagram (test_post.create_media_container/publish_container).
  7. Log the post (content_history.log_post()).

Three ways this gets run, matching the roadmap's Phase 6 (semi-autonomous
testing) -> Phase 7 (full autonomy) progression:

  --queue     Scheduled/unattended mode (Task Scheduler calls this). No
              interactive prompt -- generates the graphic + caption and
              parks them in outputs/pending_posts.json for a human to
              review with review_pending.py. THIS is what Phase 6 testing
              runs on, since a scheduled task has no one there to answer
              an input() prompt.
  (default)   Interactive mode -- prints the decision + caption + image
              path and asks y/N before publishing. Good for running by
              hand at your terminal.
  --auto      No gate at all, publishes immediately. Only flip the
              scheduled task to this once Phase 6 testing looks clean
              (see PHASE6_TESTING.md).

Usage:
    venv\\Scripts\\python.exe orchestrator.py                 # interactive approval gate, live
    venv\\Scripts\\python.exe orchestrator.py --queue           # unattended: queue for review, don't publish
    venv\\Scripts\\python.exe orchestrator.py --auto             # no gate, fully autonomous
    venv\\Scripts\\python.exe orchestrator.py --dry-run          # generate + caption only,
                                                                  #   skip queue/git push/IG publish entirely
    venv\\Scripts\\python.exe orchestrator.py --no-refresh       # skip the staleness check
"""
import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RANKINGS_CSV = os.path.join(PROJECT_ROOT, "outputs", "player_rankings_2026.csv")
LOG_PATH = os.path.join(PROJECT_ROOT, "outputs", "orchestrator_log.txt")
FAILURE_LOG_PATH = os.path.join(PROJECT_ROOT, "outputs", "orchestrator_failures.jsonl")
REFRESH_MAX_AGE_HOURS = 12
IG_PUBLISH_WAIT_SECONDS = 8
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("orchestrator")


def log_failure(step: str, error: Exception, context: dict = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": step,
        "error": str(error),
        "context": context or {},
    }
    with open(FAILURE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    log.error("FAILURE in %s: %s", step, error)


def with_retries(fn, step_name: str, *args, **kwargs):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 -- deliberately broad, this is the top-level retry wrapper
            last_err = e
            log.warning("%s attempt %d/%d failed: %s", step_name, attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    log_failure(step_name, last_err, {"args": [str(a) for a in args]})
    raise last_err


# ---------------------------------------------------------------------------
# Step 1: refresh data if necessary
# ---------------------------------------------------------------------------
def refresh_rankings_if_stale(max_age_hours: float = REFRESH_MAX_AGE_HOURS) -> None:
    """Re-runs the ranking model if outputs/player_rankings_2026.csv is
    older than max_age_hours. Deliberately does NOT touch the scrapers
    (Vegas odds, ESPN, Sleeper ADP) -- those hit external/paid sources and
    should stay a deliberate, monitored action (see roadmap Phase 7:
    Maintenance) rather than something that fires silently on a timer."""
    if not os.path.exists(RANKINGS_CSV):
        log.info("No rankings CSV yet -- running analysis/player_ranking_v1.py.")
    else:
        age_hours = (datetime.now().timestamp() - os.path.getmtime(RANKINGS_CSV)) / 3600.0
        if age_hours < max_age_hours:
            log.info("Rankings are %.1fh old (< %sh threshold) -- skipping refresh.", age_hours, max_age_hours)
            return
        log.info("Rankings are %.1fh old (>= %sh threshold) -- refreshing.", age_hours, max_age_hours)

    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "analysis", "player_ranking_v1.py")],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"player_ranking_v1.py failed: {result.stderr.strip()[-500:]}")
    log.info("Rankings refreshed.")


# ---------------------------------------------------------------------------
# Step 3: generate the graphic
# ---------------------------------------------------------------------------
GRAPHIC_ARG_BUILDERS = {
    "overall": lambda p: ["--type", "overall", "--top", str(p.get("top", 12)), "--start", str(p.get("start", 1))],
    "position": lambda p: ["--type", "position", "--position", p.get("position", "WR"),
                           "--top", str(p.get("top", 10)), "--start", str(p.get("start", 1))],
    "favorites": lambda p: ["--type", "favorites", "--top", str(p.get("top", 10))],
    "compare": lambda p: ["--type", "compare", "--players", ", ".join(p.get("players", []))],
    "movers": lambda p: ["--type", "movers", "--direction", p.get("direction", "fallers"),
                         "--top", str(p.get("top", 5))],
    "value": lambda p: ["--type", "value", "--top", str(p.get("top", 5))],
    "value_carousel": lambda p: ["--type", "value_carousel", "--top", str(p.get("top", 5))],
    "hypothetical": lambda p: ["--type", "hypothetical", "--mover", p.get("mover", ""),
                               "--to", str(p.get("to_rank")), "--from", str(p.get("from_rank") or 0)],
}

# content_slots that produce MULTIPLE images (an Instagram carousel) instead
# of one -- generate_graphic()/publish_prepared_post() branch on this set.
CAROUSEL_SLOTS = {"value_carousel"}

WROTE_RE = re.compile(r"^Wrote (.+?)\s+\[theme=(\S+) variant=(\S+) layout=(\S+)\]", re.MULTILINE)
WROTE_SLIDE_RE = re.compile(r"^Wrote (.+?)\s+\[slide=(\d+)/(\d+) theme=(\S+) variant=(\S+) layout=(\S+)\]",
                            re.MULTILINE)


def generate_graphic(chosen_slot: str, params: dict) -> dict:
    if chosen_slot not in GRAPHIC_ARG_BUILDERS:
        raise ValueError(f"No graphic-arg builder for content_slot={chosen_slot!r}")
    extra_args = GRAPHIC_ARG_BUILDERS[chosen_slot](params)
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "generate_ranking_graphic.py")] + extra_args
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"generate_ranking_graphic.py failed: {result.stderr.strip()[-800:]}")

    m = WROTE_RE.search(result.stdout)
    if not m:
        raise RuntimeError(f"Could not parse output path from generate_ranking_graphic.py stdout: {result.stdout!r}")
    return {"image_path": m.group(1).strip(), "theme": m.group(2), "variant": m.group(3), "layout": m.group(4)}


def generate_carousel_graphics(chosen_slot: str, params: dict) -> dict:
    """Same idea as generate_graphic() but for a CAROUSEL_SLOTS content type:
    generate_ranking_graphic.py prints one "Wrote ... [slide=i/N ...]" line
    per slide instead of a single WROTE_RE line, so this parses all of them
    and returns the whole ordered list under "image_paths" (plus
    "image_path" = the first slide, for any caller that only looks at the
    singular field, e.g. the interactive-mode print block)."""
    if chosen_slot not in GRAPHIC_ARG_BUILDERS:
        raise ValueError(f"No graphic-arg builder for content_slot={chosen_slot!r}")
    extra_args = GRAPHIC_ARG_BUILDERS[chosen_slot](params)
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "generate_ranking_graphic.py")] + extra_args
    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        raise RuntimeError(f"generate_ranking_graphic.py failed: {result.stderr.strip()[-800:]}")

    matches = sorted(WROTE_SLIDE_RE.finditer(result.stdout), key=lambda m: int(m.group(2)))
    if not matches:
        raise RuntimeError(f"Could not parse any carousel slide paths from stdout: {result.stdout!r}")
    image_paths = [m.group(1).strip() for m in matches]
    last = matches[-1]
    return {
        "image_paths": image_paths,
        "image_path": image_paths[0],
        "theme": last.group(4), "variant": last.group(5), "layout": last.group(6),
    }


# ---------------------------------------------------------------------------
# Steps 5-7: publish an already-generated (graphic, caption) pair. Shared by
# run_once() (interactive/--auto paths) and review_pending.py (approving a
# --queue'd post), so both go through identical logic.
# ---------------------------------------------------------------------------
def publish_prepared_post(decision: dict, graphic: dict, caption: str) -> dict:
    import content_history as ch
    import image_hosting
    import test_post

    chosen_slot, params = decision["chosen_slot"], decision["params"]
    is_carousel = "image_paths" in graphic and graphic["image_paths"]

    if is_carousel:
        # 5. Upload every slide in one commit/push, in slide order.
        image_urls = with_retries(image_hosting.publish_images, "publish_images", graphic["image_paths"])
        log.info("Carousel images hosted (%d slides): %s", len(image_urls), image_urls)

        # 6. One carousel-item container per slide (no per-slide caption --
        # IG only allows one caption, set on the parent container), then the
        # parent CAROUSEL container carries it, then publish same as single.
        children_ids = [
            with_retries(test_post.create_carousel_item, "create_carousel_item", url)
            for url in image_urls
        ]
        parent_id = with_retries(test_post.create_carousel_container, "create_carousel_container",
                                 children_ids, caption)
        time.sleep(IG_PUBLISH_WAIT_SECONDS)
        publish_result = with_retries(test_post.publish_container, "publish_container", parent_id)
        media_id = publish_result.get("id")
        log.info("Published carousel to Instagram. Media ID: %s", media_id)

        record = ch.log_post(
            content_slot=chosen_slot,
            featured_players=decision.get("subjects", []),
            parameters=params,
            layout=graphic["layout"],
            theme=graphic["theme"],
            caption_hook=caption.split("\n")[0][:140],
            image_paths=graphic["image_paths"],
            ig_media_id=media_id,
        )
        log.info("Post logged to outputs/post_history.json.")
        return {**decision, "published": True, "ig_media_id": media_id, "record": record}

    # 5. Upload image
    image_url = with_retries(image_hosting.publish_image, "publish_image", graphic["image_path"])
    log.info("Image hosted at: %s", image_url)

    # 6. Publish to Instagram
    container_id = with_retries(test_post.create_media_container, "create_media_container", image_url, caption)
    time.sleep(IG_PUBLISH_WAIT_SECONDS)
    publish_result = with_retries(test_post.publish_container, "publish_container", container_id)
    media_id = publish_result.get("id")
    log.info("Published to Instagram. Media ID: %s", media_id)

    # 7. Log the post
    record = ch.log_post(
        content_slot=chosen_slot,
        featured_players=decision.get("subjects", []),
        parameters=params,
        layout=graphic["layout"],
        theme=graphic["theme"],
        caption_hook=caption.split("\n")[0][:140],
        image_path=graphic["image_path"],
        ig_media_id=media_id,
    )
    log.info("Post logged to outputs/post_history.json.")
    return {**decision, "published": True, "ig_media_id": media_id, "record": record}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_once(auto: bool = False, dry_run: bool = False, refresh: bool = True, queue: bool = False) -> dict:
    import content_brain
    import caption_generator
    import pending_posts

    log.info("=== Orchestrator run starting (auto=%s dry_run=%s queue=%s) ===", auto, dry_run, queue)

    # 1. Refresh data if necessary
    if refresh:
        try:
            with_retries(refresh_rankings_if_stale, "refresh_rankings")
        except Exception as e:
            log.error("Refresh failed, continuing with existing rankings CSV: %s", e)

    # 2. Run the brain
    decision = content_brain.run_brain()
    log.info("Brain decision: %s", json.dumps(decision))
    if not decision.get("chosen_slot"):
        log.warning("No eligible content this run -- exiting without posting. Reason: %s",
                    decision.get("reasoning"))
        return decision

    chosen_slot, params = decision["chosen_slot"], decision["params"]

    # 3. Generate the graphic(s)
    if chosen_slot in CAROUSEL_SLOTS:
        graphic = with_retries(generate_carousel_graphics, "generate_carousel_graphics", chosen_slot, params)
        log.info("Carousel ready (%d slides): %s", len(graphic["image_paths"]), graphic["image_paths"])
    else:
        graphic = with_retries(generate_graphic, "generate_graphic", chosen_slot, params)
        log.info("Graphic ready: %s", graphic["image_path"])

    # 4. Generate the caption
    caption_result = with_retries(
        caption_generator.generate_caption, "generate_caption",
        chosen_slot, params, f"{chosen_slot} post"
    )
    caption = caption_result["full_caption"]
    log.info("Caption ready (%d chars).", len(caption))

    if dry_run:
        dry_run_path = os.path.join(PROJECT_ROOT, "outputs", "dry_run_last.json")
        with open(dry_run_path, "w", encoding="utf-8") as f:
            json.dump({**decision, "graphic": graphic, "caption": caption}, f, indent=2)
        log.info("--dry-run set -- skipping queue/git push/Instagram publish.")
        log.info("Caption + decision saved to %s", dry_run_path)
        return {**decision, "published": False, "image_path": graphic["image_path"], "caption": caption}

    if queue:
        # Unattended (Task Scheduler) mode -- never blocks on input(), never
        # publishes directly. A human reviews with review_pending.py.
        entry = pending_posts.add_pending(decision, graphic, caption)
        log.info("Queued for review as %s (outputs/pending_posts.json).", entry["id"])
        return {**decision, "published": False, "queued": True, "pending_id": entry["id"]}

    if auto is False:
        print("\n" + "=" * 70)
        print(f"CONTENT SLOT : {chosen_slot}")
        print(f"SUBJECTS     : {decision.get('subjects')}")
        print(f"PRIORITY     : {decision.get('priority')}")
        print(f"REASONING    : {decision.get('reasoning')}")
        if "image_paths" in graphic and graphic["image_paths"]:
            print(f"IMAGES       : {len(graphic['image_paths'])}-slide carousel")
            for i, p in enumerate(graphic["image_paths"], start=1):
                print(f"               slide {i}: {p}")
        else:
            print(f"IMAGE        : {graphic['image_path']}")
        print("-" * 70)
        print(caption)
        print("=" * 70)
        answer = input("Publish this post? [y/N]: ").strip().lower()
        if answer != "y":
            log.info("Run aborted by approval gate (user declined).")
            return {**decision, "published": False}

    return publish_prepared_post(decision, graphic, caption)


def main():
    parser = argparse.ArgumentParser(description="Blitz Culture master posting pipeline.")
    parser.add_argument("--auto", action="store_true",
                        help="Skip the manual approval prompt (full autonomy). Default: prompt before publishing.")
    parser.add_argument("--queue", action="store_true",
                        help="Unattended mode for Task Scheduler: generate + caption, then queue to "
                             "outputs/pending_posts.json for review_pending.py instead of publishing or prompting.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate the graphic + caption but skip queueing, git push, and Instagram publish.")
    parser.add_argument("--no-refresh", action="store_true",
                        help="Skip the stale-rankings refresh check.")
    args = parser.parse_args()

    if args.auto and args.queue:
        raise SystemExit("--auto and --queue are mutually exclusive -- pick one.")

    try:
        run_once(auto=args.auto, dry_run=args.dry_run, refresh=not args.no_refresh, queue=args.queue)
    except Exception as e:  # noqa: BLE001
        log_failure("run_once", e)
        raise


if __name__ == "__main__":
    main()
