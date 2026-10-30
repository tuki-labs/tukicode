import os
import difflib
import pathlib
from .base import tool, ToolResult, RiskLevel
from .registry import registry

# ── tuki_native: Rust-accelerated utilities ─────────────────────────────────
try:
    import tuki_native as _native
    _NATIVE = True
except ImportError:
    _native = None
    _NATIVE = False

# ── Shared ignore list (from Rust if available, otherwise hardcoded) ────────
if _NATIVE and hasattr(_native, 'default_ignore_list'):
    _DEFAULT_IGNORE = set(_native.default_ignore_list())
else:
    _DEFAULT_IGNORE = {
        "node_modules", ".git", "__pycache__", "venv", ".venv",
        "dist", "build", "target", ".expo", ".next", "out",
        "android", "ios", "Pods", ".pytest_cache",
        "tukicode.egg-info", ".tox", ".mypy_cache",
    }

@tool("read_file", "Reads the content of a file. For large files, only reads first 1000 lines.", RiskLevel.MEDIUM)
def read_file(path: str, max_lines: int = 1000, start_line: int = 0) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return ToolResult(success=False, output="", error=f"The file '{path}' does not exist or is not a valid file.")
    
    try:
        max_lines = int(max_lines)
    except:
        max_lines = 1000
    try:
        start_line = int(start_line)
    except:
        start_line = 0

    # Strategy 1: Rust native (with line numbers and binary detection)
    if _NATIVE and hasattr(_native, 'read_file_lines'):
        try:
            content, total_lines = _native.read_file_lines(str(p), max_lines, start_line)
            size = p.stat().st_size
            return ToolResult(
                success=True,
                output=content,
                metadata={
                    "size_bytes": size,
                    "total_lines": total_lines,
                    "showing_from": start_line,
                    "showing_to": min(start_line + max_lines, total_lines),
                    "extension": p.suffix,
                }
            )
        except Exception:
            pass  # fall through to Python

    # Strategy 2: Pure Python fallback
    try:
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        total_lines = len(lines)
        size = p.stat().st_size

        end = min(start_line + max_lines, total_lines)
        if start_line > 0 or total_lines > max_lines:
            selected = lines[start_line:end]
            numbered = "\n".join(
                f"{i + start_line + 1:>4} | {line}"
                for i, line in enumerate(selected)
            )
            if end < total_lines:
                numbered += f"\n\n... ({total_lines - end} more lines. Use start_line={end} to continue.)"
            content = numbered

        return ToolResult(
            success=True, output=content,
            metadata={
                "size_bytes": size,
                "total_lines": total_lines,
                "showing_from": start_line,
                "showing_to": end,
                "extension": p.suffix,
            }
        )
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error reading file: {str(e)}")

@tool("write_file", "Writes the file. If create_dirs=True, creates folders", RiskLevel.HIGH)
def write_file(path: str, content: str, create_dirs: bool = True) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if create_dirs:
        p.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Safeguard: If the model sent literal \n strings instead of real newlines
        if "\\n" in content and "\n" not in content:
            try:
                # Unescape \n, \t, etc.
                content = content.encode('utf-8').decode('unicode_escape')
            except:
                pass

        p.write_text(content, encoding="utf-8")
        return ToolResult(success=True, output=f"File '{p}' successfully written.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error writing file: {str(e)}")

