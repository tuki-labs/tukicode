import os
import sys
import signal
import threading
import time
from abc import ABC, abstractmethod
from typing import Union, Dict, Any
import subprocess
from .base import tool, ToolResult, RiskLevel
from .registry import registry

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_bg_processes: Dict[int, Dict[str, Any]] = {}
_display = None

def set_display(display):
    global _display
    _display = display

# ---------------------------------------------------------------------------
# PTY Abstraction Layer
# ---------------------------------------------------------------------------

class BasePTYProcess(ABC):
    """Abstract interface for a PTY process, regardless of OS."""

    @property
    @abstractmethod
    def pid(self) -> int: ...

    @abstractmethod
    def write(self, data: str) -> None: ...

    @abstractmethod
    def read(self, n: int) -> bytes: ...

    @abstractmethod
    def isalive(self) -> bool: ...

    @abstractmethod
    def terminate(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class _WindowsPTY(BasePTYProcess):
    """Windows implementation backed by pywinpty."""

    def __init__(self, cmd: str, cwd: str | None, env: dict, dims: tuple[int, int]):
        from winpty import PtyProcess
        shell = r"C:\Windows\System32\cmd.exe"
        cols, rows = dims
        self._proc = PtyProcess.spawn(shell, cwd=cwd, env=env, dimensions=(rows, cols))

        # Navigate to cwd and clear the screen
        if cwd:
            self._proc.write(f'cd /d "{cwd}"\r\n')
        self._proc.write("cls\r\n")
        self._proc.write(f"{cmd}\r\n")

    @property
    def pid(self) -> int:
        return self._proc.pid

    def write(self, data: str) -> None:
        self._proc.write(data)

    def read(self, n: int) -> bytes:
        chunk = self._proc.read(n)
        if isinstance(chunk, str):
            return chunk.encode("utf-8", errors="replace")
        return chunk

    def isalive(self) -> bool:
        return self._proc.isalive()

    def terminate(self) -> None:
        self._proc.terminate()

    def close(self) -> None:
        self._proc.close()


class _UnixPTY(BasePTYProcess):
    """macOS / Linux implementation backed by ptyprocess."""

    def __init__(self, cmd: str, cwd: str | None, env: dict, dims: tuple[int, int]):
        from ptyprocess import PtyProcessUnicode
        shell = os.environ.get("SHELL", "/bin/bash")
        cols, rows = dims
        self._proc = PtyProcessUnicode.spawn(
            [shell, "-c", cmd],
            cwd=cwd,
            env=env,
            dimensions=(rows, cols),
        )

    @property
    def pid(self) -> int:
        return self._proc.pid

    def write(self, data: str) -> None:
        self._proc.write(data)

    def read(self, n: int) -> bytes:
        try:
            chunk = self._proc.read(n)
            if isinstance(chunk, str):
                return chunk.encode("utf-8", errors="replace")
            return chunk
        except EOFError:
            return b""

    def isalive(self) -> bool:
        return self._proc.isalive()

    def terminate(self) -> None:
        self._proc.terminate()

    def close(self) -> None:
        self._proc.close()


def _get_pty_process(cmd: str, cwd: str | None, env: dict, dims: tuple[int, int]) -> BasePTYProcess:
    """Factory: returns the correct PTY implementation for the current OS."""
    if sys.platform == "win32":
        return _WindowsPTY(cmd, cwd, env, dims)
    return _UnixPTY(cmd, cwd, env, dims)


def _shell_cmd(command: str) -> list[str]:
    """Returns the correct shell invocation for quick (non-PTY) commands."""
    if sys.platform == "win32":
        return ["cmd", "/c", command]
    return [os.environ.get("SHELL", "/bin/sh"), "-c", command]

# ---------------------------------------------------------------------------
# PTY reader thread (shared by both implementations)
# ---------------------------------------------------------------------------

def _read_pty(proc: BasePTYProcess, pid: int, key: str):
    """Reads PTY output through a pyte VT100 emulator. Works on all platforms."""
    try:
        import pyte
    except ImportError:
        _read_pty_raw(proc, pid, key)
        return

    COLS, ROWS = 120, 40
    screen = pyte.Screen(COLS, ROWS)
    stream_parser = pyte.ByteStream(screen)
    last_snapshot = ""

    try:
        while True:
            chunk = proc.read(4096)

            if not chunk:
                if not proc.isalive():
                    break
                time.sleep(0.05)
                continue

            if pid in _bg_processes:
                _bg_processes[pid][key] += chunk
            else:
                break

            stream_parser.feed(chunk)

            snapshot_lines = []
            for line_idx in range(ROWS):
                line = screen.buffer[line_idx]
                row_text = ""
                for col_idx in range(COLS):
                    char = line[col_idx]
                    row_text += char.data if char.data else " "
                snapshot_lines.append(row_text.rstrip())

            while snapshot_lines and not snapshot_lines[-1].strip():
                snapshot_lines.pop()

            snapshot = "\n".join(snapshot_lines)

            if snapshot != last_snapshot and snapshot.strip():
                last_snapshot = snapshot
                if _display:
                    _display.set_console_screen(snapshot)

    except Exception:
        pass


def _read_pty_raw(proc: BasePTYProcess, pid: int, key: str):
    """Fallback reader without pyte."""
    try:
        while True:
            chunk = proc.read(1024)
            if not chunk:
                if not proc.isalive():
                    break
                time.sleep(0.1)
                continue
            if pid in _bg_processes:
                _bg_processes[pid][key] += chunk
                if _display:
                    _display.update_console(chunk.decode("utf-8", errors="replace"))
            else:
                break
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

BLOCKLIST = [
    "format", "diskpart", "del /s /q c:\\", "rd /s /q c:\\",
    "remove-item -recurse c:\\", "rmdir /s", "rm -rf /", ":(){ :|:& };:"
]

def is_blocked(command: str) -> bool:
    cmd_lower = command.lower()
    return any(b in cmd_lower for b in BLOCKLIST)

def strip_control_sequences(text: str) -> str:
    """
    Elimina secuencias de control de cursor pero PRESERVA colores.
    Los colores son necesarios para renderizar QRs correctamente.
    """
    import re
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")

    # Posicionamiento de cursor: ESC[row;colH o ESC[row;colf
    text = re.sub(r'\x1b\[\d*;\d*[Hf]', '', text)
    # Movimiento de cursor: ESC[nA/B/C/D (arriba/abajo/der/izq)
    text = re.sub(r'\x1b\[\d*[ABCD]', '', text)
    # Borrar pantalla/línea: ESC[nJ / ESC[nK
    text = re.sub(r'\x1b\[\d*[JK]', '', text)
    # Mode set/reset: ESC[?25h, ESC[?1004h, etc
    text = re.sub(r'\x1b\[\?\d+[hl]', '', text)
    # Mouse tracking
    text = re.sub(r'\x1b\[[\d;]*[Mm]', '', text)
    # Keypad mode
    text = re.sub(r'\x1b[=>]', '', text)
    # Set title OSC: ESC]0;texto BEL
    text = re.sub(r'\x1b\]0;[^\x07]*\x07', '', text)
    text = re.sub(r'\x1b\]0;.*?\\', '', text)
    # Caracteres de control excepto \n \r \t
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f]', '', text)
    # Normalizar saltos de línea
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\r', '\n', text)

    return text


