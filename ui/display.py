from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.tree import Tree
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
import sys
from typing import Generator
from contextlib import contextmanager
from tools.base import ToolResult

class TukiDisplay:
    def __init__(self, on_output=None, on_confirm=None):
        self.console = Console()
        self.on_output = on_output
        self.on_confirm = on_confirm
        self.should_stop = False
        import shutil
        self._shutil = shutil

    def _print(self, text):
        if self.on_output:
            # Render markup to ANSI before sending to callback
            with self.console.capture() as capture:
                self.console.print(text, end="")
            self.on_output(capture.get(), is_markup=False)
        else:
            self.console.print(text)

    def show_banner(self, version: str, model: str, risk_level: str):
        banner_text = f"[bold blue]TukiCode v{version}[/bold blue] | Model: [green]{model}[/green] | Risk: [yellow]{risk_level}[/yellow]"
        if not self.on_output:
            self.console.print(Panel(banner_text, border_style="blue"))

    def stream_response(self, chunk_generator: Generator[str, None, None]) -> str:
        if self.on_output:
            self.on_output("", is_start=True)
        else:
            self.console.print("\n[bold cyan]TukiCode:[/bold cyan] [dim]Thinking...[/dim]", end="\r")
            
        full_response = ""
        first_chunk = True
        for chunk in chunk_generator:
            if first_chunk:
                if not self.on_output:
                    # Clear the "Thinking..."
                    self.console.print("\n[bold cyan]TukiCode:[/bold cyan]               ", end="\r")
                    self.console.print("\n[bold cyan]TukiCode:[/bold cyan] ", end="")
                first_chunk = False
            
            if self.should_stop:
                self._print("\n[bold yellow]Generation stopped by user.[/bold yellow]\n")
                self.should_stop = False # Reset
                break
            if self.on_output:
                self.on_output(chunk)
            else:
                sys.stdout.write(chunk)
                sys.stdout.flush()
            full_response += chunk
        
        # After full response, if it's large and we have on_output, 
        # we might want to signal "end of message" to the UI for final rendering
        if self.on_output and full_response:
            self.on_output("", is_final=True, final_text=full_response)
            
        return full_response

    def show_tool_result(self, tool_name: str, result: ToolResult):
        color = "green" if result.success else "red"
        status = "SUCCESS" if result.success else "ERROR"
        content = result.output if result.success else result.error
        
        # Truncar output largo
        if content and len(content) > 1500:
            content = content[:1500] + "\n... [TRUNCATED]"
            
        panel = Panel(
            content or "No output.",
            title=f"Tool: {tool_name} [{status}]",
            border_style=color
        )
        
        if self.on_output:
            # Adjust width for TUI
            terminal_width = self._shutil.get_terminal_size().columns
            self.console.width = max(terminal_width - 10, 40)
            
            # We need to render rich panel to string
            with self.console.capture() as capture:
                self.console.print(panel)
            self.on_output(capture.get())
        else:
            self.console.width = None # Reset to default
            self.console.print(panel)

    def show_diff(self, diff_str: str):
        syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=True)
        if self.on_output:
            terminal_width = self._shutil.get_terminal_size().columns
            self.console.width = max(terminal_width - 10, 40)
            with self.console.capture() as capture:
                self.console.print(Panel(syntax, title="Differences", border_style="cyan"))
            self.on_output(capture.get())
        else:
            self.console.width = None
            self.console.print(Panel(syntax, title="Differences", border_style="cyan"))

    def confirm(self, message: str) -> bool:
        self.console.print(f"\n[bold yellow]⚠️ {message} [Y/n][/bold yellow]", end=" ")
        try:
            resp = input().strip().lower()
            return resp in ["", "y", "yes"]
        except EOFError:
            return False

    async def confirm_async(self, message: str) -> bool:
        if self.on_confirm:
            return await self.on_confirm(message)
        # Fallback to sync if no async callback
        return self.confirm(message)

    def show_error(self, message: str):
        if self.on_output:
            terminal_width = self._shutil.get_terminal_size().columns
            self.console.width = max(terminal_width - 10, 40)
            with self.console.capture() as capture:
                self.console.print(Panel(message, title="Error", border_style="red"))
            self.on_output(capture.get())
        else:
            self.console.width = None
            self.console.print(Panel(message, title="Error", border_style="red"))

    def show_tree(self, tree_str: str):
        if self.on_output:
            terminal_width = self._shutil.get_terminal_size().columns
            self.console.width = max(terminal_width - 10, 40)
            with self.console.capture() as capture:
                self.console.print(Panel(tree_str, title="Project Tree", border_style="blue"))
            self.on_output(capture.get())
        else:
            self.console.width = None
            self.console.print(Panel(tree_str, title="Project Tree", border_style="blue"))

    @contextmanager
    def show_spinner(self, message: str):
        with self.console.status(f"[bold green]{message}..."):
            yield

    def show_token_usage(self, used: int, total: int):
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("{task.completed}/{task.total} tokens")
        ) as progress:
            progress.add_task("Context Usage", total=total, completed=used)

    def show_history_table(self, conversations: list):
        table = Table(title="Conversation History")
        table.add_column("ID", justify="right", style="cyan")
        table.add_column("Date", style="magenta")
        table.add_column("Title", style="green")
        table.add_column("Model", style="blue")
        table.add_column("Tokens", justify="right")
        
        for conv in conversations:
            table.add_row(str(conv[0]), conv[1], conv[2], conv[3], str(conv[4]))
            
        self.console.print(table)
