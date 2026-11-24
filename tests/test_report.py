from datetime import date

import pytest
import requests

from engine.report import build_report, send

TOKEN = "123456:telegram-secret"
DAY = date(2026, 12, 5)


def ev(event, platform="instagram", slot="2026-12-05#0", ts="2026-12-05T08:05:00-05:00", **kw):
    return {"ts": ts, "app": "scrollsmack", "slot_id": slot, "platform": platform, "event": event, **kw}


def test_report_counts_and_flags_unknown():
    events = [ev("published", url="https://ig/1"), ev("published", "facebook", url="https://fb/1"),
              ev("dropped", slot="2026-12-05#1", error="unsupported claim: x"),
              ev("failed", "facebook", slot="2026-12-05#2", error="fb finish failed: HTTPError 500"),
              ev("unknown", slot="2026-12-05#3"),
              ev("published", ts="2026-12-04T20:00:00-05:00", url="https://ig/old")]
    text = build_report({"scrollsmack": {"events": events, "paused": {"facebook"}}}, DAY)
    assert "scrollsmack" in text and "instagram: 1 posted" in text and "facebook: 1 posted" in text
    assert "https://ig/1" in text and "https://ig/old" not in text
    assert "unsupported claim" in text and "HTTPError 500" in text
    assert "CHECK MANUALLY" in text and "AUTO-PAUSED: facebook" in text


def test_report_dry_run_counted():
    text = build_report({"a": {"events": [ev("dry_run")], "paused": set()}}, DAY)
    assert "instagram: 1 dry-run" in text


def test_report_truncates_to_4096():
    events = [ev("dropped", slot=f"2026-12-05#{i}", error="x" * 300) for i in range(40)]
    assert len(build_report({"a": {"events": events, "paused": set()}}, DAY)) <= 4096


def test_default_day_covers_cron_in_winter_and_summer():
    from datetime import datetime, timezone

    from engine.report import default_day
    assert default_day(datetime(2026, 12, 6, 4, 30, tzinfo=timezone.utc)) == date(2026, 12, 5)  # 23:30 EST
    assert default_day(datetime(2027, 7, 6, 4, 30, tzinfo=timezone.utc)) == date(2027, 7, 5)  # 00:30 EDT


class FakeHTTP:
    def __init__(self, exc=None):
        self.exc, self.calls = exc, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if self.exc:
            raise self.exc

        class R:
            def raise_for_status(self):
                pass
        return R()


@pytest.fixture(autouse=True)
def tg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")


def test_send_posts_to_chat():
    http = FakeHTTP()
    send("hello", http=http)
    url, kw = http.calls[0]
    assert url.endswith("/sendMessage") and kw["json"] == {"chat_id": "42", "text": "hello",
                                                            "disable_web_page_preview": True}


def test_send_error_hides_token():
    with pytest.raises(RuntimeError) as e:
        send("x", http=FakeHTTP(exc=requests.ConnectionError(f"https://api.telegram.org/bot{TOKEN}/sendMessage")))
    assert TOKEN not in str(e.value) and e.value.__suppress_context__
