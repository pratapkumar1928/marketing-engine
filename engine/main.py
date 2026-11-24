"""Engine entry point.

  python -m engine.main run [--now ISO]     post every due slot (DRY_RUN=1 unless DRY_RUN=0)
  python -m engine.main report [--day ISO]  send the daily Telegram summary
  python -m engine.main check-app <name> [--preview N]

Safety rules (do not reorder): the `publishing` line is on disk before any network call; a stale
`publishing` becomes `unknown` and is never re-posted; a slot is planned, dropped or posted at most once.
"""
import argparse
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import yaml

from engine import copywriter
from engine.config import app_file, list_apps, load_app, load_config
from engine.ledger import append, read, recent
from engine.planner import plan_slot
from engine.recipes import load_recipes, pool
from engine.schedule import due_slots
from engine.types import CopyRejected, PublishError

log = logging.getLogger("engine")
ROOT = Path(__file__).resolve().parent.parent
STALE_PUBLISHING = timedelta(minutes=30)
FINAL = {"published", "failed", "unknown"}


@dataclass
class Deps:
    llm: Callable
    broll: Callable
    music: Callable
    render: Callable  # (recipe, copy, content, app, *, broll, music, clip, out) -> Path
    publishers: dict[str, Callable]
    rng: random.Random
    write_copy: Callable = field(default=copywriter.write_copy)


def ledger_path(root: Path, slug: str) -> Path:
    return Path(root) / "state" / slug / "ledger.jsonl"


def _ts(e: dict) -> datetime:
    return datetime.fromisoformat(e["ts"])


def paused_platforms(app: dict, events: list[dict]) -> set[str]:
    """A platform pauses after its last two final outcomes both failed (or unknown) since resume_after."""
    out = set()
    for name, p in (app.get("platforms") or {}).items():
        since = p.get("resume_after")
        since = datetime.fromisoformat(str(since)) if since else None
        finals = [e["event"] for e in events if e.get("platform") == name and e.get("event") in FINAL
                  and (since is None or _ts(e) > since)]
        if len(finals) >= 2 and all(f in ("failed", "unknown") for f in finals[-2:]):
            out.add(name)
    return out


def _mark_stale(path: Path, events: list[dict], now: datetime, slug: str) -> None:
    seen = set()
    for e in reversed(events):
        key = (e.get("slot_id"), e.get("platform"))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        if e["event"] == "publishing" and now - _ts(e) > STALE_PUBLISHING:
            append(path, {"ts": now.isoformat(), "app": slug, "slot_id": key[0], "platform": key[1],
                          "event": "unknown", "error": "run ended mid-publish; check the platform, never re-posted"})


def _item(app: dict, kind: str, content_id: str) -> dict:
    return next(i for i in pool(app, kind) if str(i["id"]) == content_id)


def run(root: Path, now: datetime, *, deps: Deps, dry_run: bool | None = None) -> list[dict]:
    root = Path(root)
    if (root / "PAUSE").exists():
        log.info("PAUSE file present: nothing posted")
        return []
    if dry_run is None:
        dry_run = os.environ.get("DRY_RUN", "1") != "0"
    cfg = load_config(root)
    hard, late = int(cfg.get("hard_cap_per_platform", 10)), int(cfg.get("late_skip_minutes", 120))
    written: list[dict] = []
    for slug in list_apps(root):
        try:
            written += _run_app(root, load_app(root, slug), now, deps, dry_run, hard, late)
        except Exception as e:  # noqa: BLE001 - one broken app must not stop the others
            log.error("app %s failed: %s", slug, type(e).__name__)
    return written


def render_slot(root, app, slot, recipes, events, deps, out, on_planned=lambda plan: None):
    """Plan, write and render one video. Raises CopyRejected or a render error. -> (video, plan, copy)."""
    plan = plan_slot(slot, app, recipes, events, deps.rng)
    recipe = next(r for r in recipes if r["id"] == plan.recipe_id)
    on_planned(plan)
    content = _item(app, recipe["content"], plan.content_id)
    copy = deps.write_copy(plan, recipe, app, content, deps.llm, recent(events, "caption", 200))
    broll = None
    if any(b.get("bg") == "broll" for b in recipe["beats"]):
        keywords = yaml.safe_load((Path(app["dir"]) / "copy" / "keywords.yaml").read_text(encoding="utf-8"))
        broll = deps.broll(deps.rng.choice(keywords), Path(root) / "cache" / "broll", rng=deps.rng)
    seconds = sum(8.0 if b["dur"] == "clip" else float(b["dur"]) for b in recipe["beats"]) + 0.5
    music = deps.music(seconds, Path(root) / "cache" / "music" / f"{app['slug']}_{slot.slot_id.replace('#', '_')}.wav",
                       seed=deps.rng.randrange(1 << 30))
    clip = app_file(app, f"footage/{content['file']}") if recipe["content"] == "clip" else None
    video = deps.render(recipe, copy, content, app, broll=broll, music=music, clip=clip, out=out)
    return video, plan, copy


