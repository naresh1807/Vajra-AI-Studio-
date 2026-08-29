"""Workspace-scoped file operations for the IDE.

Every read/write is confined to the opened workspace root. Writes return a
unified diff and keep the previous content so the caller can show a diff and
roll back (manual v3.0 sections 6 and 26).
"""

from __future__ import annotations

import difflib
import os
import time
from pathlib import Path

from pydantic import BaseModel

_IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".vajra", ".pytest_cache", ".ruff_cache", ".idea", ".next",
}
_MAX_READ_BYTES = 2_000_000
_MAX_TREE_ENTRIES = 6000


class FileNode(BaseModel):
    name: str
    path: str  # workspace-relative, forward slashes
    type: str  # "file" | "dir"
    children: list[FileNode] | None = None
    size: int | None = None


FileNode.model_rebuild()


class FileContent(BaseModel):
    path: str
    content: str
    bytes: int
    encoding: str = "utf-8"
    truncated: bool = False


class WriteResult(BaseModel):
    path: str
    created: bool
    bytes: int
    diff: str
    previous: str | None = None  # prior content, for rollback
    saved_at: float


class WorkspaceError(Exception):
    pass


def _resolve(root: str | Path, rel: str) -> Path:
    base = Path(root).resolve()
    target = (base / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
    if base != target and base not in target.parents:
        raise WorkspaceError(f"path escapes workspace: {rel}")
    return target


def build_tree(root: str | Path, max_depth: int = 6) -> FileNode:
    base = Path(root).resolve()
    if not base.is_dir():
        raise WorkspaceError(f"not a directory: {root}")
    count = 0

    def walk(directory: Path, depth: int) -> list[FileNode]:
        nonlocal count
        if depth > max_depth or count > _MAX_TREE_ENTRIES:
            return []
        nodes: list[FileNode] = []
        try:
            entries = sorted(
                os.scandir(directory),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except OSError:
            return []
        for entry in entries:
            if entry.name in _IGNORE_DIRS or entry.name.startswith(".git"):
                continue
            count += 1
            rel = str(Path(entry.path).resolve().relative_to(base)).replace(os.sep, "/")
            if entry.is_dir(follow_symlinks=False):
                nodes.append(
                    FileNode(
                        name=entry.name, path=rel, type="dir",
                        children=walk(Path(entry.path), depth + 1),
                    )
                )
            else:
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = None
                nodes.append(FileNode(name=entry.name, path=rel, type="file", size=size))
        return nodes

    return FileNode(name=base.name, path="", type="dir", children=walk(base, 1))


def read_file(root: str | Path, rel: str) -> FileContent:
    target = _resolve(root, rel)
    if not target.is_file():
        raise WorkspaceError(f"not a file: {rel}")
    raw = target.read_bytes()
    truncated = len(raw) > _MAX_READ_BYTES
    text = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
    return FileContent(path=rel, content=text, bytes=len(raw), truncated=truncated)


def write_file(root: str | Path, rel: str, content: str) -> WriteResult:
    target = _resolve(root, rel)
    existed = target.is_file()
    previous = target.read_text(encoding="utf-8", errors="replace") if existed else None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")
    diff = "".join(
        difflib.unified_diff(
            (previous or "").splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
    )
    return WriteResult(
        path=rel,
        created=not existed,
        bytes=len(content.encode("utf-8")),
        diff=diff or ("(new file)" if not existed else "(no change)"),
        previous=previous,
        saved_at=time.time(),
    )
