import asyncio
from pathlib import Path

class TukiController:
    """
    Central controller for TukiCode.
    Handles the business logic, AgentLoop, Planner, and Executor.
    Separates the UI (Textual App) from the AI logic.
    """
    def __init__(self, config, client, registry, context, display, session_id=None):
        self.config = config
        self.client = client
        self.registry = registry
        self.context = context
        self.display = display
        self.session_id = session_id

        # Initialize AI components
        from agent.loop import AgentLoop
        from agent.state import PlannerState
        from agent.planner import Planner
        from agent.executor import Executor

        self.agent_loop = AgentLoop(config, client, registry, context, display)
        self.planner_state = PlannerState()
        self.planner_state.load()
        self.planner = Planner(client, display)
        self.executor = Executor(self.agent_loop, self.planner_state, display, config=config)

        self.mode = "chat" # default mode

    def set_mode(self, mode: str):
        """Sets the active mode: chat, plan, or build."""
        self.mode = mode.lower()

    async def process_input(self, text: str):
        """Processes user input based on the current mode."""
        if self.mode == "chat":
            await self._run_chat(text)
        elif self.mode == "plan":
            await self._run_plan(text)
        elif self.mode == "build":
            await self._run_build(text)
        else:
            self.display.show_error(f"Unknown mode: {self.mode}")

    async def _run_chat(self, text: str):
        try:
            await self.agent_loop.run_turn(text)
        except Exception as e:
            self._handle_error(e)

    async def _run_plan(self, text: str):
        try:
            plan = await self.planner.generate_plan(text, str(Path.cwd()))
            self.planner_state.set_plan(plan)
            
            plan_str = "\n".join([f"{s['id']}. {s['description']}" for s in self.planner_state.state["plan"]])
            self.display.print(f"**Proposed Plan:**\n{plan_str}")
            
            if hasattr(self.display, "confirm_async"):
                confirm = await self.display.confirm_async("Do you want to execute this plan? (y/n)")
            else:
                confirm = False
                
            if confirm:
                 self.display.print("Starting execution...")
                 await self.executor.execute_plan()
            else:
                 self.planner_state.state["status"] = "idle"
                 self.planner_state.save()
        except Exception as e:
            self._handle_error(e)

    async def _run_build(self, text: str):
        try:
            pending = self.planner_state.get_pending_steps()
            if not pending:
                plan = await self.planner.generate_plan(text, str(Path.cwd()))
                self.planner_state.set_plan(plan)

                # Show the plan before executing (no confirmation needed in Build Mode)
                plan_str = "\n".join(
                    [f"{s['id']}. {s['description']}" for s in self.planner_state.state["plan"]]
                )
                self.display.print(f"**Auto-generated Plan:**\n{plan_str}\n")

            self.display.print("Starting execution directly...")
            await self.executor.execute_plan()
        except Exception as e:
            self._handle_error(e)

    def _handle_error(self, e: Exception):
        from ui.display import StopRequestedException
        if isinstance(e, StopRequestedException):
            self.display.print("[bold red]Agent stopped.[/bold red]")
        else:
            self.display.show_error(str(e))

    def stop_agent(self):
        """Stops the currently running agent loop or executor."""
        self.agent_loop._stop_requested = True
        self.display.should_stop = True

    def switch_model(self, provider: str, model_name: str = None):
        """
        Switches the active LLM client based on the provider and model name.
        This logic is now in the controller, keeping the UI clean.
        """
        from agent.ollama_client import OllamaClient
        from agent.openrouter_client import OpenRouterClient
        from agent.gemini_client import GeminiClient
        from agent.anthropic_client import AnthropicClient

        if model_name:
            self.config.model.name = model_name
        self.config.model.provider = provider
        
        temp = self.config.model.temperature
        max_t = self.config.model.max_tokens
        stream = self.config.agent.stream

        if provider == "gemini":
            if not self.config.gemini.api_key:
                raise ValueError("Gemini API Key is missing.")
            new_client = GeminiClient(
                self.config.gemini.model, temp, max_t, stream, self.config.gemini.api_key
            )
        elif provider == "anthropic":
            if not self.config.anthropic.api_key:
                raise ValueError("Anthropic API Key is missing.")
            new_client = AnthropicClient(
                self.config.anthropic.model, temp, max_t, stream, self.config.anthropic.api_key
            )
        elif provider == "openrouter":
            if not self.config.openrouter.api_key:
                raise ValueError("OpenRouter API Key is missing.")
            new_client = OpenRouterClient(
                self.config.model.name, temp, max_t, stream, self.config.openrouter.api_key
            )
        else: # ollama
            new_client = OllamaClient(self.config.model.name, temp, max_t, stream)
            # We don't check availability here to avoid blocking UI thread if not async,
            # but usually it's fine.

        self.update_client(new_client)
        self.config.save()
        return new_client

    def update_client(self, new_client):
        """Updates the active LLM client across all components."""
        self.client = new_client
        self.agent_loop.llm_client = new_client
        self.planner.llm_client = new_client

    def save_session(self):
        """Saves the current conversation to history."""
        from config import get_app_dir
        db_path = get_app_dir() / "data" / "history.db"
        self.agent_loop.save_to_history(str(db_path), session_id=self.session_id)

    def save_setup(self, provider: str, model_name: str, api_key: str):
        if provider == "openrouter" and api_key: self.config.openrouter.api_key = api_key
        elif provider == "gemini" and api_key: self.config.gemini.api_key = api_key
        elif provider == "anthropic" and api_key: self.config.anthropic.api_key = api_key
        self.switch_model(provider, model_name)

    def get_history(self, limit: int = 10):
        import sqlite3
        from config import get_app_dir
        db_path = get_app_dir() / "data" / "history.db"
        if not db_path.exists():
            return []
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT id, date, title, model FROM history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return rows

    def get_available_models(self):
        models = {
            "ollama": [],
            "gemini": self.config.gemini.models,
            "anthropic": self.config.anthropic.models,
            "openrouter": self.config.openrouter.models
        }
        try:
            import ollama
            for m in ollama.list().get('models', []):
                models["ollama"].append(m['name'])
        except Exception:
            pass
        return models

    def guess_provider(self, model_name: str) -> str:
        m = model_name.lower()
        if "gemini" in m: return "gemini"
        if "claude" in m or "anthropic" in m: return "anthropic"
        if "/" in m: return "openrouter" 
        return "ollama"
