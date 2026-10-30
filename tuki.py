import sys
import os
import typer
import asyncio
from pathlib import Path

# Soporte para PyInstaller (empaquetado)
if getattr(sys, 'frozen', False):
    # Si estamos en un ejecutable, el directorio base es sys._MEIPASS
    base_path = sys._MEIPASS
else:
    # Si estamos en desarrollo, es el directorio del archivo
    base_path = os.path.abspath(os.path.dirname(__file__))

sys.path.insert(0, base_path)

from config import load_config, get_app_dir, save_config, Config
from integrations import load_integrations
from agent.ollama_client import OllamaClient
from agent.openrouter_client import OpenRouterClient
from tools.registry import registry as tool_registry
from agent.context import ConversationContext
from agent.loop import AgentLoop
from ui.display import TukiDisplay
from ui.app import TukiApp
from enum import Enum

class ConfigComponent(str, Enum):
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"

app = typer.Typer(help="TukiCode - CLI Programming Agent")


@app.callback(invoke_without_command=True)
def start(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        chat(session_id=None, model=None, risk=None)

@app.command("chat", help="Starts an interactive session with the TukiCode agent.")
def chat(session_id: int = typer.Argument(None, help="ID of a previous session to resume"),
         model: str = typer.Option(None, "--model", "-m", help="Override model"),
         risk: str = typer.Option(None, "--risk", "-r", help="Override risk level")):
    first_run = not (get_app_dir() / "tukicode.toml").exists()
    config = load_config()
    setup_ran = False
    if first_run or (not config.setup_completed and config.model.provider != "openrouter"):
        from rich.console import Console
        Console().print("Welcome to TukiCode! Configure your provider before starting your first session.")
        show_config(setup=True)
        setup_ran = True
    
    if model:
        config.model.name = model
    if risk:
        config.agent.risk_level = risk

    if config.model.provider == "openrouter" and (not setup_ran or model):
        from agent.onboarding import validate_openrouter_setup, SetupCheckError
        from rich.console import Console
        from rich.text import Text
        console = Console()
        console.print("Checking OpenRouter access with a short synthetic tool-call test (normal model pricing/limits apply; no files are sent)...")
        try:
            validate_openrouter_setup(config.openrouter.api_key, config.model.name, config.model.temperature)
        except SetupCheckError as error:
            console.print(Text(str(error), style="yellow"))
            if error.kind == "temporary":
                console.print("Retry tuki chat when the service or connection is available. Your configuration was kept.")
                raise typer.Exit(1)
            console.print("Let's repair your configuration before opening the chat.")
            show_config(setup=True)
        else:
            if not config.setup_completed:
                config.setup_completed = True
                save_config(config)

    loaded_integrations = load_integrations(config, tool_registry)
    
    display = TukiDisplay()
    
    if loaded_integrations:
        display.console.print(f"[dim]Loaded integrations: {', '.join(loaded_integrations)}[/dim]")

    context = ConversationContext(config.model.context_window)
    base_dir = get_app_dir()
    
    from core.controller import TukiController
    # Initial controller with None client, then we switch_model to initialize it
    app_controller = TukiController(config, None, tool_registry, context, display, session_id=session_id)
    
    try:
        app_controller.switch_model(config.model.provider, model or config.model.name)
    except Exception as e:
        display.show_error(str(e))
        raise typer.Exit(1)
    
    app_ui = TukiApp(app_controller)
    
    if session_id:
        db_path = base_dir / "data" / "history.db"
        if not app_controller.agent_loop.load_history(str(db_path), session_id):
            display.show_error(f"Session ID {session_id} not found or could not be loaded.")
            raise typer.Exit(1)
            
    try:
        app_ui.run()
    finally:
        db_path = base_dir / "data" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        app_controller.save_session()
        print(f"\nConversation saved. Total session tokens: {context.token_count}")


@app.command("config", help="Shows or modifies the system configuration. Use --setup to open an interactive wizard.")
def show_config(setup: bool = typer.Option(False, "--setup", "-s", help="Open interactive setup wizard.")):
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box

    config = load_config()
    console = Console()

    if setup:
        # ── Universal Interactive Wizard ──────────────────────────────
        console.print("\n[bold cyan]┌─ TukiCode Setup Wizard ─────────────────────────┐[/bold cyan]")
        console.print("[bold cyan]│[/bold cyan]  Configure your AI provider step by step          [bold cyan]│[/bold cyan]")
        console.print("[bold cyan]└─────────────────────────────────────────────────┘[/bold cyan]\n")

        providers = {
            "1": ("ollama",     "🖥️  Ollama       (Local — Free)"),
            "2": ("openrouter", "🌐  OpenRouter   (Cloud — Multi-model)"),
            "3": ("gemini",     "✨  Google Gemini (Cloud)"),
            "4": ("anthropic",  "🧠  Anthropic    (Cloud)"),
        }

        console.print("[bold]Step 1 — Choose your AI Provider:[/bold]\n")
        for key, (_, label) in providers.items():
            active = " [green](current)[/green]" if providers[key][0] == config.model.provider else ""
            console.print(f"  [cyan]{key}[/cyan]. {label}{active}")

        default_provider = next((number for number, (provider, _) in providers.items() if provider == config.model.provider), "1")
        choice = typer.prompt("\nEnter number", default=default_provider)
        if choice not in providers:
            console.print("[red]Invalid choice.[/red]")
            raise typer.Exit(1)

        provider_id, provider_label = providers[choice]
        console.print(f"\n  ✅ Selected: {provider_label}\n")

        # Step 2 — API Key (if needed)
        NEEDS_KEY = {"openrouter", "gemini", "anthropic"}
        if provider_id in NEEDS_KEY:
            console.print("[bold]Step 2 — API Key:[/bold]")
            if provider_id == "openrouter":
                from agent.model_catalog import KEYS_URL
                console.print(f"Create your key here: [link={KEYS_URL}]{KEYS_URL}[/link]")
                console.print("Sign in, select Create API Key, copy it and paste it below (input is hidden).")
            current_key = ""
            if provider_id == "openrouter": current_key = config.openrouter.api_key
            elif provider_id == "gemini":   current_key = config.gemini.api_key
            elif provider_id == "anthropic": current_key = config.anthropic.api_key
            masked = f"(current: ****{current_key[-4:]})" if current_key and len(current_key) > 4 else ""
            api_key = typer.prompt(f"  Enter {provider_id.upper()} API Key {masked}", hide_input=True, default=current_key, show_default=False)
            if not api_key or any(char.isspace() or char == "\\" for char in api_key):
                console.print("[red]Enter the provider API key, not a terminal command or file path. Configuration was not saved.[/red]")
                raise typer.Exit(1)
        else:
            api_key = ""

        # Step 3 — Model
        DEFAULT_MODELS = {
            "ollama":      ["deepseek-coder:1.3b", "llama3", "codestral"],
            "gemini":      ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
            "anthropic":   ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229"],
        }
        step_n = "Step 3" if provider_id in NEEDS_KEY else "Step 2"
        console.print(f"\n[bold]{step_n} — Model:[/bold]")
        if provider_id == "openrouter":
            from agent.model_catalog import choose_coding_model
            from agent.onboarding import validate_openrouter_setup, SetupCheckError
            from rich.text import Text
            current_model = config.model.name if config.model.provider == "openrouter" else None
            rejected_models = set()
            while True:
                model_name = choose_coding_model(console, current_model, get_app_dir() / "data" / "openrouter-models.json", rejected_models)
                console.print("Checking key, model access and a real tool call using a short synthetic test. Normal model pricing/limits apply; no files are sent.")
                try:
                    validate_openrouter_setup(api_key, model_name, config.model.temperature)
                    console.print("[green]Access and native tool calling verified.[/green]")
                    break
                except SetupCheckError as error:
                    console.print(Text(str(error), style="yellow"))
                    if error.kind == "key":
                        console.print("Create an inference key at https://openrouter.ai/settings/keys")
                        api_key = typer.prompt("Enter another OpenRouter API key", hide_input=True, show_default=False)
                    elif error.kind == "temporary":
                        if not typer.confirm("Retry the connectivity check?", default=True):
                            console.print("Configuration was not changed.")
                            raise typer.Exit(1)
                    else:
                        rejected_models.add(model_name)
                        current_model = None
                        console.print("This model will not be saved. Choose another from the list.")
        else:
            defaults = DEFAULT_MODELS.get(provider_id, [])
            if defaults:
                console.print("  Suggested models:")
                for m in defaults:
                    console.print(f"    • {m}")
            current_model = config.model.name
            model_name = typer.prompt(f"\n  Model name", default=current_model)

        # Save
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"  Provider : [cyan]{provider_id.upper()}[/cyan]")
        console.print(f"  Model    : [cyan]{model_name}[/cyan]")
        if api_key:
            masked_key = "****" + api_key[-4:] if len(api_key) > 4 else "****"
            console.print(f"  API Key  : [dim]{masked_key}[/dim]")

        confirm = typer.confirm("\nSave this configuration?", default=True)
        if not confirm:
            console.print("[yellow]Configuration not saved.[/yellow]")
            raise typer.Exit()

        from agent.onboarding import configured_copy
        candidate = configured_copy(config, provider_id, model_name, api_key)
        save_config(candidate)
        config.__dict__.update(candidate.__dict__)
        console.print("\n[bold green]✅ Configuration saved successfully![/bold green]")
        console.print(f"   Run [cyan]tuki chat[/cyan] to start using {provider_id.upper()}.\n")
        return

    # ── Display current config as a pretty table ──────────────────────
    console.print()

    # Active model panel
    active_provider = config.model.provider.upper()
    active_model = config.model.name
    has_key = False
    if config.model.provider == "openrouter": has_key = bool(config.openrouter.api_key)
    elif config.model.provider == "gemini":   has_key = bool(config.gemini.api_key)
    elif config.model.provider == "anthropic": has_key = bool(config.anthropic.api_key)

    key_status = "[green]✓ Set[/green]" if has_key else "[red]✗ Missing[/red]"

    console.print(Panel(
        f"[bold cyan]{active_provider}[/bold cyan]  ·  [white]{active_model}[/white]  ·  API Key: {key_status}",
        title="[bold green]▶ Active Model[/bold green]",
        border_style="green",
        box=box.ROUNDED
    ))

    # Agent settings table
    tbl = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan", padding=(0, 2))
    tbl.add_column("Setting", style="magenta")
    tbl.add_column("Value", style="white")
    tbl.add_row("Risk Level",     f"[{'red' if config.agent.risk_level.upper() == 'HIGH' else 'yellow' if config.agent.risk_level.upper() == 'MEDIUM' else 'green'}]{config.agent.risk_level}[/]")
    tbl.add_row("Autonomy",       config.agent.autonomy_level)
    tbl.add_row("Language",       config.agent.language)
    tbl.add_row("Stream",         "Yes" if config.agent.stream else "No")
    tbl.add_row("Think Aloud",    "Yes" if config.agent.think_aloud else "No")
    tbl.add_row("Context Window", f"{config.model.context_window:,} tokens")
    tbl.add_row("Max Tokens",     f"{config.model.max_tokens:,}")
    tbl.add_row("Temperature",    str(config.model.temperature))
    console.print(tbl)

    console.print("[dim]  Run [cyan]tuki config --setup[/cyan] to change your provider or model.[/dim]\n")



