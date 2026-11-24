"""Publisher slot. A platform is engine/publishers/<name>.py exposing
publish(video: Path, caption: str, app: dict, *, http=requests) -> Published (raises PublishError)."""
import importlib


def get(name: str):
    return importlib.import_module(f"engine.publishers.{name}").publish
