"""Renderer slot. A provider is engine/renderer/<name>.py exposing
build_html(recipe, copy, content, app, srcs) -> str and render(html, files, workdir, out, version) -> Path."""
import importlib


def get(cfg: dict):
    return importlib.import_module(f"engine.renderer.{cfg['provider']}")
