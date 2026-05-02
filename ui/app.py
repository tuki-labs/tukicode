from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.containers import Horizontal, Vertical, Container
from textual.binding import Binding
from rich.markdown import Markdown
from rich.panel import Panel
from agent_icon import TukiAnimation
import asyncio

class TukiApp(App):
    CSS = """
    Screen {
        background: #0a0a0a;
        color: #e0e0e0;
    }
    #main-container {
        height: 1fr;
    }
    #left-panel {
        width: 38;
        height: 12;
        border: none;
        margin: 1 0 0 1;
        padding: 0;
        background: transparent;
    }
    #chat-log {
        border: solid #333;
        height: 1fr;
        scrollbar-size: 1 1;
        background: #0d0d0d;
        padding: 1 2;
    }
    #thinking-panel {
        height: auto;
        max-height: 10;
        border: solid #2a2a1a;
        background: #111100;
        color: #aaaa55;
        display: none;
        margin: 0 1;
        padding: 0 1;
    }
    #thinking-panel.visible {
        display: block;
    }
    #input-bar {
        height: 3;
        border: solid #444;
        background: #111;
        margin: 0 1 1 1;
        color: #ffffff;
    }
    #status-bar {
        height: 1;
        background: #1a1a1a;
        color: #666;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Exit"),
        Binding("/", "focus_input", "Focus Input"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
    ]

    def __init__(self, config, client, registry, context, session_id=None):
        super().__init__()
        self.config = config
        self.client = client
        self.registry = registry
        self.context = context
        self.session_id = session_id
        from agent.loop import AgentLoop
        from ui.display import TukiDisplay
        self.tuki_display = TukiDisplay()
        self.tuki_display.set_app(self)
        self.agent_loop = AgentLoop(config, client, registry, context, self.tuki_display)
        self.anim = TukiAnimation(start_thread=False)
        self.session_title = None
        self._confirm_future = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            yield Static(id="left-panel")
            yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
        yield Static("", id="thinking-panel")
        yield Input(placeholder="Ask anything...", id="input-bar")
        yield Static("Initializing...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.12, self.update_mascot)
        self.update_status()
        self.query_one("#input-bar").focus()
        self.add_message("system", "Welcome to TukiCode! Type your message below.")

    def update_mascot(self) -> None:
        from rich.text import Text
        frame = self.anim.get_current_frame()
        self.query_one("#left-panel").update(Text.from_ansi("\n".join(frame)))

    def update_status(self) -> None:
        model = self.config.model.name
        tokens = int(self.context.token_count)
        risk = self.config.agent.risk_level
        status = f"Model: {model} | Tokens: {tokens} | Risk: {risk}"
        self.query_one("#status-bar").update(status)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        
        event.input.value = ""
        
        if self._confirm_future:
            if text.lower() in ["y", "yes", "s", "si"]:
                self._confirm_future.set_result(True)
            else:
                self._confirm_future.set_result(False)
            return

        if text.startswith("/"):
            await self.handle_command(text)
            return

        self.add_message("user", text)
        asyncio.create_task(self.run_agent(text))

    async def confirm_prompt(self, message: str) -> bool:
        self.add_message("system", f"[bold yellow]⚠️ {message}[/bold yellow]")
        self.query_one("#input-bar").placeholder = "Confirm? (y/n) >"
        self._confirm_future = asyncio.get_event_loop().create_future()
        try:
            return await self._confirm_future
        finally:
            self.query_one("#input-bar").placeholder = "Ask anything..."
            self._confirm_future = None

    async def handle_command(self, text):
        if text == "/exit":
            self.exit()
        elif text == "/clear":
            self.query_one("#chat-log").clear()
            self.add_message("system", "Chat history cleared.")
        elif text == "/help":
            self.add_message("assistant", "Available commands:\n- /exit: Exit TukiCode\n- /clear: Clear chat log\n- /site: Open website\n- /copy: Copy last code block")
        elif text == "/site":
            import webbrowser
            webbrowser.open("https://tukicode.site")
            self.add_message("system", "Opening TukiCode website...")
        else:
            self.add_message("error", f"Unknown command: {text}")

    def add_message(self, role: str, text):
        from rich.text import Text
        log = self.query_one("#chat-log")
        
        # Envolver strings en Text.from_ansi por si contienen escape codes
        renderable = Text.from_ansi(text) if isinstance(text, str) else text

        if role == "user":
            log.write(f"\n[bold blue]You:[/bold blue] {text}")
        elif role == "assistant":
            log.write(f"\n[bold cyan]TukiCode:[/bold cyan]")
            log.write(renderable)
        elif role == "tool_result":
            log.write(f"\n[bold green]Tool Result:[/bold green]")
            log.write(renderable)
        elif role == "error":
            log.write(f"\n[bold red]Error:[/bold red] {text}")
        elif role == "system":
            log.write(f"\n[dim italic] {text} [/dim italic]")
        
        self.update_status()

    def set_thinking(self, text: str, visible: bool):
        panel = self.query_one("#thinking-panel")
        if visible:
            panel.update(f"[bold yellow]Thinking:[/bold yellow]\n{text}")
            panel.add_class("visible")
        else:
            panel.remove_class("visible")

    async def run_agent(self, text):
        try:
            await self.agent_loop.run_turn(text)
        except Exception as e:
            self.add_message("error", str(e))

    def action_focus_input(self) -> None:
        self.query_one("#input-bar").focus()

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log").clear()
        self.add_message("system", "Chat history cleared.")