def _run_app(root, app, now, deps, dry_run, hard, late) -> list[dict]:
    slug, path = app["slug"], ledger_path(root, app["slug"])
    written = []

    def log_event(**ev):
        ev = {"ts": now.isoformat(), "app": slug, **ev}
        append(path, ev)
        written.append(ev)

    _mark_stale(path, read(path), now, slug)
    for slot in due_slots(app, now, read(path), hard, late):
        events = read(path)
        paused = paused_platforms(app, events)  # recomputed per slot: failures earlier in this run count
        plats = [p for p in slot.platforms if p not in paused and p in deps.publishers]
        if not plats:
            continue
        recipes = load_recipes(root, app)
        if not recipes:
            log.warning("%s: no usable recipes", slug)
            return written
        planned = {}

        def on_planned(plan):
            planned["plan"] = plan
            log_event(slot_id=slot.slot_id, platform=None, event="planned", recipe=plan.recipe_id,
                      combo=plan.combo, content_id=plan.content_id)

        def drop(reason: str):
            for p in plats:
                log_event(slot_id=slot.slot_id, platform=p, event="dropped",
                          recipe=planned["plan"].recipe_id, error=reason[:300])

        out = root / "out" / slug / f"{slot.slot_id.replace('#', '_')}.mp4"
        try:
            video, plan, copy = render_slot(root, app, slot, recipes, events, deps, out, on_planned)
        except CopyRejected as e:
            drop(e.reason)
            continue
        except Exception as e:  # noqa: BLE001 - a failed render drops this slot only
            drop(f"render failed: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")
            continue
        caption = f"{copy.caption}\n\n{' '.join(copywriter._tag(t) for t in copy.hashtags)}"
        for p in plats:
            base = {"slot_id": slot.slot_id, "platform": p, "recipe": plan.recipe_id, "combo": plan.combo,
                    "caption": caption}
            if dry_run:
                log_event(**base, event="dry_run", video=str(video))
                continue
            log_event(**base, event="publishing")  # on disk before the network call
            try:
                res = deps.publishers[p](video, caption, app)
                log_event(**base, event="published", post_id=res.post_id, url=res.url)
            except PublishError as e:
                log_event(**base, event="failed", error=str(e), retryable=e.retryable)
            except Exception as e:  # noqa: BLE001
                log_event(**base, event="failed", error=f"unexpected {type(e).__name__}", retryable=False)
    return written


def real_deps(root: Path) -> Deps:
    from engine import broll, llm, music, publishers, renderer
    cfg = load_config(root)
    r = renderer.get(cfg["renderer"])

    def render(recipe, copy, content, app, *, broll, music, clip, out):
        icon = app_file(app, app.get("brand", {}).get("icon", "brand/icon.png"))
        srcs, files = r.stage_assets(broll=broll, music=music, clip=clip, icon=icon)
        html = r.build_html(recipe, copy, content, app, srcs)
        return r.render(html, files, Path(root) / "cache" / "render" / app["slug"], out, cfg["renderer"]["version"])

    return Deps(llm=llm.get(cfg["llm"]), broll=broll.get(cfg["broll"]), music=music.get(cfg["music"]),
                render=render, publishers={p: publishers.get(p) for p in cfg["publishers"]}, rng=random.Random())


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--now")
    rep = sub.add_parser("report")
    rep.add_argument("--day")
    ca = sub.add_parser("check-app")
    ca.add_argument("name")
    ca.add_argument("--preview", type=int, default=0)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        now = datetime.fromisoformat(a.now) if a.now else datetime.now(timezone.utc)
        events = run(ROOT, now, deps=real_deps(ROOT))
        for e in events:
            log.info("%s %s %s %s", e.get("slot_id"), e.get("platform") or "-", e["event"], e.get("url") or e.get("error") or "")
        return 0
    if a.cmd == "report":
        from engine import report
        return report.main(ROOT, a.day)
    if a.cmd == "check-app":
        from engine import checkapp
        return checkapp.main(ROOT, a.name, a.preview)
    return 2


if __name__ == "__main__":
    sys.exit(main())
