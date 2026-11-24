import json
import shutil
from pathlib import Path

import yaml

from engine.recipes import load_recipes, validate_recipe

ROOT = Path(__file__).parent.parent


def seed_files():
    return list((ROOT / "recipes").glob("*.json")) + list((ROOT / "apps" / "scrollsmack" / "recipes").glob("*.json"))


def r(beats, content="fact"):
    return {"id": "t", "content": content, "weight": 1, "beats": beats}


END = {"block": "end_card", "dur": 2}


def test_seeds_valid():
    files = seed_files()
    assert {f.stem for f in files} >= {"fact_card", "problem_app", "roast_card", "clip_remix"}
    for f in files:
        assert validate_recipe(json.loads(f.read_text())) == [], f.name


def test_too_short_rejected():
    errs = validate_recipe(r([{"block": "fact", "dur": 3}, END]))
    assert any("length" in e for e in errs)


def test_too_long_rejected():
    errs = validate_recipe(r([{"block": "fact", "dur": 30}, END]))
    assert any("length" in e for e in errs)


def test_no_app_block_rejected():
    errs = validate_recipe(r([{"block": "hook_text", "dur": 6}, END]))
    assert any("app" in e for e in errs)


def test_must_end_with_end_card():
    errs = validate_recipe(r([{"block": "fact", "dur": 4}, {"block": "hook_text", "dur": 4}]))
    assert any("end_card" in e for e in errs)


def test_unknown_block_rejected():
    assert validate_recipe(r([{"block": "dance", "dur": 6}, END])) != []


def test_clip_duration_counts_as_clip_max():
    assert validate_recipe(r([{"block": "app_clip", "dur": "clip"}, END], content="clip")) == []


def _app(tmp_path, name, files):
    d = tmp_path / "apps" / name
    for rel, data in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    shutil.copytree(ROOT / "recipes", tmp_path / "recipes", dirs_exist_ok=True)
    return {"slug": name, "dir": d}


def test_facts_only_app_gets_only_fact_recipes(tmp_path):
    app = _app(tmp_path, "newapp", {"facts.yaml": [{"id": "f1", "text": "Free."}]})
    assert {x["id"] for x in load_recipes(tmp_path, app)} == {"fact_card", "problem_app"}


def test_app_recipe_overrides_shared_by_id(tmp_path):
    override = r([{"block": "fact", "dur": 9}, END])
    override["id"] = "fact_card"
    override["weight"] = 7
    app = _app(tmp_path, "a", {"facts.yaml": [{"id": "f1", "text": "x"}], "recipes/fact_card.json": json.dumps(override)})
    [fc] = [x for x in load_recipes(tmp_path, app) if x["id"] == "fact_card"]
    assert fc["weight"] == 7


def test_invalid_recipe_skipped(tmp_path):
    bad = r([{"block": "fact", "dur": 1}])
    bad["id"] = "bad"
    app = _app(tmp_path, "a", {"facts.yaml": [{"id": "f1", "text": "x"}], "recipes/bad.json": json.dumps(bad)})
    assert "bad" not in {x["id"] for x in load_recipes(tmp_path, app)}
