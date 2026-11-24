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
    app.setdefault("slug", name)
    return app


def _dotenv() -> dict:
    p = Path(".env")
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
        val = json.loads(blob).get(name)
        if val:
            return val
    if os.environ.get(name):
        return os.environ[name]
    val = _dotenv().get(name)
    if val:
        return val
    raise KeyError(name)
