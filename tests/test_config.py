"""Tests for the layered config system (WS1)."""
import pytest

from stato.core.config import (
    DEFAULT_REGISTRY_URL,
    StatoConfig,
    load_config,
    user_config_dir,
    user_config_path,
    write_config_template,
)


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point user config at a temp dir; return (user_dir, project_dir)."""
    user_dir = tmp_path / "userconf"
    project_dir = tmp_path / "project"
    (project_dir / ".stato").mkdir(parents=True)
    monkeypatch.setenv("STATO_CONFIG_DIR", str(user_dir))
    monkeypatch.delenv("STATO_REGISTRY_URL", raising=False)
    return user_dir, project_dir


def test_defaults(isolated_config):
    _, project_dir = isolated_config
    cfg = load_config(project_dir)
    assert cfg.registry_url == DEFAULT_REGISTRY_URL
    assert cfg.bridge_default == "agents"
    assert cfg.history_keep == 50
    assert cfg.validate_strict is False
    assert all(v == "default" for v in cfg.sources.values())


def test_user_layer(isolated_config):
    user_dir, project_dir = isolated_config
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text(
        '[registry]\nurl = "https://user.example/index.toml"\n'
        "[history]\nkeep = 10\n"
    )
    cfg = load_config(project_dir)
    assert cfg.registry_url == "https://user.example/index.toml"
    assert cfg.history_keep == 10
    assert cfg.sources["registry_url"] == "user"
    assert cfg.sources["bridge_default"] == "default"


def test_project_overrides_user(isolated_config):
    user_dir, project_dir = isolated_config
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text('[registry]\nurl = "https://user.example/i.toml"\n')
    (project_dir / ".stato" / "config.toml").write_text(
        '[registry]\nurl = "https://project.example/i.toml"\n'
        "[validate]\nstrict = true\nsuppress = [\"I006\"]\n"
    )
    cfg = load_config(project_dir)
    assert cfg.registry_url == "https://project.example/i.toml"
    assert cfg.sources["registry_url"] == "project"
    assert cfg.validate_strict is True
    assert cfg.validate_suppress == ["I006"]


def test_env_overrides_all(isolated_config, monkeypatch):
    user_dir, project_dir = isolated_config
    (project_dir / ".stato" / "config.toml").write_text(
        '[registry]\nurl = "https://project.example/i.toml"\n'
    )
    monkeypatch.setenv("STATO_REGISTRY_URL", "https://env.example/i.toml")
    cfg = load_config(project_dir)
    assert cfg.registry_url == "https://env.example/i.toml"
    assert cfg.sources["registry_url"] == "env:STATO_REGISTRY_URL"


def test_malformed_toml_raises(isolated_config):
    _, project_dir = isolated_config
    (project_dir / ".stato" / "config.toml").write_text("[registry\nurl = nope")
    with pytest.raises(RuntimeError, match="Could not parse config"):
        load_config(project_dir)


def test_wrong_type_raises(isolated_config):
    _, project_dir = isolated_config
    (project_dir / ".stato" / "config.toml").write_text("[history]\nkeep = \"lots\"\n")
    with pytest.raises(RuntimeError, match="expected int"):
        load_config(project_dir)


def test_privacy_extra_patterns(isolated_config):
    _, project_dir = isolated_config
    (project_dir / ".stato" / "config.toml").write_text(
        "[privacy]\n"
        "disable = [\"email\"]\n"
        "extra_patterns = [\n"
        "  { pattern = 'LAB-[0-9]{6}', category = 'pii', "
        "description = 'Lab id', replacement = '{LAB_ID}' },\n"
        "]\n"
    )
    cfg = load_config(project_dir)
    assert cfg.privacy_disable == ["email"]
    assert cfg.privacy_extra_patterns[0]["pattern"] == "LAB-[0-9]{6}"


def test_no_project_dir(isolated_config):
    cfg = load_config(None)
    assert isinstance(cfg, StatoConfig)


def test_config_dir_env_override(isolated_config):
    user_dir, _ = isolated_config
    assert user_config_dir() == user_dir
    assert user_config_path() == user_dir / "config.toml"


def test_xdg_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv("STATO_CONFIG_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert user_config_dir() == tmp_path / "xdg" / "stato"


def test_write_template(isolated_config):
    user_dir, _ = isolated_config
    target = user_dir / "config.toml"
    assert write_config_template(target) is True
    assert "[registry]" in target.read_text()
    # second call refuses to overwrite
    target.write_text("custom")
    assert write_config_template(target) is False
    assert target.read_text() == "custom"
