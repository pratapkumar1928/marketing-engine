import random
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from engine.ledger import append, read
from engine.main import Deps, run
from engine.types import CopyRejected, PublishError, Published

ROOT = Path(__file__).parent.parent
NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 12, 5, 8, 5, tzinfo=NY)
TAGS = ["#screentime", "#doomscrolling", "#androidapp"]


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    shutil.copytree(ROOT / "recipes", tmp_path / "recipes")
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    d = tmp_path / "apps" / "demo"
    (d / "copy").mkdir(parents=True)
    (d / "app.yaml").write_text(yaml.safe_dump({
        "name": "Demo", "timezone": "America/New_York",
        "post_times": ["08:00", "12:00", "18:00"],
        "platforms": {"instagram": {"enabled": True, "enabled_on": date(2026, 1, 1), "target": 2},
                      "facebook": {"enabled": True, "enabled_on": date(2026, 1, 1), "target": 2}}}))
    (d / "facts.yaml").write_text(yaml.safe_dump([{"id": f"f{i}", "text": f"fact {i}"} for i in range(5)]))
    (d / "copy" / "hashtags.yaml").write_text(yaml.safe_dump(TAGS))
    (d / "copy" / "keywords.yaml").write_text(yaml.safe_dump(["phone at night"]))
    (d / "copy" / "style.md").write_text("deadpan")
    return tmp_path


def ledger(root):
    return read(root / "state" / "demo" / "ledger.jsonl")


class Calls:
    def __init__(self):
        self.published, self.rendered = [], []


def fake_deps(root, calls, *, copy_fail=0, render_fail=False, publish=None):
    from engine.types import Copy
    state = {"copy_fail": copy_fail}

    def llm(prompt, schema):
        raise AssertionError("copywriter is faked in these tests")

    def render(recipe, copy, content, app, *, broll, music, clip, out):
        if render_fail:
            raise RuntimeError("check failed")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mp4")
        calls.rendered.append(recipe["id"])
        return Path(out)

    def default_publish(platform):
        def pub(video, caption, app, **kw):
            events = read(root / "state" / "demo" / "ledger.jsonl")
            assert events[-1]["event"] == "publishing" and events[-1]["platform"] == platform
            calls.published.append(platform)
            return Published(platform, f"{platform}-id", f"https://{platform}/x")
        return pub

    def writer(plan, recipe, app, content, llm_, recent):
        if state["copy_fail"] > 0:
            state["copy_fail"] -= 1
            raise CopyRejected("unsupported claim: x")
        return Copy(hook="h", texts={"hook": "h", "problem": "p"}, caption=f"cap {plan.slot.slot_id}", hashtags=TAGS)

    pubs = publish or {"instagram": default_publish("instagram"), "facebook": default_publish("facebook")}
    return Deps(llm=llm, broll=lambda q, d, rng: None, music=lambda s, out, seed: None, render=render,
                publishers=pubs, rng=random.Random(1), write_copy=writer)


def test_dry_run_default_never_calls_publish(root):
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c))
    assert c.published == [] and c.rendered
    assert {e["platform"] for e in ledger(root) if e["event"] == "dry_run"} == {"instagram", "facebook"}


def test_publishing_logged_before_publish_call(root):
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c), dry_run=False)  # fake publisher asserts the ledger order
    assert sorted(c.published) == ["facebook", "instagram"]
    assert [e["event"] for e in ledger(root) if e.get("platform") == "instagram"] == ["publishing", "published"]


def test_caption_includes_hashtags(root):
    run(root, NOW, deps=fake_deps(root, Calls()), dry_run=False)
    pub = [e for e in ledger(root) if e["event"] == "publishing"][0]
    assert pub["caption"].startswith("cap ") and pub["caption"].endswith(" ".join(TAGS))


def test_second_run_same_slot_does_not_publish(root):
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c), dry_run=False)
    run(root, NOW + timedelta(minutes=30), deps=fake_deps(root, c), dry_run=False)
    assert sorted(c.published) == ["facebook", "instagram"] and len(c.rendered) == 1


