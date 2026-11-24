"""YouTube Shorts via Data API v3 resumable upload: refresh token -> start session -> PUT bytes.

A vertical video under 3 minutes is a Short; no #Shorts tag needed. Tokens go in headers/bodies,
never URLs; errors carry the step and exception type only.
"""
from pathlib import Path

import requests

from engine.config import secret
from engine.types import PublishError, Published

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
UPLOAD_HOST = "https://www.googleapis.com/upload/"


def title_of(caption: str) -> str:
    """First line of the caption, cut to YouTube's 100-char title limit on a word boundary."""
    line = caption.strip().splitlines()[0] if caption.strip() else ""
    return line if len(line) <= 100 else line[:100].rsplit(" ", 1)[0].rstrip()


def _call(http, method: str, url: str, *, creates_post: bool, step: str, **kw):
    try:
        r = http.request(method, url, timeout=300, **kw)
        r.raise_for_status()
        return r
    except Exception as e:  # noqa: BLE001 - message may embed tokens: report the type only
        status = getattr(getattr(e, "response", None), "status_code", None)
        retryable = (not creates_post) or isinstance(e, requests.ConnectTimeout) or status == 429
        note = "" if retryable else "; may have posted, check before retrying"
        raise PublishError(f"{step} failed: {type(e).__name__}{f' {status}' if status else ''}{note}",
                           retryable=retryable) from None


def publish(video: Path, caption: str, app: dict, *, http=requests, **_) -> Published:
    y = app["youtube"]
    tok = _call(http, "POST", TOKEN_URL, creates_post=False, step="yt token",
                data={"client_id": secret(y["client_id_secret"]), "client_secret": secret(y["client_secret_secret"]),
                      "refresh_token": secret(y["refresh_token_secret"]), "grant_type": "refresh_token"}).json()
    auth = {"Authorization": f"Bearer {tok['access_token']}"}
    data = Path(video).read_bytes()
    body = {"snippet": {"title": title_of(caption), "description": caption, "categoryId": "22"},
            # clip remixes use AI-generated realistic people: YouTube wants that disclosed
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}
    start = _call(http, "POST", UPLOAD_URL, creates_post=False, step="yt start", json=body,
                  headers={**auth, "X-Upload-Content-Length": str(len(data)), "X-Upload-Content-Type": "video/mp4"})
    session = start.headers.get("Location", "")
    if not session.startswith(UPLOAD_HOST):  # never hand the token to another host
        raise PublishError("yt start returned an unexpected upload host", retryable=True)
    vid = _call(http, "PUT", session, creates_post=True, step="yt upload", data=data,
                headers={**auth, "Content-Type": "video/mp4"}).json()["id"]
    return Published(platform="youtube", post_id=str(vid), url=f"https://www.youtube.com/shorts/{vid}")
