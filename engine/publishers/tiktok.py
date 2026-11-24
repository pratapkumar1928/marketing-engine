"""TikTok inbox drafts (Content Posting API "Upload", scope video.upload).

Each video lands in the TikTok app's inbox; Pratap taps the notification, pastes the caption (sent to
Telegram, since inbox uploads can't carry one) and posts. TikTok allows at most 5 pending drafts per 24 h.

Tokens: TikTok refresh tokens rotate (the old one dies on use), so they can't live in a GitHub secret.
They live in state/<app>/tiktok_token.enc, Fernet-encrypted with the TIKTOK_TOKEN_KEY secret, and are
refreshed only when the access token is near expiry. A refresh is saved to disk and pushed at once
(gitsync, in CI), before the token is used. First token: tools/tiktok_auth.py.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from cryptography.fernet import Fernet

from engine.config import secret
from engine.types import PublishError, Published

log = logging.getLogger(__name__)
API = "https://open.tiktokapis.com/v2"
TOKEN_URL = f"{API}/oauth/token/"
INIT_URL = f"{API}/post/publish/inbox/video/init/"
STATUS_URL = f"{API}/post/publish/status/fetch/"
MAX_SINGLE_CHUNK = 64 * 1024 * 1024
POLL_SECONDS, POLL_TRIES = 10, 30
DONE = {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}


def token_path(app: dict) -> Path:
    return Path(app["dir"]).parent.parent / "state" / app["slug"] / "tiktok_token.enc"


def save_token(path: Path, key: str, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(Fernet(key).encrypt(json.dumps(data).encode()))
    os.replace(tmp, path)


def load_token(path: Path, key: str) -> dict:
    return json.loads(Fernet(key).decrypt(path.read_bytes()))


def _safe(code) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(code).lower())[:60]


def _api(http, method: str, url: str, *, creates_post: bool, step: str, **kw) -> dict:
    """One call. Errors carry step, HTTP status and TikTok's error code only (never tokens)."""
    try:
        r = http.request(method, url, timeout=300, **kw)
    except Exception as e:  # noqa: BLE001 - message may embed tokens: report the type only
        retryable = (not creates_post) or isinstance(e, requests.ConnectTimeout)
        note = "" if retryable else "; may have posted, check before retrying"
        raise PublishError(f"{step} failed: {type(e).__name__}{note}", retryable=retryable) from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    code = err.get("code") if isinstance(err, dict) else err  # oauth errors are plain strings
    if r.status_code >= 400 or code not in (None, "ok"):
        retryable = (not creates_post) or r.status_code == 429
        note = "" if retryable else "; may have posted, check before retrying"
        raise PublishError(f"{step} failed: {r.status_code} {_safe(code or '')}{note}".rstrip(), retryable=retryable)
    return body if isinstance(body, dict) else {}


def _default_checkpoint(root: Path) -> None:
    if os.environ.get("LEDGER_PUSH") == "1":
        from engine import gitsync
        gitsync.checkpoint(root)


def _default_notify(text: str) -> None:
    from engine import report
    report.send(text)


def access_token(app: dict, *, http, now: datetime, checkpoint) -> str:
    t = app["tiktok"]
    key, path = secret(t["token_key_secret"]), token_path(app)
    if not path.is_file():
        raise PublishError("no TikTok token: run tools/tiktok_auth.py and commit the .enc file", retryable=False)
    tok = load_token(path, key)
    if datetime.fromisoformat(tok["access_expires_at"]) - now > timedelta(minutes=10):
        return tok["access_token"]
    new = _api(http, "POST", TOKEN_URL, creates_post=False, step="tt token refresh",
               data={"client_key": secret(t["client_key_secret"]), "client_secret": secret(t["client_secret_secret"]),
                     "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    if not new.get("access_token") or not new.get("refresh_token"):
        raise PublishError("tt token refresh failed: no token in reply", retryable=True)
    save_token(path, key, {"access_token": new["access_token"], "refresh_token": new["refresh_token"],
                           "access_expires_at": (now + timedelta(seconds=int(new.get("expires_in", 3600)))).isoformat()})
    try:  # the old refresh token is dead now: get the new one to the remote before anything else can fail
        checkpoint(path.parent.parent.parent)
    except Exception as e:  # noqa: BLE001 - the end-of-run commit gets another try
        log.error("TikTok token saved but not pushed (%s); if it's lost, re-run tools/tiktok_auth.py", type(e).__name__)
    return new["access_token"]


def publish(video: Path, caption: str, app: dict, *, http=requests, sleep=time.sleep,
            now=lambda: datetime.now(timezone.utc), notify=_default_notify, checkpoint=_default_checkpoint) -> Published:
    data = Path(video).read_bytes()
    if len(data) > MAX_SINGLE_CHUNK:  # ponytail: one chunk only; our renders are ~10 MB. Chunk if that changes.
        raise PublishError("tt video over 64 MB (single-chunk upload only)", retryable=False)
    token = access_token(app, http=http, now=now(), checkpoint=checkpoint)
    auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    init = _api(http, "POST", INIT_URL, creates_post=False, step="tt init", headers=auth,
                json={"source_info": {"source": "FILE_UPLOAD", "video_size": len(data), "chunk_size": len(data),
                                      "total_chunk_count": 1}})["data"]
    pid, upload_url = str(init["publish_id"]), init["upload_url"]
    _api(http, "PUT", upload_url, creates_post=True, step="tt upload", data=data,
         headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}"})
    for _ in range(POLL_TRIES):  # the upload is accepted: from here only a definite FAILED may raise
        try:
            st = _api(http, "POST", STATUS_URL, creates_post=False, step="tt status", headers=auth,
                      json={"publish_id": pid}).get("data", {})
        except PublishError as e:
            log.warning("uploaded, but %s", e)
            break
        if st.get("status") in DONE:
            break
        if st.get("status") == "FAILED":
            raise PublishError(f"tt draft FAILED: {_safe(st.get('fail_reason', ''))}", retryable=False)
        sleep(POLL_SECONDS)
    else:
        log.warning("tt draft %s still processing; it should reach the inbox shortly", pid)
    try:
        notify(f"TikTok draft ready for {app.get('name', app['slug'])}. Open TikTok, tap the inbox notification, "
               f"paste this caption and post:\n\n{caption}")
    except Exception as e:  # noqa: BLE001 - the draft exists; a missed message must not fail the post
        log.warning("tt caption message not sent: %s", type(e).__name__)
    return Published(platform="tiktok", post_id=pid, url="(TikTok inbox draft: tap to post)")
