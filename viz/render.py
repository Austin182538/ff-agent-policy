"""Render an HTML string to a PNG using a locally-installed headless Chrome
or Edge -- no extra dependency to install (no Playwright/chromium download),
which keeps the whole graphics pipeline self-contained and automatable.

Both Chrome and Edge ship a `--screenshot` CLI mode. We render at a 2x device
scale factor for crisp, retina-quality output (a 1080x1350 canvas -> a
2160x2700 PNG).
"""

import os
import shutil
import subprocess
import tempfile
from typing import Optional

# Prefer Chrome, fall back to Edge (always present on Windows).
_BROWSER_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return env
    for path in _BROWSER_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "No Chrome/Edge found for rendering. Set the CHROME_PATH env var to a "
        "Chromium-based browser executable."
    )


def html_to_png(
    html: str,
    out_path: str,
    width: int = 1080,
    height: int = 1350,
    scale: int = 2,
    browser: Optional[str] = None,
) -> str:
    """Render `html` to a PNG at `out_path`. Returns the absolute output path.

    The HTML's root element should be sized to exactly width x height px with
    overflow hidden so the viewport screenshot is a clean, full-bleed crop.
    """
    browser = browser or find_browser()
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Fresh throwaway profile so a browser the user already has open doesn't
    # collide with this headless run.
    tmp_profile = tempfile.mkdtemp(prefix="viz_chrome_")
    fd, html_path = tempfile.mkstemp(suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)

    try:
        url = "file:///" + html_path.replace("\\", "/")
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={tmp_profile}",
            f"--force-device-scale-factor={scale}",
            f"--window-size={width},{height}",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",  # give CDN logos time to load
            f"--screenshot={out_path}",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if not os.path.exists(out_path):
            raise RuntimeError(
                "Headless screenshot did not produce a file.\n"
                f"stdout: {result.stdout.decode(errors='ignore')}\n"
                f"stderr: {result.stderr.decode(errors='ignore')}"
            )
        return out_path
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass
        shutil.rmtree(tmp_profile, ignore_errors=True)
