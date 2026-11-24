import pytest
import requests

from engine.publishers import get as get_publisher
from engine.publishers import youtube
from engine.types import PublishError

REFRESH, ACCESS = "1//refreshSecret", "ya29.accessSecret"
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=U1"
APP = {"youtube": {"client_id_secret": "YT_ID", "client_secret_secret": "YT_SECRET",
                   "refresh_token_secret": "YT_REFRESH"}}


@pytest.fixture(autouse=True)
def secrets(monkeypatch):
    monkeypatch.setenv("YT_ID", "cid")
    monkeypatch.setenv("YT_SECRET", "csecret")
    monkeypatch.setenv("YT_REFRESH", REFRESH)


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"0123456789")
    return p


class Resp:
    def __init__(self, payload=None, status=200, headers=None):
        self.payload, self.status_code, self.headers = payload, status, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def json(self):
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


def script(location=SESSION, upload=None):
    return [("POST", youtube.TOKEN_URL, Resp({"access_token": ACCESS})),
            ("POST", youtube.UPLOAD_URL, Resp(headers={"Location": location})),
            ("PUT", location, upload or Resp({"id": "VID1"}, status=201))]


CAPTION = "Your thumb ran a marathon today. ScrollSmack makes you type a confession first.\n\n#screentime #focus"


def test_full_flow(video):
    http = FakeHTTP(script())
    out = youtube.publish(video, CAPTION, APP, http=http)
    assert out.platform == "youtube" and out.post_id == "VID1" and out.url == "https://www.youtube.com/shorts/VID1"
    tok = http.calls[0][2]["data"]
    assert tok == {"client_id": "cid", "client_secret": "csecret", "refresh_token": REFRESH,
                   "grant_type": "refresh_token"}
    init = http.calls[1][2]
    assert init["headers"]["Authorization"] == f"Bearer {ACCESS}"
    assert init["headers"]["X-Upload-Content-Length"] == "10"
    body = init["json"]
    assert body["snippet"]["description"] == CAPTION
    assert body["snippet"]["title"] == "Your thumb ran a marathon today. ScrollSmack makes you type a confession first."
    assert body["status"]["privacyStatus"] == "public" and body["status"]["selfDeclaredMadeForKids"] is False
    assert body["status"]["containsSyntheticMedia"] is True
    put = http.calls[2][2]
    assert put["data"] == b"0123456789" and put["headers"]["Authorization"] == f"Bearer {ACCESS}"
    assert http.script == []


def test_title_is_cut_to_100_chars_on_a_word():
    t = youtube.title_of("word " * 40)
    assert len(t) <= 100 and not t.endswith(" ") and t.startswith("word word")


def test_refuses_foreign_session_host(video):
    http = FakeHTTP(script(location="https://evil.example.com/up")[:2])
    with pytest.raises(PublishError) as e:
        youtube.publish(video, CAPTION, APP, http=http)
    assert e.value.retryable is True and len(http.calls) == 2  # token never sent to the foreign host


def test_upload_timeout_is_not_retryable(video):
    http = FakeHTTP(script(upload=requests.ReadTimeout("t")))
    with pytest.raises(PublishError) as e:
        youtube.publish(video, CAPTION, APP, http=http)
    assert e.value.retryable is False and "may have posted" in str(e.value)


def test_token_failure_is_retryable_and_secret_free(video):
    http = FakeHTTP([("POST", youtube.TOKEN_URL, requests.ConnectionError(f"boom {REFRESH}"))])
    with pytest.raises(PublishError) as e:
        youtube.publish(video, CAPTION, APP, http=http)
    assert e.value.retryable is True and REFRESH not in str(e.value) and e.value.__suppress_context__


def test_publisher_slot():
    assert get_publisher("youtube") is youtube.publish
