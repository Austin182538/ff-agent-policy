"""
Headshot cleanup cache.

The raw headshot images pulled from data/bettingpros_player_props_2026.csv
(FantasyPros headshot URLs) are studio photos shot on a green/blue screen and
already chroma-keyed + flattened onto a solid background by the source. Thin
hair strands often keep a light halo/fringe baked directly into the flattened
pixels -- CSS-side tricks (cropping, scaling, mask fades) can't remove that,
because it isn't a transparency edge, it's part of the actual image content.

This module re-segments each headshot with rembg (a background-removal model)
to produce a properly alpha-matted cutout with the fringe gone, and caches the
cleaned result locally as a PNG so the network + model only get hit once per
player, ever. If rembg isn't installed or a fetch/process fails, every
function here fails soft and hands back the original URL so a render never
breaks because of this.

Setup (run once, on a machine with normal internet access -- this needs to
download the segmentation model on first use):
    pip install rembg onnxruntime

Usage:
    from viz.headshot_cache import get_clean_headshot

    src = get_clean_headshot(url)   # -> data URI on success, original url
                                     #    unchanged if cleanup wasn't possible
"""
import base64
import hashlib
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(PROJECT_ROOT, "outputs", "headshot_cache")

_REMBG_SESSION = None
_REMBG_AVAILABLE = None


def _rembg_available() -> bool:
    global _REMBG_AVAILABLE
    if _REMBG_AVAILABLE is None:
        try:
            import rembg  # noqa: F401
            _REMBG_AVAILABLE = True
        except ImportError:
            _REMBG_AVAILABLE = False
    return _REMBG_AVAILABLE


def _cache_path(url: str) -> str:
    key = hashlib.md5(url.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{key}.png")


def _download(url: str, timeout: int = 15) -> bytes:
    import requests
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.content


def _matte(raw_bytes: bytes) -> bytes:
    """Run background removal and return clean PNG bytes with real alpha."""
    from rembg import remove, new_session
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        # u2net_human_seg is tuned for people/portraits rather than generic
        # objects -- it holds up much better on hair/edge detail than the
        # default general-purpose u2net model.
        _REMBG_SESSION = new_session("u2net_human_seg")
    return remove(raw_bytes, session=_REMBG_SESSION)


def clean_headshot_path(url: str):
    """
    Return a local filesystem path to a cleanly-matted PNG for this headshot
    URL, downloading + processing it once and caching the result on disk.
    Returns None (never raises) if rembg isn't installed or the image can't
    be fetched/processed -- callers should fall back to the original url.
    """
    if not url or not isinstance(url, str):
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(url)
    if os.path.exists(path):
        return path
    if not _rembg_available():
        return None
    try:
        raw = _download(url)
        clean = _matte(raw)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(clean)
        os.replace(tmp, path)
        return path
    except Exception as e:
        print(f"[headshot_cache] failed to clean headshot ({url}): {e}")
        return None


def get_clean_headshot(url: str) -> str:
    """
    Best-effort: return a base64 data: URI for a cleaned, halo-free cutout of
    this headshot. Falls back to the original url unchanged if cleanup isn't
    possible (rembg missing, download failure, bad image, etc.) so the
    render pipeline never breaks on a single bad photo.
    """
    if not url:
        return url
    path = clean_headshot_path(url)
    if not path:
        return url
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        print(f"[headshot_cache] failed to read cached headshot ({path}): {e}")
        return url


def warm_cache(urls) -> dict:
    """
    Pre-clean a batch of headshot URLs (e.g. every player in the rankings
    CSV) so a later render never pays the download+model cost mid-run.
    Returns {url: success_bool}.
    """
    results = {}
    for url in urls:
        if not url:
            continue
        results[url] = clean_headshot_path(url) is not None
    return results
