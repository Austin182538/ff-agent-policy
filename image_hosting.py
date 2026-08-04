"""
Blitz Culture -- Image hosting (Phase 1)
--------------------------------------------
Instagram's Graph API can't upload a local file -- it needs a publicly
reachable image_url. Per the roadmap, the dev-time approach is: push the
generated PNG to the project's public GitHub repo and use the
raw.githubusercontent.com URL. Swap this module out for Cloudflare
R2/S3 later without touching orchestrator.py -- it only depends on
`publish_image(path) -> url`.

Note: outputs/graphics/ is gitignored (see .gitignore) so day-to-day dev
runs don't spam the repo -- this module force-adds the one file being
published, not the whole folder.
"""
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
GITHUB_REPO = "Austin182538/ff-agent-policy"
GITHUB_BRANCH = "main"


class ImageHostingError(RuntimeError):
    pass


def _run_git(args: list) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git"] + args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60,
    )
    return result


def publish_image_to_github(image_path: str) -> str:
    """Force-adds, commits, and pushes a single PNG, then returns its
    raw.githubusercontent.com URL. Raises ImageHostingError on any git
    failure (caller should retry / surface to failure logging)."""
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        raise ImageHostingError(f"Image not found: {abs_path}")

    rel_path = os.path.relpath(abs_path, PROJECT_ROOT).replace(os.sep, "/")

    add = _run_git(["add", "-f", rel_path])
    if add.returncode != 0:
        raise ImageHostingError(f"git add failed: {add.stderr.strip()}")

    commit = _run_git(["commit", "-m", f"post: {os.path.basename(rel_path)}"])
    if commit.returncode != 0:
        # "nothing to commit" happens if this exact file was already pushed
        # (e.g. a retry after a successful add but failed push) -- not fatal.
        if "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise ImageHostingError(f"git commit failed: {commit.stderr.strip()}")

    push = _run_git(["push", "origin", GITHUB_BRANCH])
    if push.returncode != 0:
        raise ImageHostingError(f"git push failed: {push.stderr.strip()}")

    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{rel_path}"


# Back-compat / future-proofing: orchestrator.py calls this generic name so
# swapping to R2/S3 later is a one-function change.
def publish_image(image_path: str) -> str:
    return publish_image_to_github(image_path)


def publish_images(image_paths: list) -> list:
    """Carousel version of publish_image_to_github: force-adds every slide,
    ONE commit + ONE push for the whole set (not one push per image -- keeps
    a carousel post to a single commit and avoids N round-trips to GitHub),
    then returns each image's raw.githubusercontent.com URL in the SAME
    order as image_paths, since carousel slide order matters (swipe order)."""
    if not image_paths:
        raise ImageHostingError("publish_images() called with an empty list.")

    rel_paths = []
    for image_path in image_paths:
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            raise ImageHostingError(f"Image not found: {abs_path}")
        rel_paths.append(os.path.relpath(abs_path, PROJECT_ROOT).replace(os.sep, "/"))

    add = _run_git(["add", "-f"] + rel_paths)
    if add.returncode != 0:
        raise ImageHostingError(f"git add failed: {add.stderr.strip()}")

    commit = _run_git(["commit", "-m", f"post: carousel ({len(rel_paths)} slides)"])
    if commit.returncode != 0:
        if "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise ImageHostingError(f"git commit failed: {commit.stderr.strip()}")

    push = _run_git(["push", "origin", GITHUB_BRANCH])
    if push.returncode != 0:
        raise ImageHostingError(f"git push failed: {push.stderr.strip()}")

    return [f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{rel}" for rel in rel_paths]


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python image_hosting.py <path-to-png>")
    print(publish_image(sys.argv[1]))
