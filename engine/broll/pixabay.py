"""Pixabay free stock video (Pexels paused new API keys in Nov 2026). Never fails a video: any problem
returns None and the renderer uses a dark background.

Pixabay only accepts the key as a URL parameter, so it's an exception to "tokens in headers": errors and
logs carry the exception type only, never the message or URL.
"""
import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from engine.broll.pexels import download
from engine.config import secret

log = logging.getLogger(__name__)
SEARCH = "https://pixabay.com/api/videos/"


def _best(hit: dict) -> dict | None:
    files = [f for f in (hit.get("videos") or {}).values() if isinstance(f, dict) and f.get("url") and f.get("height")]
    return max(files, key=lambda f: f["height"] * f.get("width", 0)) if files else None


def fetch(query: str, out_dir: Path, *, rng, http=requests, min_dur: float = 3.0) -> Path | None:
    try:
        r = http.get(SEARCH, params={"key": secret("PIXABAY_API_KEY"), "q": query, "per_page": 20,
                                     "safesearch": "true"}, timeout=30)
        r.raise_for_status()
        options = [(h, f) for h in r.json().get("hits", []) if h.get("duration", 0) >= min_dur and (f := _best(h))]
        portrait = [o for o in options if o[1]["height"] > o[1].get("width", 0)]
        if portrait:
            v, f = rng.choice(portrait)
        elif options:  # landscape: object-fit: cover crops it to 9:16, so take the sharpest
            v, f = max(options, key=lambda o: o[1]["height"])
        else:
            return None
        vid, h = int(v["id"]), int(f["height"])  # remote values: numbers only in the file name
        link = urlparse(str(f["url"]))
        if link.scheme != "https" or not (link.hostname or "").endswith(".pixabay.com"):
            raise ValueError("unexpected download host")
        return download(http, link.geturl(), Path(out_dir).resolve() / f"pixabay_{vid}_{h}.mp4")
    except Exception as e:  # noqa: BLE001 - b-roll is optional; never echo the message (the URL carries the key)
        log.warning("pixabay b-roll skipped: %s", type(e).__name__)
        return None
