import random
import shutil
from pathlib import Path

import pytest
import yaml

from engine.checkapp import check_app, preview
from engine.main import Deps
from engine.types import Copy

ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures" / "apps" / "newapp"


@pytest.fixture
def root(tmp_path):
    shutil.copytree(FIX, tmp_path / "apps" / "newapp")
    shutil.copytree(ROOT / "recipes", tmp_path / "recipes")
    shutil.copy(ROOT / "config.yaml", tmp_path / "config.yaml")
    return tmp_path


def edit(root, fn, rel="app.yaml"):
    p = root / "apps" / "newapp" / rel
    data = yaml.safe_load(p.read_text())
    fn(data)
    p.write_text(yaml.safe_dump(data))


def test_fixture_newapp_passes(root):
    assert check_app(root, "newapp") == []


def test_scrollsmack_passes():
    assert check_app(ROOT, "scrollsmack") == []


def test_missing_facts_reported(root):
    edit(root, lambda d: d.__delitem__(slice(2, None)), "facts.yaml")
    assert any("facts" in p for p in check_app(root, "newapp"))


def test_enabled_without_enabled_on_reported(root):
    edit(root, lambda d: d["platforms"]["instagram"].update(enabled=True))
    assert any("enabled_on" in p for p in check_app(root, "newapp"))


def test_youtube_without_secret_block_reported(root):
    edit(root, lambda d: d["platforms"].update(youtube={"enabled": True, "enabled_on": "2026-12-05"}))
    assert any("needs a youtube block" in p for p in check_app(root, "newapp"))


def test_missing_icon_reported(root):
    (root / "apps" / "newapp" / "brand" / "icon.png").unlink()
    assert any("icon" in p for p in check_app(root, "newapp"))


def test_missing_required_key_reported(root):
    edit(root, lambda d: d.pop("store_url"))
    assert any("store_url" in p for p in check_app(root, "newapp"))


def test_unknown_app_reported(root):
    assert check_app(root, "nope") != []


def test_one_failed_preview_does_not_stop_the_rest(root, capsys):
    from engine.types import CopyRejected
    calls = {"n": 0}

    def write_copy(*a):
        calls["n"] += 1
        if calls["n"] == 1:
            raise CopyRejected("non-Latin letters not allowed: 拼")
        return Copy(hook="h", texts={"hook": "h", "problem": "p"}, caption="c", hashtags=[])

    def render(recipe, copy, content, app, *, broll, music, clip, out):
        if calls["n"] == 2:
            raise RuntimeError("hyperframes check failed")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mp4")
        return Path(out)

    deps = Deps(llm=None, broll=lambda q, d, rng: None, music=lambda s, out, seed: None, render=render,
                publishers={}, rng=random.Random(0), write_copy=write_copy)
    paths = preview(root, "newapp", 3, deps)
    assert len(paths) == 1
    out = capsys.readouterr().out
    assert "copy rejected" in out and "render failed" in out


def test_preview_never_touches_ledger(root):
    rendered = []

    def render(recipe, copy, content, app, *, broll, music, clip, out):
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mp4")
        rendered.append(out)
        return Path(out)

    def publish(*a, **k):
        raise AssertionError("preview must never publish")

    deps = Deps(llm=None, broll=lambda q, d, rng: None, music=lambda s, out, seed: None, render=render,
                publishers={"instagram": publish}, rng=random.Random(0),
                write_copy=lambda *a: Copy(hook="h", texts={"hook": "h", "problem": "p"}, caption="c", hashtags=[]))
    paths = preview(root, "newapp", 2, deps)
    assert len(paths) == 2 and all(p.parent == root / "out" / "preview" / "newapp" for p in paths)
    assert not (root / "state").exists()
