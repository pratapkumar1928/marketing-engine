import json
import os
from pathlib import Path

import yaml


def read_yaml(path: Path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_config(root: Path) -> dict:
    return read_yaml(Path(root) / "config.yaml")


def list_apps(root: Path) -> list[str]:
    apps = Path(root) / "apps"
    if not apps.is_dir():
        return []
    return sorted(p.name for p in apps.iterdir() if (p / "app.yaml").is_file())


def load_app(root: Path, name: str) -> dict:
    d = Path(root) / "apps" / name
    app = read_yaml(d / "app.yaml")
    app["dir"] = d
    app["slug"] = name  # identity is the folder name; app.yaml can't redirect ledger/state paths
    return app


def app_file(app: dict, rel: str) -> Path:
    """A path from app data (icon, clip file), confined to the app's folder. Escapes raise ValueError."""
    base = Path(app["dir"]).resolve()
    rel = str(rel or "")
    if not rel or Path(rel).is_absolute() or Path(rel).drive:
        raise ValueError("asset path must be relative to the app folder")
    p = (base / rel).resolve()
    if p == base or not p.is_relative_to(base):
        raise ValueError("asset path outside the app folder")
    return p


REPO_ROOT = Path(__file__).resolve().parent.parent


def _dotenv() -> dict:
    if os.environ.get("GITHUB_ACTIONS"):
        return {}  # CI secrets come only from ENGINE_SECRETS / env
    p = REPO_ROOT / ".env"
    if not p.is_file():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def secret(name: str) -> str:
    """GitHub Actions secrets (ENGINE_SECRETS json) > env > ./.env. Missing -> KeyError(name) only."""
    blob = os.environ.get("ENGINE_SECRETS")
    if blob:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            raise RuntimeError("ENGINE_SECRETS is not valid JSON") from None  # fail closed, no content echoed
        val = data.get(name)
        if val:
            return val
    if os.environ.get(name):
        return os.environ[name]
    val = _dotenv().get(name)
    if val:
        return val
    raise KeyError(name)
