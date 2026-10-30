import httpx
import pytest

from agent.openrouter_client import OpenRouterClient, OpenRouterError


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_access_error_preserves_reason_redacts_key_and_does_not_retry(stream):
    key = "sk-or-v1-fake-test-secret"
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {
            "message": f"This model is only available on agentic harnesses. Credential: {key}",
        }})
    client = OpenRouterClient("vendor/restricted:free", 0, 20, stream, key)
    await client._client.aclose()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(OpenRouterError) as failure:
            if stream:
                async for _ in client.chat_stream([{"role": "user", "content": "Hello"}]):
                    pass
            else:
                await client.chat([{"role": "user", "content": "Hello"}])
        assert "403" in str(failure.value)
        assert "only available on agentic harnesses" in str(failure.value)
        assert "Choose another model" in str(failure.value)
        assert key not in str(failure.value)
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_non_json_error_does_not_dump_html():
    client = OpenRouterClient("vendor/model", 0, 20, True, "fake-key")
    try:
        response = httpx.Response(403, text="<html>proxy error</html>")
        with pytest.raises(OpenRouterError, match="no JSON error details") as failure:
            client._handle_error_response(response)
        assert "<html>" not in str(failure.value)
    finally:
        await client.close()
