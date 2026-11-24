from pathlib import Path

import yaml

from engine.config import load_app
from engine.recipes import load_recipes, pool

ROOT = Path(__file__).parent.parent


def test_scrollsmack_app_loads_and_recipes_valid():
    app = load_app(ROOT, "scrollsmack")
    ids = {r["id"] for r in load_recipes(ROOT, app)}
    assert ids == {"fact_card", "problem_app", "roast_card", "clip_remix"}
    assert len(pool(app, "roast")) == 40 and len(pool(app, "fact")) >= 10


def test_every_clip_file_exists_and_listed():
    d = ROOT / "apps" / "scrollsmack" / "footage"
    listed = {c["file"] for c in yaml.safe_load((d / "clips.yaml").read_text())}
    on_disk = {p.name for p in d.glob("*.mp4")}
    assert listed == on_disk
    assert all((d / f).stat().st_size < 100 * 1024 * 1024 for f in listed)


def test_brand_assets_present():
    app = load_app(ROOT, "scrollsmack")
    assert (app["dir"] / app["brand"]["icon"]).is_file()
    assert {p.name for p in (ROOT / "renderer" / "fonts").glob("*.ttf")} >= {"archivo_black.ttf", "jetbrains_mono.ttf"}


def test_overlay_block_has_placeholders_and_stays_in_safe_zone():
    html = (ROOT / "apps/scrollsmack/blocks/app_overlay.html").read_text(encoding="utf-8")
    for ph in ("{{persona}}", "{{headline}}", "{{subtitle}}", "{{t}}", "{{headline_size}}"):
        assert ph in html
    assert "left: 70px" in html and "width: 870px" in html  # right edge 940 <= 950
