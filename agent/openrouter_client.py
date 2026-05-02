import httpx
import json
from typing import Generator, List, Union

class OpenRouterError(Exception):
    pass

class OpenRouterClient:
    def __init__(self, model_name: str, temperature: float, max_tokens: int, stream: bool, api_key: str):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/tukicode",
            "X-Title": "TukiCode",
            "Content-Type": "application/json"
        }
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self._client = httpx.Client(headers=self.headers, timeout=60.0)

    @property
    def supports_tool_calling(self) -> bool:
        return True

    def chat(self, messages: List[dict], tools: List[dict] = None) -> dict:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        if self.supports_tool_calling and tools:
            payload["tools"] = tools

        try:
            response = self._client.post(f"{self.base_url}/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            if 'choices' not in data:
                raise OpenRouterError(f"Unexpected response: {data}")
                
            usage = data.get('usage', {})
            self._update_usage(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            return data
        except Exception as e:
            raise OpenRouterError(f"Error calling OpenRouter: {str(e)}")

    def chat_stream(self, messages: List[dict], tools: List[dict] = None) -> Generator[Union[str, dict], None, None]:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True
        }
        if self.supports_tool_calling and tools:
            payload["tools"] = tools

        try:
            with self._client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    
                    if line == "[DONE]":
                        break
                        
                    try:
                        chunk = json.loads(line)
                        if 'choices' in chunk and len(chunk['choices']) > 0:
                            delta = chunk['choices'][0].get('delta', {})
                            
                            if 'tool_calls' in delta and delta['tool_calls']:
                                yield chunk
                            elif 'content' in delta and delta['content'] is not None:
                                yield delta['content']
                        
                        if 'usage' in chunk:
                            usage = chunk['usage']
                            self._update_usage(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            raise OpenRouterError(f"Error in OpenRouter stream: {str(e)}")

    def _update_usage(self, prompt: int, completion: int):
        if prompt > 0 or completion > 0:
            self.prompt_tokens = prompt
            self.completion_tokens = completion
            self.total_tokens = prompt + completion

    def list_models(self) -> List[str]:
        return [self.model_name]

    def is_available(self) -> bool:
        return bool(self.api_key)
