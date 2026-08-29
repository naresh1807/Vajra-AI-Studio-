"""Build-step runner for the OS-dev loop: run one toolchain command in a
directory, capture bounded combined output, time it. argv only - no shell
string interpolation from model output.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path

_MAX_OUTPUT = 256 * 1024


@dataclass
class StepResult:
    name: str
    argv: list[str] = field(default_factory=list)
    exit_code: int | None = None
    output: str = ""
    duration_s: float = 0.0
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def _as_argv(command: str | list[str]) -> list[str]:
    if isinstance(command, (list, tuple)):
        return [str(c) for c in command]
    return shlex.split(command, posix=False)


async def run_step(
    name: str,
    command: str | list[str],
    cwd: str,
    timeout: float = 900.0,
    env: dict[str, str] | None = None,
) -> StepResult:
    argv = _as_argv(command)
    if not argv:
        return StepResult(name, output="empty command")
    workdir = Path(cwd).expanduser()
    if not workdir.is_dir():
        return StepResult(name, argv, output=f"not a directory: {workdir}")

    full_env = {**os.environ, **(env or {})}
    started = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=str(workdir), env=full_env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return StepResult(name, argv, output=f"{argv[0]}: {exc}")

    buf: list[bytes] = []
    size = 0

    async def _pump() -> None:
        nonlocal size
        assert proc.stdout
        while True:
            data = await proc.stdout.read(4096)
            if not data:
                break
            if size < _MAX_OUTPUT:
                buf.append(data)
                size += len(data)

    timed_out = False
    try:
        await asyncio.wait_for(asyncio.gather(_pump(), proc.wait()), timeout=timeout)
    except TimeoutError:
        timed_out = True
        proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()

    out = b"".join(buf).decode("utf-8", "replace")
    if size >= _MAX_OUTPUT:
        out += "\n...[output truncated]"
    return StepResult(name, argv, proc.returncode, out, round(time.monotonic() - started, 1), timed_out)
