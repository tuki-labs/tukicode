import os
import re
import pathlib
import subprocess
from datetime import datetime
from .base import tool, ToolResult, RiskLevel
from .registry import registry

@tool("search_code", "Searches for a pattern in files", RiskLevel.MEDIUM)
def search_code(query: str, path: str, file_extensions: list = None, case_sensitive: bool = False, context_lines: int = 2) -> ToolResult:
    p = pathlib.Path(path)
    if not p.exists():
        return ToolResult(success=False, output="", error=f"Ruta '{path}' no existe.")
    
    results = []
    
    # Intentar con ripgrep (rg) primero
    try:
        rg_cmd = ["rg", "-n"]
        if not case_sensitive:
            rg_cmd.append("-i")
        if context_lines > 0:
            rg_cmd.extend(["-C", str(context_lines)])
        if file_extensions:
            for ext in file_extensions:
                rg_cmd.extend(["-g", f"*.{ext.lstrip('.')}"])
        rg_cmd.extend([query, str(p)])
        
        proc = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=10, encoding="utf-8")
        if proc.returncode in [0, 1]:  # 0: matches found, 1: no matches
            out = proc.stdout.strip()
            if out:
                lines = out.splitlines()
                return ToolResult(success=True, output="\n".join(lines[:50]))
            return ToolResult(success=True, output="No se encontraron coincidencias.")
    except Exception:
        pass # Fallback a Python
        
    # Fallback Python puro
    regex_flags = 0 if case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(query, regex_flags)
    except re.error as e:
        return ToolResult(success=False, output="", error=f"Invalid regex: {str(e)}")
        
    for file_path in p.rglob("*"):
        if not file_path.is_file():
            continue
        if file_extensions:
            ext = file_path.suffix.lstrip(".")
            if ext not in file_extensions and file_path.suffix not in file_extensions:
                continue
        
        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines):
                if pattern.search(line):
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    for j in range(start, end):
                        results.append(f"{file_path}:{j+1}:{lines[j]}")
                    if len(results) >= 50:
                        break
        except Exception:
            continue
        if len(results) >= 50:
            break
            
    if not results:
        return ToolResult(success=True, output="No se encontraron coincidencias.")
    return ToolResult(success=True, output="\n".join(results[:50]))

@tool("find_files", "Searches for files by glob pattern", RiskLevel.MEDIUM)
def find_files(pattern: str, root: str, max_depth: int = 5, ignore: list = None) -> ToolResult:
    p = pathlib.Path(root)
    if not p.exists():
        return ToolResult(success=False, output="", error="Root does not exist.")
    
    ignore_set = set(ignore) if ignore else set()
    results = []
    
    for file_path in p.rglob(pattern):
        # Check ignores and depth
        rel_parts = file_path.relative_to(p).parts
        if len(rel_parts) > max_depth:
            continue
        if any(part in ignore_set for part in rel_parts):
            continue
        results.append(str(file_path.absolute()))
        if len(results) >= 100:
            break
            
    return ToolResult(success=True, output="\n".join(results) if results else "No se encontraron archivos.")

@tool("list_dir", "Lista el contenido de un directorio", RiskLevel.MEDIUM)
def list_dir(path: str, recursive: bool = False, show_hidden: bool = False) -> ToolResult:
    p = pathlib.Path(path)
    if not p.exists() or not p.is_dir():
        return ToolResult(success=False, output="", error="Directorio no existe.")
    
    lines = []
    items = p.rglob("*") if recursive else p.iterdir()
    for item in items:
        if not show_hidden and item.name.startswith("."):
            continue
        try:
            stat = item.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            tipo = "DIR " if item.is_dir() else "FILE"
            size = stat.st_size if item.is_file() else "-"
            lines.append(f"{tipo}\t{size}\t{mtime}\t{item.relative_to(p) if recursive else item.name}")
            if len(lines) > 200:
                lines.append("... (truncado)")
                break
        except Exception:
            continue
    
    return ToolResult(success=True, output="\n".join(lines) if lines else "Empty directory.")

registry.register(search_code)
registry.register(find_files)
registry.register(list_dir)
