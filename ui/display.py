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
    def __init__(self, on_output=None):
        self.console = Console()
        self.on_output = on_output
        self.should_stop = False

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
            self._print("\n[bold cyan]TukiCode:[/bold cyan]")
            
        full_response = ""
        # Usar print normal para tokens sin nueva línea
        for chunk in chunk_generator:
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
            # We need to render rich panel to string
            with self.console.capture() as capture:
                self.console.print(panel)
            self.on_output(capture.get())
        else:
            self.console.print(panel)

    def show_diff(self, diff_str: str):
        syntax = Syntax(diff_str, "diff", theme="monokai", line_numbers=True)
        self.console.print(Panel(syntax, title="Differences", border_style="cyan"))

    def confirm(self, message: str) -> bool:
        self.console.print(f"[bold yellow]⚠️ {message} [Y/n][/bold yellow]", end=" ")
        resp = input().strip().lower()
        return resp in ["", "y", "yes"]

    def show_error(self, message: str):
        self.console.print(Panel(message, title="Error", border_style="red"))

    def show_tree(self, tree_str: str):
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