def test_stale_publishing_becomes_unknown_not_retried(root):
    p = root / "state" / "demo" / "ledger.jsonl"
    old = (NOW - timedelta(minutes=45)).astimezone(timezone.utc).isoformat()
    for plat in ("instagram", "facebook"):
        append(p, {"app": "demo", "slot_id": "2026-12-05#0", "platform": plat, "event": "publishing"})
    events = read(p)
    p.write_text("".join(__import__("json").dumps({**e, "ts": old}) + "\n" for e in events))
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c), dry_run=False)
    assert c.published == []
    assert [e["event"] for e in ledger(root) if e.get("platform") == "instagram"] == ["publishing", "unknown"]


def test_copy_rejected_drops_slot_continues(root):
    later = datetime(2026, 12, 5, 12, 5, tzinfo=NY)
    p = root / "state" / "demo" / "ledger.jsonl"
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c, copy_fail=1), dry_run=False)
    run(root, later, deps=fake_deps(root, c), dry_run=False)
    dropped = [e for e in read(p) if e["event"] == "dropped"]
    assert {e["slot_id"] for e in dropped} == {"2026-12-05#0"} and "unsupported claim" in dropped[0]["error"]
    assert {e["slot_id"] for e in read(p) if e["event"] == "published"} == {"2026-12-05#1"}


def test_render_failure_drops_slot(root):
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c, render_fail=True), dry_run=False)
    assert c.published == [] and {e["event"] for e in ledger(root)} >= {"planned", "dropped"}


def failing(platform, n, calls):
    def pub(video, caption, app, **kw):
        calls.published.append(platform)
        raise PublishError("ig publish failed: ReadTimeout; may have posted", retryable=False)
    return pub


def test_two_failures_auto_pause_platform(root):
    c = Calls()
    deps = lambda: fake_deps(root, c, publish={"instagram": failing("instagram", 0, c),
                                               "facebook": fake_deps(root, c).publishers["facebook"]})
    run(root, NOW, deps=deps(), dry_run=False)
    run(root, datetime(2026, 12, 5, 12, 5, tzinfo=NY), deps=deps(), dry_run=False)
    assert c.published.count("instagram") == 2
    run(root, datetime(2026, 12, 6, 8, 5, tzinfo=NY), deps=deps(), dry_run=False)
    assert c.published.count("instagram") == 2  # paused
    assert c.published.count("facebook") == 3


def test_resume_after_clears_pause(root):
    c = Calls()
    deps = lambda pubs=None: fake_deps(root, c, publish=pubs)
    bad = {"instagram": failing("instagram", 0, c), "facebook": fake_deps(root, c).publishers["facebook"]}
    run(root, NOW, deps=deps(bad), dry_run=False)
    run(root, datetime(2026, 12, 5, 12, 5, tzinfo=NY), deps=deps(bad), dry_run=False)
    cfg = root / "apps" / "demo" / "app.yaml"
    a = yaml.safe_load(cfg.read_text())
    a["platforms"]["instagram"]["resume_after"] = datetime(2026, 12, 5, 20, 0, tzinfo=timezone.utc).isoformat()
    cfg.write_text(yaml.safe_dump(a))
    run(root, datetime(2026, 12, 6, 8, 5, tzinfo=NY), deps=deps(), dry_run=False)
    assert [e["event"] for e in ledger(root) if e.get("platform") == "instagram"][-1] == "published"


def test_pause_recomputed_between_slots_in_one_run(root):
    """Two due slots in one run: after the platform fails twice, a third slot must not try it."""
    c = Calls()
    a = yaml.safe_load((root / "apps/demo/app.yaml").read_text())
    a["post_times"] = ["08:00", "08:20", "08:40"]
    a["platforms"]["instagram"]["target"] = 3
    a["platforms"]["facebook"]["target"] = 3
    (root / "apps/demo/app.yaml").write_text(yaml.safe_dump(a))
    pubs = {"instagram": failing("instagram", 0, c), "facebook": fake_deps(root, c).publishers["facebook"]}
    run(root, datetime(2026, 12, 5, 8, 45, tzinfo=NY), deps=fake_deps(root, c, publish=pubs), dry_run=False)
    assert c.published.count("instagram") == 2 and c.published.count("facebook") == 3


