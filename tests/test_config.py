import pytest

from engine.config import list_apps, load_app, load_config, secret


def test_list_apps_finds_folders_with_app_yaml(tmp_root):
    assert list_apps(tmp_root) == ["demo"]


def test_load_app_adds_dir(tmp_root):
    app = load_app(tmp_root, "demo")
    assert app["name"] == "Demo" and app["dir"] == tmp_root / "apps" / "demo"


def test_secret_prefers_engine_secrets(monkeypatch):
    monkeypatch.setenv("ENGINE_SECRETS", '{"X":"a"}')
    monkeypatch.setenv("X", "b")
    assert secret("X") == "a"


def test_secret_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("X", "b")
    assert secret("X") == "b"


def test_secret_missing_raises_keyerror_with_name_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyError) as e:
        secret("NOPE")
    assert e.value.args == ("NOPE",)


def test_config_names_providers(root):
    assert load_config(root)["llm"]["provider"] == "gemini"
