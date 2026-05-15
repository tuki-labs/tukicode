import json
import re
from dataclasses import dataclass
from typing import Union, List

@dataclass
class ToolCall:
    tool_name: str
    args: dict
    raw: str
    call_id: str = ""

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

def extract_thinking(text: str) -> tuple[str, str]:
    """
    Retorna (thinking, texto_limpio).
    Si no hay tags, retorna ("", text) sin modificar nada.
    """
    match = re.search(r"<thinking>([\s\S]*?)</thinking>", text)
    if match:
        thinking = match.group(1).strip()
        clean_text = text[:match.start()] + text[match.end():]
        return thinking, clean_text.strip()
    return "", text

def parse_response(response: Union[dict, str], use_native: bool = True) -> Union[List[ToolCall], FinalResponse]:
    # Estrategia A - Tool calling nativo
    if use_native and isinstance(response, dict):
        tool_calls = []
        
        # Ollama format
        if "message" in response and "tool_calls" in response["message"]:
            tool_calls = response["message"]["tool_calls"]
        # OpenRouter format
        elif "choices" in response and len(response["choices"]) > 0:
            msg = response["choices"][0].get("message", {})
            if "tool_calls" in msg:
                tool_calls = msg["tool_calls"]
                
        if tool_calls and len(tool_calls) > 0:
            parsed_tools = []
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                call_id = tc.get("id", "")
                
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                        
                if not isinstance(args, dict):
                    args = {}
                    
                if tool_name and isinstance(tool_name, str):
                    parsed_tools.append(ToolCall(tool_name=tool_name, args=args, raw=json.dumps(tc), call_id=call_id))
            
            if parsed_tools:
                return parsed_tools

    # Estrategia B - Fallback por texto
    # Si response es un dict pero falló la extraccion nativa, intentamos extraer el texto
    text = ""
    if isinstance(response, dict):
        if "message" in response:
            text = response["message"].get("content", "")
        elif "choices" in response and len(response["choices"]) > 0:
            text = response["choices"][0].get("message", {}).get("content", "")
    else:
        text = str(response)

    if not text:
        return FinalResponse(text="")

    # 1. Buscar bloques de código json
    json_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
    candidate_jsons = json_blocks if json_blocks else [text]

    parsed_tools = []
    for candidate in candidate_jsons:
        candidate = candidate.strip()
        candidate = _clean_json(candidate)
        
        # Buscar el inicio de un objeto JSON que contenga "tool"
        start_matches = list(re.finditer(r"\{\s*\"tool\"", candidate))
        
        for match in start_matches:
            start_idx = match.start()
            sub_text = candidate[start_idx:]
            
            try:
                decoder = json.JSONDecoder()
                parsed, end_idx = decoder.raw_decode(sub_text)
                
                if isinstance(parsed, dict) and "tool" in parsed and isinstance(parsed["tool"], str) and parsed["tool"]:
                    args = parsed.get("args", {})
                    if not isinstance(args, dict):
                        args = {}
                    parsed_tools.append(ToolCall(tool_name=parsed["tool"], args=args, raw=text, call_id=""))
            except (json.JSONDecodeError, ValueError):
                continue
                
    if parsed_tools:
        return parsed_tools
        
    return FinalResponse(text=text)
