import pytest
import requests

from engine.llm import gemini
from engine.llm import get as get_llm

KEY = "AIzaSECRETKEY123"


class Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeHTTP:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc, self.calls = resp, exc, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if self.exc:
            raise self.exc
        return self.resp


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)


def ok(text):
    return Resp({"candidates": [{"content": {"parts": [{"text": text}]}}]})


def test_returns_parsed_json():
    http = FakeHTTP(ok('{"hook": "hi"}'))
    assert gemini.generate("p", {"type": "object"}, model="m1", http=http) == {"hook": "hi"}


def test_gemini_key_in_header_not_url():
    http = FakeHTTP(ok("{}"))
    gemini.generate("p", {"type": "object"}, model="m1", http=http)
    url, kw = http.calls[0]
    assert KEY not in url and kw["headers"]["x-goog-api-key"] == KEY and "m1:generateContent" in url
    assert kw["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_error_hides_key():
    http = FakeHTTP(exc=requests.ConnectionError(f"failed for key={KEY}"))
    with pytest.raises(RuntimeError) as e:
        gemini.generate("p", {}, model="m1", http=http)
    assert KEY not in str(e.value) and e.value.__cause__ is None and e.value.__suppress_context__


def test_non_json_text_raises_valueerror():
    with pytest.raises(ValueError):
        gemini.generate("p", {}, model="m1", http=FakeHTTP(ok("not json")))


def test_slot_getter_binds_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(gemini, "generate", lambda p, s, *, model, **kw: seen.update(model=model) or {})
    get_llm({"provider": "gemini", "model": "m9"})("p", {})
    assert seen["model"] == "m9"
