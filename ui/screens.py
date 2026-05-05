from textual.screen import ModalScreen
from textual.widgets import OptionList, Input, Label, Button, Select, RadioSet, RadioButton, Markdown
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
        "openrouter": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "tencent/hy3-preview:free"],
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
        # Collect value for current step
        if self.step == 1:
            try:
                radio_set = self.query_one(RadioSet)
                idx = radio_set.pressed_index
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
            self.step = 3
        elif self.step == 3:
            try:
                model_input = self.query_one("#model-input").value.strip()
                if model_input:
                    self.chosen_model = model_input
            except Exception:
                pass
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
        total = 4 if self.chosen_provider in self.NEEDS_KEY else 3
        self.query_one("#step-indicator").update(f"Step {self.step} of {total}")
        container = self.query_one("#step-content")
        container.remove_children()

        back_btn = self.query_one("#back-btn")
        next_btn = self.query_one("#next-btn")
        back_btn.label = "◀  Back"
        next_btn.label = "Finish ✔" if self.step == 4 else "Next  ▶"

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
