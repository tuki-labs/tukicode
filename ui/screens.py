from textual.screen import ModalScreen
from textual.widgets import OptionList, Input, Label, Button, Select, RadioSet, RadioButton, Markdown, Link
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.binding import Binding
from textual import on

MODAL_CSS = """
ModalScreen {
    align: center middle;
    background: rgba(0, 0, 0, 0.75);
}
"""

class ModelSelectScreen(ModalScreen):
    """Pantalla para seleccionar el modelo de una lista de proveedores."""
    CSS = MODAL_CSS + """
    #modal-container {
        width: 60;
        height: 30;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    #title {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
        color: $accent;
    }
    OptionList {
        background: transparent;
        border: none;
        height: 1fr;
    }
    OptionList > .option-list--option {
        padding: 0 1;
    }
    #footer {
        text-align: center;
        color: $text-disabled;
        margin-top: 1;
    }
    """

    def __init__(self, model_options: list):
        super().__init__()
        self.model_options = model_options

    def compose(self):
        with Vertical(id="modal-container"):
            yield Label("🤖  Select AI Model", id="title")
            yield OptionList(*self.model_options, id="model-list")
            yield Label("↑↓ Navigate · Enter Select · ESC Cancel", id="footer")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(event.option.id)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)


class ApiKeyScreen(ModalScreen):
    """Pantalla para pedir la API Key de un proveedor."""
    CSS = MODAL_CSS + """
    #api-container {
        width: 64;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #api-title {
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
        color: $accent;
    }
    #api-hint {
        color: $text-disabled;
        margin-bottom: 1;
        text-align: center;
    }
    Input {
        margin-bottom: 1;
        border: tall $primary;
    }
    #buttons {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    Button {
        margin: 0 1;
    }
    """
    def __init__(self, provider: str, current_key: str = ""):
        super().__init__()
        self.provider = provider
        self.current_key = current_key

    def compose(self):
        with Vertical(id="api-container"):
            yield Label(f"🔑  API Key — {self.provider}", id="api-title")
            yield Label("Your key is stored locally in tukicode.toml", id="api-hint")
            if self.provider.lower() == "openrouter":
                from agent.model_catalog import KEYS_URL
                yield Link("Create your OpenRouter API key", url=KEYS_URL)
            yield Input(
                value=self.current_key,
                placeholder=f"Paste your {self.provider} API key here...",
                password=True,
                id="api-input"
            )
            with Horizontal(id="buttons"):
                yield Button("💾  Save", variant="primary", id="save-btn")
                yield Button("✖  Cancel", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            self.dismiss(self.query_one("#api-input").value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)


class SetupWizardScreen(ModalScreen):
    """
    Wizard de configuración paso a paso dentro de la TUI.
    Paso 1: Elegir proveedor
    Paso 2: Introducir API Key (si aplica)
    Paso 3: Elegir/escribir modelo
    Paso 4: Confirmar
    """
    CSS = MODAL_CSS + """
    #wizard-container {
        width: 70;
        height: 32;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    #wizard-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #step-indicator {
        text-align: center;
        color: $text-disabled;
        margin-bottom: 1;
    }
    #step-content {
        height: 1fr;
    }
    RadioSet {
        border: none;
        background: transparent;
        height: auto;
    }
    .field-label {
        color: $text-muted;
        margin-top: 1;
        margin-bottom: 0;
    }
    Input {
        margin-bottom: 1;
        border: tall $primary;
    }
    #wizard-buttons {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    #wizard-buttons Button {
        margin: 0 0 0 1;
    }
    #summary-box {
        border: solid $primary;
        padding: 1;
        background: $surface-darken-1;
        height: auto;
    }
    """

    PROVIDERS = ["ollama", "openrouter", "gemini", "anthropic"]
    PROVIDER_LABELS = {
        "ollama": "🖥️  Ollama (Local — Free)",
        "openrouter": "🌐  OpenRouter (Cloud — Multi-model)",
        "gemini": "✨  Google Gemini (Cloud)",
        "anthropic": "🧠  Anthropic Claude (Cloud)",
    }
    DEFAULT_MODELS = {
        "ollama": ["deepseek-coder:1.3b", "llama3", "codestral"],
        "gemini": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
        "anthropic": ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
    }
    NEEDS_KEY = {"openrouter", "gemini", "anthropic"}

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.step = 1
        self.chosen_provider = config.model.provider
        self.chosen_key = ""
        self.chosen_model = config.model.name
        self.coding_catalog = None
        self.rejected_models = set()
        self.validation_message = ""
        self._validating = False
        self._render_generation = 0

    # ──────────────────────────────────────────
    # Compose
    # ──────────────────────────────────────────
    def compose(self):
        with Vertical(id="wizard-container"):
            yield Label("⚙️  TukiCode Setup Wizard", id="wizard-title")
            yield Label("", id="step-indicator")
            with ScrollableContainer(id="step-content"):
                yield Label("", id="step-body")
            with Horizontal(id="wizard-buttons"):
                yield Button("◀  Back", variant="default", id="back-btn")
                yield Button("Next  ▶", variant="primary", id="next-btn")
                yield Button("✖ Cancel", variant="error", id="cancel-btn")

    def on_mount(self):
        self._render_step()

    # ──────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "next-btn":
            self._advance()
        elif event.button.id == "back-btn":
            self._go_back()

    def _advance(self):
        if self._validating:
            return
        # Collect value for current step
        if self.step == 1:
            try:
                radio_set = self.query_one(RadioSet)
                idx = radio_set.pressed_index
                if self.PROVIDERS[idx] != self.chosen_provider:
                    self.chosen_model = ""
                    self.coding_catalog = None
                self.chosen_provider = self.PROVIDERS[idx]
            except Exception:
                pass
            if self.chosen_provider in self.NEEDS_KEY:
                self.step = 2
            else:
                self.step = 3
        elif self.step == 2:
            try:
                self.chosen_key = self.query_one("#key-input").value.strip()
            except Exception:
                pass
            if not self.chosen_key or any(c.isspace() or c == "\\" for c in self.chosen_key):
                self.notify("Enter an API key, not a command or path.", severity="warning")
                return
            self.step = 3
        elif self.step == 3:
            try:
                model_input = self.query_one("#model-input").value.strip()
                if model_input:
                    self.chosen_model = model_input
            except Exception:
                pass
            if not self.chosen_model:
                self.notify("Choose or enter a model first.", severity="warning")
                return
            if self.chosen_provider == "openrouter" and self.coding_catalog:
                if self.chosen_model not in {m.id for m in self.coding_catalog.models}:
                    self.notify("Choose a model with tool calling from the current catalog.", severity="warning")
                    return
            if self.chosen_provider == "openrouter":
                if self.chosen_model in self.rejected_models:
                    self.notify("This model failed its access check. Choose another model.", severity="warning")
                    return
                self._validating = True
                self.query_one("#next-btn", Button).disabled = True
                self.run_worker(self._validate_openrouter_selection(self._render_generation),
                                group="setup-validation", exclusive=True)
                return
            self.step = 4
        elif self.step == 4:
            # Confirmed — save and dismiss
            self._save_and_dismiss()
            return
        self._render_step()

    def _go_back(self):
        if self.step == 1:
            self.dismiss(None)
        elif self.step == 2:
            self.step = 1
        elif self.step == 3:
            self.step = 2 if self.chosen_provider in self.NEEDS_KEY else 1
        elif self.step == 4:
            self.step = 3
        self._render_step()

    # ──────────────────────────────────────────
    # Rendering each step
    # ──────────────────────────────────────────
    def _render_step(self):
        self._render_generation += 1
        self._validating = False
        self.run_worker(self._render_step_content(self._render_generation),
                        group="setup-render", exclusive=True)

    async def _render_step_content(self, generation):
        total = 4 if self.chosen_provider in self.NEEDS_KEY else 3
        self.query_one("#step-indicator").update(f"Step {self.step} of {total}")
        container = self.query_one("#step-content")
        await container.remove_children()
        if not self.is_mounted or generation != self._render_generation:
            return

        back_btn = self.query_one("#back-btn")
        next_btn = self.query_one("#next-btn")
        next_btn.disabled = False
        back_btn.label = "◀  Back"
        next_btn.label = "Finish ✔" if self.step == 4 else "Next  ▶"
        if self.validation_message:
            from textual.widgets import Static
            from rich.text import Text
            container.mount(Static(Text(self.validation_message, style="yellow")))

        if self.step == 1:
            self._render_step1(container)
        elif self.step == 2:
            self._render_step2(container)
        elif self.step == 3:
            self._render_step3(container)
        elif self.step == 4:
            self._render_step4(container)

    def _render_step1(self, container):
        from textual.widgets import Static
        container.mount(Static("[bold]Choose your AI Provider:[/bold]\n"))
        buttons = []
        for i, p in enumerate(self.PROVIDERS):
            buttons.append(RadioButton(
                self.PROVIDER_LABELS[p],
                value=(p == self.chosen_provider)
            ))
        container.mount(RadioSet(*buttons))

    def _render_step2(self, container):
        from textual.widgets import Static
        provider_label = self.PROVIDER_LABELS.get(self.chosen_provider, self.chosen_provider)
        container.mount(Static(f"[bold]API Key for {provider_label}[/bold]\n"))
        container.mount(Static("[dim]Your key will be stored locally in tukicode.toml[/dim]"))
        if self.chosen_provider == "openrouter":
            from agent.model_catalog import KEYS_URL
            container.mount(Link("Create your OpenRouter API key", url=KEYS_URL))

        # Pre-fill with existing key if present
        existing = ""
        if self.chosen_provider == "openrouter":
            existing = self.config.openrouter.api_key
        elif self.chosen_provider == "gemini":
            existing = self.config.gemini.api_key
        elif self.chosen_provider == "anthropic":
            existing = self.config.anthropic.api_key

        container.mount(
            Input(value=existing, placeholder="sk-...", password=True, id="key-input")
        )

    def _render_step3(self, container):
        from textual.widgets import Static
        container.mount(Static(f"[bold]Choose or type a model for {self.chosen_provider.upper()}:[/bold]\n"))
        defaults = self.DEFAULT_MODELS.get(self.chosen_provider, [])
        if defaults:
            container.mount(Static("[dim]Suggested models (or type your own below):[/dim]"))
            for m in defaults:
                container.mount(Static(f"  • {m}"))
        container.mount(Static(""))
        container.mount(
            Input(value=self.chosen_model, placeholder="model-name", id="model-input")
        )
        if self.chosen_provider == "openrouter":
            container.mount(Static("Next checks your key and runs a short synthetic tool-call test before saving. Normal model pricing/limits apply; no files are sent."))
            container.mount(Static("Fetching current coding models with tool calling...", id="catalog-status"))
            self.run_worker(self._load_coding_models(container), group="coding-catalog", exclusive=True)

    async def _load_coding_models(self, container):
        import asyncio
        from rich.text import Text
        from textual.widgets import Static
        from textual.widgets.option_list import Option
        from config import get_app_dir
        from agent.model_catalog import fetch_coding_catalog, CodingCatalog, MODELS_PAGE
        try:
            catalog = await asyncio.to_thread(fetch_coding_catalog, get_app_dir() / "data" / "openrouter-models.json")
        except RuntimeError:
            if self.is_mounted and self.step == 3 and self.chosen_provider == "openrouter":
                self.query_one("#catalog-status", Static).update("Catalog unavailable. Enter a model ID manually; tool support could not be verified.")
                await container.mount(Link("Browse models with tool calling", url=MODELS_PAGE))
            return
        if not self.is_mounted or self.step != 3 or self.chosen_provider != "openrouter":
            return
        catalog = CodingCatalog(tuple(m for m in catalog.models if m.id not in self.rejected_models), catalog.fetched_at, catalog.cached)
        self.coding_catalog = catalog
        source = "CACHED (online lookup failed)" if catalog.cached else "LIVE"
        self.query_one("#catalog-status", Static).update(Text(
            f"{source} | {catalog.fetched_at}\nOpenRouter coding index (Artificial Analysis); unscored last. "
            "All entries advertise tools; known app restrictions excluded. Account access may vary. Prices: USD / 1M input / output tokens. "
            "Free options may have stricter limits. Select a model below."
        ))
        options = [Option(Text(f"{m.id} | {m.price_label} | context {m.context:,}"), id=m.id)
                   for m in catalog.recommendations()]
        await container.mount(OptionList(*options, id="coding-model-options"), before="#model-input")

    async def _validate_openrouter_selection(self, generation):
        import asyncio
        from agent.onboarding import validate_openrouter_setup, SetupCheckError
        model_name, key = self.chosen_model, self.chosen_key
        try:
            await asyncio.to_thread(validate_openrouter_setup, key, model_name, self.config.model.temperature)
        except SetupCheckError as error:
            if not self.is_mounted or generation != self._render_generation:
                return
            self.validation_message = str(error) + " Configuration was not saved."
            if error.kind == "key":
                self.step = 2
            elif error.kind == "model":
                self.rejected_models.add(model_name)
                self.chosen_model = ""
            self._render_step()
            return
        if not self.is_mounted or generation != self._render_generation:
            return
        self.validation_message = "OpenRouter access and native tool calling verified."
        self.step = 4
        self._render_step()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        if event.option_list.id == "coding-model-options":
            self.query_one("#model-input", Input).value = event.option.id

    def _render_step4(self, container):
        from textual.widgets import Static
        key_display = "****" + self.chosen_key[-4:] if self.chosen_key and len(self.chosen_key) > 4 else ("(none)" if not self.chosen_key else self.chosen_key)
        summary = (
            f"[bold green]✅ Ready to save:[/bold green]\n\n"
            f"  Provider : [cyan]{self.chosen_provider.upper()}[/cyan]\n"
            f"  Model    : [cyan]{self.chosen_model}[/cyan]\n"
        )
        if self.chosen_provider in self.NEEDS_KEY:
            summary += f"  API Key  : [dim]{key_display}[/dim]\n"
        container.mount(Static(summary, id="summary-box"))

    # ──────────────────────────────────────────
    # Save
    # ──────────────────────────────────────────
    def _save_and_dismiss(self):
        result = {
            "provider": self.chosen_provider,
            "model": self.chosen_model,
            "key": self.chosen_key,
        }
        self.dismiss(result)

    def on_key(self, event):
        if event.key == "escape":
            self.dismiss(None)
