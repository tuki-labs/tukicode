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

@tool("read_file", "Reads the content of a file", RiskLevel.MEDIUM)
def read_file(path: str) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return ToolResult(success=False, output="", error=f"The file '{path}' does not exist or is not a valid file.")
    
    try:
        content = p.read_text(encoding="utf-8")
        lines = len(content.splitlines())
        size = p.stat().st_size
        return ToolResult(success=True, output=content, metadata={"size_bytes": size, "lines": lines, "extension": p.suffix})
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

@tool("patch_file", "Replaces old_str with new_str in the file", RiskLevel.HIGH)
def patch_file(path: str, old_str: str, new_str: str) -> ToolResult:
    p = pathlib.Path(path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        return ToolResult(success=False, output="", error=f"The file '{path}' does not exist.")
    
    try:
        content = p.read_text(encoding="utf-8")
        count = content.count(old_str)
        if count == 0:
            return ToolResult(success=False, output="", error="The string 'old_str' was not found in the file.")
        if count > 1:
            return ToolResult(success=False, output="", error="The string 'old_str' appears multiple times. Ambiguity detected.")
        
        if "\\n" in new_str and "\n" not in new_str:
            try:
                new_str = new_str.encode('utf-8').decode('unicode_escape')
            except:
                pass

        new_content = content.replace(old_str, new_str)
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
    default_ignore = {
        "node_modules", ".git", "__pycache__", "venv", ".venv",
        "dist", "build", "target", ".expo", ".next", "out",
        "android", "ios", "Pods"
    }
    ignore_set = set(ignore) if ignore else set()
    ignore_set.update(default_ignore)
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
