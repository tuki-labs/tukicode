import ollama
from typing import Generator, List, Union

class OllamaNotAvailableError(Exception):
    pass

class OllamaClient:
    def __init__(self, model_name: str, temperature: float, max_tokens: int, stream: bool):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

    @property
    def supports_tool_calling(self) -> bool:
        supported_models = {"llama3.1", "llama3.2", "qwen2.5", "mistral", "mixtral", "llama3-groq"}
        # Some models might have tags like llama3.1:8b, so we check if the base name is in supported
        base_name = self.model_name.split(":")[0]
        return base_name in supported_models

    def chat(self, messages: List[dict], tools: List[dict] = None) -> dict:
        try:
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }
            if self.supports_tool_calling and tools:
                kwargs["tools"] = tools
                
            response = ollama.chat(**kwargs)
            self._update_usage(response.get("prompt_eval_count", 0), response.get("eval_count", 0))
            return response
        except Exception as e:
            raise OllamaNotAvailableError(f"Error llamando a Ollama: {str(e)}")

    def chat_stream(self, messages: List[dict], tools: List[dict] = None) -> Generator[Union[str, dict], None, None]:
        # Native tool calling with streaming in Ollama might return the tool call chunks or not stream at all
        # We will yield chunks that can be strings or dicts depending on what we receive
        try:
            kwargs = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            }
            if self.supports_tool_calling and tools:
                kwargs["tools"] = tools
                
            response_stream = ollama.chat(**kwargs)
            for chunk in response_stream:
                if "eval_count" in chunk:
                    self._update_usage(chunk.get("prompt_eval_count", 0), chunk.get("eval_count", 0))
                
                # If chunk has tool_calls, yield the whole chunk so loop.py can handle native tool calling
                if 'message' in chunk:
                    msg = chunk['message']
                    if 'tool_calls' in msg and msg['tool_calls']:
                        yield chunk
                    elif 'content' in msg and msg['content']:
                        yield msg['content']
        except Exception as e:
            raise OllamaNotAvailableError(f"Error en stream de Ollama: {str(e)}")

    def _update_usage(self, prompt: int, completion: int):
        if prompt > 0 or completion > 0:
            self.prompt_tokens = prompt
            self.completion_tokens = completion
            self.total_tokens = prompt + completion

    def list_models(self) -> List[str]:
        try:
            resp = ollama.list()
            # Handle object-based response (newer versions)
            if hasattr(resp, 'models'):
                return [m.model for m in resp.models]
            # Handle dict-based response (older versions)
            if isinstance(resp, dict):
                return [m['name'] for m in resp.get('models', [])]
            return []
        except Exception:
            return []

    def is_available(self) -> bool:
        try:
            ollama.list()
            return True
        except Exception:
            return False
