import httpx
import json
import time
import asyncio
from typing import Generator, List, Union

class OpenRouterError(Exception):
    pass

# Modelos que NO soportan tool calling en OpenRouter (lo ajusto en el futuro)
MODELS_WITHOUT_TOOL_CALLING = {
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "mistralai/mistral-7b-instruct:free",
    "huggingfaceh4/zephyr-7b-beta:free",
}

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
        self._client = httpx.AsyncClient(headers=self.headers, timeout=60.0)

    @property
    def supports_tool_calling(self) -> bool:
        return self.model_name not in MODELS_WITHOUT_TOOL_CALLING

    def _build_payload(self, messages: List[dict], tools: List[dict] = None, stream: bool = False) -> dict:
        """Construye el payload evitando tools en modelos que no las soportan."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if stream:
            payload["stream"] = True
        if tools and self.supports_tool_calling:
            payload["tools"] = tools
        return payload

    async def chat(self, messages: List[dict], tools: List[dict] = None, response_format: dict = None) -> dict:
        payload = self._build_payload(messages, tools, stream=False)
        if response_format:
            payload["response_format"] = response_format
        try:
            response = await self._client.post(f"{self.base_url}/chat/completions", json=payload)
            
            # Si el modelo no soporta response_format, OpenRouter devuelve 400.
            # Reintentamos sin response_format.
            if response.status_code == 400 and response_format:
                payload.pop("response_format")
                response = await self._client.post(f"{self.base_url}/chat/completions", json=payload)
                
            response.raise_for_status()
            data = response.json()
            if 'choices' not in data:
                raise OpenRouterError(f"Unexpected response: {data}")
            usage = data.get('usage', {})
            self._update_usage(usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            return data
        except Exception as e:
            raise OpenRouterError(f"Error calling OpenRouter: {str(e)}")

    async def chat_stream(self, messages: List[dict], tools: List[dict] = None) -> Generator[Union[str, dict], None, None]:
        payload = self._build_payload(messages, tools, stream=True)

        MAX_RETRIES = 3
        RETRY_DELAY = 2

        for attempt in range(MAX_RETRIES):
            try:
                async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            line = line[6:]
                        if line == "[DONE]":
                            return
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
                                self._update_usage(
                                    usage.get('prompt_tokens', 0),
                                    usage.get('completion_tokens', 0)
                                )
                        except json.JSONDecodeError:
                            continue
                return  # éxito

            except httpx.RemoteProtocolError:
                # WinError 10054 — servidor cerró la conexión
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise OpenRouterError(f"Connection reset by server after {MAX_RETRIES} attempts.")

            except httpx.ConnectTimeout:
                # WinError 10060 — timeout de conexión
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise OpenRouterError(f"Connection timeout after {MAX_RETRIES} attempts.")

            except httpx.ReadTimeout:
                # Timeout leyendo el stream
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise OpenRouterError(f"Read timeout after {MAX_RETRIES} attempts.")

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

    async def close(self):
        await self._client.aclose()