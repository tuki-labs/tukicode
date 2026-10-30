from agent.anthropic_client import AnthropicClient


def test_tool_observations_preserve_order_and_errors():
    client = AnthropicClient("mock", 0, 100, False, "")
    _, messages = client._convert_messages([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "tool request"},
        {"role": "tool", "tool_call_id": "a", "content": "file contents"},
        {"role": "tool", "tool_call_id": "b", "content": "ERROR: missing file"},
        {"role": "assistant", "content": "final"},
    ])
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2]["content"] == "[TOOL RESULT a]\nfile contents\n\n[TOOL RESULT b]\nERROR: missing file"
