import pytest
import requests

from engine.publishers import facebook, instagram
from engine.publishers import get as get_publisher
from engine.types import PublishError

TOKEN = "EAAGsecretPageToken"
G = "https://graph.facebook.com/v21.0"
APP = {"meta": {"ig_user_id_secret": "IG_ID", "page_id_secret": "PAGE_ID", "token_secret": "META_TOKEN"}}


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("IG_ID", "1784")
    monkeypatch.setenv("PAGE_ID", "9001")
    monkeypatch.setenv("META_TOKEN", TOKEN)


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"0123456789")
    return p


class Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
        return self.payload


class FakeHTTP:
    """Scripted: list of (method, url-substring, response-or-exception)."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        exp_method, exp_url, out = self.script.pop(0)
        assert method == exp_method and exp_url in url, (method, url)
        if isinstance(out, Exception):
            raise out
        return out


def ig_script(status_seq=("IN_PROGRESS", "FINISHED"), publish=None):
    s = [("POST", f"{G}/1784/media", Resp({"id": "C1"})),
         ("POST", "https://rupload.facebook.com/ig-api-upload/v21.0/C1", Resp({"success": True}))]
    s += [("GET", f"{G}/C1", Resp({"status_code": st})) for st in status_seq]
    s += [("POST", f"{G}/1784/media_publish", publish or Resp({"id": "M1"})),
          ("GET", f"{G}/M1", Resp({"permalink": "https://www.instagram.com/reel/abc/"}))]
    return s


def test_ig_full_flow_order(video):
    http = FakeHTTP(ig_script())
    out = instagram.publish(video, "cap #tag", APP, http=http, sleep=lambda s: None)
    assert out.post_id == "M1" and out.url == "https://www.instagram.com/reel/abc/" and out.platform == "instagram"
    m, url, kw = http.calls[0]
    assert kw["data"]["media_type"] == "REELS" and kw["data"]["upload_type"] == "resumable"
    assert kw["data"]["caption"] == "cap #tag"
    up = http.calls[1][2]
    assert up["headers"]["offset"] == "0" and up["headers"]["file_size"] == "10" and up["data"] == b"0123456789"
    assert http.script == []


def test_ig_container_error_raises_nonretryable(video):
    http = FakeHTTP(ig_script(status_seq=("ERROR",))[:3])
    with pytest.raises(PublishError) as e:
        instagram.publish(video, "c", APP, http=http, sleep=lambda s: None)
    assert e.value.retryable is False


def test_ig_publish_timeout_is_not_retryable(video):
    http = FakeHTTP(ig_script(publish=requests.ReadTimeout("t"))[:-1])
    with pytest.raises(PublishError) as e:
        instagram.publish(video, "c", APP, http=http, sleep=lambda s: None)
    assert e.value.retryable is False and "may have posted" in str(e.value)


def test_ig_container_create_timeout_is_retryable(video):
    http = FakeHTTP([("POST", f"{G}/1784/media", requests.ReadTimeout("t"))])
    with pytest.raises(PublishError) as e:
        instagram.publish(video, "c", APP, http=http, sleep=lambda s: None)
    assert e.value.retryable is True


def test_ig_permalink_failure_is_only_a_warning(video):
    script = ig_script()
    script[-1] = ("GET", f"{G}/M1", requests.ConnectionError("x"))
    out = instagram.publish(video, "c", APP, http=FakeHTTP(script), sleep=lambda s: None)
    assert out.post_id == "M1" and out.url.startswith("https://www.instagram.com/")


def fb_script(upload_url="https://rupload.facebook.com/video-upload/v21.0/V9", finish=None):
    return [("POST", f"{G}/9001/video_reels", Resp({"video_id": "V9", "upload_url": upload_url})),
            ("POST", upload_url, Resp({"success": True})),
            ("POST", f"{G}/9001/video_reels", finish or Resp({"success": True}))]


def test_fb_full_flow(video):
    http = FakeHTTP(fb_script())
    out = facebook.publish(video, "cap", APP, http=http)
    assert out.post_id == "V9" and out.url == "https://www.facebook.com/reel/V9"
    assert http.calls[0][2]["data"]["upload_phase"] == "start"
    fin = http.calls[2][2]["data"]
    assert fin["upload_phase"] == "finish" and fin["video_state"] == "PUBLISHED" and fin["description"] == "cap"


def test_fb_refuses_foreign_upload_host(video):
    http = FakeHTTP(fb_script(upload_url="https://evil.example.com/up")[:1])
    with pytest.raises(PublishError):
        facebook.publish(video, "c", APP, http=http)
    assert len(http.calls) == 1  # token never sent to the foreign host


def test_fb_finish_429_is_retryable(video):
    http = FakeHTTP(fb_script(finish=Resp({}, status=429)))
    with pytest.raises(PublishError) as e:
        facebook.publish(video, "c", APP, http=http)
    assert e.value.retryable is True


def test_token_never_in_url_or_error(video):
    http = FakeHTTP([("POST", f"{G}/1784/media", requests.ConnectionError(f"boom {TOKEN}"))])
    with pytest.raises(PublishError) as e:
        instagram.publish(video, "c", APP, http=http, sleep=lambda s: None)
    assert TOKEN not in str(e.value) and e.value.__suppress_context__
    assert http.calls[0][2]["headers"]["Authorization"] == f"OAuth {TOKEN}"
    assert TOKEN not in http.calls[0][1]


def test_publisher_slot():
    assert get_publisher("instagram") is instagram.publish
