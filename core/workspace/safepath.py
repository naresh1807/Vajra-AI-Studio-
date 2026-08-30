"""Strict workspace-scoped path resolution (master-prompt P5).

``safe_resolve(root, rel)`` returns an absolute path that is provably inside
``root`` after resolving ``..``, symlinks and Windows junctions, or raises
``PathEscape``. It also rejects the sneakier tricks: absolute / drive-relative
paths, UNC paths, NUL bytes, and NTFS alternate-data-stream syntax.
"""

from __future__ import annotations

import os
from pathlib import Path


class PathEscape(Exception):
    """A path that would leave the workspace root."""


def _norm(p: str | os.PathLike) -> str:
    # case- and separator-insensitive on Windows, exact elsewhere
    return os.path.normcase(os.path.realpath(p))


def is_within(root: str | os.PathLike, target: str | os.PathLike) -> bool:
    r = _norm(root)
    t = _norm(target)
    return t == r or t.startswith(r + os.sep)


def safe_resolve(root: str | os.PathLike, rel: str) -> Path:
    if not isinstance(rel, str) or rel == "":
        raise PathEscape("empty path")
    if "\x00" in rel:
        raise PathEscape("NUL byte in path")
    # NTFS alternate data stream: "file.txt:stream" (a bare drive letter "C:" is fine)
    tail = rel.split("\\")[-1].split("/")[-1]
    if ":" in tail:
        raise PathEscape(f"alternate data stream / drive-relative path: {rel!r}")
    p = Path(rel)
    if p.is_absolute() or p.drive or rel.startswith(("\\\\", "//")):
        # absolute or UNC - only allowed if it already lands inside root
        cand = Path(rel)
        if not is_within(root, cand):
            raise PathEscape(f"absolute path outside the workspace: {rel!r}")
        resolved = cand.resolve()
    else:
        resolved = (Path(root) / p).resolve()

    if not is_within(root, resolved):
        raise PathEscape(f"path escapes the workspace: {rel!r}")
    # realpath catches a symlink/junction anywhere on the way in
    if not is_within(root, os.path.realpath(resolved)):
        raise PathEscape(f"path resolves (via a link) outside the workspace: {rel!r}")
    return resolved