def strip_ansi(text: str) -> str:
    """Elimina TODOS los códigos ANSI incluyendo colores. Usar solo para output de texto plano."""
    import re
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def truncate_output(text: str, max_lines: int = 500) -> str:
    if not text:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    
    # Limpiar control sequences pero preservar colores
    text = strip_control_sequences(text)
    
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return f"... [Truncated first {len(lines) - max_lines} lines] ...\n" + "\n".join(lines[-max_lines:])

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool("run_shell", "Executes a command. Use background=True for long-running servers (expo, npm start).", RiskLevel.HIGH)
def run_shell(command: str, cwd: str = None, timeout_seconds: Union[int, str] = 30, background: bool = False) -> ToolResult:
    try:
        timeout_seconds = int(timeout_seconds)
    except Exception:
        timeout_seconds = 30

    if isinstance(background, str):
        background = background.lower() == "true"

    if is_blocked(command):
        return ToolResult(success=False, output="", error="The command contains security-blocked patterns.")

    env = os.environ.copy()
    env["FORCE_COLOR"] = "1"
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["CI"] = "false"
    env["PYTHONUNBUFFERED"] = "1"

    # ── Background (PTY) mode ────────────────────────────────────────────────
    if background:
        try:
            proc = _get_pty_process(command, cwd, env, dims=(120, 40))
            pid = proc.pid

            _bg_processes[pid] = {
                "process": proc,
                "command": command,
                "start_time": time.time(),
                "cwd": cwd or os.getcwd(),
                "stdout": b"",
                "stderr": b"",
                "is_pty": True,
            }

            threading.Thread(target=_read_pty, args=(proc, pid, "stdout"), daemon=True).start()

            return ToolResult(
                success=True,
                output=f"Interactive Terminal started (PID {pid}, 120x40). Capturing live output...",
                metadata={"pid": pid, "background": True, "pty": True},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Error starting PTY: {str(e)}")

    # ── Quick (subprocess) mode ──────────────────────────────────────────────
    start_time = time.time()
    try:
        proc = subprocess.run(
            _shell_cmd(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        exec_time = int((time.time() - start_time) * 1000)
        output = truncate_output(proc.stdout)
        if proc.stderr:
            output += "\n--- STDERR ---\n" + truncate_output(proc.stderr)
        return ToolResult(
            success=proc.returncode == 0,
            output=output.strip(),
            metadata={"exit_code": proc.returncode, "command": command, "cwd": cwd, "execution_time_ms": exec_time},
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error="Timeout. Use background=True for interactive servers.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error: {str(e)}")


@tool("get_process_output", "Reads output from a background process.", RiskLevel.MEDIUM)
def get_process_output(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except Exception:
        return ToolResult(success=False, output="", error="Invalid PID format.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"No process found with PID {pid}.")

    info = _bg_processes[pid]
    output = truncate_output(info["stdout"], max_lines=500)

    status = "Running"
    if info.get("is_pty"):
        if not info["process"].isalive():
            status = "Finished"
    else:
        if info["process"].poll() is not None:
            status = "Finished"

    return ToolResult(
        success=True,
        output=output,
        metadata={"pid": pid, "status": status, "command": info["command"]},
    )


@tool("list_processes", "Lists all active background processes.", RiskLevel.MEDIUM)
def list_processes() -> ToolResult:
    if not _bg_processes:
        return ToolResult(success=True, output="No active processes.")
    lines = ["Active Processes:"]
    for pid, info in _bg_processes.items():
        elapsed = int(time.time() - info["start_time"])
        lines.append(f"  PID {pid}: {info['command']} ({elapsed}s)")
    return ToolResult(success=True, output="\n".join(lines))


@tool("stop_process", "Stops a background process.", RiskLevel.HIGH)
def stop_process(pid: Union[int, str]) -> ToolResult:
    try:
        pid = int(pid)
    except Exception:
        return ToolResult(success=False, output="", error="Invalid PID.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"PID {pid} not found.")

    try:
        info = _bg_processes[pid]
        proc = info["process"]
        if info.get("is_pty"):
            proc.terminate()
            proc.close()
        else:
            proc.terminate()
        del _bg_processes[pid]
        return ToolResult(success=True, output=f"Process {pid} stopped.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error: {str(e)}")


@tool("send_process_input", "Sends text input to a running background process (e.g. to answer interactive prompts).", RiskLevel.MEDIUM)
def send_process_input(pid: Union[int, str], text: str) -> ToolResult:
    try:
        pid = int(pid)
    except Exception:
        return ToolResult(success=False, output="", error="Invalid PID.")

    if pid not in _bg_processes:
        return ToolResult(success=False, output="", error=f"PID {pid} not found.")

    try:
        info = _bg_processes[pid]
        proc = info["process"]
        if not info.get("is_pty"):
            return ToolResult(success=False, output="", error="Process is not a PTY — cannot send input.")
        if not text.endswith("\n"):
            text += "\r\n"
        proc.write(text)
        return ToolResult(success=True, output=f"Input sent to PID {pid}.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error sending input: {str(e)}")


registry.register(run_shell)
registry.register(get_process_output)
registry.register(list_processes)
registry.register(stop_process)
registry.register(send_process_input)