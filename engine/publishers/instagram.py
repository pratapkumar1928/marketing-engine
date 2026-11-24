"""Instagram Reels via the Graph API resumable upload (no public video URL needed)."""
import logging
import time
from pathlib import Path

import requests

from engine.publishers.meta_http import GRAPH, RUPLOAD_HOST, call, creds
from engine.types import PublishError, Published

log = logging.getLogger(__name__)
POLL_SECONDS, POLL_TRIES = 5, 60


def publish(video: Path, caption: str, app: dict, *, http=requests, sleep=time.sleep) -> Published:
    c = creds(app)
    tok, ig = c["token"], c["ig"]
    cid = call(http, "POST", f"{GRAPH}/{ig}/media", token=tok, creates_post=False, step="ig container",
               data={"media_type": "REELS", "upload_type": "resumable", "caption": caption})["id"]
    data = Path(video).read_bytes()
    call(http, "POST", f"{RUPLOAD_HOST}ig-api-upload/v21.0/{cid}", token=tok, creates_post=False, step="ig upload",
         headers={"offset": "0", "file_size": str(len(data))}, data=data)
    for _ in range(POLL_TRIES):
        st = call(http, "GET", f"{GRAPH}/{cid}", token=tok, creates_post=False, step="ig status",
                  params={"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            raise PublishError("ig container processing ERROR", retryable=False)
        sleep(POLL_SECONDS)
    else:
        raise PublishError("ig container not ready in time", retryable=True)
    media_id = call(http, "POST", f"{GRAPH}/{ig}/media_publish", token=tok, creates_post=True, step="ig publish",
                    data={"creation_id": cid})["id"]
    url = "https://www.instagram.com/"
    try:  # after the post exists nothing may raise, or a retry would double-post
        url = call(http, "GET", f"{GRAPH}/{media_id}", token=tok, creates_post=False, step="ig permalink",
                   params={"fields": "permalink"}).get("permalink", url)
    except PublishError as e:
        log.warning("posted, but %s", e)
    return Published(platform="instagram", post_id=str(media_id), url=url)
