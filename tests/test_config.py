from dataclasses import asdict
import tomllib

import pytest
import config


def test_all_providers_and_special_characters_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "_config_instance", None)
    settings = config.Config()
    settings.model.provider = "gemini"
    settings.search.ignored_paths = [r'C:\projects\folder', 'single\' and "double"', 'Español 🐸', '\x7f']
    settings.openrouter.api_key = 'fake\\key"with\nnewlines\tand tabs'
    settings.openrouter.model = "custom-router-model"
    settings.gemini.api_key = "fake-gemini-key"
    settings.gemini.model = "custom-gemini"
    settings.anthropic.api_key = "fake-anthropic-key"
    settings.anthropic.model = "custom-anthropic"
    config.save_config(settings)
    with (tmp_path / "tukicode.toml").open("rb") as stream:
        tomllib.load(stream)
    restored = config.load_config()
    assert asdict(restored) == asdict(settings)


def test_failed_atomic_replace_preserves_existing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_app_dir", lambda: tmp_path)
    target = tmp_path / "tukicode.toml"
    target.write_text('existing = "keep me"\n', encoding="utf-8")
    def fail_replace(*args):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(config.os, "replace", fail_replace)
    with pytest.raises(OSError):
        config.save_config(config.Config())
    assert target.read_text(encoding="utf-8") == 'existing = "keep me"\n'
    assert not list(tmp_path.glob(".tukicode-*.tmp"))


def test_setup_rejects_shell_command_without_displaying_stored_key(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from tuki import app
    settings = config.Config()
    settings.openrouter.api_key = "fake-existing-secret-1234"
    monkeypatch.setattr(config, "_config_instance", settings)
    monkeypatch.setattr(config, "get_app_dir", lambda: tmp_path)
    result = CliRunner().invoke(app, ["config", "--setup"], input="2\n.\\.venv\\Scripts\\python.exe .\\tuki.py config --setup\n")
    assert result.exit_code == 1
    assert "not a terminal command" in result.output
    assert settings.openrouter.api_key not in result.output
    assert not (tmp_path / "tukicode.toml").exists()


def test_installed_config_uses_writable_user_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "site-packages" / "config.py"))
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-appdata"))
    assert config.get_app_dir() == tmp_path / "local-appdata" / "TukiCode"


def test_existing_source_config_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "__file__", str(tmp_path / "config.py"))
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    (tmp_path / "tukicode.toml").write_text("setup_completed = true\n")
    assert config.get_app_dir() == tmp_path
