from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table
from rich.ansi import AnsiDecoder
from typing import Generator
from tools.base import ToolResult


class StopRequestedException(Exception):
    pass


class TukiDisplay:
    def __init__(self, on_output=None, on_confirm=None):
        self.app = None
        self.console = Console()
        self.should_stop = False

        # 🔥 Consola (PTY / ANSI / QR)
        self.decoder = AnsiDecoder()
        self._buffer = ""

    # =============================
    # 🔗 CONEXIÓN CON TEXTUAL APP
    # =============================
    def set_app(self, app):
        self.app = app

    def _call_ui(self, func, *args):
        if self.app:
            self.app.call_later(func, *args)

    # =============================
    # 🖥️ CONSOLA EN VIVO (CRÍTICO)
    # =============================
    def update_console(self, text: str):
        """Agrega texto crudo a la consola (usado como fallback)."""
        if self.app:
            from rich.text import Text
            try:
                renderable = Text.from_ansi(text)
            except Exception:
                renderable = text

            def _write():
                try:
                    log = self.app.query_one("#console-log")
                    log.write(renderable)
                except Exception as e:
                    pass

            self.app.call_later(_write)

    def set_console_screen(self, text: str):
        """Reemplaza el contenido completo de la consola con un snapshot de pyte.
        Esto garantiza que el QR y las UI de terminal se vean correctamente."""
        if self.app:
            def _replace():
                try:
                    log = self.app.query_one("#console-log")
                    log.clear()
                    log.write(text)
                except Exception as e:
                    pass
            self.app.call_later(_replace)

    # =============================
    # 🧠 PRINT GENERAL
    # =============================
    def print(self, text):
        if self.app:
            if isinstance(text, Panel) and "Thinking" in str(text.title):
                content = str(text.renderable)
                self._call_ui(self.app.set_thinking, content, True)
            else:
                self._call_ui(self.app.add_message, "system", str(text))
        else:
            self.console.print(text)

    # =============================
    # 💬 STREAM IA
    # =============================
    def stream_response(self, chunk_generator: Generator[str, None, None]) -> str:
        full_response = ""
        last_thinking = ""

        for chunk in chunk_generator:
            if self.should_stop:
                self.should_stop = False
                self.print("[bold red]Generation aborted by user.[/bold red]")
                raise StopRequestedException("User requested stop")

            full_response += chunk

            # 🧠 THINKING PARSER
            if "<thinking>" in full_response:
                try:
                    thinking_part = full_response.split("<thinking>")[1].split("</thinking>")[0]
                except IndexError:
                    thinking_part = full_response.split("<thinking>")[1]

                if thinking_part != last_thinking:
                    self.show_thinking(thinking_part, True)
                    last_thinking = thinking_part
            else:
                self.show_thinking("Tuki is thinking...", True)

            # 🧼 LIMPIAR Y MOSTRAR STREAM
            import re
            clean = re.sub(r"<thinking>[\s\S]*?</thinking>", "", full_response).strip()
            if clean:
                self._call_ui(self.app.update_active_response, clean)

        # FINAL
        import re
        final = re.sub(r"<thinking>[\s\S]*?</thinking>", "", full_response).strip()

        if self.app:
            self._call_ui(self.app.set_thinking, "", False)
            self._call_ui(self.app.finish_streaming, "assistant", final)
        else:
            self.console.print(Markdown(final))

        return full_response

    # =============================
    # 🧩 TOOL RESULT
    # =============================
    def show_tool_result(self, tool_name: str, result: ToolResult):
        content = result.output if result.success else result.error

        console_tools = [
            "run_shell", "get_process_output",
            "write_file", "read_file",
            "list_dir", "file_exists",
            "create_file", "run_command",
            "get_project_tree", "get_files_in_directory"
        ]

        # 👉 Consola derecha
        if tool_name in console_tools:
            if content:
                self.update_console(content)
            return

        # 👉 Chat
        if content and len(content) > 1500:
            content = content[:1500] + "\n... [TRUNCATED]"

        msg = f"{tool_name}: {'Success' if result.success else 'Error'}\n{content}"

        if self.app:
            self._call_ui(self.app.add_message, "tool_result", msg)
        else:
            self.console.print(msg)

    # =============================
    # 🧠 THINKING
    # =============================
    def show_thinking(self, text: str, visible: bool = True):
        if self.app:
            self._call_ui(self.app.set_thinking, text, visible)
        else:
            if visible:
                self.console.print(Panel(text, title="Thinking", border_style="dim"))

    # =============================
    # 🔍 DIFF
    # =============================
    def show_diff(self, diff_text: str):
        syntax = Syntax(diff_text, "diff", theme="monokai")
        if self.app:
            self._call_ui(self.app.add_message, "system", syntax)
        else:
            self.console.print(syntax)

    # =============================
    # 📜 HISTORY
    # =============================
    def show_history_table(self, rows):
        table = Table(title="Conversation History")
        table.add_column("ID", style="cyan")
        table.add_column("Date", style="magenta")
        table.add_column("Title", style="green")
        table.add_column("Model", style="blue")
        table.add_column("Tokens", style="yellow")

        for r in rows:
            table.add_row(str(r[0]), r[1], r[2], r[3], str(r[4]))

        if self.app:
            self._call_ui(self.app.add_message, "assistant", table)
        else:
            self.console.print(table)

    # =============================
    # ❓ CONFIRM
    # =============================
    async def confirm_async(self, message: str) -> bool:
        if self.app:
            return await self.app.confirm_prompt(message)
        return True

    # =============================
    # ❌ ERROR
    # =============================
    def show_error(self, message: str):
        if self.app:
            self._call_ui(self.app.add_message, "error", message)
        else:
            self.console.print(f"[red]Error: {message}[/red]")

    # =============================
    # ⏳ SPINNER
    # =============================
    def show_spinner(self, message: str, details: str = ""):
        from contextlib import contextmanager

        msg = f"[dim]{message}[/dim]"
        if details:
            msg += f" [grey37]({details})[/grey37]"

        self.print(msg)

        @contextmanager
        def spinner():
            yield

        return spinner()