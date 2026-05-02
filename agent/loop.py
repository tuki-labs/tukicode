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
        
        for _ in range(20): # max 20 iterations
            self.context.compress_if_needed(self.llm_client)
            
            messages = self.context.get_messages()
            native_tools = self._get_native_tools()
            
            loop = asyncio.get_event_loop()
            full_response = await loop.run_in_executor(None, self._chat_and_stream, messages, native_tools)
            
            # Debug
            try:
                debug_path = Path("last_response.json")
                if isinstance(full_response, str):
                    debug_path.write_text(full_response, encoding="utf-8")
                else:
                    debug_path.write_text(json.dumps(full_response, ensure_ascii=False), encoding="utf-8")
            except:
                pass
            
            # Extraer thinking antes de parsear
            text_for_thinking = ""
            if isinstance(full_response, str):
                text_for_thinking = full_response
            elif isinstance(full_response, dict):
                if "message" in full_response:
                    text_for_thinking = full_response["message"].get("content", "")
                elif "choices" in full_response and len(full_response["choices"]) > 0:
                    text_for_thinking = full_response["choices"][0].get("message", {}).get("content", "")
                    
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
                    elif "choices" in full_response and len(full_response["choices"]) > 0:
                        full_response["choices"][0]["message"]["content"] = clean_text
            
            # Parsear la respuesta (str o dict)
            use_native = getattr(self.llm_client, "supports_tool_calling", False)
            parsed = parse_response(full_response, use_native=use_native)
            
            if isinstance(parsed, ToolCall):
                # Guardamos lo que nos devolvió para que quede en el historial de contexto
                if isinstance(full_response, str):
                    self.context.add_message("assistant", full_response)
                else:
                    self.context.add_message("assistant", json.dumps(full_response))
                
                tool_item = self.tool_registry._tools.get(parsed.tool_name)
                if tool_item:
                    from tools.base import BaseTool
                    tool_risk = tool_item.risk_level if isinstance(tool_item, BaseTool) else getattr(tool_item, "__tool_risk__")
                    
                    if tool_risk.value >= RiskLevel.MEDIUM.value:
                        args_str = str(parsed.args)
                        if len(args_str) > 200: args_str = args_str[:197] + "..."
                        msg = f"Tool: [bold cyan]{parsed.tool_name}[/bold cyan]\nArgs: {args_str}\nRisk: [bold yellow]{tool_risk.name}[/bold yellow]\n¿Confirmar?"
                        
                        if hasattr(self.display, "confirm_async"):
                            confirmed = await self.display.confirm_async(msg)
                        else:
                            confirmed = self.display.confirm(msg)
                        
                        if not confirmed:
                            self.context.add_message("tool_result", "Acción cancelada por el usuario.")
                            continue
                
                # Execute tool
                with self.display.show_spinner(f"Executing {parsed.tool_name}..."):
                    result = await loop.run_in_executor(None, self.tool_registry.execute, parsed.tool_name, parsed.args, self.config.agent.risk_level)
                
                self.display.show_tool_result(parsed.tool_name, result)
                
                if result.success and "diff" in result.metadata:
                    self.display.show_diff(result.metadata["diff"])
                    
                result_str = f"Success: {result.success}\nOutput:\n{result.output}"
                if result.error:
                    result_str += f"\nError:\n{result.error}"
                    
                self.context.add_message("tool_result", result_str)
            
            elif isinstance(parsed, FinalResponse):
                self.context.add_message("assistant", parsed.text)
                return parsed.text
                
        return "ReAct loop iteration limit reached."

    def _chat_and_stream(self, messages, tools=None):
        stream = self.llm_client.chat_stream(messages, tools=tools)
        
        full_dict = None
        
        def display_gen():
            nonlocal full_dict
            for chunk in stream:
                if isinstance(chunk, str):
                    yield chunk
                elif isinstance(chunk, dict):
                    full_dict = chunk
                    
        full_text = self.display.stream_response(display_gen())
        
        if full_dict:
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
                self.context.token_count = sum(len(m.get('content', '').split()) * 1.3 for m in messages)
                return True
            return False
        except Exception:
            return False
        finally:
            conn.close()
