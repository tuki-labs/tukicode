from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static, DirectoryTree, OptionList, Tabs, Tab
from textual.widgets.option_list import Option
from textual.containers import Horizontal, Vertical, Container
from textual.binding import Binding
from rich.markdown import Markdown
from rich.panel import Panel
from agent_icon import TukiAnimation
import asyncio
from ui.screens import ModelSelectScreen, ApiKeyScreen

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
        border: none;
        margin: 1 0 0 1;
        padding: 0;
        background: transparent;
    }
    #mascot-container {
        height: 12;
        background: transparent;
    }
    #file-explorer {
        height: 1fr;
        border: solid #333;
        background: #0d0d0d;
        margin-top: 1;
        scrollbar-size: 1 1;
    }
    #chat-area {
        height: 1fr;
        border: solid #333;
        background: #0d0d0d;
        margin: 1 1 0 0;
    }
    #console-area {
        width: 60;
        height: 1fr;
        border: solid #333;
        background: #080808;
        margin: 1 1 0 0;
        display: block;
    }
    #console-area.hidden {
        display: none;
    }
    #console-log {
        border: none;
        height: 1fr;
        scrollbar-size: 1 1;
        background: transparent;
    }
    #active-response {
        display: none;
        padding: 0 2 1 2;
        background: transparent;
        color: #ffffff;
        height: auto;
        max-height: 15;
    }
    #active-response.visible {
        display: block;
    }
    #chat-log {
        border: none;
        height: 1fr;
        scrollbar-size: 1 1;
        background: transparent;
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
    .console-header {
        background: #1a1a2a;
        color: #ff00ff;
        padding: 0 1;
        border-bottom: solid #333;
        text-align: center;
        height: 1;
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
        Binding("ctrl+s", "stop_agent", "Stop Agent"),
        Binding("ctrl+b", "toggle_console", "Toggle Console"),
    ]

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        # Sync Display with Controller
        self.controller.display.set_app(self)
        
        # mascot and state
        self.anim = TukiAnimation(start_thread=False)
        self._confirm_future = None
        self._is_running = False
        self.session_title = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Tabs(
            Tab("Chat Mode", id="tab-chat"),
            Tab("Plan Mode", id="tab-plan"),
            Tab("Build Mode", id="tab-build")
        )
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static(id="mascot-container")
                yield DirectoryTree("./", id="file-explorer")
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
                yield Static("", id="active-response")
            with Vertical(id="console-area"):
                yield Static("[bold cyan]LIVE CONSOLE[/bold cyan]", classes="console-header")
                yield RichLog(id="console-log", wrap=False, highlight=False, markup=False)
        yield Static("", id="thinking-panel")
        yield Input(placeholder="Ask anything...", id="input-bar")
        yield Static("Initializing...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.12, self.update_mascot)
        self.update_status()
        self.query_one("#input-bar").focus()
        
        # Restaurar historial si existe
        messages = self.controller.context.get_messages()
        if len(messages) > 1:
            self.add_message("system", f"--- Restored Session {self.controller.session_id} ---")
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system" and "TukiCode" in (content or ""):
                    continue
                if content:
                    self.add_message(role, content)
            self.add_message("system", "-------------------------------")
        else:
            self.add_message("system", "Welcome to TukiCode! Type your message below.")

    def update_mascot(self) -> None:
        from rich.text import Text
        frame = self.anim.get_current_frame()
        self.query_one("#mascot-container").update(Text.from_ansi("\n".join(frame)))

    def update_status(self) -> None:
        model = self.controller.config.model.name
        tokens = int(self.controller.context.token_count)
        autonomy = self.controller.config.agent.autonomy_level.upper()
        mode = self.controller.mode.upper()
        
        step_info = ""
        p_state = self.controller.planner_state.state
        if p_state["status"] in ["building", "pending_confirmation"]:
            step = p_state["current_step"]
            total = len(p_state["plan"])
            if total > 0:
                step_info = f" | Plan: {step}/{total}"

        status = f"Mode: {mode} | Model: {model} | Tokens: {tokens} | Autonomy: {autonomy}{step_info}"
        self.query_one("#status-bar").update(status)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        
        if self._is_running and not self._confirm_future:
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
        self._is_running = True
        self._set_input_locked(True)
        
        async def run_task():
            try:
                await self.controller.process_input(text)
            finally:
                self._is_running = False
                self._set_input_locked(False)
                self.update_status()

        asyncio.create_task(run_task())

    async def confirm_prompt(self, message: str, color: str = "yellow") -> bool:
        self.add_message("system", f"[bold {color}]⚠️ {message}[/bold {color}]")
        input_bar = self.query_one("#input-bar")
        input_bar.placeholder = "Confirm? (y/n) >"
        input_bar.styles.border = ("solid", color)
        self._confirm_future = asyncio.get_event_loop().create_future()
        try:
            return await self._confirm_future
        finally:
            input_bar.placeholder = "Ask anything..."
            input_bar.styles.border = ("solid", "#444")
            self._confirm_future = None

    async def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = str(event.path)
        self.add_message("system", f"Analyzing file: [cyan]{path}[/cyan]")
        user_text = f"Read and analyze the file: {path}"
        self.add_message("user", user_text)
        self._is_running = True
        self._set_input_locked(True)
        
        async def run_task():
            try:
                await self.controller.process_input(user_text)
            finally:
                self._is_running = False
                self._set_input_locked(False)
                self.update_status()
        
        asyncio.create_task(run_task())

    async def handle_command(self, text):
        parts = text.split()
        if not parts: return
        cmd = parts[0]
        args = parts[1:]

        if cmd == "/exit":
            self.controller.save_session()
            self.exit()
        elif cmd == "/clear":
            self.query_one("#chat-log").clear()
            self.add_message("system", "Chat cleared.")
        elif cmd == "/help":
            self.add_message("assistant",
"""[bold cyan]─── TukiCode Commands ───[/bold cyan]

[bold magenta]/setup[/bold magenta]                  → Open the interactive configuration wizard
[bold magenta]/model[/bold magenta]                  → Open model selection menu
[bold magenta]/model[/bold magenta] [dim]<name>[/dim]          → Switch directly to a model
[bold magenta]/autonomy[/bold magenta] [dim][low|medium|high][/dim]→ Set confirmation level
[bold magenta]/history[/bold magenta]                → Show past sessions
[bold magenta]/clear[/bold magenta]                  → Clear chat log
[bold magenta]/copy[/bold magenta]                   → Copy last code block
[bold magenta]/site[/bold magenta]                   → Open TukiCode website
[bold magenta]/exit[/bold magenta]                   → Exit TukiCode
""")
        elif cmd == "/setup":
            self._open_setup_wizard()
        elif cmd == "/site":
            import webbrowser
            webbrowser.open("https://tukicode.site")
            self.add_message("system", "Opening TukiCode website...")
        elif cmd == "/copy":
            self.action_copy_code()
        elif cmd == "/model":
            if not args:
                options = self.get_model_options()
                def select_callback(choice_id):
                    if choice_id and ":" in str(choice_id):
                        provider, model_name = str(choice_id).split(":", 1)
                        self.handle_provider_switch(provider.lower(), model_name)
                self.push_screen(ModelSelectScreen(options), select_callback)
            else:
                new_model = args[0]
                provider = self.controller.guess_provider(new_model)
                self.handle_provider_switch(provider, new_model)
        elif cmd == "/autonomy":
            if not args:
                current = self.controller.config.agent.autonomy_level
                self.add_message("system", f"Current autonomy: [bold]{current}[/bold]  (options: low / medium / high)")
            else:
                level = args[0].lower()
                if level in ["low", "medium", "high"]:
                    self.controller.config.agent.autonomy_level = level
                    self.controller.config.save()
                    self.add_message("system", f"Autonomy → [bold]{level}[/bold]")
                    self.update_status()
                else:
                    self.add_message("error", "Invalid autonomy level. Use: low / medium / high")
        elif cmd == "/history":
            self.show_history()
        else:
            self.add_message("error", f"Unknown command: [bold]{cmd}[/bold]. Type [bold]/help[/bold] for a list.")

    COMMAND_HINTS = {
        "/setup":    "→ Open configuration wizard",
        "/model":    "→ Switch AI model",
        "/autonomy": "→ Set autonomy    [low|medium|high]",
        "/history":  "→ Show past sessions",
        "/clear":    "→ Clear chat log",
        "/copy":     "→ Copy last code block",
        "/site":     "→ Open website",
        "/help":     "→ Show all commands",
        "/exit":     "→ Exit TukiCode",
    }

    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        status = self.query_one("#status-bar")
        if value.startswith("/") and not self._is_running:
            matches = {k: v for k, v in self.COMMAND_HINTS.items() if k.startswith(value.split()[0])}
            if matches:
                hint_text = "   ".join(f"[cyan]{k}[/cyan] {v}" for k, v in list(matches.items())[:4])
                status.update(hint_text)
            else:
                self.update_status()
        else:
            self.update_status()

    def _open_setup_wizard(self):
        from ui.screens import SetupWizardScreen
        def wizard_callback(result):
            if not result:
                self.add_message("system", "Setup cancelled.")
                return
            provider = result["provider"]
            model = result["model"]
            key = result.get("key", "")
            
            try:
                self.controller.save_setup(provider, model, key)
                self.add_message("system", f"[bold green]✓ Configuration saved![/bold green] Provider: [cyan]{provider.upper()}[/cyan] | Model: [cyan]{model}[/cyan]")
            except Exception as e:
                self.add_message("error", str(e))
                
        self.push_screen(SetupWizardScreen(self.controller.config), wizard_callback)

    def handle_provider_switch(self, provider: str, model_name: str = None) -> None:
        # Verificar si necesita API Key
        needs_key = provider in ["gemini", "anthropic", "openrouter"]
        current_key = ""
        if provider == "gemini": current_key = self.controller.config.gemini.api_key
        elif provider == "anthropic": current_key = self.controller.config.anthropic.api_key
        elif provider == "openrouter": current_key = self.controller.config.openrouter.api_key
        
        if needs_key and not current_key:
            def api_callback(key):
                if key:
                    if provider == "gemini": self.controller.config.gemini.api_key = key
                    elif provider == "anthropic": self.controller.config.anthropic.api_key = key
                    elif provider == "openrouter": self.controller.config.openrouter.api_key = key
                    
                    try:
                        self.controller.switch_model(provider, model_name)
                        self.add_message("system", f"Provider changed to {provider.upper()} and API Key saved.")
                    except Exception as e:
                        self.add_message("error", str(e))
                else:
                    self.add_message("error", f"API Key required for {provider.upper()}")
            
            self.push_screen(ApiKeyScreen(provider.upper()), api_callback)
        else:
            try:
                self.controller.switch_model(provider, model_name)
                self.add_message("system", f"Provider changed to {provider.upper()}")
            except Exception as e:
                self.add_message("error", str(e))

    def get_model_options(self) -> list:
        options = []
        curr_provider = self.controller.config.model.provider.lower()
        curr_model = self.controller.config.model.name
        
        def fmt_option(p, m):
            is_active = (p == curr_provider and m == curr_model)
            text = f"  {m}"
            if is_active: text += " [b](active)[/b]"
            return Option(text, id=f"{p}:{m}")

        models = self.controller.get_available_models()

        options.append(Option("[b][cyan]Ollama (Local)[/cyan][/b]", id="header:ollama", disabled=True))
        if models["ollama"]:
            for m in models["ollama"]:
                options.append(fmt_option("ollama", m))
        else:
            options.append(Option("  (Error connecting to Ollama or no models)", disabled=True))

        options.append(Option("[b][cyan]Google (Gemini)[/cyan][/b]", id="header:gemini", disabled=True))
        for m in models["gemini"]:
            options.append(fmt_option("gemini", m))

        options.append(Option("[b][cyan]Anthropic (Claude)[/cyan][/b]", id="header:anthropic", disabled=True))
        for m in models["anthropic"]:
            options.append(fmt_option("anthropic", m))

        options.append(Option("[b][cyan]OpenRouter (Cloud)[/cyan][/b]", id="header:openrouter", disabled=True))
        for m in models["openrouter"]:
            options.append(fmt_option("openrouter", m))
        
        return options

    def show_history(self) -> None:
        rows = self.controller.get_history(limit=10)
        
        if not rows:
            self.add_message("system", "No conversations in history.")
            return
            
        from rich.table import Table
        table = Table(title="Recent Conversations")
        table.add_column("ID", style="cyan")
        table.add_column("Date", style="magenta")
        table.add_column("Title", style="green")
        table.add_column("Model", style="blue")
        
        for r in rows:
            table.add_row(str(r[0]), r[1], r[2], r[3])
            
        self.add_message("assistant", table)

    def action_copy_code(self) -> None:
        if hasattr(self, "_last_assistant_response") and self._last_assistant_response:
            import re
            code_blocks = re.findall(r"```[\s\S]*?\n([\s\S]*?)```", self._last_assistant_response)
            if code_blocks:
                import pyperclip
                try:
                    pyperclip.copy(code_blocks[-1])
                    self.add_message("system", "Last code block copied to clipboard.")
                except Exception:
                    self.add_message("error", "Could not copy to clipboard. Ensure pyperclip is installed.")
            else:
                self.add_message("system", "No code blocks found in last response.")
        else:
            self.add_message("system", "No assistant response to copy from.")

    def add_message(self, role: str, text):
        from rich.text import Text
        from rich.markdown import Markdown
        log = self.query_one("#chat-log")
        
        if isinstance(text, str):
            if role in ["assistant", "user"] and ("#" in text or "**" in text or "```" in text):
                renderable = Markdown(text)
            elif role in ["assistant", "system"] and "[" in text and "]" in text:
                renderable = Text.from_markup(text)
            else:
                renderable = Text.from_ansi(text)
        else:
            renderable = text

        if role == "user":
            log.write(f"\n[bold blue]You:[/bold blue]")
            log.write(renderable)
        elif role == "assistant":
            log.write(f"\n[bold cyan]TukiCode:[/bold cyan]")
            log.write(renderable)
            if isinstance(text, str): self._last_assistant_response = text
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

    def update_active_response(self, text: str, role: str = "assistant"):
        panel = self.query_one("#active-response")
        if text:
            if role == "assistant" and ("#" in text or "**" in text or "```" in text):
                renderable = Markdown(text)
            else:
                renderable = text
            
            header = "\n[bold cyan]TukiCode:[/bold cyan]\n"
            panel.update(header + text)
            panel.add_class("visible")
            log = self.query_one("#chat-log")
            log.scroll_end()
            panel.scroll_visible()
        else:
            panel.remove_class("visible")

    def finish_streaming(self, role: str, final_text: str):
        panel = self.query_one("#active-response")
        panel.remove_class("visible")
        panel.update("")
        if final_text:
            self.add_message(role, final_text)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        mode_map = {"tab-chat": "chat", "tab-plan": "plan", "tab-build": "build"}
        mode = mode_map.get(tab_id, "chat")
        self.controller.set_mode(mode)
        self.add_message("system", f"Switched to [bold]{mode.upper()}[/bold] mode.")
        self.update_status()

    def _set_input_locked(self, locked: bool):
        try:
            input_bar = self.query_one("#input-bar")
            if locked:
                input_bar.placeholder = "⏳ Tuki is working... (Ctrl+S to stop)"
                input_bar.styles.border = ("solid", "#555")
                input_bar.styles.color = "#666"
            else:
                input_bar.placeholder = "Ask anything..."
                input_bar.styles.border = ("solid", "#444")
                input_bar.styles.color = "#ffffff"
        except Exception:
            pass

    def action_focus_input(self) -> None:
        self.query_one("#input-bar").focus()

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log").clear()
        self.add_message("system", "Chat history cleared.")

    def action_stop_agent(self) -> None:
        if self._is_running:
            self.controller.stop_agent()
            self._is_running = False 
            self.add_message("system", "[bold red]Emergency Stop Triggered.[/bold red]")
        else:
            self.add_message("system", "Agent is not running.")

    def action_toggle_console(self) -> None:
        console = self.query_one("#console-area")
        if console.has_class("hidden"):
            console.remove_class("hidden")
        else:
            console.add_class("hidden")
