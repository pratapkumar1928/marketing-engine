import html as htmllib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.config import load_app
from engine.renderer.hyperframes import SAFE_BOX, build_html, render, stage_assets, timeline
from engine.types import Copy

ROOT = Path(__file__).parent.parent
APP = load_app(ROOT, "scrollsmack")
ROAST = {"id": "grandma-3", "persona": "The Grandma", "headline": "You'll ruin your eyes & ears",
         "subtitle": "Staring at that thing since dinner."}
FACT = {"id": "no_internet", "text": "ScrollSmack has no internet permission."}
CLIP = {"id": "skit_couple", "file": "skit_couple.mp4", "dur": 7.93, "desc": "x", "floor": True}
COPY = Copy(hook="it's 1am. reel #400.", texts={"hook": "it's 1am. reel #400.", "problem": "3 hours. gone."},
            caption="c", hashtags=[])
SRCS = {"broll": "assets/broll.mp4", "music": "assets/music.wav", "clip": "assets/clip.mp4", "icon": "assets/icon.png"}


def recipe(name):
    p = ROOT / "recipes" / f"{name}.json"
    if not p.exists():
        p = ROOT / "apps" / "scrollsmack" / "recipes" / f"{name}.json"
    return json.loads(p.read_text())


def test_roast_text_verbatim_in_html():
    h = build_html(recipe("roast_card"), COPY, ROAST, APP, SRCS)
    assert htmllib.escape(ROAST["headline"]) in h and htmllib.escape(ROAST["subtitle"]) in h
    assert "{{" not in h and "PERSONA: The Grandma" in h


def test_missing_broll_uses_dark_bg():
    h = build_html(recipe("fact_card"), COPY, FACT, APP, {**SRCS, "broll": None})
    assert "<video" not in h and "bg-dark" in h


def test_broll_video_present_when_available():
    h = build_html(recipe("fact_card"), COPY, FACT, APP, SRCS)
    assert 'src="assets/broll.mp4"' in h and "muted" in h


def test_total_duration_matches_recipe():
    h = build_html(recipe("roast_card"), COPY, ROAST, APP, SRCS)
    assert 'data-duration="8.6"' in h  # 2.6 + 4.2 + 1.8 on the root
    assert [round(d, 2) for _b, _t, d in timeline(recipe("clip_remix"), CLIP)] == [7.93, 1.8]


def test_clip_audio_track_and_floor_fade():
    h = build_html(recipe("clip_remix"), COPY, CLIP, APP, SRCS)
    assert re.search(r'<audio[^>]+src="assets/clip.mp4"', h) and "floor-fade" in h


def test_text_blocks_inside_safe_box():
    for name, content in [("roast_card", ROAST), ("fact_card", FACT), ("problem_app", FACT), ("clip_remix", CLIP)]:
        h = build_html(recipe(name), COPY, content, APP, SRCS)
        boxes = re.findall(r'class="txt[^"]*" style="left:(\d+)px;top:(\d+)px;width:(\d+)px', h)
        assert boxes, name
        for left, top, width in map(lambda b: map(int, b), boxes):
            assert left >= SAFE_BOX["left"] and top >= SAFE_BOX["top"], name
            assert left + width <= SAFE_BOX["left"] + SAFE_BOX["width"], name
            assert top <= SAFE_BOX["top"] + SAFE_BOX["height"], name


def test_every_block_type_renders():
    r = {"id": "all", "content": "fact", "weight": 1, "beats": [
        {"block": b, "dur": 1.5, "bg": "broll", "text": "hook"} for b in
        ["hook_text", "text_beat", "broll", "fact", "app_overlay", "app_clip"]] + [{"block": "end_card", "dur": 2}]}
    content = {**FACT, **ROAST, **CLIP}
    h = build_html(r, COPY, content, APP, SRCS)
    assert h.count('class="clip') >= 7 and "window.__timelines" in h


def test_user_text_is_escaped():
    evil = Copy(hook='<img src=x onerror=alert(1)>', texts={"hook": '<img src=x onerror=alert(1)>'}, caption="", hashtags=[])
    h = build_html(recipe("fact_card"), evil, FACT, APP, SRCS)
    assert "<img src=x" not in h


def test_stage_assets_maps_only_present_files(tmp_path):
    b = tmp_path / "b.mp4"
    b.write_bytes(b"x")
    srcs, files = stage_assets(broll=b, music=None, clip=None, icon=APP["dir"] / "brand/icon.png")
    assert srcs["broll"] == "assets/broll.mp4" and srcs["music"] is None
    assert set(files) == {"broll.mp4", "icon.png"}


def test_subprocess_env_has_no_secrets(monkeypatch):
    from engine.renderer import hyperframes as hf
    monkeypatch.setenv("ENGINE_SECRETS", '{"X":"y"}')
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("SCROLLSMACK_META_PAGE_TOKEN", "t")
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(hf.subprocess, "run", fake_run)
    hf._run(["npx", "x"], Path("."))
    env = seen["env"]
    assert "ENGINE_SECRETS" not in env and "GEMINI_API_KEY" not in env and "SCROLLSMACK_META_PAGE_TOKEN" not in env
    assert "PATH" in env or "Path" in env


@pytest.mark.slow
def test_real_render_each_seed(tmp_path):
    from engine.music.synth import make_track
    clipf = APP["dir"] / "footage" / CLIP["file"]
    for name, content in [("roast_card", ROAST), ("fact_card", FACT), ("clip_remix", CLIP)]:
        music = make_track(12, tmp_path / f"{name}.wav", seed=1)
        srcs, files = stage_assets(broll=None, music=music, clip=clipf if name == "clip_remix" else None,
                                   icon=APP["dir"] / "brand/icon.png")
        out = ROOT / "out" / "seed-check" / f"{name}.mp4"
        render(build_html(recipe(name), COPY, content, APP, srcs), files, tmp_path / name, out, "0.8.106")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name,pix_fmt,width,height", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout.strip()
        assert probe == "h264,1080,1920,yuv420p", (name, probe)
