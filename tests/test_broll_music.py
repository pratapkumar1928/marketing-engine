import random
import wave

import pytest
import requests

from engine.broll import get as get_broll
from engine.broll import pexels
from engine.music import get as get_music
from engine.music import synth

KEY = "pexels-secret-key"


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
        return Resp(self.payload) if "search" in url else Resp()


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", KEY)


def video(vid, dur, files):
    return {"id": vid, "duration": dur, "video_files": [
        {"link": f"https://videos.pexels.com/{vid}/{w}x{h}.mp4", "width": w, "height": h, "file_type": "video/mp4"} for w, h in files]}


def test_pexels_picks_portrait_hd(tmp_path):
    http = FakeHTTP({"videos": [video(1, 2, [(1080, 1920)]), video(2, 10, [(1920, 1080), (720, 1280), (1080, 1920)])]})
    p = pexels.fetch("phone at night", tmp_path, rng=random.Random(0), http=http)
    assert p and p.exists() and p.read_bytes() == b"mp4bytes"
    assert http.calls[-1][0] == "https://videos.pexels.com/2/1080x1920.mp4"
    url, kw = http.calls[0]
    assert kw["headers"]["Authorization"] == KEY and KEY not in url
    assert kw["params"]["orientation"] == "portrait"


def test_pexels_falls_back_to_tallest_portrait(tmp_path):
    http = FakeHTTP({"videos": [video(3, 9, [(540, 960), (720, 1280), (1280, 720)])]})
    pexels.fetch("q", tmp_path, rng=random.Random(0), http=http)
    assert http.calls[-1][0] == "https://videos.pexels.com/3/720x1280.mp4"


def test_pexels_no_portrait_returns_none(tmp_path):
    http = FakeHTTP({"videos": [video(4, 9, [(1920, 1080)])]})
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=http) is None


def test_pexels_http_error_returns_none(tmp_path):
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP(exc=requests.ConnectionError(KEY))) is None


def test_pexels_missing_key_returns_none(tmp_path, monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY")
    monkeypatch.setattr("engine.config.REPO_ROOT", tmp_path)
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP({"videos": []})) is None


def test_pexels_rejects_non_pexels_host(tmp_path):
    v = video(5, 9, [(1080, 1920)])
    v["video_files"][0]["link"] = "http://169.254.169.254/latest/meta-data"
    http = FakeHTTP({"videos": [v]})
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=http) is None
    assert len(http.calls) == 1  # never fetched the bad link


def test_pexels_non_numeric_id_rejected(tmp_path):
    v = video("../../evil", 9, [(1080, 1920)])
    v["video_files"][0]["link"] = "https://videos.pexels.com/x.mp4"
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP({"videos": [v]})) is None
    assert list(tmp_path.parent.glob("*evil*")) == []


def test_pexels_download_size_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(pexels, "MAX_BYTES", 4)
    v = video(6, 9, [(1080, 1920)])
    v["video_files"][0]["link"] = "https://videos.pexels.com/6.mp4"
    assert pexels.fetch("q", tmp_path, rng=random.Random(0), http=FakeHTTP({"videos": [v]})) is None
    assert list(tmp_path.glob("*.mp4")) == []


def test_synth_writes_wav_of_length(tmp_path):
    out = synth.make_track(6.0, tmp_path / "m.wav", seed=3)
    with wave.open(str(out)) as w:
        assert abs(w.getnframes() / w.getframerate() - 6.0) < 0.05


def test_synth_seed_changes_track(tmp_path):
    a = synth.make_track(3.0, tmp_path / "a.wav", seed=1).read_bytes()
    b = synth.make_track(3.0, tmp_path / "b.wav", seed=2).read_bytes()
    c = synth.make_track(3.0, tmp_path / "c.wav", seed=1).read_bytes()
    assert a != b and a == c


def test_slot_getters():
    assert get_broll({"provider": "pexels"}) is pexels.fetch
    assert get_music({"provider": "synth"}) is synth.make_track
