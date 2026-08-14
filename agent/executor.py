import asyncio
from agent.state import PlannerState
from agent.loop import AgentLoop

class Executor:
    def __init__(self, agent_loop: AgentLoop, state: PlannerState, display, config=None):
        self.agent_loop = agent_loop
        self.state = state
        self.display = display
        self.config = config
        self.max_retries = 4
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

    def _classify_error(self, error_msg: str) -> str:
        """Classifies an error to determine the best recovery strategy.

        Returns one of:
          'rate_limit'    — API rate limited, need to back off
          'timeout'       — Network timeout or connection reset
          'model_error'   — Model-specific error (overloaded, unavailable)
          'auth'          — Auth/billing error (don't retry)
          'unknown'       — Unknown error
        """
        msg = error_msg.lower()

        if any(kw in msg for kw in ["rate limit", "429", "too many requests"]):
            return "rate_limit"

        if any(kw in msg for kw in [
            "timeout", "timed out", "10054", "10060",
            "connection reset", "remote protocol", "read timeout",
            "connect timeout"
        ]):
            return "timeout"

        if any(kw in msg for kw in [
            "529", "overloaded", "model_error", "server error",
            "502", "503", "500"
        ]):
            return "model_error"

        if any(kw in msg for kw in ["401", "402", "403", "auth", "billing", "insufficient"]):
            return "auth"

        return "unknown"

    def _get_backoff_delay(self, error_type: str, attempt: int) -> float:
        """Returns the delay before retrying based on error type and attempt number."""
        import random
        if error_type == "rate_limit":
            # Aggressive backoff for rate limits: 5s, 15s, 30s, 60s
            base = min(5 * (3 ** attempt), 60)
            return base + random.uniform(0, base * 0.4)
        elif error_type == "timeout":
            # Moderate backoff: 3s, 6s, 12s
            return min(3 * (2 ** attempt), 15) + random.uniform(0, 2)
        elif error_type == "model_error":
            # Wait longer — model might need time to recover: 10s, 20s, 40s
            return min(10 * (2 ** attempt), 45) + random.uniform(0, 5)
        else:
            return min(2 * (2 ** attempt), 10)

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

        total_steps = len(self.state.state["plan"])
        completed_count = 0

        try:
            for step in pending_steps:
                if self.agent_loop._stop_requested:
                    self.display.print("Execution stopped by user.")
                    break

                step_id = step["id"]
                description = step["description"]

                self.state.state["current_step"] = step_id
                self.state.save()

                self.display.print(
                    f"--- Executing Step {step_id}/{total_steps} ---"
                )
                self.display.print(f"Task: {description}")

                success = False
                for attempt in range(self.max_retries):
                    if self.agent_loop._stop_requested:
                        break

                    if attempt > 0:
                        self.display.show_error(
                            f"Retry {attempt + 1}/{self.max_retries} for Step {step_id}"
                        )

                    completed = [
                        s for s in self.state.state["plan"]
                        if s["status"] == "completed"
                    ]
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
                        error_type = self._classify_error(error_msg)

                        self.display.show_error(
                            f"Step {step_id} error [{error_type}]: {error_msg[:120]}"
                        )

                        # ── Auth errors: abort immediately ──
                        if error_type == "auth":
                            self.display.show_error(
                                "Authentication/billing error — cannot continue."
                            )
                            self.state.mark_step_failed(step_id)
                            self.state.state["status"] = "idle"
                            self.state.save()
                            return

                        # ── Rate limits: aggressive backoff before retry ──
                        if error_type == "rate_limit":
                            delay = self._get_backoff_delay("rate_limit", attempt)
                            self.display.print(
                                f"⏳ Rate limited. Waiting {delay:.0f}s before retry..."
                            )
                            await asyncio.sleep(delay)

                            # Clear the context to reduce token usage on retry
                            # (prevents re-sending the same large context)
                            self.agent_loop.context.clear()
                            self.agent_loop.start_session()
                            continue

                        # ── Timeout / Connection errors: backoff + optional fallback ──
                        if error_type in ("timeout", "model_error"):
                            if attempt < self.max_retries - 1:
                                delay = self._get_backoff_delay(error_type, attempt)
                                self.display.print(
                                    f"⏳ Waiting {delay:.0f}s before retry..."
                                )
                                await asyncio.sleep(delay)

                                # Try fallback model on 2nd timeout
                                if attempt >= 1:
                                    current_model = self.agent_loop.llm_client.model_name
                                    switched = self._switch_to_fallback(current_model)
                                    if switched:
                                        self.display.print(
                                            "Retrying with fallback model..."
                                        )
                                continue

                        # ── Unknown errors: moderate backoff ──
                        if attempt < self.max_retries - 1:
                            delay = self._get_backoff_delay("unknown", attempt)
                            await asyncio.sleep(delay)
                            continue

                if success:
                    self.state.mark_step_completed(step_id)
                    completed_count += 1
                    self.display.print(
                        f"✓ Step {step_id} completed successfully. "
                        f"({completed_count}/{total_steps})"
                    )
                else:
                    self.state.mark_step_failed(step_id)
                    self.display.show_error(
                        f"Step {step_id} failed after {self.max_retries} attempts. "
                        f"Skipping to next step."
                    )
                    # Instead of aborting the entire plan, continue to the next step
                    continue

        finally:
            # Restaurar modelo original al terminar o si hay error
            if self._original_model:
                self.agent_loop.llm_client.model_name = self._original_model

        failed_steps = [
            s for s in self.state.state["plan"] if s["status"] == "failed"
        ]
        if not self.state.get_pending_steps():
            if failed_steps:
                self.state.state["status"] = "completed_with_errors"
                self.state.save()
                self.display.print(
                    f"⚠ Plan completed with {len(failed_steps)} failed step(s): "
                    + ", ".join([f"#{s['id']}" for s in failed_steps])
                )
            else:
                self.state.state["status"] = "completed"
                self.state.save()
                self.display.print(" ✓ Plan execution completed entirely!")
