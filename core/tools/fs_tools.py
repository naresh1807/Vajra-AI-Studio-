"""Filesystem tools: read / write / patch / create. Workspace-scoped."""

from __future__ import annotations

import difflib
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_MAX_READ_BYTES = 400_000


def _guard(ctx: ToolContext, relative: str):
    target = ctx.resolve(relative)
    if ctx.root not in target.parents and target != ctx.root:
        raise PermissionError(f"path escapes workspace: {relative}")
    return target


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "workspace-relative path"}},
        "required": ["path"],
    }

    async def run(self, ctx: ToolContext, path: str = "", **_: Any) -> ToolResult:
        try:
            target = _guard(ctx, path)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))
        if not target.is_file():
            return ToolResult.fail(f"not a file: {path}")
        data = target.read_bytes()[:_MAX_READ_BYTES]
        return ToolResult.ok(data.decode("utf-8", errors="replace"), metadata={"bytes": len(data)})


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a text file inside the workspace."
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    async def run(self, ctx: ToolContext, path: str = "", content: str = "", **_: Any) -> ToolResult:
        try:
            target = _guard(ctx, path)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult.ok(
            f"{'updated' if existed else 'created'} {path}",
            changed_files=[path],
            metadata={"existed": existed, "bytes": len(content.encode())},
        )


class PatchFileTool(Tool):
    name = "patch_file"
    description = (
        "Apply a search/replace patch to an existing file. Preferred over full rewrites. "
        "Fails if 'find' is not present exactly once."
    )
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "find": {"type": "string", "description": "exact text to replace (must be unique)"},
            "replace": {"type": "string"},
        },
        "required": ["path", "find", "replace"],
    }

    async def run(
        self, ctx: ToolContext, path: str = "", find: str = "", replace: str = "", **_: Any
    ) -> ToolResult:
        try:
            target = _guard(ctx, path)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))
        if not target.is_file():
            return ToolResult.fail(f"not a file: {path}")
        original = target.read_text(encoding="utf-8")
        count = original.count(find)
        if count == 0:
            return ToolResult.fail("'find' text not found")
        if count > 1:
            return ToolResult.fail(f"'find' text is not unique ({count} matches)")
        updated = original.replace(find, replace, 1)
        target.write_text(updated, encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return ToolResult.ok(diff or f"patched {path}", changed_files=[path])


class CreateDirectoryTool(Tool):
    name = "create_directory"
    description = "Create a directory (and parents) inside the workspace."
    risk = RiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def run(self, ctx: ToolContext, path: str = "", **_: Any) -> ToolResult:
        try:
            target = _guard(ctx, path)
        except PermissionError as exc:
            return ToolResult.fail(str(exc))
        target.mkdir(parents=True, exist_ok=True)
        return ToolResult.ok(f"created {path}", changed_files=[path])
