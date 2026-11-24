import random
from datetime import datetime, timedelta, timezone

import yaml

from engine.planner import plan_slot
from engine.types import Slot

AT = datetime(2026, 12, 10, 13, 0, tzinfo=timezone.utc)


def mk_app(tmp_path, n_facts=3):
    d = tmp_path / "apps" / "a"
    d.mkdir(parents=True)
    (d / "facts.yaml").write_text(yaml.safe_dump([{"id": f"f{i}", "text": f"fact {i}"} for i in range(n_facts)]))
    return {"slug": "a", "dir": d}


R1 = {"id": "r1", "content": "fact", "weight": 1, "beats": []}
R2 = {"id": "r2", "content": "fact", "weight": 1, "beats": []}
SLOT = Slot(app="a", slot_id="2026-12-10#0", at=AT, platforms=["instagram"])


def planned(recipe, content, days_ago):
    ts = (AT - timedelta(days=days_ago)).isoformat()
    return {"ts": ts, "app": "a", "event": "planned", "recipe": recipe, "combo": f"{recipe}:{content}", "content_id": content}


def test_no_same_recipe_twice_in_a_row(tmp_path):
    app = mk_app(tmp_path)
    for seed in range(20):
        p = plan_slot(SLOT, app, [R1, R2], [planned("r1", "f0", 1)], random.Random(seed))
        assert p.recipe_id == "r2"


def test_single_recipe_may_repeat(tmp_path):
    app = mk_app(tmp_path)
    assert plan_slot(SLOT, app, [R1], [planned("r1", "f0", 1)], random.Random(0)).recipe_id == "r1"


def test_respects_cooldown(tmp_path):
    app = mk_app(tmp_path)
    events = [planned("r1", "f0", 1), planned("r1", "f1", 13)]
    for seed in range(20):
        p = plan_slot(SLOT, app, [R1], events, random.Random(seed))
        assert p.content_id == "f2" and p.combo == "r1:f2"


def test_exhausted_pool_picks_lru(tmp_path):
    app = mk_app(tmp_path)
    events = [planned("r1", "f1", 5), planned("r1", "f0", 9), planned("r1", "f2", 2)]
    assert plan_slot(SLOT, app, [R1], events, random.Random(0)).content_id == "f0"


def test_cooldown_expired_item_is_available(tmp_path):
    app = mk_app(tmp_path, n_facts=1)
    p = plan_slot(SLOT, app, [R1], [planned("r1", "f0", 20)], random.Random(0))
    assert p.content_id == "f0"


def test_deterministic_with_seeded_rng(tmp_path):
    app = mk_app(tmp_path, n_facts=10)
    a = plan_slot(SLOT, app, [R1, R2], [], random.Random(42))
    b = plan_slot(SLOT, app, [R1, R2], [], random.Random(42))
    assert (a.recipe_id, a.content_id) == (b.recipe_id, b.content_id)
