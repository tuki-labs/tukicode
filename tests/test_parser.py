import pytest
from agent.parser import parse_response, ToolCall, FinalResponse

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
    assert isinstance(res, list) and len(res) == 1
    assert isinstance(res[0], ToolCall)
    assert res[0].tool_name == "read_file"
    assert res[0].args["path"] == "test.txt"

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
    assert isinstance(res, list) and len(res) == 1
    assert isinstance(res[0], ToolCall)
    assert res[0].tool_name == "run"
