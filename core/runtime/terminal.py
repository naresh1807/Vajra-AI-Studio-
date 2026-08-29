"""Interactive-ish terminal command runner for the Studio / extension terminal.

Unlike the ``run_command`` *tool* (argv-only, no shell - the model must not be
able to inject shell syntax), the terminal is driven by a human typing, so it
runs through the platform shell: PATHEXT resolution (`npm`, `npx`, `tsc`, ...),
pipes, `&&`, redirection and builtins all work. Still one shell per command -
`cd` only persists within a single line (`cd sub && ...`).
"""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import subprocess
import sys
import time

_MAX_OUTPUT = 200_000


def _to_line(command: str | list[str]) -> str:
    if isinstance(command, str):
        return command
    return subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command)


async def run_terminal(
    root: str, command: str | list[str], timeout_seconds: int = 300
) -> dict:
    cmd = _to_line(command)
    started = time.perf_counter()
    try:
        # create_subprocess_shell routes through cmd.exe /c (Windows) or /bin/sh -c,
        # so PATHEXT (npm, npx, tsc...), pipes, &&, redirection and builtins work.
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=root or None,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return {
            "stdout": "", "stderr": f"cannot start shell: {exc}", "exit_code": 1,
            "duration_ms": 0, "cwd": root, "command": cmd,
        }
    out, rc = b"", None
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        rc = proc.returncode
    except TimeoutError:
        rc = 124
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
    text = out.decode("utf-8", "replace")[:_MAX_OUTPUT]
    return {
        "stdout": text,
        "stderr": "",
        "exit_code": rc,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "cwd": root,
        "command": cmd,
    }
