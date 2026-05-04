from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from typing import Generator, Optional
import asyncio
from tools.base import ToolResult

class StopRequestedException(Exception):
    """Excepción lanzada cuando el usuario solicita detener la ejecución."""
    pass

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
        last_thinking = ""
        
        for chunk in chunk_generator:
            if self.should_stop:
                self.should_stop = False
                self.print("[bold red]Generation aborted by user.[/bold red]")
                raise StopRequestedException("User requested stop")
            full_response += chunk
            
            # Extraer pensamiento en tiempo real si es posible
            if "<thinking>" in full_response:
                try:
                    thinking_part = full_response.split("<thinking>")[1].split("</thinking>")[0]
                    if thinking_part != last_thinking:
                        self.show_thinking(thinking_part, True)
                        last_thinking = thinking_part
                except IndexError:
                    # Aún no se cierra el tag, mostrar lo que llevamos
                    thinking_part = full_response.split("<thinking>")[1]
                    if thinking_part != last_thinking:
                        self.show_thinking(thinking_part, True)
                        last_thinking = thinking_part
            else:
            # Si no hay thinking o ya terminó, mostrar indicador genérico
                self.show_thinking("Tuki is thinking...", True)
            
            # Actualizar respuesta activa en tiempo real
            import re
            current_clean = re.sub(r"<thinking>[\s\S]*?</thinking>", "", full_response).strip()
            if current_clean:
                self._call_ui(self.app.update_active_response, current_clean)
        
        # Limpiar tags de thinking del mensaje final
        import re
        clean_response = re.sub(r"<thinking>[\s\S]*?</thinking>", "", full_response).strip()
        
        if self.app:
            self._call_ui(self.app.set_thinking, "", False) # Ocultar thinking
            self._call_ui(self.app.finish_streaming, "assistant", clean_response)
        elif self.app:
            self._call_ui(self.app.set_thinking, "", False)
        
        if not self.app:
            self.console.print(Markdown(clean_response))
            
        return full_response

    def show_diff(self, diff_text: str):
        from rich.syntax import Syntax
        if self.app:
            self._call_ui(self.app.add_message, "system", Syntax(diff_text, "diff", theme="monokai"))
        else:
            self.console.print(Syntax(diff_text, "diff", theme="monokai"))

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
        
        msg = f"{tool_name}: {'Success' if result.success else 'Error'}\n{content}"
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

    def show_spinner(self, message: str, details: str = ""):
        from contextlib import contextmanager
        msg = f"[dim] {message}[/dim]"
        if details:
            msg += f" [grey37]({details})[/grey37]"
        self.print(msg)
        @contextmanager
        def spinner():
            yield
        return spinner()

    def show_history_table(self, rows):
        from rich.table import Table
        table = Table(title="Conversation History", border_style="blue")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Date", style="magenta")
        table.add_column("Title", style="green")
        table.add_column("Model", style="blue")
        table.add_column("Tokens", style="yellow")
        
        for r in rows:
            table.add_row(str(r[0]), r[1], r[2], r[3], str(r[4]))
            
        self.console.print(table)

    def show_banner(self, version: str, model: str, risk_level: str):
        # El banner ahora es parte del layout de Textual
        pass
