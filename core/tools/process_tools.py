"""Command / process tools. No shell string interpolation from model output:
commands are passed as argument arrays.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_MAX_OUTPUT = 60_000


def _as_argv(command: Any) -> list[str]:
    if isinstance(command, list):
        return [str(c) for c in command]
    return shlex.split(str(command), posix=False)


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Run a command in the workspace and wait for it to finish. "
        "Pass 'command' as a list of args (preferred) or a string."
    )
    risk = RiskLevel.MEDIUM
    timeout_seconds = 600
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "oneOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "string"},
                ]
            },
            "timeout_seconds": {"type": "integer", "default": 300},
        },
        "required": ["command"],
    }

    async def run(
        self, ctx: ToolContext, command: Any = None, timeout_seconds: int = 300, **_: Any
    ) -> ToolResult:
        if not command:
            return ToolResult.fail("no command given")
        argv = _as_argv(command)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(ctx.root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            return ToolResult.fail(f"cannot start process: {exc}")
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            proc.kill()
            return ToolResult.fail(f"timed out after {timeout_seconds}s", exit_code=124)
        stdout = out.decode("utf-8", "replace")[:_MAX_OUTPUT]
        stderr = err.decode("utf-8", "replace")[:_MAX_OUTPUT]
        return ToolResult(
            success=proc.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            metadata={"argv": argv},
        )
