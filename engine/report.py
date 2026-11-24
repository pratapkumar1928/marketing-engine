"""Daily Telegram summary. Notification only: no buttons, nothing waits on a reply."""
import logging
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

from engine.config import list_apps, load_app, secret
from engine.ledger import read

log = logging.getLogger(__name__)
LIMIT = 4096
TZ = ZoneInfo("America/New_York")


def _on_day(e: dict, day: date) -> bool:
    try:
        return datetime.fromisoformat(e["ts"]).astimezone(TZ).date() == day
    except (KeyError, ValueError):
        return False


def build_report(per_app: dict[str, dict], day: date) -> str:
    """per_app: {slug: {"events": [...], "paused": {platform, ...}}}"""
    lines = [f"Marketing engine, {day.isoformat()}"]
    for slug, data in per_app.items():
        today = [e for e in data["events"] if _on_day(e, day)]
        lines.append(f"\n{slug}")
        posted = Counter(e["platform"] for e in today if e["event"] == "published")
        dry = Counter(e["platform"] for e in today if e["event"] == "dry_run")
        for p in sorted(set(posted) | set(dry)):
            bits = [f"{posted[p]} posted"] if posted[p] else []
            bits += [f"{dry[p]} dry-run"] if dry[p] else []
            lines.append(f"  {p}: {', '.join(bits)}")
        for e in today:
            if e["event"] == "published":
                lines.append(f"  + {e['platform']} {e.get('url', '')}")
        for e in today:
            if e["event"] == "unknown":
                lines.append(f"  ! CHECK MANUALLY {e['platform']} {e['slot_id']}: may or may not have posted")
            elif e["event"] == "failed":
                lines.append(f"  x failed {e['platform']} {e['slot_id']}: {e.get('error', '')}")
            elif e["event"] == "dropped":
                lines.append(f"  - dropped {e['platform']} {e['slot_id']}: {e.get('error', '')}")
        if data.get("paused"):
            lines.append(f"  AUTO-PAUSED: {', '.join(sorted(data['paused']))} (set resume_after in app.yaml)")
        if len(lines) == 2:
            lines.append("  nothing today")
    text = "\n".join(lines)
    return text if len(text) <= LIMIT else text[: LIMIT - 20] + "\n...(truncated)"


def send(text: str, *, http=requests) -> None:
    try:
        r = http.post(f"https://api.telegram.org/bot{secret('TELEGRAM_BOT_TOKEN')}/sendMessage",
                      json={"chat_id": secret("TELEGRAM_CHAT_ID"), "text": text, "disable_web_page_preview": True},
                      timeout=30)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - the token is in the URL path: never echo the message
        raise RuntimeError(f"telegram send failed: {type(e).__name__}") from None


def main(root, day_iso: str | None) -> int:
    from engine.main import ledger_path, paused_platforms
    day = date.fromisoformat(day_iso) if day_iso else datetime.now(TZ).date()
    per_app = {}
    for slug in list_apps(root):
        app = load_app(root, slug)
        events = read(ledger_path(root, slug))
        per_app[slug] = {"events": events, "paused": paused_platforms(app, events)}
    text = build_report(per_app, day)
    print(text)
    send(text)
    return 0
