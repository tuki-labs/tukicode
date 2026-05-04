import os
import signal
import threading
import time
from typing import Union, Dict
from winpty import PtyProcess
import subprocess
from .base import tool, ToolResult, RiskLevel
from .registry import registry

# Global dict to store background processes (PTYs)
_bg_processes: Dict[int, Dict] = {}

def _read_stream(stream, pid, key):
    """Lee el stream carácter por carácter para respuesta inmediata (usado en subprocess)."""
    try:
        while True:
            char = stream.read(1)
            if not char:
                break
            if pid in _bg_processes:
                _bg_processes[pid][key] += char
            else:
                break
    except:
        pass
    finally:
        try:
            stream.close()
        except:
            pass

def _read_pty(proc, pid, key):
    """Lee la salida de un PTY real y guarda un log de depuración."""
    debug_file = "pty_debug.log"
    with open(debug_file, "a", encoding="utf-8") as f:
        f.write(f"\n--- Starting PTY Read for PID {pid} ---\n")
    
    try:
        while True:
            # Leer bloque del PTY
            try:
                chunk = proc.read(1024)
            except EOFError:
                with open(debug_file, "a", encoding="utf-8") as f:
                    f.write(f"--- PTY PID {pid} EOF ---\n")
                break
                
            if not chunk:
                # Si el proceso sigue vivo, esperamos un poco
                if not proc.isalive():
                    break
                time.sleep(0.1)
                continue
            
            # Log de depuración crudo
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(chunk)
                
            if pid in _bg_processes:
                _bg_processes[pid][key] += chunk
            else:
                break
    except Exception as e:
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- PTY ERROR: {str(e)} ---\n")

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
    
    first_part = lines[:20]
    last_part = lines[-50:]
    return "\n".join(first_part) + f"\n\n... [Truncated {len(lines) - 70} lines for performance] ...\n\n" + "\n".join(last_part)

@tool("run_shell", "Executes a command. Use background=True for servers (expo, npm start) to get a real TTY.", RiskLevel.HIGH)
def run_shell(command: str, cwd: str = None, timeout_seconds: Union[int, str] = 30, background: bool = False) -> ToolResult:
    try:
        timeout_seconds = int(timeout_seconds)
    except:
        timeout_seconds = 30
    
    if isinstance(background, str):
        background = background.lower() == "true"

    if is_blocked(command):
        return ToolResult(success=False, output="", error=f"The command contains security-blocked patterns.")
    
    # Configuración de entorno interactivo
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["CI"] = "false"
    env["PYTHONUNBUFFERED"] = "1"

    if background:
        try:
            # Evitar doble envoltorio si el comando ya parece completo
            if "powershell" in command.lower() or "cmd.exe" in command.lower() or "&&" in command:
                # Si tiene && o ya es un shell, lo lanzamos vía cmd para mayor compatibilidad en Windows
                full_command = f"cmd.exe /c {command}" if "cmd.exe" not in command.lower() else command
            else:
                shell_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
                full_command = f"{shell_path} -NoProfile -ExecutionPolicy Bypass -Command \"{command}\""
            
            # Spawnear con dimensiones mayores para QRs grandes
            proc = PtyProcess.spawn(full_command, cwd=cwd, env=env, dimensions=(40, 120))
            pid = proc.pid
            
            _bg_processes[pid] = {
                "process": proc,
                "command": command,
                "start_time": time.time(),
                "cwd": cwd or os.getcwd(),
                "stdout": "",
                "stderr": "",
                "is_pty": True
            }
            
            # Hilo para leer la salida del PTY
            threading.Thread(target=_read_pty, args=(proc, pid, "stdout"), daemon=True).start()
            
            return ToolResult(
                success=True, 
                output=f"Process started in a REAL PTY (PID {pid}, 120x40). Expo QR codes and interactive elements will be captured.",
                metadata={"pid": pid, "background": True, "pty": True}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error starting PTY process: {str(e)}")

    # Ejecución normal para comandos rápidos
    start_time = time.time()
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
            env=env
        )
        exec_time = int((time.time() - start_time) * 1000)
        output = truncate_output(proc.stdout)
        if proc.stderr:
            output += "\n--- STDERR ---\n" + truncate_output(proc.stderr)
            
        return ToolResult(
            success=proc.returncode == 0,
            output=output.strip(),
            metadata={"exit_code": proc.returncode, "command": command, "cwd": cwd, "execution_time_ms": exec_time}
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"Timeout. Use background=True for interactive servers.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error: {str(e)}")

@tool("get_process_output", "Reads output from a background process. Supports real TTY output (QRs, colors).", RiskLevel.MEDIUM)
def get_process_output(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except:
        return ToolResult(success=False, output="", error="Invalid PID format.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"No process found with PID {pid}.")
    
    info = _bg_processes[pid]
    stdout = info["stdout"]
    
    # Truncado inteligente
    output = truncate_output(stdout, max_lines=300)
    
    status = "Running"
    if info.get("is_pty"):
        if not info["process"].isalive():
            status = f"Finished"
    else:
        if info["process"].poll() is not None:
            status = f"Finished"
    
    return ToolResult(
        success=True, 
        output=output, 
        metadata={"pid": pid, "status": status, "command": info["command"]}
    )

@tool("list_processes", "Lists all active background processes.", RiskLevel.MEDIUM)
def list_processes() -> ToolResult:
    if not _bg_processes:
        return ToolResult(success=True, output="No active processes.")
    
    lines = ["Active Processes:"]
    for pid, info in _bg_processes.items():
        elapsed = int(time.time() - info["start_time"])
        lines.append(f"- PID {pid}: {info['command']} ({elapsed}s)")
    return ToolResult(success=True, output="\n".join(lines))

@tool("stop_process", "Stops a background process.", RiskLevel.HIGH)
def stop_process(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except:
        return ToolResult(success=False, output="", error="Invalid PID.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"PID {pid} not found.")
    
    try:
        info = _bg_processes[pid]
        if info.get("is_pty"):
            # Terminar proceso PTY
            info["process"].terminate()
            info["process"].close()
        else:
            if os.name == 'nt':
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                info["process"].terminate()
            
        del _bg_processes[pid]
        return ToolResult(success=True, output=f"Process {pid} stopped.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error: {str(e)}")

registry.register(run_shell)
registry.register(get_process_output)
registry.register(list_processes)
registry.register(stop_process)
