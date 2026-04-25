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
    # 1. Buscar bloques de código json
    json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate_jsons = json_blocks if json_blocks else [text]

    for candidate in candidate_jsons:
        candidate = candidate.strip()
        
        # Buscar el inicio de un objeto JSON que contenga "tool"
        # Buscamos la posición de {"tool" o { "tool"
        start_matches = list(re.finditer(r"\{\s*\"tool\"", candidate))
        
        for match in start_matches:
            start_idx = match.start()
            sub_text = candidate[start_idx:]
            
            try:
                # raw_decode parsea el primer objeto JSON válido y devuelve el objeto y dónde terminó
                decoder = json.JSONDecoder()
                parsed, end_idx = decoder.raw_decode(sub_text)
                
                if isinstance(parsed, dict) and "tool" in parsed and isinstance(parsed["tool"], str):
                    args = parsed.get("args", {})
                    if not isinstance(args, dict):
                        args = {}
                    return ToolCall(tool_name=parsed["tool"], args=args, raw=text)
            except (json.JSONDecodeError, ValueError):
                continue
                
    return FinalResponse(text=text)
