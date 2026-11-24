"""Recipes = video formats as data. Shared ones in <root>/recipes, app-only ones in apps/<app>/recipes."""
import json
import logging
import re
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

log = logging.getLogger(__name__)
_VALIDATOR = Draft202012Validator(json.loads((Path(__file__).parent / "recipe.schema.json").read_text()))
APP_BLOCKS = {"app_clip", "app_overlay", "fact"}
MIN_LEN, MAX_LEN = 7.0, 30.0

# content kind -> file (relative to the app dir) that must hold a non-empty list
POOLS = {"roast": "copy/roasts.yaml", "fact": "facts.yaml", "clip": "footage/clips.yaml"}


def validate_recipe(r: dict, clip_max: float = 8.0) -> list[str]:
    errs = [e.message for e in _VALIDATOR.iter_errors(r)]
    if errs:
        return errs
    total = sum(clip_max if b["dur"] == "clip" else b["dur"] for b in r["beats"])
    if not MIN_LEN <= total <= MAX_LEN:
        errs.append(f"length {total:.1f}s outside {MIN_LEN:.0f}-{MAX_LEN:.0f}s")
    if not any(b["block"] in APP_BLOCKS for b in r["beats"]):
        errs.append("no beat shows the app (needs app_clip, app_overlay or fact)")
    if r["beats"][-1]["block"] != "end_card":
        errs.append("last beat must be end_card")
    return errs


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _reject_constant(c):
    raise ValueError(f"non-finite number {c}")


def pool(app: dict, kind: str) -> list[dict]:
    """Content items for a kind. Only dicts with a safe string id survive (ids build the combo key)."""
    p = Path(app["dir"]) / POOLS[kind]
    if not p.is_file():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        return []
    return [i for i in data if isinstance(i, dict) and _SAFE_ID.match(str(i.get("id", "")))]


def load_recipes(root: Path, app: dict) -> list[dict]:
    by_id: dict[str, dict] = {}
    for d in (Path(root) / "recipes", Path(app["dir"]) / "recipes"):
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            try:
                r = json.loads(f.read_text(encoding="utf-8"), parse_constant=_reject_constant)
            except (ValueError, OSError) as e:  # JSONDecodeError and UnicodeDecodeError are ValueErrors
                log.warning("recipe %s unreadable: %s", f.name, type(e).__name__)
                continue
            if not isinstance(r, dict):
                log.warning("recipe %s: not an object", f.name)
                continue
            errs = validate_recipe(r)
            if errs:
                log.warning("recipe %s skipped: %s", f.name, "; ".join(errs))
                continue
            by_id[r["id"]] = r  # app folder is read second, so it overrides shared
    return [r for r in by_id.values() if pool(app, r["content"])]
