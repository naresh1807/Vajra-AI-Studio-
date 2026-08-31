"""Git change-control tools: status, diff, checkpoint, restore.

Checkpoints use lightweight tags on top of a commit of Vajra-owned changes so a
rollback only touches what Vajra changed.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult


async def _git(ctx: ToolContext, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(ctx.root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show porcelain git status for the workspace."
    risk = RiskLevel.LOW

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        code, out, err = await _git(ctx, "status", "--porcelain=v1", "--branch")
        return ToolResult(success=code == 0, stdout=out, stderr=err, exit_code=code)


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show the current working-tree diff (optionally for one path)."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "staged": {"type": "boolean"}},
    }

    async def run(self, ctx: ToolContext, path: str = "", staged: bool = False, **_: Any) -> ToolResult:
        args = ["diff"]
        if staged:
            args.append("--cached")
        if path:
            args += ["--", path]
        code, out, err = await _git(ctx, *args)
        return ToolResult(success=code == 0, stdout=out, stderr=err, exit_code=code)


class GitCheckpointTool(Tool):
    name = "git_checkpoint"
    description = "Commit current changes and tag them as a Vajra rollback point."
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
    }

    async def run(self, ctx: ToolContext, label: str = "checkpoint", **_: Any) -> ToolResult:
        tag = f"vajra/{int(time.time())}-{label.replace(' ', '-')[:40]}"
        await _git(ctx, "add", "-A")
        code, out, err = await _git(ctx, "commit", "-m", f"vajra checkpoint: {label}", "--allow-empty")
        if code != 0:
            return ToolResult.fail(err or out, exit_code=code)
        tcode, _, terr = await _git(ctx, "tag", tag)
        if tcode != 0:
            return ToolResult.fail(terr, exit_code=tcode)
        return ToolResult.ok(f"checkpoint {tag}", metadata={"tag": tag})


class GitCommitTool(Tool):
    name = "git_commit"
    description = (
        "Stage every change and commit it with a message. Use this for a 'commit' "
        "task (git_checkpoint is for rollback points during a run)."
    )
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    async def run(self, ctx: ToolContext, message: str = "", **_: Any) -> ToolResult:
        msg = (message or "").strip() or "vajra: commit changes"
        await _git(ctx, "add", "-A")
        code, out, err = await _git(ctx, "commit", "-m", msg)
        if code != 0:
            detail = (err or out).strip()
            if "nothing to commit" in detail:
                return ToolResult.ok("nothing to commit - working tree already clean")
            return ToolResult.fail(detail, exit_code=code)
        return ToolResult.ok(out.strip() or f"committed: {msg}")


class GitRestoreTool(Tool):
    name = "git_restore"
    description = "Reset the working tree back to a Vajra checkpoint tag (Vajra-owned changes only)."
    risk = RiskLevel.HIGH
    parameters = {
        "type": "object",
        "properties": {"tag": {"type": "string"}},
        "required": ["tag"],
    }

    async def run(self, ctx: ToolContext, tag: str = "", **_: Any) -> ToolResult:
        if not tag.startswith("vajra/"):
            return ToolResult.fail("refusing to restore a non-Vajra tag")
        code, out, err = await _git(ctx, "reset", "--hard", tag)
        return ToolResult(success=code == 0, stdout=out, stderr=err, exit_code=code)
