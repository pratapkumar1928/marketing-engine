import random

import pytest
import requests

from engine.broll import get as get_broll
from engine.broll import pixabay

KEY = "pixabay-secret-key"


class Resp:
    def __init__(self, payload=None, content=b"mp4bytes"):
        self.payload, self.content = payload, content

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload

    def iter_content(self, chunk_size=1):
        yield self.content


class FakeHTTP:
    def __init__(self, payload=None, exc=None):
        self.payload, self.exc, self.calls = payload, exc, []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        if self.exc:
            raise self.exc
        return Resp(self.payload) if url == pixabay.SEARCH else Resp()


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("PIXABAY_API_KEY", KEY)


def hit(vid, dur, w, h, host="cdn.pixabay.com", tags="phone, night"):
    return {"id": vid, "duration": dur, "tags": tags, "videos": {
        "large": {"url": f"https://{host}/video/{vid}/large.mp4", "width": w, "height": h},
        "small": {"url": f"https://{host}/video/{vid}/small.mp4", "width": w // 3, "height": h // 3}}}


def test_prefers_portrait_among_equally_relevant(tmp_path):
    http = FakeHTTP({"hits": [hit(1, 10, 1920, 1080), hit(2, 10, 1080, 1920)]})
    p = pixabay.fetch("phone at night", tmp_path, rng=random.Random(0), http=http)
    assert p.name == "pixabay_2_1920.mp4" and p.read_bytes() == b"mp4bytes"
    assert http.calls[-1][0] == "https://cdn.pixabay.com/video/2/large.mp4"
    assert http.calls[0][1]["params"]["key"] == KEY and http.calls[0][1]["params"]["q"] == "phone at night"


def test_relevance_beats_orientation(tmp_path):
    # the real failure: a vertical lake clip won over a horizontal phone clip for "person on phone on couch"
    http = FakeHTTP({"hits": [hit(7, 10, 2160, 3840, tags="landscape, lake, mount fuji"),
                              hit(8, 10, 3840, 2160, tags="woman, phone, smartphone, person")]})
    pixabay.fetch("person on phone on couch", tmp_path, rng=random.Random(0), http=http)
    assert http.calls[-1][0] == "https://cdn.pixabay.com/video/8/large.mp4"


def test_irrelevant_only_returns_none(tmp_path):
    http = FakeHTTP({"hits": [hit(9, 10, 1080, 1920, tags="cow, meadow")]})
    assert pixabay.fetch("person on phone on couch", tmp_path, rng=random.Random(0), http=http) is None


def test_green_screen_skipped(tmp_path):
    http = FakeHTTP({"hits": [hit(10, 10, 1080, 1920, tags="phone, green screen, scrolling")]})
    assert pixabay.fetch("phone scrolling", tmp_path, rng=random.Random(0), http=http) is None


def test_landscape_prefers_sharp_enough_to_crop(tmp_path):
    http = FakeHTTP({"hits": [hit(3, 10, 3840, 2160), hit(4, 10, 1280, 720)]})
    pixabay.fetch("phone", tmp_path, rng=random.Random(0), http=http)
    assert http.calls[-1][0] == "https://cdn.pixabay.com/video/3/large.mp4"


def test_too_short_or_empty_returns_none(tmp_path):
    assert pixabay.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP({"hits": [hit(5, 2, 1080, 1920)]})) is None
    assert pixabay.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP({"hits": []})) is None


def test_error_returns_none_without_key(tmp_path, caplog):
    out = pixabay.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP(exc=requests.ConnectionError(KEY)))
    assert out is None and KEY not in caplog.text


def test_rejects_foreign_host(tmp_path):
    http = FakeHTTP({"hits": [hit(6, 10, 1080, 1920, host="evil.example.com")]})
    assert pixabay.fetch("q", tmp_path, rng=random.Random(0), http=http) is None
    assert len(http.calls) == 1


def test_slot():
    assert get_broll({"provider": "pixabay"}) is pixabay.fetch
