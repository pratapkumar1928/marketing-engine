import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


@pytest.fixture
def tmp_root(tmp_path):
    shutil.copytree(FIX / "apps", tmp_path / "apps")
    (tmp_path / "apps" / "not_an_app").mkdir()
    return tmp_path


@pytest.fixture
def root():
    return ROOT


@pytest.fixture(autouse=True)
def _no_engine_secrets(monkeypatch):
    monkeypatch.delenv("ENGINE_SECRETS", raising=False)
