from engine.ledger import append, last_status, read, recent


def test_append_then_read_roundtrip(tmp_path):
    p = tmp_path / "state" / "x" / "ledger.jsonl"
    append(p, {"slot_id": "2026-12-05#0", "platform": "instagram", "event": "planned"})
    events = read(p)
    assert len(events) == 1 and events[0]["event"] == "planned" and "ts" in events[0]


def test_read_missing_is_empty(tmp_path):
    assert read(tmp_path / "nope.jsonl") == []


def test_last_status_returns_latest(tmp_path):
    p = tmp_path / "l.jsonl"
    for ev in ["publishing", "published"]:
        append(p, {"slot_id": "s", "platform": "instagram", "event": ev})
    append(p, {"slot_id": "s", "platform": "facebook", "event": "failed"})
    events = read(p)
    assert last_status(events, "s", "instagram") == "published"
    assert last_status(events, "s", "facebook") == "failed"
    assert last_status(events, "other", "instagram") is None


def test_corrupt_last_line_ignored(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text('{"a":1}\n{"bro', encoding="utf-8")
    assert read(p) == [{"a": 1}]


def test_recent_skips_nulls_and_limits():
    events = [{"caption": "a"}, {"caption": None}, {"x": 1}, {"caption": "b"}, {"caption": "c"}]
    assert recent(events, "caption", 2) == ["b", "c"]
