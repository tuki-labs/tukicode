import subprocess
import time
import os
import signal
import threading
from typing import Union, Dict
from .base import tool, ToolResult, RiskLevel
from .registry import registry

# Global dict to store background processes
_bg_processes: Dict[int, Dict] = {}

def _read_stream(stream, pid, key):
    """Lee un stream y lo guarda en el buffer del proceso."""
    try:
        for line in iter(stream.readline, ''):
            if pid in _bg_processes:
                _bg_processes[pid][key] += line
            else:
                break
    except:
        pass
    finally:
        try:
            stream.close()
        except:
            pass

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

def truncate_output(text: str, max_lines: int = 100) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    
    # Send first 20 and last 50 lines
    first_part = lines[:20]
    last_part = lines[-50:]
    return "\n".join(first_part) + f"\n\n... [Truncated {len(lines) - 70} lines for performance] ...\n\n" + "\n".join(last_part)

@tool("run_shell", "Executes a command. Set background=True for servers (npm start, expo start).", RiskLevel.HIGH)
def run_shell(command: str, cwd: str = None, timeout_seconds: Union[int, str] = 30, background: bool = False) -> ToolResult:
    # Asegurar tipos correctos
    try:
        timeout_seconds = int(timeout_seconds)
    except:
        timeout_seconds = 30
    
    # Convertir background a bool si llega como string
    if isinstance(background, str):
        background = background.lower() == "true"

    if is_blocked(command):
        return ToolResult(success=False, output="", error=f"The command contains security-blocked patterns.")
    
    if background:
        try:
            # En Windows usamos Popen con creación de grupo de procesos
            proc = subprocess.Popen(
                ["powershell", "-Command", command],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1, # Line buffered
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            pid = proc.pid
            _bg_processes[pid] = {
                "process": proc,
                "command": command,
                "start_time": time.time(),
                "cwd": cwd or os.getcwd(),
                "stdout": "",
                "stderr": ""
            }
            
            # Lanzar hilos para capturar salida sin bloquear
            threading.Thread(target=_read_stream, args=(proc.stdout, pid, "stdout"), daemon=True).start()
            threading.Thread(target=_read_stream, args=(proc.stderr, pid, "stderr"), daemon=True).start()
            
            return ToolResult(
                success=True, 
                output=f"Process started in background (PID {pid}). Use get_process_output to see the logs/QR code.",
                metadata={"pid": pid, "background": True}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error starting background process: {str(e)}")

    start_time = time.time()
    try:
        # Ejecución normal (bloqueante)
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
        
        stdout = truncate_output(proc.stdout)
        stderr = truncate_output(proc.stderr)
        
        output = stdout
        if stderr:
            output += "\n--- STDERR ---\n" + stderr
            
        return ToolResult(
            success=proc.returncode == 0,
            output=output.strip(),
            metadata={"exit_code": proc.returncode, "command": command, "cwd": cwd, "execution_time_ms": exec_time}
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"Command timed out after {timeout_seconds}s. Consider using background=True for long tasks.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error executing command: {str(e)}")

@tool("get_process_output", "Reads the current stdout and stderr of a background process. Useful for seeing QR codes or logs.", RiskLevel.MEDIUM)
def get_process_output(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except:
        return ToolResult(success=False, output="", error="Invalid PID format.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"No background process found with PID {pid}.")
    
    info = _bg_processes[pid]
    stdout = info["stdout"]
    stderr = info["stderr"]
    
    # Truncar para no saturar si es mucho
    output = truncate_output(stdout, max_lines=200)
    if stderr:
        output += "\n--- STDERR ---\n" + truncate_output(stderr, max_lines=50)
        
    status = "Running" if info["process"].poll() is None else f"Finished (Code: {info['process'].poll()})"
    
    return ToolResult(
        success=True, 
        output=output, 
        metadata={"pid": pid, "status": status, "command": info["command"]}
    )

@tool("list_processes", "Lists all background processes started by TukiCode", RiskLevel.MEDIUM)
def list_processes() -> ToolResult:
    if not _bg_processes:
        return ToolResult(success=True, output="No background processes running.")
    
    lines = ["Active Background Processes:"]
    to_remove = []
    
    for pid, info in _bg_processes.items():
        proc = info["process"]
        poll = proc.poll()
        if poll is not None:
            # El proceso terminó
            status = f"Finished (Exit Code: {poll})"
            to_remove.append(pid)
        else:
            status = "Running"
        
        elapsed = int(time.time() - info["start_time"])
        lines.append(f"- PID {pid}: [{status}] {info['command']} (Elapsed: {elapsed}s)")
    
    # Limpiar terminados
    for pid in to_remove:
        del _bg_processes[pid]
        
    return ToolResult(success=True, output="\n".join(lines))

@tool("stop_process", "Stops a background process by its PID", RiskLevel.HIGH)
def stop_process(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except:
        return ToolResult(success=False, output="", error="Invalid PID format.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"No background process found with PID {pid}.")
    
    try:
        info = _bg_processes[pid]
        proc = info["process"]
        
        if os.name == 'nt':
            # En Windows, enviar CTRL_BREAK_EVENT al grupo de procesos
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
            
        # Esperar un poco a que muera
        time.sleep(0.5)
        if proc.poll() is None:
            proc.kill()
            
        del _bg_processes[pid]
        return ToolResult(success=True, output=f"Process {pid} stopped successfully.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error stopping process: {str(e)}")

registry.register(run_shell)
registry.register(get_process_output)
registry.register(list_processes)
registry.register(stop_process)
