import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent.loop import AgentLoop
from agent.context import ConversationContext
from agent.result import TurnResult
from tools.base import RiskLevel, ToolResult, tool
from tools.registry import ToolRegistry, ToolPermissionError


@pytest.fixture
def loop(tmp_path, monkeypatch):
    monkeypatch.setattr("config.get_app_dir", lambda: tmp_path)
    registry = ToolRegistry()
    @tool("write", "test tool", RiskLevel.HIGH)
    def write(path: str, enabled: bool = True, count: int = 1):
        return ToolResult(True, "written")
    registry.register(write)
    display = MagicMock()
    display.confirm_async = AsyncMock(return_value=True)
    config = SimpleNamespace(agent=SimpleNamespace(autonomy_level="high", risk_level="low"))
    client = SimpleNamespace(supports_tool_calling=True)
    return AgentLoop(config, client, registry, ConversationContext(10000), display)


def tool_call():
    return {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "call-1", "function": {"name": "write", "arguments": '{"path":"file"}'}}
    ]}}]}


@pytest.mark.asyncio
async def test_autonomy_cannot_override_risk(loop):
    loop._chat_and_stream = AsyncMock(return_value=tool_call())
    with pytest.raises(ToolPermissionError):
        await loop.run_turn("write file")


@pytest.mark.asyncio
async def test_finished_turn_includes_actual_evidence(loop):
    loop.config.agent.risk_level = "high"
    loop._chat_and_stream = AsyncMock(side_effect=[tool_call(), "Done"])
    result = await loop.run_turn("write file")
    assert isinstance(result, TurnResult) and result.status == "finished"
    assert result.tool_results[0]["output"] == "written"
    assert result.tool_results[0]["success"] is True


@pytest.mark.asyncio
async def test_denied_approval_is_cancelled(loop):
    loop.display.confirm_async.return_value = False
    loop._chat_and_stream = AsyncMock(return_value=tool_call())
    result = await loop.run_turn("write file")
    assert result.status == "cancelled"
    assert not result.tool_results


@pytest.mark.asyncio
async def test_iteration_limit_never_reports_success(loop):
    loop._chat_and_stream = AsyncMock(side_effect=asyncio.TimeoutError)
    result = await loop.run_turn("task")
    assert result.status == "limit_reached"
    assert loop._chat_and_stream.await_count == 20


def test_tool_schema_preserves_types_and_optional_arguments(loop):
    parameters = loop._get_native_tools()[0]["function"]["parameters"]
    assert parameters["properties"]["enabled"]["type"] == "boolean"
    assert parameters["properties"]["count"]["type"] == "integer"
    assert parameters["required"] == ["path"]
