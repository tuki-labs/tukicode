import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from agent.planner import Planner

@pytest.mark.asyncio
async def test_generate_plan_success():
    # Mock LLM Client
    llm_client = AsyncMock()
    llm_client.chat.return_value = {
        "choices": [{
            "message": {
                "content": "<thinking>I need to create a simple plan.</thinking>\n```json\n[{\"description\": \"Step 1\"}, {\"description\": \"Step 2\"}]\n```"
            }
        }]
    }
    
    # Mock Display
    display = MagicMock()
    
    planner = Planner(llm_client, display)
    plan = await planner.generate_plan("Test request", "Test CWD")
    
    assert len(plan) == 2
    assert plan[0]["description"] == "Step 1"
    assert plan[1]["description"] == "Step 2"
    display.show_thinking.assert_called_once()

@pytest.mark.asyncio
async def test_generate_plan_retry_on_invalid_json():
    # Mock LLM Client to fail once then succeed
    llm_client = AsyncMock()
    llm_client.chat.side_effect = [
        {
            "choices": [{
                "message": {
                    "content": "Invalid JSON here"
                }
            }]
        },
        {
            "choices": [{
                "message": {
                    "content": "```json\n[{\"description\": \"Fixed Step\"}]\n```"
                }
            }]
        }
    ]
    
    display = MagicMock()
    planner = Planner(llm_client, display)
    
    plan = await planner.generate_plan("Test request", "Test CWD")
    
    assert len(plan) == 1
    assert plan[0]["description"] == "Fixed Step"
    assert llm_client.chat.call_count == 2
