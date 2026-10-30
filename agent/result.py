"""Turn results retain string compatibility for the chat interface."""


class TurnResult(str):
    def __new__(cls, text, status="finished", tool_results=()):
        result = super().__new__(cls, text)
        result.status = status
        result.tool_results = tuple(tool_results)
        return result
