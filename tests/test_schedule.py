from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from engine.schedule import daily_cap, due_slots, slots_for_day

NY = ZoneInfo("America/New_York")
TIMES = ["08:00", "10:00", "12:00", "13:30", "15:00", "17:00", "18:30", "19:30", "20:30", "22:00"]


def app(ig=5, fb=5, on=date(2026, 12, 5)):
    return {
        "slug": "demo",
        "timezone": "America/New_York",
        "post_times": TIMES,
        "platforms": {
            "instagram": {"enabled": True, "enabled_on": on, "target": ig},
            "facebook": {"enabled": True, "enabled_on": on, "target": fb},
        },
    }


def test_ramp():
    p = {"enabled": True, "enabled_on": date(2026, 12, 5), "target": 5}
    caps = [daily_cap(p, date(2026, 12, 5) + timedelta(weeks=w), 10) for w in range(5)]
    assert caps == [2, 3, 4, 5, 5]


def test_disabled_or_future_is_zero():
    assert daily_cap({"enabled": False, "enabled_on": date(2026, 1, 1), "target": 5}, date(2026, 12, 5), 10) == 0
    assert daily_cap({"enabled": True, "enabled_on": date(2026, 12, 6), "target": 5}, date(2026, 12, 5), 10) == 0
    assert daily_cap({"enabled": True, "target": 5}, date(2026, 12, 5), 10) == 0


def test_hard_cap_wins():
    p = {"enabled": True, "enabled_on": date(2026, 1, 1), "target": 50}
    assert daily_cap(p, date(2026, 12, 5), 10) == 10


def test_slots_spread_and_platform_subsets():
    a = app(ig=4, fb=2, on=date(2026, 1, 1))
    slots = slots_for_day(a, date(2026, 12, 5), 10)
    assert len(slots) == 4
    assert [s.slot_id for s in slots] == [f"2026-12-05#{i}" for i in range(4)]
    assert all("instagram" in s.platforms for s in slots)
    fb = [i for i, s in enumerate(slots) if "facebook" in s.platforms]
    assert len(fb) == 2 and fb != [0, 1]
    hours = [s.at.hour for s in slots]
    assert hours == sorted(hours) and hours[0] == 8 and hours[-1] >= 17


def test_late_slot_skipped():
    a = app(ig=1, fb=0)
    now = datetime(2026, 12, 5, 10, 1, tzinfo=NY)
    assert due_slots(a, now, [], 10, 120) == []


def test_slot_due_within_window():
    a = app(ig=1, fb=0)
    now = datetime(2026, 12, 5, 8, 31, tzinfo=NY)
    [s] = due_slots(a, now, [], 10, 120)
    assert s.platforms == ["instagram"]


def test_future_slot_not_due():
    a = app(ig=1, fb=0)
    assert due_slots(a, datetime(2026, 12, 5, 7, 59, tzinfo=NY), [], 10, 120) == []


def test_already_logged_platform_not_due():
    a = app(ig=1, fb=1)
    now = datetime(2026, 12, 5, 8, 5, tzinfo=NY)
    events = [{"slot_id": "2026-12-05#0", "platform": "instagram", "event": "publishing"}]
    [s] = due_slots(a, now, events, 10, 120)
    assert s.platforms == ["facebook"]


def test_dst_day_has_correct_local_times():
    a = app(ig=1, fb=0, on=date(2026, 1, 1))
    [s] = slots_for_day(a, date(2027, 3, 14), 10)
    assert s.at.hour == 8 and s.at.utcoffset() == timedelta(hours=-4)
