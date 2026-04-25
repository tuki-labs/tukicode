import ollama
from typing import Generator, List

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

    def chat(self, messages: List[dict]) -> str:
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            self._update_usage(response.get("prompt_eval_count", 0), response.get("eval_count", 0))
            return response['message']['content']
        except Exception as e:
            raise OllamaNotAvailableError(f"Error llamando a Ollama: {str(e)}")

    def chat_stream(self, messages: List[dict]) -> Generator[str, None, None]:
        try:
            response_stream = ollama.chat(
                model=self.model_name,
                messages=messages,
                stream=True,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens
                }
            )
            for chunk in response_stream:
                if "eval_count" in chunk:
                    self._update_usage(chunk.get("prompt_eval_count", 0), chunk.get("eval_count", 0))
                if 'message' in chunk and 'content' in chunk['message']:
                    yield chunk['message']['content']
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