def test_clip_path_outside_app_dir_dropped(root):
    d = root / "apps" / "demo"
    (d / "footage").mkdir()
    (d / "footage" / "clips.yaml").write_text(yaml.safe_dump([{"id": "evil", "file": "../../../config.yaml", "dur": 8}]))
    (d / "recipes").mkdir()
    for rid in ("fact_card", "problem_app"):  # every usable recipe is the clip one
        (d / "recipes" / f"{rid}.json").write_text((ROOT / "apps/scrollsmack/recipes/clip_remix.json").read_text()
                                                   .replace('"clip_remix"', f'"{rid}"'))
    c = Calls()
    run(root, NOW, deps=fake_deps(root, c), dry_run=False)
    assert c.rendered == [] and any("outside" in e.get("error", "") for e in ledger(root) if e["event"] == "dropped")


def test_publishing_checkpoint_runs_before_publish_and_blocks_on_failure(root):
    c = Calls()
    order = []

    def checkpoint():
        events = ledger(root)
        order.append(("checkpoint", events[-1]["event"]))
        raise RuntimeError("push rejected")

    deps = fake_deps(root, c)
    deps.checkpoint = checkpoint
    run(root, NOW, deps=deps, dry_run=False)
    assert c.published == [] and order and all(ev == "publishing" for _, ev in order)
    finals = [e for e in ledger(root) if e.get("platform") == "instagram"]
    assert [e["event"] for e in finals] == ["publishing", "failed"] and "not saved" in finals[-1]["error"]


def test_exact_caption_repeat_is_seen_by_duplicate_check(root):
    seen = {}
    c = Calls()
    deps = fake_deps(root, c)
    inner = deps.write_copy

    def spy(plan, recipe, app, content, llm, recent_caps):
        seen.setdefault("recent", recent_caps)
        return inner(plan, recipe, app, content, llm, recent_caps)

    run(root, NOW, deps=deps, dry_run=False)
    deps2 = fake_deps(root, c)
    deps2.write_copy = lambda *a: (seen.update(recent=a[5]), inner(*a))[1]
    run(root, datetime(2026, 12, 5, 12, 5, tzinfo=NY), deps=deps2, dry_run=False)
    assert "cap 2026-12-05#0" in seen["recent"]  # bare caption, no hashtags appended


def test_naive_resume_after_is_treated_as_utc(root):
    c = Calls()
    cfg = root / "apps" / "demo" / "app.yaml"
    a = yaml.safe_load(cfg.read_text())
    a["platforms"]["instagram"]["resume_after"] = datetime(2026, 12, 1, 0, 0)  # naive, as YAML would give
    cfg.write_text(yaml.safe_dump(a))
    append(root / "state" / "demo" / "ledger.jsonl", {"ts": "2026-12-02T12:00:00+00:00", "app": "demo",
           "slot_id": "2026-12-02#0", "platform": "instagram", "event": "published"})
    run(root, NOW, deps=fake_deps(root, c), dry_run=False)
    assert "instagram" in c.published


def test_planner_error_drops_slot_and_later_slots_continue(root, monkeypatch):
    import engine.main as m
    real = m.plan_slot
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("empty pool")
        return real(*a, **k)

    monkeypatch.setattr(m, "plan_slot", flaky)
    a = yaml.safe_load((root / "apps/demo/app.yaml").read_text())
    a["post_times"] = ["08:00", "08:20", "08:40"]
    (root / "apps/demo/app.yaml").write_text(yaml.safe_dump(a))
    c = Calls()
    run(root, datetime(2026, 12, 5, 8, 45, tzinfo=NY), deps=fake_deps(root, c), dry_run=False)
    events = ledger(root)
    assert any(e["event"] == "dropped" and e["slot_id"] == "2026-12-05#0" for e in events)
    assert any(e["event"] == "published" and e["slot_id"] == "2026-12-05#1" for e in events)


def test_pause_file_stops_everything(root):
    (root / "PAUSE").write_text("")
    c = Calls()
    assert run(root, NOW, deps=fake_deps(root, c), dry_run=False) == []
    assert c.rendered == [] and ledger(root) == []


def test_nothing_due_does_nothing(root):
    c = Calls()
    run(root, datetime(2026, 12, 5, 7, 0, tzinfo=NY), deps=fake_deps(root, c), dry_run=False)
    assert c.rendered == [] and ledger(root) == []
