"""Is an app folder ready? Plus a preview mode that renders N videos without touching the ledger or posting."""
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml

from engine.config import app_file, load_app, load_config
from engine.recipes import load_recipes, pool
from engine.types import CopyRejected, Slot

REQUIRED = ["name", "store_url", "timezone", "post_times", "platforms"]
SECRET_BLOCK = {"instagram": ("meta", "token_secret"), "facebook": ("meta", "token_secret"),
                "youtube": ("youtube", "refresh_token_secret")}
MAX_CLIP = 100 * 1024 * 1024


def _list(path: Path) -> list:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def check_app(root: Path, name: str) -> list[str]:
    root = Path(root)
    if not (root / "apps" / name / "app.yaml").is_file():
        return [f"apps/{name}/app.yaml not found"]
    app = load_app(root, name)
    d = Path(app["dir"])
    problems = [f"app.yaml: missing '{k}'" for k in REQUIRED if not app.get(k)]
    brand = app.get("brand") or {}
    if not brand.get("colors"):
        problems.append("app.yaml: missing brand.colors")
    try:
        if not app_file(app, brand.get("icon", "")).is_file():
            problems.append("brand icon file not found")
    except ValueError:
        problems.append("brand icon path must stay inside the app folder")
    for pname, p in (app.get("platforms") or {}).items():
        if p.get("enabled") and not p.get("enabled_on"):
            problems.append(f"platforms.{pname}: enabled without enabled_on")
        block, key = SECRET_BLOCK.get(pname, (None, None))
        if p.get("enabled") and block and not (app.get(block) or {}).get(key):
            problems.append(f"platforms.{pname}: needs a {block} block with secret names")
    if len(pool(app, "fact")) < 5:
        problems.append("facts.yaml: need at least 5 facts (each with a safe id and text)")
    if len(_list(d / "copy" / "hashtags.yaml")) < 5:
        problems.append("copy/hashtags.yaml: need at least 5 hashtags")
    if len(_list(d / "copy" / "keywords.yaml")) < 3:
        problems.append("copy/keywords.yaml: need at least 3 b-roll keywords")
    style = d / "copy" / "style.md"
    if not style.is_file() or not style.read_text(encoding="utf-8").strip():
        problems.append("copy/style.md: missing or empty")
    if not load_recipes(root, app):
        problems.append("no usable recipe for this app")
    for clip in pool(app, "clip"):
        try:
            f = app_file(app, f"footage/{clip.get('file', '')}")
        except ValueError:
            problems.append(f"clip {clip['id']}: path must stay inside the app folder")
            continue
        if not f.is_file():
            problems.append(f"clip {clip['id']}: {f.name} not found")
        elif f.stat().st_size >= MAX_CLIP:
            problems.append(f"clip {clip['id']}: {f.name} is over 100 MB")
    return problems


def preview(root: Path, name: str, n: int, deps) -> list[Path]:
    """Plan, write and render n videos into out/preview/<name>/. No ledger, no publishing."""
    from engine.main import render_slot
    root = Path(root)
    app = load_app(root, name)
    recipes = load_recipes(root, app)
    now = datetime.now(timezone.utc)
    out = []
    for i in range(n):
        slot = Slot(app=name, slot_id=f"preview#{i}", at=now, platforms=[])
        try:
            video, _plan, _copy = render_slot(root, app, slot, recipes, [], deps,
                                              root / "out" / "preview" / name / f"preview_{i}.mp4")
            out.append(video)
        except CopyRejected as e:
            print(f"preview {i}: copy rejected: {e.reason}")
        except Exception as e:  # noqa: BLE001 - one bad preview must not stop the others
            print(f"preview {i}: render failed: {type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}")
    return out


def main(root: Path, name: str, n: int) -> int:
    problems = check_app(root, name)
    for p in problems:
        print(f"- {p}")
    if problems:
        return 1
    print(f"{name}: ready")
    if n:
        from engine.main import real_deps
        deps = real_deps(root)
        deps.rng = random.Random()
        for p in preview(root, name, n, deps):
            print(f"preview: {p}")
    return 0
