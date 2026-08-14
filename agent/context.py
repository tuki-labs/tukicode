import sqlite3
from typing import List, Dict
from typing import List, Dict, Any
from .prompts import build_compression_prompt

# ── tuki_native: Rust-accelerated token estimation ──────────────────────────
try:
    import tuki_native as _native
    _HAS_NATIVE = True
except ImportError:
    _native = None
    _HAS_NATIVE = False


def estimate_tokens(text: str) -> int:
    """Improved token estimation.

    Uses Rust-accelerated estimation when available, otherwise uses a
    heuristic that differentiates between code and natural language.
    """
    if not text:
        return 0

    if _HAS_NATIVE and hasattr(_native, 'estimate_tokens'):
        return _native.estimate_tokens(text)

    # ── Improved Python heuristic ──
    # Code has more symbols → more tokens per character
    # Spanish/accented text → ~3.2 chars per token
    # English text → ~4 chars per token
    total_chars = len(text)
    if total_chars == 0:
        return 0

    non_alnum = sum(1 for c in text if not c.isalnum() and not c.isspace())
    symbol_ratio = non_alnum / max(total_chars, 1)

    if symbol_ratio > 0.25:
        # Likely code: ~3 chars/token
        return int(total_chars / 3.0)
    elif symbol_ratio > 0.10:
        # Mixed content: ~3.5 chars/token
        return int(total_chars / 3.5)
    else:
        # Natural language: ~4 chars/token
        return int(total_chars / 4.0)


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
        
        spinner_ctx = None
        try:
            if display:
                spinner_ctx = display.show_spinner("Compressing memory to prevent context bloat...")
                spinner_ctx.__enter__()
            
            response = await llm_client.chat([{"role": "user", "content": prompt}])

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
            self.token_count = sum(estimate_tokens(m.get("content") or "") for m in self.messages)
        except Exception as e:
            print(f"Error compressing context: {e}")
        finally:
            if spinner_ctx:
                try:
                    spinner_ctx.__exit__(None, None, None)
                except:
                    pass
