"""B-roll slot. A provider is engine/broll/<name>.py exposing fetch(query, out_dir, *, rng) -> Path | None."""
import importlib


def get(cfg: dict):
    return importlib.import_module(f"engine.broll.{cfg['provider']}").fetch
