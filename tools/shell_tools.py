import os
import signal
import threading
import time
from typing import Union, Dict
from typing import Union, Dict, Any
from winpty import PtyProcess
import subprocess
from .base import tool, ToolResult, RiskLevel
from .registry import registry

# Global dict to store background processes (PTYs)
_bg_processes: Dict[int, Dict[str, Any]] = {}
_display = None

def set_display(display):
    global _display
    _display = display

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
    """Lee PTY usando pyte como emulador VT100. Maneja cursor movements y renderiza QR correctamente."""
    try:
        import pyte
    except ImportError:
        # Fallback sin pyte
        _read_pty_raw(proc, pid, key)
        return

    COLS, ROWS = 120, 40
    screen = pyte.Screen(COLS, ROWS)
    stream_parser = pyte.ByteStream(screen)

    debug_file = "pty_debug.log"
    with open(debug_file, "a", encoding="utf-8") as f:
        f.write(f"\n--- Starting PTY Read (pyte) for PID {pid} ---\n")

    last_snapshot = ""

    try:
        while True:
            try:
                chunk = proc.read(4096)
            except EOFError:
                break

            if not chunk:
                if not proc.isalive():
                    break
                time.sleep(0.05)
                continue

            # Guardar raw en buffer del proceso (para get_process_output)
            if pid in _bg_processes:
                _bg_processes[pid][key] += chunk
            else:
                break

            # Alimentar pyte con los bytes del PTY
            if isinstance(chunk, str):
                stream_parser.feed(chunk.encode("utf-8", errors="replace"))
            else:
                stream_parser.feed(chunk)

            # Renderizar el snapshot actual de la pantalla virtual
            snapshot_lines = []
            for line_idx in range(ROWS):
                line = screen.buffer[line_idx]
                row_text = ""
                for col_idx in range(COLS):
                    char = line[col_idx]
                    row_text += char.data if char.data else " "
                snapshot_lines.append(row_text.rstrip())

            # Quitar líneas vacías del final
            while snapshot_lines and not snapshot_lines[-1].strip():
                snapshot_lines.pop()

            snapshot = "\n".join(snapshot_lines)

            # Solo actualizar la UI si la pantalla cambió
            if snapshot != last_snapshot and snapshot.strip():
                last_snapshot = snapshot
                if _display:
                    _display.set_console_screen(snapshot)

    except Exception as e:
        with open(debug_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- PTY ERROR: {str(e)} ---\n")


def _read_pty_raw(proc, pid, key):
    """Fallback sin pyte: lee crudo."""
    debug_file = "pty_debug.log"
    try:
        while True:
            try:
                chunk = proc.read(1024)
            except EOFError:
                break
            if not chunk:
                if not proc.isalive():
                    break
                time.sleep(0.1)
                continue
            with open(debug_file, "a", encoding="utf-8") as f:
                f.write(chunk)
            if pid in _bg_processes:
                _bg_processes[pid][key] += chunk
                if _display:
                    _display.update_console(chunk)
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

def strip_ansi(text: str) -> str:
    """Elimina códigos de escape ANSI para que la IA lea texto limpio."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def truncate_output(text: str, max_lines: int = 500) -> str:
    if not text:
        return ""
    
    # IMPORTANTE: Para la IA (ToolResult), siempre limpiamos el texto ANSI.
    # El Live Console seguirá recibiendo el texto crudo con colores.
    text = strip_ansi(text)
    
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    
    # Si es muy largo, mostramos el final
    return f"... [Truncated first {len(lines) - max_lines} lines for the agent] ...\n" + "\n".join(lines[-max_lines:])

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
    
    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["CI"] = "false"
    env["PYTHONUNBUFFERED"] = "1"

    if background:
        try:
            shell_path = r"C:\Windows\System32\cmd.exe"
            
            proc = PtyProcess.spawn(shell_path, cwd=cwd, env=env, dimensions=(40, 120))
            pid = proc.pid
            
            if cwd:
                proc.write(f"cd /d \"{cwd}\"\r\n")
            
            # Limpiar pantalla inicial
            proc.write("cls\r\n")
            
            # Ejecutar el comando
            proc.write(f"{command}\r\n")
            
            _bg_processes[pid] = {
                "process": proc,
                "command": command,
                "start_time": time.time(),
                "cwd": cwd or os.getcwd(),
                "stdout": "",
                "stderr": "",
                "is_pty": True
            }
            
            threading.Thread(target=_read_pty, args=(proc, pid, "stdout"), daemon=True).start()
            
            return ToolResult(
                success=True, 
                output=f"Interactive Terminal started (PID {pid}, 120x40). Capturing live output...",
                metadata={"pid": pid, "background": True, "pty": True}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error starting PTY: {str(e)}")

    # Ejecución normal para comandos rápidos
    start_time = time.time()
    try:
        proc = subprocess.run(
            ["cmd", "/c", command],
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
    output = truncate_output(stdout, max_lines=500)
    
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
