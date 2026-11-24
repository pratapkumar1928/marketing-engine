"""Which slots exist today, which platforms each slot posts to, and which are due now."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from engine.ledger import last_status
from engine.types import Slot


def daily_cap(p: dict, day: date, hard_cap: int) -> int:
    on = p.get("enabled_on")
    if not p.get("enabled") or not on or day < on:
        return 0
    weeks = (day - on).days // 7
    return min(int(p.get("target", 5)), hard_cap, 2 + weeks)


def _spread(n: int, k: int) -> list[int]:
    """k indices spread evenly over range(n)."""
    return [j * n // k for j in range(k)]


def slots_for_day(app: dict, day: date, hard_cap: int) -> list[Slot]:
    caps = {name: daily_cap(p, day, hard_cap) for name, p in (app.get("platforms") or {}).items()}
    caps = {k: v for k, v in caps.items() if v > 0}
    if not caps:
        return []
    times = [str(t) for t in app["post_times"]]
    n = min(max(caps.values()), len(times))
    tz = ZoneInfo(app["timezone"])
    members = {name: set(_spread(n, min(c, n))) for name, c in caps.items()}
    slots = []
    for i, ti in enumerate(_spread(len(times), n)):
        hh, mm = (int(x) for x in times[ti].split(":"))
        at = datetime.combine(day, time(hh, mm), tzinfo=tz)
        plats = [name for name in caps if i in members[name]]
        slots.append(Slot(app=app["slug"], slot_id=f"{day.isoformat()}#{i}", at=at, platforms=plats))
    return slots


def due_slots(app: dict, now: datetime, events: list[dict], hard_cap: int, late_min: int) -> list[Slot]:
    local_day = now.astimezone(ZoneInfo(app["timezone"])).date()
    out = []
    for s in slots_for_day(app, local_day, hard_cap):
        if not (s.at <= now and now - s.at <= timedelta(minutes=late_min)):
            continue
        plats = [p for p in s.platforms if last_status(events, s.slot_id, p) is None]
        if plats:
            s.platforms = plats
            out.append(s)
    return out