@tool("patch_file", "Replaces old_str with new_str. Default requires a unique match; -1=all, N>0=0-indexed occurrence. Narrow old_str to disambiguate.", RiskLevel.HIGH)
def patch_file(path: str, old_str: str, new_str: str, occurrence: int = 0) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return ToolResult(success=False, output="", error=f"The file '{path}' does not exist.")
    
    try:
        occurrence = int(occurrence)
    except:
        occurrence = 0

    # Apply the same ambiguity policy before either the Rust or Python path.
    if not old_str or occurrence < -1:
        return ToolResult(success=False, output="", error="Invalid patch target or occurrence.")
    try:
        count = p.read_text(encoding="utf-8").count(old_str)
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error reading file: {e}")
    if occurrence == 0 and count > 1:
        return ToolResult(success=False, output="", error="Ambiguity: old_str matches multiple locations. Narrow old_str or explicitly select an occurrence.")

    # Strategy 1: Rust native diff engine
    if _NATIVE and hasattr(_native, 'apply_patch'):
        try:
            diff = _native.apply_patch(str(p), old_str, new_str, occurrence)
            return ToolResult(
                success=True,
                output=f"File '{p}' successfully modified.",
                metadata={"diff": diff}
            )
        except Exception as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return ToolResult(success=False, output="", error="The string 'old_str' was not found in the file.")
            # fall through to Python for other errors

    # Strategy 2: Pure Python fallback
    try:
        content = p.read_text(encoding="utf-8")
        count = content.count(old_str)
        if count == 0:
            return ToolResult(success=False, output="", error="The string 'old_str' was not found in the file.")
        
        if "\\n" in new_str and "\n" not in new_str:
            try:
                new_str = new_str.encode('utf-8').decode('unicode_escape')
            except:
                pass

        if occurrence == -1:
            new_content = content.replace(old_str, new_str)
        elif occurrence == 0:
            new_content = content.replace(old_str, new_str, 1)
        else:
            # Replace Nth occurrence manually
            parts = content.split(old_str)
            if occurrence >= len(parts) - 1:
                return ToolResult(success=False, output="", error=f"Requested occurrence {occurrence} but only {count} found.")
            new_content = old_str.join(parts[:occurrence + 1]) + new_str + old_str.join(parts[occurrence + 1:])

        p.write_text(new_content, encoding="utf-8")
        
        diff = "\n".join(difflib.unified_diff(
            content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=""
        ))
        return ToolResult(success=True, output=f"File '{p}' successfully modified.", metadata={"diff": diff})
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error patching file: {str(e)}")

@tool("delete_file", "Deletes a single file", RiskLevel.HIGH)
def delete_file(path: str) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        return ToolResult(success=False, output="", error=f"The file '{path}' does not exist.")
    if p.is_dir():
        return ToolResult(success=False, output="", error=f"'{path}' is a directory. Use delete_directory to delete folders.")
    try:
        p.unlink()
        return ToolResult(success=True, output=f"File '{p}' deleted.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error deleting file: {str(e)}")

@tool("delete_directory", "Deletes a folder and all its contents recursively", RiskLevel.HIGH)
def delete_directory(path: str) -> ToolResult:
    import shutil
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists():
        return ToolResult(success=False, output="", error=f"The directory '{path}' does not exist.")
    if not p.is_dir():
        return ToolResult(success=False, output="", error=f"'{path}' is not a directory.")
    try:
        shutil.rmtree(p)
        return ToolResult(success=True, output=f"Directory '{p}' and all its contents have been deleted.")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Error deleting directory: {str(e)}")

@tool("get_project_tree", "Returns the folder tree. Automatically ignores heavy folders like node_modules.", RiskLevel.MEDIUM)
def get_project_tree(path: str, max_depth: int = 4, ignore: list = None) -> ToolResult:
    try:
        max_depth = int(max_depth)
    except:
        max_depth = 4
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return ToolResult(success=False, output="", error=f"Directory '{path}' not found.")

    if _NATIVE:
        try:
            result = _native.get_project_tree(str(p), max_depth, list(ignore) if ignore else None)
            return ToolResult(success=True, output=result)
        except Exception as e:
            pass  # fall through to Python impl

    # ── Pure Python fallback ────────────────────────────────────
    ignore_set = set(ignore) if ignore else set()
    ignore_set.update(_DEFAULT_IGNORE)
    tree_lines = []

    def walk(directory, prefix="", depth=0):
        if depth > max_depth:
            return
        try:
            items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            items = [item for item in items if item.name not in ignore_set]
            if len(items) > 100:
                tree_lines.append(f"{prefix}└── [Too many items ({len(items)}), consider a more specific path]")
                return
            for index, item in enumerate(items):
                is_last = (index == len(items) - 1)
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{item.name}")
                if item.is_dir():
                    extension = "    " if is_last else "│   "
                    walk(item, prefix + extension, depth + 1)
        except PermissionError:
            tree_lines.append(f"{prefix}└── [Access denied]")
        except Exception as e:
            tree_lines.append(f"{prefix}└── [Error: {str(e)}]")

    tree_lines.append(p.name + "/")
    walk(p)
    return ToolResult(success=True, output="\n".join(tree_lines))

registry.register(read_file)
registry.register(write_file)
registry.register(patch_file)
registry.register(delete_file)
registry.register(delete_directory)
registry.register(get_project_tree)
