import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from typer.testing import CliRunner

import config
import tuki
import typer
from agent import onboarding
from agent.model_catalog import CodingCatalog, CodingModel
from core.controller import TukiController


@pytest.fixture
def probe_http(monkeypatch):
    original = httpx.Client
    def install(handler):
        monkeypatch.setattr(onboarding.httpx, "Client", lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(handler)))
    return install


def good_tool_response():
    return {"choices": [{"message": {"tool_calls": [{"type": "function", "function": {
        "name": "tuki_setup_probe", "arguments": '{"marker":"ok"}',
    }}]}}]}


def test_probe_checks_key_and_actual_native_call_without_user_files(probe_http):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer fake-key"
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"is_management_key": False}})
        body = json.loads(request.content)
        assert body["model"] == "vendor/model"
        assert body["max_tokens"] == 256
        assert body["provider"]["require_parameters"] is True
        assert body["tool_choice"]["function"]["name"] == "tuki_setup_probe"
        assert "fake-key" not in request.content.decode()
        assert "C:\\" not in request.content.decode()
        return httpx.Response(200, json=good_tool_response())
    probe_http(handler)
    onboarding.validate_openrouter_setup("fake-key", "vendor/model")
    assert len(requests) == 2


@pytest.mark.parametrize("status,kind", [(401, "key"), (403, "model"), (429, "temporary"), (503, "temporary")])
def test_probe_classifies_access_and_service_errors(probe_http, status, kind):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(status, json={"error": {"message": "rejected credential fake-key"}})
    probe_http(handler)
    with pytest.raises(onboarding.SetupCheckError) as failure:
        onboarding.validate_openrouter_setup("fake-key", "vendor/model")
    assert failure.value.kind == kind
    assert "fake-key" not in str(failure.value)


def test_management_key_is_rejected_before_generation(probe_http):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"is_management_key": True}})
    probe_http(handler)
    with pytest.raises(onboarding.SetupCheckError, match="management key"):
        onboarding.validate_openrouter_setup("fake-key", "vendor/model")
    assert len(requests) == 1


def test_plain_text_does_not_pass_native_tool_validation(probe_http):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "I support tools"}}]})
    probe_http(handler)
    with pytest.raises(onboarding.SetupCheckError, match="valid native tool call"):
        onboarding.validate_openrouter_setup("fake-key", "vendor/model")


