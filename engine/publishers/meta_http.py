"""Shared Graph API plumbing for Instagram + Facebook. Token goes in a header; errors never carry URLs, params or tokens."""
import requests

from engine.config import secret
from engine.types import PublishError

GRAPH = "https://graph.facebook.com/v21.0"
RUPLOAD_HOST = "https://rupload.facebook.com/"


def creds(app: dict) -> dict:
    m = app["meta"]
    return {"ig": secret(m["ig_user_id_secret"]) if m.get("ig_user_id_secret") else None,
            "page": secret(m["page_id_secret"]) if m.get("page_id_secret") else None,
            "token": secret(m["token_secret"])}


def call(http, method: str, url: str, *, token: str, creates_post: bool, step: str, headers=None, **kw) -> dict:
    """One Graph call. A post-creating call with an unknown outcome is not retryable (it may have posted)."""
    try:
        r = http.request(method, url, headers={"Authorization": f"OAuth {token}", **(headers or {})}, timeout=120, **kw)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001 - message may embed the URL / token: report the type only
        status = getattr(getattr(e, "response", None), "status_code", None)
        retryable = (not creates_post) or isinstance(e, requests.ConnectTimeout) or status == 429
        note = "" if retryable else "; may have posted, check before retrying"
        raise PublishError(f"{step} failed: {type(e).__name__}{f' {status}' if status else ''}{note}",
                           retryable=retryable) from None
