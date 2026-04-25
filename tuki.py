import sys
import os
import typer
import asyncio
from pathlib import Path

# Añadir el directorio actual al path para importaciones absolutas
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import load_config, get_app_dir, save_config, Config
from integrations import load_integrations
from agent.ollama_client import OllamaClient
from tools.registry import registry as tool_registry
from agent.context import ConversationContext
from agent.loop import AgentLoop
from ui.display import TukiDisplay
from ui.input import TukiInput, COMMANDS
from ui.layout import TukiApp

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
    display.show_banner("1.0.0", config.model.name, config.agent.risk_level)
    
    if loaded_integrations:
        display.console.print(f"[dim]Loaded integrations: {', '.join(loaded_integrations)}[/dim]")

    client = OllamaClient(
        model_name=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        stream=config.agent.stream
    )

    with display.show_spinner("Verifying Ollama"):
        if not client.is_available():
            display.show_error("Ollama is not available. Make sure it is running (ollama serve).")
            raise  typer.Exit(1)

    context = ConversationContext(config.model.context_window)
    base_dir = get_app_dir()
    
    app_ui = TukiApp(config, client, tool_registry, context, session_id=session_id)
    
    if session_id:
        db_path = base_dir / "data" / "history.db"
        if not app_ui.agent_loop.load_history(str(db_path), session_id):
            display.show_error(f"Session ID {session_id} not found or could not be loaded.")
            raise typer.Exit(1)
            
    # The UI will render the loaded context in its __init__ if any messages exist.
    app_ui.render_loaded_context()
    
    try:
        app_ui.run()
    finally:
        db_path = base_dir / "data" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        title = getattr(app_ui, "session_title", None)
        app_ui.agent_loop.save_to_history(str(db_path), custom_title=title, session_id=session_id)
        print(f"\nConversation saved. Total session tokens: {context.token_count}")


@app.command("config", help="Shows the current system configuration.")
def show_config():
    config = load_config()
    display = TukiDisplay()
    # Simple dict dump
    import dataclasses
    import json
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


@app.command("models", help="Lists the downloaded models in your local Ollama server.")
def list_models():
    config = load_config()
    client = OllamaClient(config.model.name, 0, 0, False)
    
    if not client.is_available():
        print("Error: Ollama is not available.")
        return
        
    models = client.list_models()
    for m in models:
        prefix = "✅ " if m == config.model.name else "   "
        print(f"{prefix}{m}")

if __name__ == "__main__":
    app()