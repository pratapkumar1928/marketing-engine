"""Daily Telegram summary. Notification only: no buttons, nothing waits on a reply."""
import logging
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from engine.config import list_apps, load_app, secret
from engine.ledger import read

log = logging.getLogger(__name__)
LIMIT = 4096
TZ = ZoneInfo("America/New_York")


def _on_day(e, day: date) -> bool:
    try:
        return datetime.fromisoformat(e["ts"]).astimezone(TZ).date() == day
    except (KeyError, TypeError, ValueError):
        return False


def build_report(per_app: dict[str, dict], day: date) -> str:
    """per_app: {slug: {"events": [...], "paused": {platform, ...}}}

    Warnings and counts always come first and are never dropped for space; post links are the
    lowest priority and are trimmed (with a count) when the message would pass Telegram's limit.
    """
    lines, links = [f"Marketing engine, {day.isoformat()}"], []
    for slug, data in per_app.items():
        today = [e for e in data.get("events", []) if isinstance(e, dict) and _on_day(e, day)]
        section = []
        if data.get("paused"):
            section.append(f"  AUTO-PAUSED: {', '.join(sorted(data['paused']))} (set resume_after in app.yaml)")
        for e in today:
            p, s, err, kind = e.get("platform", "?"), e.get("slot_id", "?"), e.get("error", ""), e.get("event")
            if kind == "unknown":
                section.append(f"  ! CHECK MANUALLY {p} {s}: may or may not have posted")
            elif kind == "failed":
                section.append(f"  x failed {p} {s}: {err}")
            elif kind == "dropped":
                section.append(f"  - dropped {p} {s}: {err}")
        posted = Counter(e.get("platform", "?") for e in today if e.get("event") == "published")
        dry = Counter(e.get("platform", "?") for e in today if e.get("event") == "dry_run")
        for p in sorted(set(posted) | set(dry)):
            bits = [f"{posted[p]} posted"] if posted[p] else []
            bits += [f"{dry[p]} dry-run"] if dry[p] else []
            section.insert(0, f"  {p}: {', '.join(bits)}")
        lines += [f"\n{slug}"] + (section or ["  nothing today"])
        links += [f"  + {slug} {e.get('platform', '?')} {e.get('url', '')}" for e in today if e.get("event") == "published"]
    text = "\n".join(lines)
    if len(text) > LIMIT:
        return text[: LIMIT - 20] + "\n...(truncated)"
    if not links:
        return text
    body = text
    text += "\n\nPosts"
    for i, link in enumerate(links):
        note = f"\n  ({len(links) - i} post links omitted)"
        last = i == len(links) - 1
        if len(text) + 1 + len(link) + (0 if last else len(note)) > LIMIT:
            if i == 0:  # not even one link fits: drop the header too
                text = body
            text += note
            break
        text += "\n" + link
    return text[:LIMIT]  # hard ceiling: warnings above are never displaced by links


def send(text: str, *, http=requests) -> None:
    try:
        r = http.post(f"https://api.telegram.org/bot{secret('TELEGRAM_BOT_TOKEN')}/sendMessage",
                      json={"chat_id": secret("TELEGRAM_CHAT_ID"), "text": text, "disable_web_page_preview": True},
                      timeout=30)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - the token is in the URL path: never echo the message
        raise RuntimeError(f"telegram send failed: {type(e).__name__}") from None


def default_day(now: datetime) -> date:
    """The cron fires 04:30 UTC: 23:30 EST or 00:30 EDT. An hour back is always the day being reported."""
    return (now.astimezone(TZ) - timedelta(hours=1)).date()


def main(root, day_iso: str | None) -> int:
    from engine.main import ledger_path, paused_platforms
    day = date.fromisoformat(day_iso) if day_iso else default_day(datetime.now(TZ))
    per_app = {}
    for slug in list_apps(root):
        app = load_app(root, slug)
        events = read(ledger_path(root, slug))
        per_app[slug] = {"events": events, "paused": paused_platforms(app, events)}
    text = build_report(per_app, day)
    print(text)
    send(text)
    return 0
