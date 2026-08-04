"""
Blitz Culture -- Review queued posts (Phase 6)
----------------------------------------------------
During semi-autonomous testing, the scheduled task runs
`orchestrator.py --queue`, which generates each post but parks it in
outputs/pending_posts.json instead of publishing. Run this script (by hand,
whenever you check in) to review what's queued: approve to publish it for
real, reject to discard it and leave a note in outputs/rejected_posts.json
for later pattern-spotting (repeated content, bad captions, etc. -- see
PHASE6_TESTING.md).

Usage:
    venv\\Scripts\\python.exe review_pending.py            # interactive review, one by one
    venv\\Scripts\\python.exe review_pending.py --list      # just list what's queued, no prompts
"""
import argparse

import pending_posts
from orchestrator import publish_prepared_post, log_failure


def _print_entry(entry: dict) -> None:
    decision = entry["decision"]
    print("\n" + "=" * 70)
    print(f"ID           : {entry['id']}")
    print(f"QUEUED AT    : {entry['queued_at']}")
    print(f"CONTENT SLOT : {decision.get('chosen_slot')}")
    print(f"SUBJECTS     : {decision.get('subjects')}")
    print(f"PRIORITY     : {decision.get('priority')}")
    print(f"REASONING    : {decision.get('reasoning')}")
    graphic = entry["graphic"]
    if graphic.get("image_paths"):
        print(f"IMAGES       : {len(graphic['image_paths'])}-slide carousel")
        for i, p in enumerate(graphic["image_paths"], start=1):
            print(f"               slide {i}: {p}")
    else:
        print(f"IMAGE        : {graphic['image_path']}")
    print(f"THEME/LAYOUT : {graphic['theme']} / {graphic['layout']}")
    print("-" * 70)
    print(entry["caption"])
    print("=" * 70)


def review_all() -> None:
    items = pending_posts.load_pending()
    if not items:
        print("Nothing queued -- outputs/pending_posts.json is empty.")
        return

    print(f"{len(items)} post(s) queued for review.\n")
    for entry in list(items):
        _print_entry(entry)
        answer = input("[a]pprove & publish / [r]eject / [s]kip for now? ").strip().lower()
        if answer == "a":
            try:
                result = publish_prepared_post(entry["decision"], entry["graphic"], entry["caption"])
                pending_posts.remove_pending(entry["id"])
                print(f"Published. Instagram media ID: {result.get('ig_media_id')}")
            except Exception as e:  # noqa: BLE001
                log_failure("review_pending.approve", e, {"pending_id": entry["id"]})
                print(f"Publish failed, left in queue for retry: {e}")
        elif answer == "r":
            reason = input("Reason (optional, for the reject log): ").strip()
            pending_posts.remove_pending(entry["id"])
            pending_posts.log_rejected(entry, reason)
            print("Rejected and logged to outputs/rejected_posts.json.")
        else:
            print("Skipped -- still queued for next review.")


def list_only() -> None:
    items = pending_posts.load_pending()
    if not items:
        print("Nothing queued.")
        return
    for entry in items:
        d = entry["decision"]
        print(f"{entry['id']:<28} slot={d.get('chosen_slot'):<12} priority={d.get('priority'):<8} "
              f"subjects={d.get('subjects')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="List queued posts without prompting for review.")
    args = parser.parse_args()
    if args.list:
        list_only()
    else:
        review_all()


if __name__ == "__main__":
    main()
