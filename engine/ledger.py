"""Append-only JSONL post log. One line per event; the newest line for a (slot, platform) is its status."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def append(path: Path, event: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **event}, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())  # durable before any network call that follows


def read(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # torn last line from a killed run
    return out


def last_status(events: list[dict], slot_id: str, platform: str) -> str | None:
    for e in reversed(events):
        if e.get("slot_id") == slot_id and e.get("platform") == platform:
            return e.get("event")
    return None


def recent(events: list[dict], field: str, n: int) -> list:
    vals = [e[field] for e in events if e.get(field) is not None]
    return vals[-n:]