@app.command("history", help="Shows the past conversation history.")
def show_history(limit: int = typer.Option(10, "--limit", "-l", help="Amount to show"),
                 delete: str = typer.Option(None, "--delete", "-d", help="Delete 'all' or a specific session ID")):
    import sqlite3
    from config import get_app_dir
    base_dir = get_app_dir()
    db_path = base_dir / "data" / "history.db"
    if not db_path.exists():
        print("No history available.")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    if delete:
        display = TukiDisplay()
        if delete.lower() == "all":
            c.execute("DELETE FROM history")
            display.console.print("[bold red]All sessions have been deleted.[/bold red]")
        else:
            try:
                session_id = int(delete)
                c.execute("DELETE FROM history WHERE id=?", (session_id,))
                if c.rowcount > 0:
                    display.console.print(f"[bold green]Session {session_id} deleted successfully.[/bold green]")
                else:
                    display.console.print(f"[bold red]Session {session_id} not found.[/bold red]")
            except ValueError:
                display.console.print("[bold red]Invalid ID. Please provide 'all' or a numeric session ID.[/bold red]")
        conn.commit()
        conn.close()
        return

    c.execute("SELECT id, date, title, model, tokens FROM history ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    
    display = TukiDisplay()
    if not rows:
        display.console.print("[dim]No sessions found in history.[/dim]")
    else:
        display.show_history_table(rows)


@app.command("models", help="Lists available local and cloud models.")
def list_models():
    config = load_config()
    display = TukiDisplay()
    
    # 1. Local Ollama Models
    ollama_client = OllamaClient(config.model.name, 0, 0, False)
    display.console.print("\n[bold cyan]─── Local Ollama Models ───[/bold cyan]")
    if ollama_client.is_available():
        models = ollama_client.list_models()
        if not models:
            display.console.print("[dim]  No local models found.[/dim]")
        for m in models:
            # Marcamos como activo solo si OpenRouter está desactivado y el nombre coincide
            is_active = (m == config.model.name and not config.openrouter.enabled)
            prefix = "✅ " if is_active else "   "
            display.console.print(f"{prefix}{m}")
    else:
        display.console.print("[yellow]  Ollama is not available (not running).[/yellow]")

    # 2. Cloud Model (OpenRouter)
    if config.openrouter.enabled:
        display.console.print("\n[bold cyan]─── Cloud Model (OpenRouter) ───[/bold cyan]")
        display.console.print(f"✅ {config.model.name} [dim](Active)[/dim]")
    elif config.openrouter.api_key:
        display.console.print("\n[bold cyan]─── Cloud Model (OpenRouter) ───[/bold cyan]")
        display.console.print(f"   {config.model.name} [dim](Inactive - using Ollama)[/dim]")

def main():
    app()

if __name__ == "__main__":
    main()
