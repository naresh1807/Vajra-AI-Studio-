"""The Studio / extension terminal runs commands through a real shell."""

from __future__ import annotations

import sys

from core.runtime.terminal import run_terminal


async def test_runs_through_shell_operators(tmp_path):
    res = await run_terminal(str(tmp_path), "echo a && echo b")
    assert res["exit_code"] == 0
    assert "a" in res["stdout"] and "b" in res["stdout"]


async def test_string_and_list_forms(tmp_path):
    a = await run_terminal(str(tmp_path), [sys.executable, "-c", "print('hi')"])
    b = await run_terminal(str(tmp_path), f'"{sys.executable}" -c "print(\'hi\')"')
    assert a["stdout"].strip() == "hi" and b["stdout"].strip() == "hi"


async def test_nonzero_exit_is_reported(tmp_path):
    res = await run_terminal(str(tmp_path), f'"{sys.executable}" -c "import sys; sys.exit(5)"')
    assert res["exit_code"] == 5


async def test_timeout(tmp_path):
    res = await run_terminal(
        str(tmp_path), f'"{sys.executable}" -c "import time; time.sleep(5)"', timeout_seconds=1
    )
    assert res["exit_code"] == 124


async def test_cwd_is_the_root(tmp_path):
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    cmd = "dir /b" if sys.platform == "win32" else "ls"
    res = await run_terminal(str(tmp_path), cmd)
    assert "marker.txt" in res["stdout"]
