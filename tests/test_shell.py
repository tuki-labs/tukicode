import shlex
import subprocess
import sys
import time

import pytest
from tools.shell_tools import run_shell, get_process_output, _bg_processes


def python_command(source):
    args = [sys.executable, "-c", source]
    return subprocess.list2cmdline(args) if sys.platform == "win32" else shlex.join(args)


@pytest.mark.parametrize("exit_code", [0, 7])
def test_shell_reports_actual_exit_code(tmp_path, exit_code):
    result = run_shell(python_command(f"import sys; print('shell-regression'); sys.exit({exit_code})"),
                       cwd=str(tmp_path), timeout_seconds=5)
    assert result.metadata.get("background") is not True
    assert result.metadata["exit_code"] == exit_code
    assert result.success is (exit_code == 0)
    assert "shell-regression" in result.output


def test_background_failure_is_not_reported_as_success(tmp_path):
    result = run_shell(python_command("import time,sys; time.sleep(0.2); sys.exit(9)"),
                       cwd=str(tmp_path), background=True)
    assert result.success and result.metadata["background"]
    pid = result.metadata["pid"]
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            observation = get_process_output(pid)
            if observation.metadata["status"] == "Finished":
                break
            time.sleep(0.05)
        assert observation.metadata["status"] == "Finished"
        assert observation.metadata["exit_code"] == 9
        assert observation.success is False
    finally:
        info = _bg_processes.pop(pid)
        if info["process"].isalive():
            info["process"].terminate()
        info["process"].close()
