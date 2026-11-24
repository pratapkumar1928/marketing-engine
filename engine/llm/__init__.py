"""LLM slot. A provider is engine/llm/<name>.py exposing generate(prompt, schema, *, model) -> dict."""
import functools
import importlib


def get(cfg: dict):
    mod = importlib.import_module(f"engine.llm.{cfg['provider']}")
    return functools.partial(mod.generate, model=cfg["model"])
