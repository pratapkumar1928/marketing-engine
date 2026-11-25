"""Pexels free stock video. Never fails a video: any problem returns None and the renderer uses a dark background."""
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from engine.config import secret

log = logging.getLogger(__name__)
SEARCH = "https://api.pexels.com/videos/search"
MAX_BYTES = 150 * 1024 * 1024


def _pick_file(video: dict) -> dict | None:
    portrait = [f for f in video.get("video_files", []) if f.get("height", 0) > f.get("width", 0)]
    if not portrait:
        return None
    hd = [f for f in portrait if f["height"] >= 1920]
    return min(hd, key=lambda f: f["height"]) if hd else max(portrait, key=lambda f: f["height"])


def download(http, url: str, out: Path) -> Path:
    """Fetch url into out (cached by name), capped at MAX_BYTES. Shared by the b-roll providers."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        dl = http.get(url, stream=True, timeout=120)
        dl.raise_for_status()
        part, written = out.with_suffix(".part"), 0
        try:
            with open(part, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 16):
                    written += len(chunk)
                    if written > MAX_BYTES:
                        raise ValueError("download too large")
                    fh.write(chunk)
            part.replace(out)
        finally:
            part.unlink(missing_ok=True)
    return out


def fetch(query: str, out_dir: Path, *, rng, http=requests, min_dur: float = 3.0) -> Path | None:
    try:
        key = secret("PEXELS_API_KEY")
        r = http.get(SEARCH, headers={"Authorization": key},
                     params={"query": query, "orientation": "portrait", "per_page": 15}, timeout=30)
        r.raise_for_status()
        options = []
        for v in r.json().get("videos", []):
            f = _pick_file(v) if v.get("duration", 0) >= min_dur else None
            if f:
                options.append((v, f))
        if not options:
            return None
        v, f = rng.choice(options)
        vid, h = int(v["id"]), int(f["height"])  # remote values: numbers only in the file name
        link = urlparse(str(f["link"]))
        if link.scheme != "https" or not (link.hostname or "").endswith(".pexels.com"):
            raise ValueError("unexpected download host")
        return download(http, link.geturl(), Path(out_dir).resolve() / f"pexels_{vid}_{h}.mp4")
    except Exception as e:  # noqa: BLE001 - b-roll is optional; never echo the message (may carry the key)
        log.warning("pexels b-roll skipped: %s", type(e).__name__)
        return None
