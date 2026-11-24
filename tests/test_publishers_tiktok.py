from datetime import datetime, timedelta, timezone

import pytest
import requests
from cryptography.fernet import Fernet

from engine.publishers import get as get_publisher
from engine.publishers import tiktok
from engine.types import PublishError

KEY = Fernet.generate_key().decode()
NOW = datetime(2026, 12, 5, 13, 0, tzinfo=timezone.utc)
UP = "https://open-upload.tiktokapis.com/upload/?upload_id=1&upload_token=x"
OLD_REFRESH, NEW_REFRESH = "rft.oldSecret", "rft.newSecret"


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("TT_KEY", "ck")
    monkeypatch.setenv("TT_SECRET", "cs")
    monkeypatch.setenv("TT_TOKEN_KEY", KEY)


@pytest.fixture
def app(tmp_path):
    d = tmp_path / "apps" / "demo"
    d.mkdir(parents=True)
    return {"slug": "demo", "dir": d, "tiktok": {"client_key_secret": "TT_KEY", "client_secret_secret": "TT_SECRET",
                                                  "token_key_secret": "TT_TOKEN_KEY"}}


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"0123456789")
    return p


class Resp:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        if self.payload is None:
            raise ValueError("no body")
        return self.payload


class FakeHTTP:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        exp_method, exp_url, out = self.script.pop(0)
        assert method == exp_method and exp_url in url, (method, url)
        if isinstance(out, Exception):
            raise out
        return out


def ok(data):
    return Resp({"data": data, "error": {"code": "ok", "message": ""}})


def store(app, expires_in_min=60):
    tiktok.save_token(tiktok.token_path(app), KEY, {
        "access_token": "act.cached", "refresh_token": OLD_REFRESH,
        "access_expires_at": (NOW + timedelta(minutes=expires_in_min)).isoformat()})


def post_script(status="SEND_TO_USER_INBOX"):
    return [("POST", tiktok.INIT_URL, ok({"publish_id": "P1", "upload_url": UP})),
            ("PUT", UP, Resp(status=201)),
            ("POST", tiktok.STATUS_URL, ok({"status": "PROCESSING_UPLOAD"})),
            ("POST", tiktok.STATUS_URL, ok({"status": status, "fail_reason": "file_format_check_failed"}))]


def run(app, video, http, **kw):
    sent, pushed = [], []
    kw = {"sleep": lambda s: None, "now": lambda: NOW, "notify": sent.append,
          "checkpoint": lambda root: pushed.append(root), **kw}
    out = tiktok.publish(video, "cap text\n\n#tag", app, http=http, **kw)
    return out, sent, pushed


def test_cached_token_flow(app, video):
    store(app)
    http = FakeHTTP(post_script())
    out, sent, pushed = run(app, video, http)
    assert out.platform == "tiktok" and out.post_id == "P1" and http.script == []
    init = http.calls[0][2]
    assert init["headers"]["Authorization"] == "Bearer act.cached"
    assert init["json"] == {"source_info": {"source": "FILE_UPLOAD", "video_size": 10, "chunk_size": 10,
                                            "total_chunk_count": 1}}
    put = http.calls[1][2]
    assert put["data"] == b"0123456789" and put["headers"]["Content-Range"] == "bytes 0-9/10"
    assert "Authorization" not in put["headers"]
    assert pushed == [] and len(sent) == 1 and "cap text" in sent[0] and "#tag" in sent[0]


def test_expired_token_refreshes_saves_and_pushes_first(app, video):
    store(app, expires_in_min=2)
    refresh = ("POST", tiktok.TOKEN_URL, Resp({"access_token": "act.new", "expires_in": 7200,
                                               "refresh_token": NEW_REFRESH, "refresh_expires_in": 15552000}))
    http = FakeHTTP([refresh] + post_script())
    out, _, pushed = run(app, video, http)
    assert http.calls[0][2]["data"] == {"client_key": "ck", "client_secret": "cs", "grant_type": "refresh_token",
                                        "refresh_token": OLD_REFRESH}
    saved = tiktok.load_token(tiktok.token_path(app), KEY)
    assert saved["refresh_token"] == NEW_REFRESH and saved["access_token"] == "act.new"
    assert pushed == [app["dir"].parent.parent]
    assert http.calls[1][2]["headers"]["Authorization"] == "Bearer act.new"
    assert NEW_REFRESH.encode() not in tiktok.token_path(app).read_bytes()  # encrypted at rest


def test_push_failure_still_posts(app, video):
    store(app, expires_in_min=2)
    refresh = ("POST", tiktok.TOKEN_URL, Resp({"access_token": "act.new", "expires_in": 7200,
                                               "refresh_token": NEW_REFRESH}))

    def boom(root):
        raise RuntimeError("ledger push failed")
    out, _, _ = run(app, video, FakeHTTP([refresh] + post_script()), checkpoint=boom)
    assert out.post_id == "P1"


def test_refused_refresh_keeps_old_file(app, video):
    store(app, expires_in_min=2)
    before = tiktok.token_path(app).read_bytes()
    http = FakeHTTP([("POST", tiktok.TOKEN_URL, Resp({"error": "invalid_grant", "error_description": OLD_REFRESH},
                                                     status=400))])
    with pytest.raises(PublishError) as e:
        run(app, video, http)
    assert "invalid_grant" in str(e.value) and OLD_REFRESH not in str(e.value)
    assert tiktok.token_path(app).read_bytes() == before


def test_missing_token_file_says_how_to_fix(app, video):
    with pytest.raises(PublishError) as e:
        run(app, video, FakeHTTP([]))
    assert "tools/tiktok_auth.py" in str(e.value)


def test_pending_share_cap_is_reported_by_code(app, video):
    store(app)
    http = FakeHTTP([("POST", tiktok.INIT_URL, Resp({"data": {}, "error": {
        "code": "spam_risk_too_many_pending_share", "message": "x"}}, status=403))])
    with pytest.raises(PublishError) as e:
        run(app, video, http)
    assert "spam_risk_too_many_pending_share" in str(e.value) and e.value.retryable is True


def test_upload_timeout_is_not_retryable(app, video):
    store(app)
    script = post_script()[:2]
    script[1] = ("PUT", UP, requests.ReadTimeout("t"))
    with pytest.raises(PublishError) as e:
        run(app, video, FakeHTTP(script))
    assert e.value.retryable is False and "may have posted" in str(e.value)


def test_failed_status_raises(app, video):
    store(app)
    with pytest.raises(PublishError) as e:
        run(app, video, FakeHTTP(post_script(status="FAILED")))
    assert e.value.retryable is False and "file_format_check_failed" in str(e.value)


def test_status_poll_error_after_upload_is_only_a_warning(app, video):
    store(app)
    script = post_script()[:3]
    script[2] = ("POST", tiktok.STATUS_URL, requests.ConnectionError("x"))
    out, sent, _ = run(app, video, FakeHTTP(script))
    assert out.post_id == "P1" and len(sent) == 1


def test_notify_failure_is_swallowed(app, video):
    store(app)

    def bad(text):
        raise RuntimeError("telegram send failed")
    out, _, _ = run(app, video, FakeHTTP(post_script()), notify=bad)
    assert out.post_id == "P1"


def test_publisher_slot():
    assert get_publisher("tiktok") is tiktok.publish
