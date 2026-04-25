import sqlite3
import datetime
import asyncio
from pathlib import Path
from .parser import parse_response, ToolCall, FinalResponse

class AgentLoop:
    def __init__(self, config, ollama_client, tool_registry, context, display):
        self.config = config
        self.ollama_client = ollama_client
        self.tool_registry = tool_registry
        self.context = context
        self.display = display

    def start_session(self):
        from .prompts import build_system_prompt
        sys_prompt = build_system_prompt(self.config, self.tool_registry)
        self.context.clear()
        self.context.add_message("system", sys_prompt)

    async def run_turn(self, user_message: str) -> str:
        self.context.add_message("user", user_message)
        
        for _ in range(20): # max 20 iterations
            self.context.compress_if_needed(self.ollama_client)
            
            messages = self.context.get_messages()
            
            # Note: We are using chat_stream which returns a generator.
            # In an async context, it should ideally be an async generator.
            # But ollama library's chat(stream=True) is a blocking generator.
            # We can wrap it in a thread or use an async client.
            # For simplicity, we'll run the blocking generator in a thread.
            
            loop = asyncio.get_event_loop()
            full_response = await loop.run_in_executor(None, self._chat_and_stream, messages)
            
            parsed = parse_response(full_response)
            
            if isinstance(parsed, ToolCall):
                self.context.add_message("assistant", full_response)
                
                tool_item = self.tool_registry._tools.get(parsed.tool_name)
                if tool_item:
                    from ..tools.base import BaseTool
                    tool_risk = tool_item.risk_level if isinstance(tool_item, BaseTool) else getattr(tool_item, "__tool_risk__")
                    if tool_risk.name == "HIGH":
                        # This needs to be async-aware confirmation
                        if hasattr(self.display, "confirm_async"):
                            confirmed = await self.display.confirm_async(f"The tool {parsed.tool_name} has HIGH risk. Allow execution?")
                        else:
                            confirmed = self.display.confirm(f"The tool {parsed.tool_name} has HIGH risk. Allow execution?")
                        
                        if not confirmed:
                            self.context.add_message("tool_result", "Execution cancelled by the user.")
                            continue
                
                # Execute tool (might be blocking, run in executor)
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

    def _chat_and_stream(self, messages):
        stream = self.ollama_client.chat_stream(messages)
        return self.display.stream_response(stream)

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
        import json
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
                      (date_str, title, self.ollama_client.model_name, self.context.token_count, content_json))
        
        conn.commit()
        conn.close()

    def load_history(self, db_path: str, session_id: int):
        import json
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
                # Recalculate tokens roughly
                self.context.token_count = sum(len(m.get('content', '').split()) * 1.3 for m in messages)
                return True
            return False
        except Exception:
            return False
        finally:
            conn.close()
