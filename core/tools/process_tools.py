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


class StartProcessTool(Tool):
    name = "start_process"
    description = (
        "Start a long-running process (dev server, watcher) in the background and return "
        "its id. Use this for `npm run dev`, `flask run`, `uvicorn --reload`, etc - NOT "
        "run_command, which waits for the command to exit."
    )
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "command": {"oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}]},
            "label": {"type": "string"},
        },
        "required": ["command"],
    }

    async def run(self, ctx: ToolContext, command: Any = None, label: str = "", **_: Any) -> ToolResult:
        from core.runtime import process_manager

        if not command:
            return ToolResult.fail("no command given")
        try:
            mp = await process_manager.start(command, cwd=str(ctx.root), label=label or "")
        except (FileNotFoundError, OSError) as exc:
            return ToolResult.fail(f"cannot start process: {exc}")
        await asyncio.sleep(2.0)  # let it boot / bind a port
        snap = mp.snapshot(tail=60)
        return ToolResult(
            success=snap["running"],
            stdout=snap["output"],
            stderr="" if snap["running"] else f"process exited ({snap['exit_code']})",
            metadata={"process_id": mp.id, "url": snap["url"], "running": snap["running"]},
        )


class ReadProcessOutputTool(Tool):
    name = "read_process_output"
    description = "Read recent output from a background process started with start_process."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {"process_id": {"type": "string"}, "tail": {"type": "integer", "default": 120}},
        "required": ["process_id"],
    }

    async def run(self, ctx: ToolContext, process_id: str = "", tail: int = 120, **_: Any) -> ToolResult:
        from core.runtime import process_manager

        mp = process_manager.get(process_id)
        if not mp:
            return ToolResult.fail(f"unknown process: {process_id}")
        snap = mp.snapshot(tail=tail)
        return ToolResult(
            success=True, stdout=snap["output"],
            metadata={"running": snap["running"], "url": snap["url"], "exit_code": snap["exit_code"]},
        )


class StopProcessTool(Tool):
    name = "stop_process"
    description = "Stop a background process started with start_process."
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {"process_id": {"type": "string"}},
        "required": ["process_id"],
    }

    async def run(self, ctx: ToolContext, process_id: str = "", **_: Any) -> ToolResult:
        from core.runtime import process_manager

        ok = await process_manager.stop(process_id)
        return ToolResult(success=ok, stdout="stopped" if ok else f"unknown process: {process_id}")


class ListProcessesTool(Tool):
    name = "list_processes"
    description = "List background processes started with start_process."
    risk = RiskLevel.LOW
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        from core.runtime import process_manager

        rows = [mp.snapshot(tail=0) for mp in process_manager.list()]
        return ToolResult(success=True, stdout="\n".join(
            f"{r['id']}  {'up' if r['running'] else 'down'}  {r['url'] or ''}  {r['label']}" for r in rows
        ) or "(none)", metadata={"processes": rows})
