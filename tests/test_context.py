import pytest
from tukicode.agent.context import ConversationContext

def test_context_add_message():
    ctx = ConversationContext(1000)
    ctx.add_message("user", "Hola")
    assert len(ctx.messages) == 1
    assert ctx.token_count > 0

def test_context_usage():
    ctx = ConversationContext(100)
    # Estimate len//4. "A" * 200 = 50 tokens
    ctx.add_message("user", "A" * 200)
    assert ctx.usage_percent == 0.5

def test_context_clear():
    ctx = ConversationContext(1000)
    ctx.add_message("system", "Sys")
    ctx.add_message("user", "Hola")
    ctx.clear()
    assert len(ctx.messages) == 1
    assert ctx.messages[0]["role"] == "system"
