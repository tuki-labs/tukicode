"""Validate a new configuration before accepting it; probes never execute tools."""
from copy import deepcopy
import json

import httpx

from agent.openrouter_client import OpenRouterClient, OpenRouterError


class SetupCheckError(Exception):
    def __init__(self, message, kind="model"):
        super().__init__(message)
        self.kind = kind


def validate_openrouter_setup(api_key, model_name, temperature=0.2):
    """Check credentials and a real native tool call with a synthetic prompt.

    Uses the selected model's normal pricing and quota. No repository, user
    message or local tool implementation is sent; the returned call is inspected
    as data and is never executed. There is no silent model/provider fallback.
    """
    if not api_key or any(c.isspace() or c == "\\" for c in api_key):
        raise SetupCheckError("Enter a valid OpenRouter API key, not a command or path.", "key")
    if not model_name or "/" not in model_name:
        raise SetupCheckError("Choose an OpenRouter model ID.")
    # Reuse safe error classification without creating an async client/event loop.
    errors = OpenRouterClient.__new__(OpenRouterClient)
    errors.api_key = api_key
    def check(response, phase):
        try:
            errors._handle_error_response(response)
        except OpenRouterError as error:
            kind = "key" if response.status_code == 401 or phase == "key" else "model"
            if response.status_code in (408, 429, 500, 502, 503, 529):
                kind = "temporary"
            raise SetupCheckError(str(error), kind) from None
    headers = {"Authorization": f"Bearer {api_key}",
               "HTTP-Referer": "https://github.com/tuki-labs/tukicode", "X-Title": "TukiCode"}
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, headers=headers) as client:
            key_response = client.get("https://openrouter.ai/api/v1/key")
            check(key_response, "key")
            key_data = key_response.json()["data"]
            if key_data.get("is_management_key") or key_data.get("is_provisioning_key"):
                raise SetupCheckError("This is a management key. Create a regular inference API key at https://openrouter.ai/settings/keys.", "key")
            response = client.post("https://openrouter.ai/api/v1/chat/completions", json={
                "model": model_name,
                "messages": [{"role": "user", "content":
                    "TukiCode setup test: call tuki_setup_probe with marker ok. Do not write any text."}],
                "temperature": temperature,
                "max_tokens": 256,
                "tools": [{"type": "function", "function": {
                    "name": "tuki_setup_probe", "description": "A synthetic setup check. No action is executed.",
                    "parameters": {"type": "object", "properties": {"marker": {"type": "string", "enum": ["ok"]}},
                                   "required": ["marker"], "additionalProperties": False},
                }}],
                "tool_choice": {"type": "function", "function": {"name": "tuki_setup_probe"}},
                "provider": {"require_parameters": True},
            })
            check(response, "model")
            calls = response.json()["choices"][0]["message"].get("tool_calls") or []
            for call in calls:
                function = call.get("function", {})
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if function.get("name") == "tuki_setup_probe" and arguments == {"marker": "ok"}:
                    return
            raise SetupCheckError("The model did not return a valid native tool call. Choose another model or retry the check.")
    except httpx.HTTPError:
        raise SetupCheckError("OpenRouter could not be reached. Check your connection and retry; configuration was not changed.", "temporary") from None
    except (KeyError, ValueError, TypeError, AttributeError, IndexError):
        raise SetupCheckError("OpenRouter returned an unexpected validation response. Retry; configuration was not changed.", "temporary") from None


def configured_copy(settings, provider, model_name, api_key):
    candidate = deepcopy(settings)
    candidate.model.provider = provider
    candidate.model.name = model_name
    candidate.setup_completed = True
    for cloud in ("openrouter", "gemini", "anthropic"):
        section = getattr(candidate, cloud)
        section.enabled = cloud == provider
        if cloud == provider:
            section.model = model_name
            section.api_key = api_key
            if model_name not in section.models:
                section.models.append(model_name)
    return candidate
