"""Facebook Page Reels: start -> upload bytes -> finish(PUBLISHED)."""
from pathlib import Path

import requests

from engine.publishers.meta_http import GRAPH, RUPLOAD_HOST, call, creds
from engine.types import PublishError, Published


def publish(video: Path, caption: str, app: dict, *, http=requests, **_) -> Published:
    c = creds(app)
    tok, page = c["token"], c["page"]
    start = call(http, "POST", f"{GRAPH}/{page}/video_reels", token=tok, creates_post=False, step="fb start",
                 data={"upload_phase": "start"})
    vid, upload_url = str(start["video_id"]), str(start["upload_url"])
    if not upload_url.startswith(RUPLOAD_HOST):  # never hand the page token to another host
        raise PublishError("fb start returned an unexpected upload host", retryable=False)
    data = Path(video).read_bytes()
    call(http, "POST", upload_url, token=tok, creates_post=False, step="fb upload",
         headers={"offset": "0", "file_size": str(len(data))}, data=data)
    call(http, "POST", f"{GRAPH}/{page}/video_reels", token=tok, creates_post=True, step="fb finish",
         data={"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": caption})
    return Published(platform="facebook", post_id=vid, url=f"https://www.facebook.com/reel/{vid}")
