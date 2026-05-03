import subprocess
import time
from typing import Union
from .base import tool, ToolResult, RiskLevel
from .registry import registry

BLOCKLIST = [
    "format", "diskpart", "del /s /q c:\\", "rd /s /q c:\\",
    "remove-item -recurse c:\\", "rmdir /s", "rm -rf /", ":(){ :|:& };:"
]

def is_blocked(command: str) -> bool:
    cmd_lower = command.lower()
    for blocked in BLOCKLIST:
        if blocked in cmd_lower:
            return True
    return False

@tool("run_shell", "Executes a command in the terminal", RiskLevel.HIGH)
def run_shell(command: str, cwd: str = None, timeout_seconds: Union[int, str] = 30) -> ToolResult:
    # Asegurar tipos correctos
    try:
        timeout_seconds = int(timeout_seconds)
    except:
        timeout_seconds = 30

    if is_blocked(command):
        return ToolResult(success=False, output="", error=f"The command contains security-blocked patterns.")
    
    start_time = time.time()
    try:
        # En Windows usamos powershell
        proc = subprocess.run(
            ["powershell", "-Command", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace"
        )
        exec_time = int((time.time() - start_time) * 1000)
        output = proc.stdout
        if proc.stderr:
            output += "\n--- STDERR ---\n" + proc.stderr
            
        return ToolResult(
            success=proc.returncode == 0,
            output=output.strip(),
            metadata={"exit_code": proc.returncode, "command": command, "cwd": cwd, "execution_time_ms": exec_time}
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"The command exceeded the time limit of {timeout_seconds} segundos.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error executing command: {str(e)}")

registry.register(run_shell)
