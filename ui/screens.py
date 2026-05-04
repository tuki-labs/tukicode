from textual.screen import ModalScreen
from textual.widgets import OptionList, Input, Label, Button
from textual.containers import Vertical, Horizontal
from textual.binding import Binding

class ModelSelectScreen(ModalScreen):
    """Pantalla para seleccionar el modelo de una lista de proveedores."""
    CSS = """
    ModelSelectScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.6);
    }
    #modal-container {
        width: 50;
        height: 24;
        border: thick $primary;
        background: $surface;
        padding: 1;
        border-title-align: center;
        border-title-color: $accent;
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
            yield Label("Select AI Model", id="title")
            yield OptionList(*self.model_options, id="model-list")
            yield Label("ESC to cancel", id="footer")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self.dismiss(event.option.id)

class ApiKeyScreen(ModalScreen):
    """Pantalla para pedir la API Key de un proveedor."""
    CSS = """
    ApiKeyScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #api-container {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1;
    }
    #api-title {
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    Input {
        margin-bottom: 1;
        border: tall $primary;
    }
    #buttons {
        align: center middle;
        height: auto;
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
            yield Label(f"API Key for {self.provider}", id="api-title")
            yield Input(value=self.current_key, placeholder="Paste your key here...", password=True, id="api-input")
            with Horizontal(id="buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-btn":
            self.dismiss(self.query_one("#api-input").value)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        self.dismiss(event.value)
