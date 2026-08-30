"""Filesystem tools: read / write / patch / create. Workspace-scoped."""

from __future__ import annotations

import difflib
import hashlib
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_MAX_READ_BYTES = 400_000


def _sha(text: str) -> str:
    # normalise line endings so an editor's CRLF<->LF flip alone isn't a "change"
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8", "replace")).hexdigest()


def _disk_text(target) -> str:
    return target.read_bytes().decode("utf-8", "replace")


def _guard(ctx: ToolContext, relative: str):
    from core.workspace.safepath import PathEscape

    try:
        return ctx.resolve(relative)  # strict: raises PathEscape on any escape
    except PathEscape as exc:
        raise PermissionError(str(exc)) from exc


def _conflict(ctx: ToolContext, path: str, current: str) -> ToolResult | None:
    """If the agent read this file earlier and it has since changed on disk
    (a user edit), refuse the write and tell the agent to re-read it (P9)."""
    known = ctx.file_shas.get(path)
    if known and known != _sha(current):
        return ToolResult.fail(
            f"{path} changed on disk since you read it - read_file it again before editing."
        )
    return None


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
        text = data.decode("utf-8", errors="replace")
        ctx.file_shas[path] = _sha(text)
        return ToolResult.ok(text, metadata={"bytes": len(data)})


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
        existed = target.is_file()
        if existed and (conflict := _conflict(ctx, path, _disk_text(target))):
            return conflict
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        ctx.file_shas[path] = _sha(content)
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
        original = _disk_text(target)
        if conflict := _conflict(ctx, path, original):
            return conflict
        count = original.count(find)
        if count == 0:
            return ToolResult.fail("'find' text not found")
        if count > 1:
            return ToolResult.fail(f"'find' text is not unique ({count} matches)")
        updated = original.replace(find, replace, 1)
        target.write_text(updated, encoding="utf-8")
        ctx.file_shas[path] = _sha(updated)
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
