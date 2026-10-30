import json
from decimal import Decimal

import httpx
import pytest
from typer.testing import CliRunner

import config
from agent import model_catalog as catalog


def model(model_id, tools=True, price="0.000001", **overrides):
    return dict(id=model_id, supported_parameters=["tools"] if tools else [],
                context_length=32768, pricing={"prompt": price, "completion": price}, **overrides)


@pytest.fixture
def mock_catalog_http(monkeypatch):
    original = httpx.Client
    def install(handler):
        monkeypatch.setattr(catalog.httpx, "Client", lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(handler)))
    return install


def test_live_coding_order_filter_prices_and_free_options(tmp_path, mock_catalog_http):
    data = [model("vendor/no-tools", tools=False), model("vendor/best"),
            model("thinkingmachines/inkling-small:free", price="0"),
            model("thinkingmachines/inkling:free", price="0"),
            model("vendor/batch:batch"), model("vendor/second"),
            model("vendor/expired", expiration_date="2020-01-01"),
            model("vendor/free", price="0"), model("vendor/best")]
    def handler(request):
        assert request.url.params["sort"] == "coding-high-to-low"
        assert request.url.params["supported_parameters"] == "tools"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"data": data})
    mock_catalog_http(handler)
    result = catalog.fetch_coding_catalog(tmp_path / "models.json")
    assert not result.cached
    assert [m.id for m in result.models] == ["vendor/best", "vendor/second", "vendor/free"]
    assert result.models[0].price_label == "$1.00 / $1.00"
    assert result.models[-1].price_label == "Free"
    assert result.models[-1].free


def test_outage_uses_labelled_cache_without_losing_order(tmp_path, mock_catalog_http):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"sort": "coding-high-to-low", "fetched_at": "2026-10-30T00:00:00+00:00",
                                "data": [model("vendor/cached")]}), encoding="utf-8")
    mock_catalog_http(lambda request: httpx.Response(503))
    result = catalog.fetch_coding_catalog(path)
    assert result.cached
    assert result.models[0].id == "vendor/cached"
    assert result.fetched_at == "2026-10-30T00:00:00+00:00"


def test_outage_without_cache_is_explicit(tmp_path, mock_catalog_http):
    mock_catalog_http(lambda request: httpx.Response(429))
    with pytest.raises(RuntimeError, match="no usable cached"):
        catalog.fetch_coding_catalog(tmp_path / "missing.json")


def test_successful_lookup_survives_read_only_cache(tmp_path, mock_catalog_http):
    parent = tmp_path / "file"
    parent.write_text("not a directory")
    mock_catalog_http(lambda request: httpx.Response(200, json={"data": [model("vendor/live")]}))
    assert not catalog.fetch_coding_catalog(parent / "cache.json").cached


def test_free_additions_preserve_upstream_coding_order():
    models = tuple(catalog.CodingModel(f"vendor/model-{i}", 32768,
                                      Decimal(0 if i > 5 else 1), Decimal(0 if i > 5 else 1)) for i in range(10))
    result = catalog.CodingCatalog(models, "now")
    assert result.recommendations() == list(models[:9])


def test_cli_setup_shows_key_link_and_saves_number_selection(tmp_path, monkeypatch, mock_catalog_http):
    from tuki import app
    settings = config.Config()
    monkeypatch.setattr(config, "_config_instance", settings)
    monkeypatch.setattr(config, "get_app_dir", lambda: tmp_path)
    monkeypatch.setattr("agent.onboarding.validate_openrouter_setup", lambda *args: None)
    mock_catalog_http(lambda request: httpx.Response(200, json={"data": [model("vendor/coder")]}))
    result = CliRunner().invoke(app, ["config", "--setup"], input="2\nfake-openrouter-key\n99\n1\ny\n")
    assert result.exit_code == 0, result.output
    assert catalog.KEYS_URL in result.output
    assert "LIVE" in result.output
    assert "vendor/coder" in result.output
    assert "fake-openrouter-key" not in result.output
    assert settings.model.name == "vendor/coder"
    assert settings.model.provider == "openrouter"


@pytest.mark.asyncio
async def test_tool_requests_require_capable_provider_instead_of_static_blacklist():
    from agent.openrouter_client import OpenRouterClient
    client = OpenRouterClient("openai/gpt-oss-120b:free", 0, 100, False, "fake-key")
    try:
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        payload = client._build_payload([], tools)
        assert payload["tools"] == tools
        assert payload["provider"]["require_parameters"] is True
    finally:
        await client.close()
