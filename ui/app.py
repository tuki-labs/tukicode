from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, Static, DirectoryTree, OptionList
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

    def __init__(self, config, client, registry, context, session_id=None):
        super().__init__()
        self.config = config
        self.client = client
        self.registry = registry
        self.context = context
        self.session_id = session_id
        from agent.loop import AgentLoop
        
        # Conectar Display con App
        from ui.display import TukiDisplay
        self.tuki_display = TukiDisplay()
        self.tuki_display.set_app(self)
        
        # Conectar herramientas con Display para la consola en vivo
        from tools.shell_tools import set_display
        set_display(self.tuki_display)
        
        self.agent_loop = AgentLoop(config, client, registry, context, self.tuki_display)
        self.anim = TukiAnimation(start_thread=False)
        self.session_title = None
        self._confirm_future = None
        self._is_running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static(id="mascot-container")
                yield DirectoryTree("./", id="file-explorer")
            with Vertical(id="chat-area"):
                yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True)
                yield Static("", id="active-response")
            with Vertical(id="console-area"):
                yield Static("[bold magenta] 🖥️  LIVE CONSOLE[/bold magenta]", classes="console-header")
                yield RichLog(id="console-log", wrap=False, highlight=True, markup=False)
        yield Static("", id="thinking-panel")
        yield Input(placeholder="Ask anything...", id="input-bar")
        yield Static("Initializing...", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(0.12, self.update_mascot)
        self.update_status()
        self.query_one("#input-bar").focus()
        
        # Restaurar historial si existe
        messages = self.context.get_messages()
        if len(messages) > 1:
            self.add_message("system", f"--- Restored Session {self.session_id} ---")
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                # No mostrar el system prompt base para no ensuciar
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
        model = self.config.model.name
        tokens = int(self.context.token_count)
        risk = self.config.agent.risk_level
        autonomy = self.config.agent.autonomy_level.upper()
        status = f"Model: {model} | Tokens: {tokens} | Risk: {risk} | Autonomy: {autonomy}"
        self.query_one("#status-bar").update(status)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        
        if self._is_running and not self._confirm_future:
            # No limpiar el input para que el usuario no pierda lo que escribió
            self.add_message("error", "Agent is busy. Please wait for the current turn to finish.")
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
        asyncio.create_task(self.run_agent(text))

    async def confirm_prompt(self, message: str) -> bool:
        self.add_message("system", f"[bold yellow]⚠️ {message}[/bold yellow]")
        input_bar = self.query_one("#input-bar")
        input_bar.placeholder = "Confirm? (y/n) >"
        input_bar.styles.border = ("solid", "yellow")
        self._confirm_future = asyncio.get_event_loop().create_future()
        try:
            return await self._confirm_future
        finally:
            input_bar.placeholder = "Ask anything..."
            input_bar.styles.border = ("solid", "#444")
            self._confirm_future = None

    async def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Al seleccionar un archivo en el árbol, pedir a Tuki que lo analice."""
        path = str(event.path)
        self.add_message("system", f"Analyzing file: [cyan]{path}[/cyan]")
        
        # Enviar mensaje automático al agente
        user_text = f"Read and analyze the file: {path}"
        self.add_message("user", user_text)
        self._is_running = True
        asyncio.create_task(self.run_agent(user_text))

    async def handle_command(self, text):
        parts = text.split()
        if not parts: return
        cmd = parts[0]
        args = parts[1:]

        if cmd == "/exit":
            self.save_session()
            self.exit()
        elif cmd == "/history":
            self.show_history()
        elif cmd == "/clear":
            self.query_one("#chat-log").clear()
            self.add_message("system", "Chat history cleared.")
        elif cmd == "/help":
            self.add_message("assistant", """
[bold cyan]Available commands:[/bold cyan]
- [bold magenta]/exit[/bold magenta]: Exit TukiCode
- [bold magenta]/clear[/bold magenta]: Clear chat log
- [bold magenta]/model[/bold magenta] [dim][name][/dim]: Change current model
- [bold magenta]/risk[/bold magenta] [dim][low/medium/high][/dim]: Change risk level
- [bold magenta]/autonomy[/bold magenta] [dim][low/medium/high][/dim]: Change autonomy level
    * [bold green]low[/bold green]: Maximum safety. Asks for confirmation on all actions.
    * [bold yellow]medium[/bold yellow]: Balanced. Allows reading/listing, asks for writing/deleting.
    * [bold red]high[/bold red]: High speed. Only asks for confirmation once per turn.
- [bold magenta]/history[/bold magenta]: Show recent conversations
- [bold magenta]/site[/bold magenta]: Open official website
- [bold magenta]/copy[/bold magenta]: Copy last code block to clipboard
            """)
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
                provider = self.guess_provider(new_model)
                self.handle_provider_switch(provider, new_model)
        elif cmd == "/risk":
            if not args:
                self.add_message("system", f"Current risk: {self.config.agent.risk_level}")
            else:
                try:
                    new_risk = args[0].upper()
                    self.config.agent.risk_level = new_risk
                    self.config.save()
                    self.add_message("system", f"Risk level changed to {new_risk}")
                except Exception:
                    self.add_message("error", "Invalid risk level. Use low, medium, or high.")
        elif cmd == "/autonomy":
            if not args:
                self.add_message("system", f"Current autonomy: {self.config.agent.autonomy_level}")
            else:
                level = args[0].lower()
                if level in ["low", "medium", "high"]:
                    self.config.agent.autonomy_level = level
                    self.config.save()
                    self.add_message("system", f"Autonomy level changed to {level}")
                    self.update_status()
                else:
                    self.add_message("error", "Invalid autonomy level. Use low, medium, or high.")
        elif cmd == "/history":
            self.show_history()
        else:
            self.add_message("error", f"Unknown command: {cmd}")

    def update_client(self) -> None:
        """Actualiza el cliente LLM según la configuración actual con manejo de errores."""
        from agent.ollama_client import OllamaClient
        from agent.openrouter_client import OpenRouterClient
        from agent.gemini_client import GeminiClient
        from agent.anthropic_client import AnthropicClient
        
        provider = self.config.model.provider.lower()
        model_name = self.config.model.name
        
        try:
            if provider == "gemini":
                if not self.config.gemini.api_key: raise ValueError("Gemini API Key is missing.")
                self.client = GeminiClient(self.config.gemini.model, self.config.model.temperature, self.config.model.max_tokens, True, self.config.gemini.api_key)
            elif provider == "anthropic":
                if not self.config.anthropic.api_key: raise ValueError("Anthropic API Key is missing.")
                self.client = AnthropicClient(self.config.anthropic.model, self.config.model.temperature, self.config.model.max_tokens, True, self.config.anthropic.api_key)
            elif provider == "openrouter":
                if not self.config.openrouter.api_key: raise ValueError("OpenRouter API Key is missing.")
                self.client = OpenRouterClient(model_name, self.config.model.temperature, self.config.model.max_tokens, True, self.config.openrouter.api_key)
            else:
                self.client = OllamaClient(model_name, self.config.model.temperature, self.config.model.max_tokens, True)
                if not self.client.is_available():
                    raise ConnectionError("Ollama is not running. Start it with 'ollama serve'.")
            
            self.agent_loop.llm_client = self.client
            self.update_status()
            self.add_message("system", f"Successfully switched to [bold cyan]{model_name}[/bold cyan] ({provider.upper()})")
        except Exception as e:
            self.add_message("error", f"Failed to switch model: {str(e)}")
            # Intentar volver a Ollama si falla
            if provider != "ollama":
                self.add_message("system", "Reverting to Ollama default...")
                self.config.model.provider = "ollama"
                self.update_client()

    def handle_provider_switch(self, provider: str, model_name: str = None) -> None:
        """Lógica para cambiar de proveedor, pidiendo API key si es necesario."""
        self.config.model.provider = provider
        if model_name:
            self.config.model.name = model_name
        
        # Verificar si necesita API Key
        needs_key = provider in ["gemini", "anthropic", "openrouter"]
        current_key = ""
        if provider == "gemini": current_key = self.config.gemini.api_key
        elif provider == "anthropic": current_key = self.config.anthropic.api_key
        elif provider == "openrouter": current_key = self.config.openrouter.api_key
        
        if needs_key and not current_key:
            def api_callback(key):
                if key:
                    if provider == "gemini": 
                        self.config.gemini.api_key = key
                        if model_name: 
                            self.config.gemini.model = model_name
                            if model_name not in self.config.gemini.models: self.config.gemini.models.append(model_name)
                    elif provider == "anthropic": 
                        self.config.anthropic.api_key = key
                        if model_name: 
                            self.config.anthropic.model = model_name
                            if model_name not in self.config.anthropic.models: self.config.anthropic.models.append(model_name)
                    elif provider == "openrouter": 
                        self.config.openrouter.api_key = key
                        if model_name and model_name not in self.config.openrouter.models: self.config.openrouter.models.append(model_name)
                    self.config.save()
                    self.update_client()
                    self.add_message("system", f"Provider changed to {provider.upper()} and API Key saved.")
                else:
                    self.add_message("error", f"API Key required for {provider.upper()}")
            
            self.push_screen(ApiKeyScreen(provider.upper()), api_callback)
        else:
            if provider == "gemini" and model_name: 
                self.config.gemini.model = model_name
                if model_name not in self.config.gemini.models: self.config.gemini.models.append(model_name)
            elif provider == "anthropic" and model_name: 
                self.config.anthropic.model = model_name
                if model_name not in self.config.anthropic.models: self.config.anthropic.models.append(model_name)
            elif provider == "openrouter" and model_name:
                if model_name not in self.config.openrouter.models: self.config.openrouter.models.append(model_name)
                
            self.config.save()
            self.update_client()
            self.add_message("system", f"Provider changed to {provider.upper()}")

    def get_model_options(self) -> list:
        """Obtiene la lista de modelos con indicadores de estado e historial."""
        options = []
        curr_provider = self.config.model.provider.lower()
        curr_model = self.config.model.name
        
        def fmt_option(p, m):
            is_active = (p == curr_provider and m == curr_model)
            text = f"  {m}"
            if is_active: text += " [b](active)[/b]"
            return Option(text, id=f"{p}:{m}")

        # 1. Ollama
        options.append(Option("[b][cyan]Ollama (Local)[/cyan][/b]", id="header:ollama", disabled=True))
        try:
            from agent.ollama_client import OllamaClient
            o_client = OllamaClient(curr_model, 0, 0, False)
            for m in o_client.list_models():
                options.append(fmt_option("ollama", m))
        except Exception:
            options.append(Option("  (Error connecting to Ollama)", disabled=True))

        # 2. Google
        options.append(Option("[b][cyan]Google (Gemini)[/cyan][/b]", id="header:gemini", disabled=True))
        for m in self.config.gemini.models:
            options.append(fmt_option("gemini", m))

        # 3. Anthropic
        options.append(Option("[b][cyan]Anthropic (Claude)[/cyan][/b]", id="header:anthropic", disabled=True))
        for m in self.config.anthropic.models:
            options.append(fmt_option("anthropic", m))

        # 4. OpenRouter
        options.append(Option("[b][cyan]OpenRouter (Cloud)[/cyan][/b]", id="header:openrouter", disabled=True))
        for m in self.config.openrouter.models:
            options.append(fmt_option("openrouter", m))
        
        return options

    def guess_provider(self, model_name: str) -> str:
        """Adivina el proveedor basado en el nombre del modelo."""
        m = model_name.lower()
        if "gemini" in m: return "gemini"
        if "claude" in m or "anthropic" in m: return "anthropic"
        if "/" in m: return "openrouter" # Ejemplo: openai/gpt-4o
        return "ollama"

    def save_session(self) -> None:
        from tuki import get_app_dir
        db_path = get_app_dir() / "data" / "history.db"
        self.agent_loop.save_to_history(str(db_path), custom_title=self.session_title, session_id=self.session_id)
        self.add_message("system", "Conversation saved.")

    def show_history(self) -> None:
        from tuki import get_app_dir
        import sqlite3
        db_path = get_app_dir() / "data" / "history.db"
        if not db_path.exists():
            self.add_message("system", "No history found.")
            return
            
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT id, date, title, model FROM history ORDER BY id DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        
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
        
        # Envolver strings en el renderizador adecuado
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
            # Si contiene markdown o similar
            if role == "assistant" and ("#" in text or "**" in text or "```" in text):
                renderable = Markdown(text)
            else:
                renderable = text
            
            header = "\n[bold cyan]TukiCode:[/bold cyan]\n"
            panel.update(header + text)
            panel.add_class("visible")
            # Scroll chat log to bottom to make room
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

    async def run_agent(self, text):
        try:
            response = await self.agent_loop.run_turn(text)
            self._last_assistant_response = response
        except Exception as e:
            from ui.display import StopRequestedException
            if isinstance(e, StopRequestedException):
                self.add_message("system", "[bold red]Agent stopped.[/bold red]")
            else:
                self.add_message("error", str(e))
        finally:
            self._is_running = False

    def action_focus_input(self) -> None:
        self.query_one("#input-bar").focus()

    def action_clear_chat(self) -> None:
        self.query_one("#chat-log").clear()
        self.add_message("system", "Chat history cleared.")

    def action_stop_agent(self) -> None:
        """Detiene la ejecución del agente de forma inmediata."""
        if self._is_running:
            self.agent_loop._stop_requested = True
            self.tuki_display.should_stop = True
            # Forzar el flag de ejecución a falso para permitir nueva entrada rápido
            self._is_running = False 
            self.add_message("system", "[bold red]Emergency Stop Triggered.[/bold red]")
        else:
            self.add_message("system", "Agent is not running.")

    def action_toggle_console(self) -> None:
        """Muestra u oculta el panel de la consola."""
        console = self.query_one("#console-area")
        console.has_class("hidden")
        if console.has_class("hidden"):
            console.remove_class("hidden")
            self.add_message("system", "Console visible.")
        else:
            console.add_class("hidden")
            self.add_message("system", "Console hidden.")
