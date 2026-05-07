import pytest
from pathlib import Path
from tools.file_tools import read_file, write_file, patch_file
from tools.search_tools import search_code, find_files

def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hola mundo", encoding="utf-8")
    
    res = read_file(path=str(f))
    assert res.success == True
    assert res.output == "Hola mundo"
    
    res = read_file(path=str(tmp_path / "no_existe.txt"))
    assert res.success == False

def test_write_file(tmp_path):
    f = tmp_path / "sub" / "test.txt"
    res = write_file(path=str(f), content="Adios", create_dirs=True)
    assert res.success == True
    assert f.read_text(encoding="utf-8") == "Adios"

def test_patch_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("A B C\n1 2 3", encoding="utf-8")
    
    res = patch_file(path=str(f), old_str="B", new_str="X")
    assert res.success == True
    assert "X" in f.read_text(encoding="utf-8")
    
    # Múltiples ocurrencias
    f.write_text("A B B", encoding="utf-8")
    res = patch_file(path=str(f), old_str="B", new_str="X")
    assert res.success == False
    assert "Ambiguity" in res.error

def test_search_code(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("def hola():\n    pass", encoding="utf-8")
    
    res = search_code(query="def hola", path=str(tmp_path), case_sensitive=True, context_lines=0)
    assert res.success == True
    assert "def hola" in res.output

def test_find_files(tmp_path):
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "sub" / "b.py"
    f1.write_text("")
    f2.parent.mkdir()
    f2.write_text("")
    
    res = find_files(pattern="*.py", root=str(tmp_path), max_depth=5, ignore=[])
    assert res.success == True
    assert "a.py" in res.output
    assert "b.py" in res.output
