import pytest
from unittest.mock import AsyncMock, MagicMock
from agent.executor import Executor
from agent.state import PlannerState

@pytest.mark.asyncio
async def test_execute_plan_success():
    # Mock Agent Loop
    agent_loop = MagicMock()
    agent_loop.run_turn = AsyncMock(return_value="Step completed successfully")
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
