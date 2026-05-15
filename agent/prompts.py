import json
import pathlib
from typing import List, Dict
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).parent.parent

try:
    import tuki_native
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False

def build_system_prompt(config, tool_registry) -> str:
    prompt_path = get_base_dir() / "prompts" / "system_prompt.json"
    if not prompt_path.exists():
        return "Eres TukiCode, un agente local."
        
    with open(prompt_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    template = data.get("system", "")
    
    # Obtener el esquema de herramientas
    schema = tool_registry.get_schema()
    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    
    # Detección de entorno
    import platform
    home = pathlib.Path.home()
    
    os_name = platform.system()
    if os_name == "Windows":
        shell_name = "CMD (Command Prompt) / PowerShell"
        os_rules = """WINDOWS RULES — CRITICAL:
1. ALWAYS use Windows path format: C:\\Users\\name\\file
2. To chain commands use `&&`.
3. NEVER assume the OS is Linux or macOS.
4. For environment variables use `%VARIABLE%` or `$env:VARIABLE` depending on shell."""
    elif os_name == "Darwin":
        shell_name = "zsh / bash"
        os_rules = """MACOS RULES — CRITICAL:
1. ALWAYS use Unix path format: /Users/name/file
2. You can use standard Unix utilities (ls, cat, grep).
3. NEVER assume the OS is Windows."""
    else:
        shell_name = "bash / sh"
        os_rules = """LINUX RULES — CRITICAL:
1. ALWAYS use Unix path format: /home/name/file
2. You can use standard Unix utilities (ls, cat, grep).
3. NEVER assume the OS is Windows."""

    # Pre-fetch project tree
    project_tree = "Project tree not available."
    if HAS_NATIVE:
        try:
            tree_output = tuki_native.get_project_tree(str(pathlib.Path.cwd()), 3, [".git", "node_modules", "venv", "target", "build", "__pycache__"])
            if tree_output:
                lines = tree_output.splitlines()
                if len(lines) > 150:
                    tree_output = "\n".join(lines[:150]) + "\n... (Tree truncated for context limit)"
                project_tree = tree_output
        except Exception:
            pass

    # Rellenar el template
    full_prompt = template.format(
        os_name=os_name,
        shell_name=shell_name,
        os_rules=os_rules,
        cwd=pathlib.Path.cwd(),
        home=home,
        autonomy_level=config.agent.autonomy_level,
        project_tree=project_tree,
        tools=schema_str
    )
    
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
