import json
import re
from dataclasses import dataclass
from typing import Union

@dataclass
class ToolCall:
    tool_name: str
    args: dict
    raw: str

@dataclass
class FinalResponse:
    text: str

class ParseError(Exception):
    pass

def _clean_json(text: str) -> str:
    # Manejar comillas simples a dobles (básico) y trailing commas
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text

def parse_response(text: str) -> Union[ToolCall, FinalResponse]:
    # Buscar bloque ```json ... ```
    json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate_jsons = json_blocks if json_blocks else [text]
    
    for candidate in candidate_jsons:
        candidate = candidate.strip()
        # Intentar extraer algo que parezca un objeto JSON si hay texto adicional
        match = re.search(r"\{[\s\S]*\}", candidate)
        if match:
            candidate = match.group(0)
            
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                cleaned = _clean_json(candidate)
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict) and "tool" in parsed and isinstance(parsed["tool"], str):
                    args = parsed.get("args", {})
                    if not isinstance(args, dict):
                        args = {}
                    return ToolCall(tool_name=parsed["tool"], args=args, raw=text)
            except json.JSONDecodeError:
                continue
                
    return FinalResponse(text=text)
