from decimal import Decimal

import pytest
from textual.app import App
from textual.widgets import Button, Input, Link, OptionList

from config import Config
from agent.model_catalog import CodingCatalog, CodingModel, KEYS_URL
from ui.screens import SetupWizardScreen


@pytest.mark.asyncio
async def test_tui_setup_has_key_link_and_live_selectable_models(monkeypatch):
    settings = Config()
    settings.model.provider = "openrouter"
    settings.openrouter.api_key = "fake-key-for-ui-test"
    catalog = CodingCatalog((CodingModel("vendor/live-coder", 65536, Decimal(0), Decimal(0)),), "test-time")
    monkeypatch.setattr("agent.model_catalog.fetch_coding_catalog", lambda _: catalog)
    monkeypatch.setattr("agent.onboarding.validate_openrouter_setup", lambda *args: None)
    app = App()
    wizard = SetupWizardScreen(settings)
    async with app.run_test(size=(120, 45)) as pilot:
        await app.push_screen(wizard)
        await pilot.pause()
        wizard.query_one("#next-btn", Button).press()
        await pilot.pause()
        assert wizard.step == 2
        assert wizard.query_one(Link).url == KEYS_URL
        assert wizard.query_one("#key-input", Input).value == "fake-key-for-ui-test"
        wizard.query_one("#next-btn", Button).press()
        await pilot.pause()
        await wizard.workers.wait_for_complete()
        assert wizard.step == 3
        choices = wizard.query_one("#coding-model-options", OptionList)
        choices.highlighted = 0
        choices.action_select()
        await pilot.pause()
        assert wizard.query_one("#model-input", Input).value == "vendor/live-coder"
        wizard.query_one("#next-btn", Button).press()
        await pilot.pause()
        await wizard.workers.wait_for_complete()
        assert wizard.step == 4
        assert wizard.chosen_model == "vendor/live-coder"


@pytest.mark.asyncio
async def test_tui_rejects_new_model_restriction_without_saving(monkeypatch):
    from agent.onboarding import SetupCheckError
    settings = Config()
    settings.model.provider = "openrouter"
    settings.openrouter.api_key = "fake-key"
    original_model = settings.model.name
    catalog = CodingCatalog(tuple(CodingModel(name, 65536, Decimal(0), Decimal(0))
                                  for name in ("vendor/blocked", "vendor/good")), "test-time")
    monkeypatch.setattr("agent.model_catalog.fetch_coding_catalog", lambda _: catalog)
    def validate(key, model, temperature):
        if model == "vendor/blocked":
            raise SetupCheckError("New harness access restriction (403)")
    monkeypatch.setattr("agent.onboarding.validate_openrouter_setup", validate)
    app = App()
    wizard = SetupWizardScreen(settings)
    async with app.run_test(size=(120, 45)) as pilot:
        await app.push_screen(wizard)
        await pilot.pause()
        for _ in range(2):
            wizard.query_one("#next-btn", Button).press()
            await pilot.pause()
        await wizard.workers.wait_for_complete()
        choices = wizard.query_one("#coding-model-options", OptionList)
        choices.highlighted = 0
        choices.action_select()
        await pilot.pause()
        wizard.query_one("#next-btn", Button).press()
        await pilot.pause()
        await wizard.workers.wait_for_complete()
        await pilot.pause()
        assert wizard.step == 3
        assert "vendor/blocked" in wizard.rejected_models
        assert "Configuration was not saved" in wizard.validation_message
        assert settings.model.name == original_model
        assert settings.setup_completed is False
        choices = wizard.query_one("#coding-model-options", OptionList)
        assert choices.option_count == 1
        choices.highlighted = 0
        choices.action_select()
        await pilot.pause()
        wizard.query_one("#next-btn", Button).press()
        await pilot.pause()
        await wizard.workers.wait_for_complete()
        assert wizard.step == 4
        assert wizard.chosen_model == "vendor/good"


@pytest.mark.asyncio
async def test_back_during_validation_cannot_confirm_a_stale_selection(monkeypatch):
    import asyncio
    import threading
    settings = Config()
    settings.model.provider = "openrouter"
    settings.openrouter.api_key = "fake-key"
    catalog = CodingCatalog((CodingModel("vendor/model", 32768, Decimal(0), Decimal(0)),), "test-time")
    monkeypatch.setattr("agent.model_catalog.fetch_coding_catalog", lambda _: catalog)
    entered, release = threading.Event(), threading.Event()
    def validate(*args):
        entered.set()
        release.wait(timeout=5)
    monkeypatch.setattr("agent.onboarding.validate_openrouter_setup", validate)
    app = App()
    wizard = SetupWizardScreen(settings)
    try:
        async with app.run_test(size=(120, 45)) as pilot:
            await app.push_screen(wizard)
            await pilot.pause()
            for _ in range(2):
                wizard.query_one("#next-btn", Button).press()
                await pilot.pause()
            await wizard.workers.wait_for_complete()
            choices = wizard.query_one("#coding-model-options", OptionList)
            choices.highlighted = 0
            choices.action_select()
            await pilot.pause()
            wizard.query_one("#next-btn", Button).press()
            await pilot.pause()
            assert await asyncio.to_thread(entered.wait, 1)
            assert wizard.query_one("#next-btn", Button).disabled
            wizard.query_one("#back-btn", Button).press()
            await pilot.pause()
            assert wizard.step == 2
            release.set()
            await wizard.workers.wait_for_complete()
            assert wizard.step == 2
    finally:
        release.set()
