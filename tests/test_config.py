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


def test_app_yaml_cannot_override_slug(tmp_root):
    (tmp_root / "apps" / "demo" / "app.yaml").write_text("name: Demo\nslug: other\n")
    assert load_app(tmp_root, "demo")["slug"] == "demo"


def test_dotenv_ignored_on_github_actions(monkeypatch, tmp_path):
    import engine.config as c
    (tmp_path / ".env").write_text("Y=from_dotenv\n")
    monkeypatch.setattr(c, "REPO_ROOT", tmp_path)
    assert secret("Y") == "from_dotenv"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(KeyError):
        secret("Y")


def test_dotenv_read_from_repo_root_not_cwd(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("Z=cwd_value\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(KeyError):
        secret("Z")


def test_malformed_engine_secrets_fails_closed(monkeypatch):
    monkeypatch.setenv("ENGINE_SECRETS", "{not json")
    monkeypatch.setenv("X", "b")
    with pytest.raises(RuntimeError) as e:
        secret("X")
    assert "ENGINE_SECRETS" in str(e.value) and "b" not in str(e.value).replace("ENGINE_SECRETS", "")


def test_config_names_providers(root):
    assert load_config(root)["llm"]["provider"] == "gemini"
