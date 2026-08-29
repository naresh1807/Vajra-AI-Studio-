"""Structured Git operations for the Studio's Source Control panel.

Thin wrapper over the `git` CLI. Everything is scoped to a workspace root.
Rollback only ever targets a Vajra checkpoint tag (`vajra/*`) or an explicit
single-file discard - never arbitrary history rewriting.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


async def _git(root: str, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=root,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


class GitError(RuntimeError):
    pass


@dataclass
class GitFile:
    path: str
    staged: bool
    unstaged: bool
    status: str  # human label: modified / added / deleted / untracked / renamed


@dataclass
class GitStatus:
    is_repo: bool
    branch: str = ""
    ahead: int = 0
    behind: int = 0
    files: list[GitFile] | None = None


_XY = {
    "M": "modified", "A": "added", "D": "deleted", "R": "renamed",
    "C": "copied", "U": "unmerged", "T": "type-changed", "?": "untracked",
}


async def status(root: str) -> GitStatus:
    code, out, _ = await _git(root, "status", "--porcelain=v1", "--branch", "-z")
    if code != 0:
        return GitStatus(is_repo=False)
    parts = out.split("\0")
    st = GitStatus(is_repo=True, files=[])
    i = 0
    while i < len(parts):
        entry = parts[i]
        if not entry:
            i += 1
            continue
        if entry.startswith("## "):
            head = entry[3:]
            st.branch = head.split("...")[0].strip()
            if "[ahead " in head:
                st.ahead = int(head.split("[ahead ", 1)[1].split("]")[0].split(",")[0])
            if "behind " in head:
                st.behind = int(head.split("behind ", 1)[1].split("]")[0])
            i += 1
            continue
        x, y, path = entry[0], entry[1], entry[3:]
        if x == "R":  # rename: next NUL chunk is the old path
            i += 1
        if entry[:2] == "??":
            label = "untracked"
        else:
            label = _XY.get(x if x not in (" ", "?") else y, "modified")
        st.files.append(
            GitFile(
                path=path,
                staged=x not in (" ", "?"),
                unstaged=y != " ",
                status=label,
            )
        )
        i += 1
    st.files.sort(key=lambda f: f.path)
    return st


async def diff(root: str, path: str | None = None, staged: bool = False) -> str:
    args = ["diff", "--no-color"]
    if staged:
        args.append("--cached")
    if path:
        args += ["--", path]
    code, out, err = await _git(root, *args)
    if code != 0 and err:
        raise GitError(err.strip())
    if not out and path and not staged:
        # untracked file: show it as an all-add diff
        code2, content, _ = await _git(root, "show", f":{path}")
        if code2 != 0:
            try:
                from pathlib import Path

                text = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
                return f"--- /dev/null\n+++ b/{path}\n" + "".join(f"+{ln}\n" for ln in text.splitlines())
            except OSError:
                return ""
    return out


async def stage(root: str, paths: list[str]) -> None:
    code, _, err = await _git(root, "add", "--", *paths) if paths else await _git(root, "add", "-A")
    if code != 0:
        raise GitError(err.strip())


async def unstage(root: str, paths: list[str]) -> None:
    args = ["restore", "--staged", "--"] + (paths or ["."])
    code, _, err = await _git(root, *args)
    if code != 0:
        raise GitError(err.strip())


async def discard(root: str, path: str) -> None:
    # revert tracked changes; delete if untracked
    code, _, _ = await _git(root, "checkout", "--", path)
    if code != 0:
        await _git(root, "clean", "-fd", "--", path)


async def commit(root: str, message: str) -> str:
    if not message.strip():
        raise GitError("empty commit message")
    code, out, err = await _git(root, "commit", "-m", message)
    if code != 0:
        raise GitError((err or out).strip())
    code2, sha, _ = await _git(root, "rev-parse", "--short", "HEAD")
    return sha.strip()


async def checkpoints(root: str, limit: int = 40) -> list[dict]:
    """Vajra checkpoint tags newest-first, plus a synthetic HEAD entry."""
    code, out, _ = await _git(
        root, "for-each-ref", "--sort=-creatordate",
        "--format=%(refname:short)%09%(creatordate:iso8601)%09%(subject)",
        "refs/tags/vajra",
    )
    rows: list[dict] = []
    if code == 0:
        for line in out.splitlines()[:limit]:
            tag, date, *subj = line.split("\t")
            rows.append({"tag": tag, "date": date, "subject": "\t".join(subj)})
    return rows


async def restore(root: str, target: str) -> None:
    """Hard-reset the working tree to a Vajra checkpoint tag."""
    if not target.startswith("vajra/"):
        raise GitError("restore only accepts a vajra/* checkpoint tag")
    code, _, err = await _git(root, "reset", "--hard", target)
    if code != 0:
        raise GitError(err.strip())
    await _git(root, "clean", "-fd")


async def checkpoint(root: str, label: str) -> dict:
    import time

    tag = f"vajra/{int(time.time())}-{label.strip().replace(' ', '-')[:40] or 'checkpoint'}"
    await _git(root, "add", "-A")
    code, out, err = await _git(root, "commit", "-m", f"vajra checkpoint: {label}", "--allow-empty")
    if code != 0 and "nothing to commit" not in (out + err):
        raise GitError((err or out).strip())
    tcode, _, terr = await _git(root, "tag", tag)
    if tcode != 0:
        raise GitError(terr.strip())
    return {"tag": tag}
