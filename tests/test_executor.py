import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.executor import Executor
from agent.state import PlannerState
from agent.result import TurnResult

@pytest.mark.asyncio
async def test_execute_plan_success():
    # Mock Agent Loop
    agent_loop = MagicMock()
    agent_loop.run_turn = AsyncMock(return_value=TurnResult(
        "Step completed successfully", tool_results=[{"success": True, "tool": "read_file", "output": "expected contents"}]))
    agent_loop.llm_client.chat = AsyncMock(return_value={"message": {"content": '{"completed":true,"evidence":"read_file confirmed contents"}'}})
    agent_loop._stop_requested = False
    agent_loop.llm_client.model_name = "test-model"
    
    # Mock State
    state = PlannerState()
    state.state = {
        "status": "idle",
        "plan": [
            {"id": 1, "description": "Step 1", "status": "pending"},
            {"id": 2, "description": "Step 2", "status": "pending"}
        ],
        "current_step": 0
    }
    state.save = MagicMock()
    
    # Mock Display
    display = MagicMock()
    
    executor = Executor(agent_loop, state, display)
    await executor.execute_plan()
    
    assert state.state["status"] == "completed"
    assert state.state["plan"][0]["status"] == "completed"
    assert state.state["plan"][1]["status"] == "completed"
    assert agent_loop.run_turn.call_count == 2

@pytest.mark.asyncio
async def test_execute_plan_stop_requested():
    agent_loop = MagicMock()
    agent_loop.run_turn = AsyncMock(return_value="Step completed")
    agent_loop._stop_requested = True # Simulate user stop
    agent_loop.llm_client.model_name = "test-model"
    
    state = PlannerState()
    state.state = {
        "status": "idle",
        "plan": [{"id": 1, "description": "Step 1", "status": "pending"}],
        "current_step": 0
    }
    state.save = MagicMock()
    
    display = MagicMock()
    executor = Executor(agent_loop, state, display)
    await executor.execute_plan()
    
    # Status should still be building or pending if it stopped early
    # But current implementation marks it as building at start
    assert state.state["plan"][0]["status"] == "pending"
    assert state.state["status"] == "paused"


def make_executor(tmp_path, result, verdict='{"completed":true,"evidence":"verified"}'):
    loop = MagicMock()
    loop._stop_requested = False
    loop.run_turn = AsyncMock(return_value=result)
    loop.llm_client.model_name = "test-model"
    loop.llm_client.chat = AsyncMock(return_value={"message": {"content": verdict}})
    state = PlannerState(str(tmp_path))
    state.set_plan([{"description": "Create file"}, {"description": "Use file"}])
    return Executor(loop, state, MagicMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    "I could not complete this task.",
    TurnResult("Done"),
    TurnResult("Done", tool_results=[{"success": False, "error": "write failed"}]),
    TurnResult("Limit", "limit_reached"),
    TurnResult("Timeout", "timed_out"),
])
async def test_unverified_results_block_dependencies(tmp_path, result):
    executor = make_executor(tmp_path, result)
    await executor.execute_plan()
    assert executor.state.state["status"] == "blocked"
    assert executor.state.state["plan"][0]["status"] == "failed"
    assert executor.state.state["plan"][1]["status"] == "pending"
    assert executor.agent_loop.run_turn.await_count == 1
    executor.agent_loop.llm_client.chat.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", [
    '{"completed":false,"evidence":"missing file"}',
    '{"completed":"true","evidence":"claim"}',
    '{"completed":true,"evidence":""}',
    'Not JSON',
])
async def test_invalid_or_negative_verification_blocks(tmp_path, verdict):
    result = TurnResult("Done", tool_results=[{"success": True, "tool": "read_file", "output": "contents"}])
    executor = make_executor(tmp_path, result, verdict)
    await executor.execute_plan()
    assert executor.state.state["status"] == "blocked"
    assert executor.agent_loop.run_turn.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["stopped", "cancelled"])
async def test_interruption_leaves_step_pending(tmp_path, status):
    executor = make_executor(tmp_path, TurnResult("Interrupted", status))
    await executor.execute_plan()
    assert executor.state.state["status"] == "paused"
    assert executor.state.state["plan"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_verifier_failure_does_not_replay_side_effects(tmp_path):
    result = TurnResult("Done", tool_results=[{"success": True, "tool": "write_file"}])
    executor = make_executor(tmp_path, result)
    executor.agent_loop.llm_client.chat.side_effect = RuntimeError("503 unavailable")
    await executor.execute_plan()
    assert executor.state.state["status"] == "blocked"
    assert executor.agent_loop.run_turn.await_count == 1


@pytest.mark.asyncio
async def test_transport_error_after_tools_does_not_retry(tmp_path):
    executor = make_executor(tmp_path, None)
    executor.agent_loop.turn_tools_started = True
    executor.agent_loop.run_turn.side_effect = RuntimeError("503 server error")
    await executor.execute_plan()
    assert executor.state.state["status"] == "blocked"
    assert executor.agent_loop.run_turn.await_count == 1
