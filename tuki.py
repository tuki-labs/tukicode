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

@app.command("chat", help="Starts an interactive session with the TukiCode agent.")
def chat(session_id: int = typer.Argument(None, help="ID of a previous session to resume"),
         model: str = typer.Option(None, "--model", "-m", help="Override model"),
         risk: str = typer.Option(None, "--risk", "-r", help="Override risk level")):
    config = load_config()
    
    if model:
        config.model.name = model
    if risk:
        config.agent.risk_level = risk

    loaded_integrations = load_integrations(config, tool_registry)
    
    display = TukiDisplay()
    
    if loaded_integrations:
        display.console.print(f"[dim]Loaded integrations: {', '.join(loaded_integrations)}[/dim]")

    if config.openrouter.enabled:
        client = OpenRouterClient(
            model_name=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            stream=config.agent.stream,
            api_key=config.openrouter.api_key
        )
        if not client.is_available():
            display.show_error("OpenRouter API Key is missing. Check your tukicode.toml.")
            raise typer.Exit(1)
    else:
        client = OllamaClient(
            model_name=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            stream=config.agent.stream
        )
        with display.show_spinner("Verifying Ollama"):
            if not client.is_available():
                display.show_error("Ollama is not available. Make sure it is running (ollama serve).")
                raise typer.Exit(1)

    context = ConversationContext(config.model.context_window)
    base_dir = get_app_dir()
    
    app_ui = TukiApp(config, client, tool_registry, context, session_id=session_id)
    
    if session_id:
        db_path = base_dir / "data" / "history.db"
        if not app_ui.agent_loop.load_history(str(db_path), session_id):
            display.show_error(f"Session ID {session_id} not found or could not be loaded.")
            raise typer.Exit(1)
            
    # La renderización del contexto cargado se puede hacer dentro del mount de la app o aquí
    # Para Textual, lo haremos después de iniciar o pasando los mensajes.
    # Por ahora, iniciamos la app.
    
    try:
        app_ui.run()
    finally:
        db_path = base_dir / "data" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        title = getattr(app_ui, "session_title", None)
        app_ui.agent_loop.save_to_history(str(db_path), custom_title=title, session_id=session_id)
        print(f"\nConversation saved. Total session tokens: {context.token_count}")


@app.command("config", help="Shows or modifies the system configuration. Use --setup to enter interactive mode.")
def show_config(setup: ConfigComponent = typer.Option(None, "--setup", help="Setup a specific component interactively.")):
    from config import save_config
    config = load_config()
    display = TukiDisplay()

    if setup == ConfigComponent.OLLAMA:
        display.console.print("\n[bold cyan]─── Ollama Configuration (Local) ───[/bold cyan]")
        config.openrouter.enabled = False
        config.model.name = typer.prompt("Ollama model name", default=config.model.name)
        config.model.temperature = float(typer.prompt("Temperature", default=str(config.model.temperature)))
        config.model.max_tokens = int(typer.prompt("Max tokens", default=str(config.model.max_tokens)))
        config.model.context_window = int(typer.prompt("Context window", default=str(config.model.context_window)))
        save_config(config)
        display.console.print("\n[bold green]✅ Ollama configuration saved and set as active![/bold green]")
        return

    if setup == ConfigComponent.OPENROUTER:
        display.console.print("\n[bold cyan]─── OpenRouter Configuration (Cloud) ───[/bold cyan]")
        config.openrouter.enabled = True
        config.model.name = typer.prompt("OpenRouter model name", default=config.model.name)
        config.openrouter.api_key = typer.prompt("OpenRouter API Key", default=config.openrouter.api_key, hide_input=True)
        save_config(config)
        display.console.print("\n[bold green]✅ OpenRouter configuration saved and set as active![/bold green]")
        return

    # Default behavior: show current config
    import dataclasses
    import json
    display.console.print("\n[bold cyan]Current Configuration:[/bold cyan]")
    data = dataclasses.asdict(config)
    display.console.print(json.dumps(data, indent=2, ensure_ascii=False))


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