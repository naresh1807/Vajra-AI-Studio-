"""Search / project-tree tools."""

from __future__ import annotations

import fnmatch
import os
import re
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_IGNORE = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".vajra"}
_MAX_HITS = 200


class SearchTextTool(Tool):
    name = "search_text"
    description = "Regex search across workspace text files. Returns path:line:match."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "glob": {"type": "string", "description": "optional filename glob, e.g. *.py"},
        },
        "required": ["pattern"],
    }

    async def run(self, ctx: ToolContext, pattern: str = "", glob: str = "*", **_: Any) -> ToolResult:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return ToolResult.fail(f"bad regex: {exc}")
        hits: list[str] = []
        for dirpath, dirnames, filenames in os.walk(ctx.root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE]
            for fn in filenames:
                if not fnmatch.fnmatch(fn, glob):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ctx.root)
                try:
                    with open(full, encoding="utf-8", errors="ignore") as fh:
                        for i, line in enumerate(fh, 1):
                            if rx.search(line):
                                hits.append(f"{rel}:{i}:{line.strip()[:200]}")
                                if len(hits) >= _MAX_HITS:
                                    return ToolResult.ok("\n".join(hits), metadata={"truncated": True})
                except OSError:
                    continue
        return ToolResult.ok("\n".join(hits) or "(no matches)", metadata={"hits": len(hits)})


class SemanticSearchTool(Tool):
    name = "semantic_search"
    description = (
        "Find the workspace code chunks most relevant to a natural-language query "
        "(meaning, not exact text). Returns path:lines + a snippet, best first. "
        "Use for 'where is X handled', 'how does Y work' - complements search_text."
    )
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "k": {"type": "integer", "description": "how many chunks (default 6)"},
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str = "", k: int = 6, **_: Any) -> ToolResult:
        from core.rag import rag_manager

        if not ctx.workspace_root:
            return ToolResult.fail("no workspace open")
        hits = await rag_manager.retrieve(ctx.workspace_root, query, k=max(1, min(k, 15)))
        if not hits:
            return ToolResult.ok("(no indexed matches - run /api/rag/reindex)")
        blocks = [f"### {h.ref}  (score {h.score:.2f})\n{h.text}" for h in hits]
        return ToolResult.ok("\n\n".join(blocks), metadata={"hits": [h.ref for h in hits]})


class ProjectTreeTool(Tool):
    name = "project_tree"
    description = "List the workspace file tree (depth-limited, ignores vendor dirs)."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {"max_depth": {"type": "integer", "default": 3}},
    }

    async def run(self, ctx: ToolContext, max_depth: int = 3, **_: Any) -> ToolResult:
        lines: list[str] = []
        root = ctx.root
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE)
            rel = os.path.relpath(dirpath, root)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > max_depth:
                dirnames[:] = []
                continue
            indent = "  " * depth
            if rel != ".":
                lines.append(f"{indent}{os.path.basename(dirpath)}/")
            for fn in sorted(filenames):
                lines.append(f"{indent}  {fn}")
            if len(lines) > 1000:
                lines.append("... (truncated)")
                break
        return ToolResult.ok("\n".join(lines))
