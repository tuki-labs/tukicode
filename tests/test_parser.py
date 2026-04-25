import pytest
from tukicode.agent.parser import parse_response, ToolCall, FinalResponse

def test_parse_tool_call_valid():
    text = """
    Pensando...
    ```json
    {
      "tool": "read_file",
      "args": {"path": "test.txt"}
    }
    ```
    """
    res = parse_response(text)
    assert isinstance(res, ToolCall)
    assert res.tool_name == "read_file"
    assert res.args["path"] == "test.txt"

def test_parse_final_response():
    text = "Hola, he terminado la tarea."
    res = parse_response(text)
    assert isinstance(res, FinalResponse)
    assert res.text == text

def test_parse_trailing_comma():
    text = """```json
    {
      "tool": "run",
      "args": {"cmd": "ls"},
    }
    ```"""
    res = parse_response(text)
    assert isinstance(res, ToolCall)
    assert res.tool_name == "run"
