import json
import pathlib
from typing import List, Dict

TOOL_SCHEMA_TEMPLATE = "{schema}"

import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).parent.parent

def build_system_prompt(config, tool_registry) -> str:
    prompt_path = get_base_dir() / "prompts" / "system_prompt.json"
    if not prompt_path.exists():
        return "Eres TukiCode, un agente local."
        
    with open(prompt_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    system_base = data.get("system", "")
    
    # Inyectar tools usando el registry
    schema = tool_registry.get_schema()
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    
    full_prompt = f"{system_base}\n"
    full_prompt += f"Tu nivel de riesgo actual es: {config.agent.risk_level}\n"
    full_prompt += f"Las herramientas disponibles son:\n{schema_str}\n"
    
    return full_prompt

def build_compression_prompt(messages_to_compress: List[Dict[str, str]]) -> str:
    prompt_path = get_base_dir() / "prompts" / "compression_prompt.txt"
    if not prompt_path.exists():
        template = "Resume esto:\n{history_text}"
    else:
        template = prompt_path.read_text(encoding="utf-8")
        
    history_text = ""
    for m in messages_to_compress:
        history_text += f"[{m['role'].upper()}]: {m['content']}\n\n"
        
    return template.replace("{history_text}", history_text)
