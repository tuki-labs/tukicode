import httpx
import json
import time
import asyncio
import re
from typing import Generator, List, Union

class OpenRouterError(Exception):
    pass

class RateLimitError(OpenRouterError):
    """Raised when OpenRouter returns 429 (rate limited) or 529 (overloaded)."""
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after

class ModelOverloadedError(OpenRouterError):
    """Raised when the upstream model provider is overloaded (529)."""
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
            "HTTP-Referer": "https://github.com/tuki-labs/tukicode",
            "X-Title": "TukiCode",
            "Content-Type": "application/json"
        }
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0

        # ── Resilience settings ──────────────────────────────────────
        self._client = httpx.AsyncClient(headers=self.headers, timeout=90.0)
        self._semaphore = asyncio.Semaphore(2)   # max 2 concurrent requests
        self._last_request_time = 0.0
        self._min_request_interval = 0.5         # 500ms minimum between requests
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

    @property
    def supports_tool_calling(self) -> bool:
        # Setup filters against the live catalog. Provider routing enforces
        # capability at request time rather than relying on a stale blacklist.
        return True

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
            payload["provider"] = {"require_parameters": True}
        return payload

    async def _throttle(self):
        """Ensures minimum interval between requests to avoid rate limiting."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _get_retry_delay(self, attempt: int, retry_after: float = 0) -> float:
        """Exponential backoff with jitter. Respects Retry-After header."""
        if retry_after > 0:
            return min(retry_after, 60.0)
        # Exponential: 2s, 4s, 8s, 16s, 32s (capped)
        import random
        base = min(2 ** (attempt + 1), 32)
        jitter = random.uniform(0, base * 0.3)
        return base + jitter

    def _handle_error_response(self, response: httpx.Response):
        """Classifies HTTP errors and raises appropriate exceptions."""
        status = response.status_code
        try:
            error = response.json().get("error", {})
            detail = error.get("message", "No error details provided.") if isinstance(error, dict) else str(error)
        except (ValueError, AttributeError):
            detail = "The service returned no JSON error details."
        detail = str(detail)
        if self.api_key:
            detail = detail.replace(self.api_key, "[REDACTED]")
        detail = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", detail)
        detail = "".join(c for c in detail if c.isprintable() or c in "\n\t")[:1000]

        # Rate limited
        if status == 429:
            retry_after = float(response.headers.get("Retry-After", "5"))
            raise RateLimitError(
                f"Rate limited by OpenRouter (429): {detail}. Retry after {retry_after}s.",
                retry_after=retry_after
            )

        # Model overloaded (OpenRouter specific)
        if status == 529:
            raise ModelOverloadedError(
                "Model provider is temporarily overloaded (529). Will retry."
            )

        # Server errors (500-503)
        if 500 <= status <= 503:
            raise OpenRouterError(f"OpenRouter server error ({status}). Will retry.")

        # Auth errors (don't retry)
        if status == 401:
            raise OpenRouterError(f"Authentication failed (401): {detail}. Check your OpenRouter API key.")
        if status == 402:
            raise OpenRouterError(f"Credits/budget error (402): {detail}. Check your OpenRouter balance and key limits.")
        if status == 403:
            raise OpenRouterError(
                f"Access denied (403): {detail}. Choose another model or review your OpenRouter access settings."
            )

        # Other client errors
        if not response.is_success:
            raise OpenRouterError(f"OpenRouter request rejected ({status}): {detail}")

    async def chat(self, messages: List[dict], tools: List[dict] = None, response_format: dict = None) -> dict:
        MAX_RETRIES = 5

        for attempt in range(MAX_RETRIES):
            async with self._semaphore:
                await self._throttle()

                payload = self._build_payload(messages, tools, stream=False)
                if response_format:
                    payload["response_format"] = response_format

                try:
                    response = await self._client.post(
                        f"{self.base_url}/chat/completions", json=payload
                    )

                    # Si el modelo no soporta response_format, OpenRouter devuelve 400.
                    if response.status_code == 400 and response_format:
                        payload.pop("response_format", None)
                        response = await self._client.post(
                            f"{self.base_url}/chat/completions", json=payload
                        )

                    self._handle_error_response(response)

                    data = response.json()
                    if 'choices' not in data:
                        raise OpenRouterError(f"Unexpected response: {data}")

                    usage = data.get('usage', {})
                    self._update_usage(
                        usage.get('prompt_tokens', 0),
                        usage.get('completion_tokens', 0)
                    )
                    self._consecutive_errors = 0
                    return data

                except (RateLimitError, ModelOverloadedError) as e:
                    self._consecutive_errors += 1
                    retry_after = getattr(e, 'retry_after', 0)
                    delay = self._get_retry_delay(attempt, retry_after)

                    if attempt < MAX_RETRIES - 1:
                        # Increase throttle interval on rate limits
                        self._min_request_interval = min(
                            self._min_request_interval * 1.5, 5.0
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Rate limited after {MAX_RETRIES} retries: {str(e)}"
                    )

                except OpenRouterError:
                    raise  # Auth errors, etc. — don't retry

                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
                    self._consecutive_errors += 1
                    if attempt < MAX_RETRIES - 1:
                        delay = self._get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Connection failed after {MAX_RETRIES} attempts: {str(e)}"
                    )

                except Exception as e:
                    raise OpenRouterError(f"Error calling OpenRouter: {str(e)}")

        raise OpenRouterError(f"Request failed after {MAX_RETRIES} attempts.")

    async def chat_stream(self, messages: List[dict], tools: List[dict] = None):
        MAX_RETRIES = 5

        for attempt in range(MAX_RETRIES):
            async with self._semaphore:
                await self._throttle()

                payload = self._build_payload(messages, tools, stream=True)

                try:
                    async with self._client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        json=payload
                    ) as response:
                        # Check for error status before reading stream
                        if response.status_code != 200:
                            # Buffer the error before classifying it; raise_for_status
                            # alone loses the provider's actual reason for a rejection.
                            await response.aread()
                            self._handle_error_response(response)

                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            if line.startswith("data: "):
                                line = line[6:]
                            if line == "[DONE]":
                                self._consecutive_errors = 0
                                return
                            try:
                                chunk = json.loads(line)

                                # OpenRouter can send error objects mid-stream
                                if "error" in chunk:
                                    error_msg = chunk["error"].get("message", str(chunk["error"]))
                                    if "rate" in error_msg.lower() or chunk["error"].get("code") == 429:
                                        raise RateLimitError(f"Mid-stream rate limit: {error_msg}")
                                    raise OpenRouterError(f"Stream error: {error_msg}")

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

                    self._consecutive_errors = 0
                    return  # Stream completed successfully

                except (RateLimitError, ModelOverloadedError) as e:
                    self._consecutive_errors += 1
                    retry_after = getattr(e, 'retry_after', 0)
                    delay = self._get_retry_delay(attempt, retry_after)

                    if attempt < MAX_RETRIES - 1:
                        self._min_request_interval = min(
                            self._min_request_interval * 1.5, 5.0
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Rate limited after {MAX_RETRIES} retries: {str(e)}"
                    )

                except httpx.RemoteProtocolError:
                    self._consecutive_errors += 1
                    if attempt < MAX_RETRIES - 1:
                        delay = self._get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Connection reset by server after {MAX_RETRIES} attempts."
                    )

                except httpx.ConnectTimeout:
                    self._consecutive_errors += 1
                    if attempt < MAX_RETRIES - 1:
                        delay = self._get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Connection timeout after {MAX_RETRIES} attempts."
                    )

                except httpx.ReadTimeout:
                    self._consecutive_errors += 1
                    if attempt < MAX_RETRIES - 1:
                        delay = self._get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                        continue
                    raise OpenRouterError(
                        f"Read timeout after {MAX_RETRIES} attempts."
                    )

                except OpenRouterError:
                    raise

                except Exception as e:
                    raise OpenRouterError(f"Error in OpenRouter stream: {str(e)}")

        raise OpenRouterError(f"Stream failed after {MAX_RETRIES} attempts.")

    @property
    def is_rate_limited(self) -> bool:
        """Returns True if we've been hitting rate limits frequently."""
        return self._consecutive_errors >= 3

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
