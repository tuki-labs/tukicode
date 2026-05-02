from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from typing import Generator, Optional
import asyncio
from tools.base import ToolResult

class TukiDisplay:
    def __init__(self, on_output=None, on_confirm=None):
        # Mantener firma para compatibilidad, pero usaremos app
        self.app = None
        self.console = Console()
        self.should_stop = False

    def _call_ui(self, func, *args):
        if self.app:
            # call_later es seguro desde el mismo bucle de eventos
            self.app.call_later(func, *args)

    def set_app(self, app):
        self.app = app

    def print(self, text):
        if self.app:
            # Si es un Panel de "Thinking" de AgentLoop
            if isinstance(text, Panel) and "Thinking" in str(text.title):
                # Extraer contenido del panel para el panel de thinking de Textual
                content = str(text.renderable)
                self._call_ui(self.app.set_thinking, content, True)
            else:
                self._call_ui(self.app.add_message, "system", str(text))
        else:
            self.console.print(text)

    def stream_response(self, chunk_generator: Generator[str, None, None]) -> str:
        full_response = ""
        for chunk in chunk_generator:
            if self.should_stop:
                self.print("[bold yellow]Generation stopped by user.[/bold yellow]")
                self.should_stop = False
                break
            full_response += chunk
        
        if self.app:
            self._call_ui(self.app.set_thinking, "", False) # Ocultar thinking
            self._call_ui(self.app.add_message, "assistant", Markdown(full_response))
        else:
            self.console.print(Markdown(full_response))
            
        return full_response

    def show_thinking(self, text: str, visible: bool = True):
        if self.app:
            self._call_ui(self.app.set_thinking, text, visible)
        else:
            if visible:
                self.console.print(Panel(text, title="Thinking", border_style="dim"))

    def show_tool_result(self, tool_name: str, result: ToolResult):
        content = result.output if result.success else result.error
        if content and len(content) > 1500:
            content = content[:1500] + "\n... [TRUNCATED]"
        
        msg = f"⚙️ [bold]{tool_name}[/bold]: {'Success' if result.success else 'Error'}\n{content}"
        if self.app:
            self._call_ui(self.app.add_message, "tool_result", msg)
        else:
            self.console.print(msg)

    async def confirm_async(self, message: str) -> bool:
        if self.app:
            # Delegar confirmación a la app de Textual
            return await self.app.confirm_prompt(message)
        return True

    def show_error(self, message: str):
        if self.app:
            self._call_ui(self.app.add_message, "error", message)
        else:
            self.console.print(f"[red]Error: {message}[/red]")

    def show_spinner(self, message: str):
        from contextlib import contextmanager
        self.print(f"[dim] {message}... [/dim]")
        @contextmanager
        def spinner():
            yield
        return spinner()

    def show_banner(self, version: str, model: str, risk_level: str):
        # El banner ahora es parte del layout de Textual
        pass
