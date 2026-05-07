import sqlite3
import datetime
import asyncio
from pathlib import Path
from .parser import parse_response, ToolCall, FinalResponse, extract_thinking
from tools.base import RiskLevel
import json

class AgentLoop:
    def __init__(self, config, llm_client, tool_registry, context, display):
        self.config = config
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.context = context
        self.display = display
        self._stop_requested = False

    def start_session(self):
        from .prompts import build_system_prompt
        sys_prompt = build_system_prompt(self.config, self.tool_registry)
        self.context.clear()
        self.context.add_message("system", sys_prompt)

    def _get_native_tools(self):
        native_tools = []
        for t in self.tool_registry.get_schema():
            properties = {}
            for arg_name, arg_type in t["args"].items():
                properties[arg_name] = {"type": "string"}
            native_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(t["args"].keys())
                    }
                }
            })
        return native_tools

    async def run_turn(self, user_message: str) -> str:
        self.context.add_message("user", user_message)
        self._turn_confirmed = False

        # ── Anti-loop: tracking de repeticiones ──
        last_tool_calls = []
        repeated_count = 0
        MAX_ITERATIONS = 20
        NUDGE_AT = 8        # iteraciones antes de recordarle que termine
        MAX_REPEATED = 3    # veces que puede repetir la misma tool antes de cortar

        try:
            for iteration in range(MAX_ITERATIONS):
                if self._stop_requested:
                    self._stop_requested = False
                    return "Agent execution stopped by user."

                self.context.compress_if_needed(self.llm_client)
                messages = self.context.get_messages()
                native_tools = self._get_native_tools()

                # ── Nudge: recordarle al modelo que debe terminar ──
                if iteration == NUDGE_AT:
                    self.context.add_message("system",
                        "You have been working for several steps. "
                        "If you have enough information, provide your FINAL RESPONSE now. "
                        "Do not call more tools unless strictly necessary."
                    )

                # ── Timeout por llamada al LLM (60s) ──
                try:
                    full_response = await asyncio.wait_for(
                        self._chat_and_stream(messages, native_tools),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    self.display.show_error("LLM response timed out. Retrying...")
                    continue

                # Debug
                try:
                    debug_path = Path("last_response.json")
                    if isinstance(full_response, str):
                        debug_path.write_text(full_response, encoding="utf-8")
                    else:
                        debug_path.write_text(json.dumps(full_response, ensure_ascii=False), encoding="utf-8")
                except:
                    pass

                # Extraer thinking
                text_for_thinking = ""
                if isinstance(full_response, str):
                    text_for_thinking = full_response
                elif isinstance(full_response, dict):
                    if "message" in full_response:
                        text_for_thinking = full_response["message"].get("content", "") or ""
                    elif "choices" in full_response and full_response["choices"]:
                        text_for_thinking = full_response["choices"][0].get("message", {}).get("content", "") or ""

                if text_for_thinking:
                    thinking, clean_text = extract_thinking(text_for_thinking)
                    if thinking:
                        self.display.show_thinking(thinking)
                    else:
                        self.display.show_thinking("", visible=False)

                    if isinstance(full_response, str):
                        full_response = clean_text
                    elif isinstance(full_response, dict):
                        if "message" in full_response:
                            full_response["message"]["content"] = clean_text
                        elif "choices" in full_response and full_response["choices"]:
                            full_response["choices"][0]["message"]["content"] = clean_text

                use_native = getattr(self.llm_client, "supports_tool_calling", False)
                parsed = parse_response(full_response, use_native=use_native)

                if isinstance(parsed, ToolCall):
                    # ── Anti-loop: detectar tool calls repetidas ──
                    tool_signature = f"{parsed.tool_name}:{json.dumps(parsed.args, sort_keys=True)}"
                    if tool_signature in last_tool_calls[-3:]:
                        repeated_count += 1
                        if repeated_count >= MAX_REPEATED:
                            # Inyectar mensaje de error y forzar respuesta final
                            self.context.add_message("tool",
                                f"ERROR: Tool '{parsed.tool_name}' has been called with the same arguments "
                                f"{MAX_REPEATED} times in a row. Stop repeating and provide your FINAL RESPONSE.",
                                tool_call_id=parsed.call_id
                            )
                            self.display.show_error(f"Loop detected: '{parsed.tool_name}' repeated {MAX_REPEATED} times. Forcing final response.")
                            repeated_count = 0
                            last_tool_calls = []
                            continue
                    else:
                        repeated_count = 0

                    last_tool_calls.append(tool_signature)
                    if len(last_tool_calls) > 10:
                        last_tool_calls.pop(0)

                    # Guardar en contexto
                    if isinstance(full_response, dict):
                        msg_obj = {}
                        if "choices" in full_response:
                            msg_obj = full_response["choices"][0].get("message", {})
                        elif "message" in full_response:
                            msg_obj = full_response["message"]
                        self.context.add_message("assistant", msg_obj.get("content"), tool_calls=msg_obj.get("tool_calls"))
                    else:
                        self.context.add_message("assistant", str(full_response))

                    # Confirmación por riesgo
                    tool_item = self.tool_registry._tools.get(parsed.tool_name)
                    if tool_item:
                        from tools.base import BaseTool
                        tool_risk = tool_item.risk_level if isinstance(tool_item, BaseTool) else getattr(tool_item, "__tool_risk__")
                        autonomy = self.config.agent.autonomy_level.lower()
                        should_prompt = True

                        if autonomy == "high":
                            if self._turn_confirmed:
                                should_prompt = False
                        elif autonomy == "medium":
                            if tool_risk.value < RiskLevel.HIGH.value:
                                should_prompt = False

                        if should_prompt and tool_risk.value >= RiskLevel.MEDIUM.value:
                            details = ""
                            if "command" in parsed.args: details = f"Command: [yellow]{parsed.args['command']}[/yellow]"
                            elif "path" in parsed.args: details = f"Path: [yellow]{parsed.args['path']}[/yellow]"
                            elif "content" in parsed.args:
                                snippet = parsed.args['content'][:50] + "..." if len(parsed.args['content']) > 50 else parsed.args['content']
                                details = f"Content: [yellow]{snippet}[/yellow]"

                            msg = f"[bold yellow]Security Check[/bold yellow]\nAction: [cyan]{parsed.tool_name}[/cyan]\nRisk: [yellow]{tool_risk.name}[/yellow]\n{details}\n¿Permitir ejecución?"

                            if hasattr(self.display, "confirm_async"):
                                confirmed = await self.display.confirm_async(msg)
                            else:
                                confirmed = self.display.confirm(msg)

                            if not confirmed:
                                self.context.add_message("tool", "Action cancelled by user.", tool_call_id=parsed.call_id)
                                return "Action cancelled by user. What would you like to do next?"

                            self._turn_confirmed = True

                    # Ejecutar tool con timeout
                    details = ""
                    if "command" in parsed.args: details = parsed.args["command"]
                    elif "path" in parsed.args: details = parsed.args["path"]
                    if len(details) > 60: details = details[:57] + "..."

                    try:
                        with self.display.show_spinner(f"Executing {parsed.tool_name}", details=details):
                            loop = asyncio.get_event_loop()
                            result = await asyncio.wait_for(
                                loop.run_in_executor(None, self.tool_registry.execute, parsed.tool_name, parsed.args, self.config.agent.risk_level),
                                timeout=30.0  # tools síncronas tienen 30s máximo
                            )
                    except asyncio.TimeoutError:
                        result_str = f"ERROR: Tool '{parsed.tool_name}' timed out after 30 seconds. Use background=True for long-running processes."
                        self.display.show_error(f"Tool '{parsed.tool_name}' timed out.")
                        self.context.add_message("tool", result_str, tool_call_id=parsed.call_id)
                        continue

                    self.display.show_tool_result(parsed.tool_name, result)

                    if result.success and "diff" in result.metadata:
                        self.display.show_diff(result.metadata["diff"])

                    result_str = f"Success: {result.success}\nOutput:\n{result.output}"
                    if result.error:
                        result_str += f"\nError:\n{result.error}"

                    self.context.add_message("tool", result_str, tool_call_id=parsed.call_id)

                elif isinstance(parsed, FinalResponse):
                    self.display.show_thinking("", visible=False)
                    self.context.add_message("assistant", parsed.text)
                    return parsed.text

            # Límite alcanzado — forzar respuesta con lo que tiene
            self.display.show_error("Max iterations reached. Forcing final response.")
            self.context.add_message("system", 
                "MAX ITERATIONS REACHED. You MUST provide your final response NOW. "
                "Summarize what you have done and what the result is."
            )
            final = await self._chat_and_stream(self.context.get_messages(), None)
            if isinstance(final, str):
                return final
            return "Task completed. Max iterations reached."

        except Exception as e:
            from ui.display import StopRequestedException
            if isinstance(e, StopRequestedException):
                self._stop_requested = False
                return "Execution stopped by user."
            raise e

    def _merge_delta(self, target: dict, source: dict):
        """Fusiona un chunk de delta en un diccionario acumulado."""
        # Formato OpenRouter / OpenAI
        if "choices" in source and len(source["choices"]) > 0:
            delta = source["choices"][0].get("delta", {})
            if "tool_calls" in delta:
                if "choices" not in target:
                    target["choices"] = [{"message": {"tool_calls": []}}]
                
                target_tc = target["choices"][0]["message"]["tool_calls"]
                for stc in delta["tool_calls"]:
                    idx = stc.get("index", 0)
                    while len(target_tc) <= idx:
                        target_tc.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    
                    ttc = target_tc[idx]
                    if "id" in stc: ttc["id"] += stc["id"]
                    func = stc.get("function", {})
                    if "name" in func: ttc["function"]["name"] += func["name"]
                    if "arguments" in func: ttc["function"]["arguments"] += func["arguments"]
            
            # Mantener otros metadatos
            for key in ["id", "model", "object"]:
                if key in source: target[key] = source[key]
        
        # Formato Ollama
        if "message" in source:
            if "choices" not in target:
                target["choices"] = [{"message": {"content": "", "tool_calls": []}}]
            
            tmsg = target["choices"][0]["message"]
            smsg = source["message"]
            if "content" in smsg and smsg["content"]:
                tmsg["content"] += smsg["content"]
            if "tool_calls" in smsg:
                tmsg["tool_calls"] = smsg["tool_calls"] # Ollama suele mandar el tool_call completo

    async def _chat_and_stream(self, messages, tools=None):
        stream = self.llm_client.chat_stream(messages, tools=tools)
        
        full_dict = {}
        
        async def display_gen():
            nonlocal full_dict
            async for chunk in stream:
                if isinstance(chunk, str):
                    yield chunk
                elif isinstance(chunk, dict):
                    self._merge_delta(full_dict, chunk)
                    
        full_text = await self.display.stream_response(display_gen())
        
        if full_dict and "choices" in full_dict:
            return full_dict
        return full_text

    def save_to_history(self, db_path: str, custom_title: str = None, session_id: int = None):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS history
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      date TEXT, 
                      title TEXT, 
                      model TEXT, 
                      tokens INTEGER,
                      content TEXT)''')
        
        date_str = datetime.datetime.now().isoformat()
        content_json = json.dumps(self.context.get_messages(), ensure_ascii=False)
        
        title = custom_title
        if not title:
            title = "Conversation"
            if len(self.context.messages) > 1:
                title = self.context.messages[1]["content"][:50] + "..."
                
        if session_id:
            c.execute("UPDATE history SET date=?, title=COALESCE(?, title), tokens=?, content=? WHERE id=?",
                      (date_str, custom_title, self.context.token_count, content_json, session_id))
        else:
            c.execute("INSERT INTO history (date, title, model, tokens, content) VALUES (?, ?, ?, ?, ?)",
                      (date_str, title, self.llm_client.model_name, self.context.token_count, content_json))
        
        conn.commit()
        conn.close()

    def load_history(self, db_path: str, session_id: int):
        if not Path(db_path).exists():
            return False
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        try:
            c.execute("SELECT content FROM history WHERE id=?", (session_id,))
            row = c.fetchone()
            if row:
                messages = json.loads(row[0])
                self.context.messages = messages
                # Asegurar que content sea string para el conteo de tokens
                self.context.token_count = sum(len((m.get('content') or '').split()) * 1.3 for m in messages)
                return True
            return False
        except Exception:
            return False
        finally:
            conn.close()
