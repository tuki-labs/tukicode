import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from core.controller import TukiController


@pytest.mark.asyncio
async def test_new_operation_resets_stop_after_previous_operation_finished():
    controller = TukiController.__new__(TukiController)
    controller._processing = False
    controller.mode = "chat"
    controller.agent_loop = SimpleNamespace(_stop_requested=True)
    controller.display = MagicMock()
    controller.display.should_stop = True
    controller._run_chat = AsyncMock()
    await controller.process_input("resume")
    assert controller.agent_loop._stop_requested is False
    assert controller.display.should_stop is False
    assert controller._processing is False
    controller._run_chat.assert_awaited_once_with("resume")


@pytest.mark.asyncio
async def test_concurrent_request_cannot_clear_stop_or_start_another_operation():
    controller = TukiController.__new__(TukiController)
    controller._processing = False
    controller.mode = "chat"
    controller.agent_loop = SimpleNamespace(_stop_requested=False)
    controller.display = MagicMock()
    entered, release = asyncio.Event(), asyncio.Event()
    async def work(_):
        entered.set()
        await release.wait()
    controller._run_chat = AsyncMock(side_effect=work)
    task = asyncio.create_task(controller.process_input("first"))
    await entered.wait()
    controller.stop_agent()
    await controller.process_input("second")
    assert controller.agent_loop._stop_requested is True
    assert controller._run_chat.await_count == 1
    release.set()
    await task
    assert controller._processing is False
