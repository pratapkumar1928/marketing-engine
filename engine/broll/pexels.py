"""Pexels free stock video. Never fails a video: any problem returns None and the renderer uses a dark background."""
import logging
from pathlib import Path

import requests

from engine.config import secret

log = logging.getLogger(__name__)
SEARCH = "https://api.pexels.com/videos/search"


def _pick_file(video: dict) -> dict | None:
    portrait = [f for f in video.get("video_files", []) if f.get("height", 0) > f.get("width", 0)]
    if not portrait:
        return None
    hd = [f for f in portrait if f["height"] >= 1920]
    return min(hd, key=lambda f: f["height"]) if hd else max(portrait, key=lambda f: f["height"])


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
        out = Path(out_dir) / f"pexels_{v['id']}_{f['height']}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.exists():
            dl = http.get(f["link"], stream=True, timeout=120)
            dl.raise_for_status()
            with open(out, "wb") as fh:
                for chunk in dl.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
        return out
    except Exception as e:  # noqa: BLE001 - b-roll is optional; never echo the message (may carry the key)
        log.warning("pexels b-roll skipped: %s", type(e).__name__)
        return None