def setup_cli(monkeypatch, tmp_path):
    settings = config.Config()
    monkeypatch.setattr(config, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(tuki, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "_config_instance", settings)
    models = (CodingModel("vendor/blocked", 32768, None, None), CodingModel("vendor/good", 32768, None, None))
    monkeypatch.setattr("agent.model_catalog.fetch_coding_catalog", lambda _: CodingCatalog(models, "test-time"))
    return settings


def test_cli_rejects_unknown_new_restriction_then_saves_verified_alternative(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    calls = []
    def validate(key, model, temperature):
        calls.append(model)
        if model == "vendor/blocked":
            raise onboarding.SetupCheckError("Access denied (403): new restriction")
    monkeypatch.setattr(onboarding, "validate_openrouter_setup", validate)
    result = CliRunner().invoke(tuki.app, ["config", "--setup"], input="2\nfake-key\n1\n1\ny\n")
    assert result.exit_code == 0, result.output
    assert calls == ["vendor/blocked", "vendor/good"]
    assert "This model will not be saved" in result.output
    assert settings.model.name == "vendor/good"
    assert settings.setup_completed is True
    assert 'name = "vendor/good"' in (tmp_path / "tukicode.toml").read_text()


def test_unreachable_service_keeps_existing_configuration(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    config.save_config(settings)
    before = (tmp_path / "tukicode.toml").read_bytes()
    def fail(*args):
        raise onboarding.SetupCheckError("Service unavailable", "temporary")
    monkeypatch.setattr(onboarding, "validate_openrouter_setup", fail)
    result = CliRunner().invoke(tuki.app, ["config", "--setup"], input="2\nfake-key\n1\nn\n")
    assert result.exit_code == 1
    assert (tmp_path / "tukicode.toml").read_bytes() == before
    assert settings.model.provider == "ollama"


def test_no_argument_first_run_guides_setup_before_opening_chat(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    validated = []
    monkeypatch.setattr(onboarding, "validate_openrouter_setup", lambda key, model, temperature: validated.append(model))
    class Controller:
        def __init__(self, *args, **kwargs):
            pass
        def switch_model(self, provider, model):
            assert validated == ["vendor/good"]
            assert provider == "openrouter" and model == "vendor/good"
        def save_session(self):
            pass
    app = MagicMock()
    monkeypatch.setattr("core.controller.TukiController", Controller)
    monkeypatch.setattr(tuki, "TukiApp", lambda _: app)
    result = CliRunner().invoke(tuki.app, [], input="2\nfake-key\n2\ny\n")
    assert result.exit_code == 0, result.output
    assert "first session" in " ".join(result.output.split())
    app.run.assert_called_once()


def test_failed_tui_save_restores_previous_configuration_and_client(monkeypatch):
    controller = TukiController.__new__(TukiController)
    previous = config.Config()
    controller.config = previous
    controller.client = object()
    old_client = controller.client
    controller.agent_loop = SimpleNamespace(llm_client=old_client)
    controller.planner = SimpleNamespace(llm_client=old_client)
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(controller, "switch_model", fail)
    with pytest.raises(OSError):
        controller.save_setup("openrouter", "vendor/new", "fake-key")
    assert controller.config is previous
    assert previous.openrouter.api_key == ""
    assert controller.client is old_client


def test_cancelled_first_setup_is_required_again_on_next_launch(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    config.save_config(settings)  # A template exists, but setup was never completed.
    wizard = MagicMock(side_effect=typer.Exit(0))
    ui = MagicMock()
    monkeypatch.setattr(tuki, "show_config", wizard)
    monkeypatch.setattr(tuki, "TukiApp", ui)
    result = CliRunner().invoke(tuki.app, ["chat"])
    assert result.exit_code == 0
    wizard.assert_called_once_with(setup=True)
    ui.assert_not_called()
    assert settings.setup_completed is False


def test_existing_model_is_preflighted_and_repaired_before_ui_opens(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    settings.model.provider = "openrouter"
    settings.model.name = "vendor/previously-working"
    settings.openrouter.api_key = "fake-key"
    settings.setup_completed = True
    config.save_config(settings)
    calls = []
    ui = MagicMock()
    def validate(key, model, temperature):
        assert not ui.run.called
        calls.append(model)
        if len(calls) == 1:
            raise onboarding.SetupCheckError("A new access restriction (403)")
    monkeypatch.setattr(onboarding, "validate_openrouter_setup", validate)
    monkeypatch.setattr("core.controller.TukiController", MagicMock())
    monkeypatch.setattr(tuki, "TukiApp", lambda _: ui)
    result = CliRunner().invoke(tuki.app, ["chat"], input="2\nfake-key\n2\ny\n")
    assert result.exit_code == 0, result.output
    assert calls == ["vendor/previously-working", "vendor/good"]
    ui.run.assert_called_once()


def test_startup_outage_keeps_valid_config_and_does_not_open_broken_chat(tmp_path, monkeypatch):
    settings = setup_cli(monkeypatch, tmp_path)
    settings.model.provider = "openrouter"
    settings.openrouter.api_key = "fake-key"
    settings.setup_completed = True
    config.save_config(settings)
    before = (tmp_path / "tukicode.toml").read_bytes()
    def fail(*args):
        raise onboarding.SetupCheckError("Network unavailable", "temporary")
    monkeypatch.setattr(onboarding, "validate_openrouter_setup", fail)
    ui = MagicMock()
    monkeypatch.setattr(tuki, "TukiApp", ui)
    result = CliRunner().invoke(tuki.app, ["chat"])
    assert result.exit_code == 1
    assert "Your configuration was kept" in " ".join(result.output.split())
    ui.assert_not_called()
    assert (tmp_path / "tukicode.toml").read_bytes() == before
