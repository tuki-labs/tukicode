import sqlite3
from typing import List, Dict
from typing import List, Dict, Any
from .prompts import build_compression_prompt

def estimate_tokens(text: str) -> int:
    return len(text) // 3

class ConversationContext:
    def __init__(self, context_window: int):
        self.messages: List[Dict[str, str]] = []
        self.token_count: int = 0
        self.context_window: int = context_window

    def add_message(self, role: str, content: str, **kwargs):
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)
        self.token_count += estimate_tokens(content or "")

    def get_messages(self) -> List[Dict[str, str]]:
        return self.messages

    def clear(self):
        if self.messages and self.messages[0]["role"] == "system":
            sys_msg = self.messages[0]
            self.messages = [sys_msg]
            self.token_count = estimate_tokens(sys_msg["content"])
        else:
            self.messages = []
            self.token_count = 0

    @property
    def usage_percent(self) -> float:
        return self.token_count / self.context_window if self.context_window > 0 else 0.0

    async def compress_if_needed(self, llm_client: Any, display: Any = None):
        if self.usage_percent <= 0.80:
            return
            
        if len(self.messages) <= 5:
            return # Not enough context to compress
            
        sys_msg = self.messages[0]
        to_compress = self.messages[1:-4]
        keep = self.messages[-4:]
        
        prompt = build_compression_prompt(to_compress)
        
        try:
            if display:
                ctx_manager = display.show_spinner("Compressing memory to prevent context bloat...")
                ctx_manager.__enter__()
            
            response = await llm_client.chat([{"role": "user", "content": prompt}])
            
            if display:
                ctx_manager.__exit__(None, None, None)

            # Extract summary from dict
            summary = ""
            if isinstance(response, str):
                summary = response
            elif isinstance(response, dict):
                if "message" in response:
                    summary = response["message"].get("content", "") or ""
                elif "choices" in response and response["choices"]:
                    summary = response["choices"][0].get("message", {}).get("content", "") or ""

            compressed_msg = {"role": "system", "content": "[CONTEXT SUMMARY]:\n" + summary}
            self.messages = [sys_msg, compressed_msg] + keep
            
            # Recalculate tokens
            self.token_count = sum(estimate_tokens(m["content"]) for m in self.messages)
        except Exception as e:
            if display:
                try: ctx_manager.__exit__(None, None, None) 
                except: pass
            print(f"Error compressing context: {e}")
