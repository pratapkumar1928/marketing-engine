"""Music slot. A provider is engine/music/<name>.py exposing make_track(seconds, out, *, seed) -> Path."""
import importlib


def get(cfg: dict):
    return importlib.import_module(f"engine.music.{cfg['provider']}").make_track
