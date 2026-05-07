import asyncio
from agent.state import PlannerState
from agent.loop import AgentLoop

class Executor:
    def __init__(self, agent_loop: AgentLoop, state: PlannerState, display, config=None):
        self.agent_loop = agent_loop
        self.state = state
        self.display = display
        self.config = config
        self.max_retries = 3
        self._original_model = None  # para restaurar al final

    def _get_fallback_models(self) -> list:
        """Lee los modelos de fallback desde la config."""
        if self.config and hasattr(self.config, 'model'):
            return getattr(self.config.model, 'fallback_models', [])
        return [
            "tencent/hy3-preview:free",
            "qwen/qwen3-coder-480b:free",
            "deepseek/deepseek-r1:free",
        ]

    def _switch_to_fallback(self, failed_model: str) -> bool:
        """Cambia al siguiente modelo de fallback. Retorna True si pudo cambiar."""
        fallbacks = self._get_fallback_models()
        try:
            idx = fallbacks.index(failed_model)
            next_model = fallbacks[idx + 1] if idx + 1 < len(fallbacks) else None
        except ValueError:
            next_model = fallbacks[0] if fallbacks else None

        if next_model and next_model != failed_model:
            self.display.show_error(
                f"Switching model: [{failed_model}] → [{next_model}]"
            )
            self.agent_loop.llm_client.model_name = next_model
            return True
        return False

    async def execute_plan(self):
        """Ejecuta los pasos pendientes del plan secuencialmente."""
        pending_steps = self.state.get_pending_steps()
        if not pending_steps:
            self.display.print("No pending steps in the plan.")
            return

        # Guardar modelo original para restaurar al terminar
        self._original_model = self.agent_loop.llm_client.model_name
        self.state.state["status"] = "building"
        self.state.save()

        try:
            for step in pending_steps:
                if self.agent_loop._stop_requested:
                    self.display.print("Execution stopped by user.")
                    break

                step_id = step["id"]
                description = step["description"]

                self.state.state["current_step"] = step_id
                self.state.save()

                self.display.print(f"--- Executing Step {step_id}/{len(self.state.state['plan'])} ---")
                self.display.print(f"Task: {description}")

                success = False
                for attempt in range(self.max_retries):
                    if self.agent_loop._stop_requested:
                        break

                    if attempt > 0:
                        self.display.show_error(
                            f"Retry {attempt + 1}/{self.max_retries} for Step {step_id}"
                        )

                    completed = [s for s in self.state.state["plan"] if s["status"] == "completed"]
                    context_msg = "Completed steps so far:\n" + "\n".join(
                        [f"- {s['description']}" for s in completed]
                    )

                    step_prompt = f"""[PLANNER EXECUTION]
{context_msg}

CURRENT STEP TO EXECUTE:
{description}

CRITICAL INSTRUCTIONS:
1. Complete ONLY this step. Do not try to complete future steps.
2. Use tools to verify your work if needed.
3. Once you verify the step is done, output your FINAL RESPONSE confirming the result.
4. Keep the code strictly required for this step.
"""
                    try:
                        result = await self.agent_loop.run_turn(step_prompt)

                        if "Execution stopped" in result:
                            break

                        success = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        self.display.show_error(f"Step {step_id} error: {error_msg}")

                        # ── Fallback de modelo si es timeout o error de red ──
                        is_timeout = any(kw in error_msg.lower() for kw in [
                            "timeout", "timed out", "10054", "10060",
                            "connection reset", "remote protocol"
                        ])

                        if is_timeout and attempt < self.max_retries - 1:
                            current_model = self.agent_loop.llm_client.model_name
                            switched = self._switch_to_fallback(current_model)
                            if switched:
                                self.display.print("Retrying with fallback model...")
                                continue
                        # Si no es timeout o ya no hay fallback, continúa el retry normal

                if success:
                    self.state.mark_step_completed(step_id)
                    self.display.print(f"✓ Step {step_id} completed successfully.")
                else:
                    self.state.mark_step_failed(step_id)
                    self.display.show_error(
                        f"Step {step_id} failed after {self.max_retries} attempts. Aborting."
                    )
                    self.state.state["status"] = "idle"
                    self.state.save()
                    return

        finally:
            # Restaurar modelo original al terminar o si hay error
            if self._original_model:
                self.agent_loop.llm_client.model_name = self._original_model

        if not self.state.get_pending_steps():
            self.state.state["status"] = "completed"
            self.state.save()
            self.display.print(" ✓ Plan execution completed entirely!")
