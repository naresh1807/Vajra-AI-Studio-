"""Computer-agent tools (manual v3.0 section 11 / section 15 Computer group).

These act OUTSIDE any project workspace, so every mutating tool is ELEVATED or
higher and goes through the approval gate. Priority order per the manual:
native OS API -> CLI/PowerShell -> UI automation -> keyboard/mouse (last only).
No shell-string interpolation from model output: commands are argument arrays;
the one PowerShell escape hatch is HIGH-risk and always needs approval.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_KNOWN_FOLDERS = {
    "home": Path.home(),
    "desktop": Path.home() / "Desktop",
    "documents": Path.home() / "Documents",
    "downloads": Path.home() / "Downloads",
    "pictures": Path.home() / "Pictures",
    "music": Path.home() / "Music",
    "videos": Path.home() / "Videos",
}

# name -> candidate executables (first found on PATH wins)
_KNOWN_APPS = {
    "vscode": ["code", "code.cmd"],
    "code": ["code", "code.cmd"],
    "notepad": ["notepad.exe", "notepad"],
    "explorer": ["explorer.exe"],
    "chrome": ["chrome", "chrome.exe"],
    "edge": ["msedge", "msedge.exe"],
    "firefox": ["firefox", "firefox.exe"],
    "powershell": ["pwsh", "powershell.exe"],
    "terminal": ["wt.exe", "wt"],
    "docker": ["docker"],
    "calc": ["calc.exe"],
}


def _expand(path: str) -> Path:
    p = path.strip().strip('"')
    low = p.lower()
    for name, folder in _KNOWN_FOLDERS.items():
        if low == name or low.startswith(name + "/") or low.startswith(name + "\\"):
            rest = p[len(name):].lstrip("/\\")
            return (folder / rest) if rest else folder
    return Path(os.path.expandvars(os.path.expanduser(p)))


class ResolveKnownFolderTool(Tool):
    name = "resolve_known_folder"
    description = "Resolve a well-known folder name (desktop, documents, downloads, home, …) to an absolute path."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    async def run(self, ctx: ToolContext, name: str = "", **_: Any) -> ToolResult:
        folder = _KNOWN_FOLDERS.get(name.strip().lower())
        if not folder:
            return ToolResult.fail(f"unknown folder: {name}. known: {sorted(_KNOWN_FOLDERS)}")
        return ToolResult.ok(str(folder), metadata={"exists": folder.exists()})


class ListDirTool(Tool):
    name = "list_dir"
    description = "List the entries of a directory anywhere on the machine (read-only)."
    risk = RiskLevel.LOW
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def run(self, ctx: ToolContext, path: str = "", **_: Any) -> ToolResult:
        target = _expand(path)
        if not target.is_dir():
            return ToolResult.fail(f"not a directory: {target}")
        rows = []
        for e in sorted(os.scandir(target), key=lambda x: (not x.is_dir(), x.name.lower())):
            rows.append(f"{'d' if e.is_dir() else 'f'}  {e.name}")
        return ToolResult.ok("\n".join(rows) or "(empty)", metadata={"path": str(target)})


class FindFilesTool(Tool):
    name = "find_files"
    description = "Find files under a directory matching a glob, optionally only those modified in the last N days."
    risk = RiskLevel.LOW
    parameters = {
        "type": "object",
        "properties": {
            "root": {"type": "string"},
            "pattern": {"type": "string", "description": "filename glob, e.g. *.iso"},
            "modified_within_days": {"type": "integer"},
        },
        "required": ["root", "pattern"],
    }

    async def run(
        self, ctx: ToolContext, root: str = "", pattern: str = "*",
        modified_within_days: int | None = None, **_: Any,
    ) -> ToolResult:
        base = _expand(root)
        if not base.is_dir():
            return ToolResult.fail(f"not a directory: {base}")
        cutoff = time.time() - modified_within_days * 86400 if modified_within_days else None
        hits: list[str] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules"]
            for fn in filenames:
                if not fnmatch.fnmatch(fn, pattern):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    if cutoff and os.path.getmtime(full) < cutoff:
                        continue
                except OSError:
                    continue
                hits.append(full)
                if len(hits) >= 500:
                    return ToolResult.ok("\n".join(hits), metadata={"truncated": True})
        return ToolResult.ok("\n".join(hits) or "(no matches)", metadata={"count": len(hits)})


class ListProcessesTool(Tool):
    name = "computer_list_processes"
    description = "List running processes (name and pid) on the machine."
    risk = RiskLevel.LOW
    parameters = {"type": "object", "properties": {"name_contains": {"type": "string"}}}

    async def run(self, ctx: ToolContext, name_contains: str = "", **_: Any) -> ToolResult:
        try:
            if sys.platform == "win32":
                out = subprocess.run(
                    ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=15
                ).stdout
                rows = []
                for line in out.splitlines():
                    parts = [p.strip('"') for p in line.split('","')]
                    if len(parts) >= 2 and (not name_contains or name_contains.lower() in parts[0].lower()):
                        rows.append(f"{parts[1]:>8}  {parts[0]}")
            else:
                out = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True, text=True, timeout=15).stdout
                rows = [ln for ln in out.splitlines() if not name_contains or name_contains.lower() in ln.lower()]
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok("\n".join(rows[:300]) or "(none)")


class CreateFolderTool(Tool):
    name = "create_folder"
    description = "Create a folder anywhere on the machine (outside the project). Requires approval."
    risk = RiskLevel.ELEVATED
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def run(self, ctx: ToolContext, path: str = "", **_: Any) -> ToolResult:
        target = _expand(path)
        existed = target.exists()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(
            f"{'already existed' if existed else 'created'}: {target}",
            changed_files=[str(target)], metadata={"created": not existed},
        )


class WriteFileAnywhereTool(Tool):
    name = "write_desktop_file"
    description = "Create or overwrite a text file anywhere on the machine (outside the project). Requires approval."
    risk = RiskLevel.ELEVATED
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    async def run(self, ctx: ToolContext, path: str = "", content: str = "", **_: Any) -> ToolResult:
        target = _expand(path)
        existed = target.exists()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(
            f"{'updated' if existed else 'created'}: {target}", changed_files=[str(target)]
        )


class OpenPathTool(Tool):
    name = "open_path"
    description = "Open a file or folder with the OS default handler (Explorer / default app)."
    risk = RiskLevel.MEDIUM
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def run(self, ctx: ToolContext, path: str = "", **_: Any) -> ToolResult:
        target = _expand(path)
        if not target.exists():
            return ToolResult.fail(f"does not exist: {target}")
        try:
            if sys.platform == "win32":
                os.startfile(str(target))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except OSError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(f"opened {target}")


class OpenAppTool(Tool):
    name = "open_app"
    description = (
        "Launch a known desktop application (vscode, notepad, chrome, edge, explorer, "
        "powershell, terminal, docker, calc), optionally with arguments. Requires approval."
    )
    risk = RiskLevel.ELEVATED
    parameters = {
        "type": "object",
        "properties": {
            "app": {"type": "string"},
            "args": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["app"],
    }

    async def run(self, ctx: ToolContext, app: str = "", args: list[str] | None = None, **_: Any) -> ToolResult:
        candidates = _KNOWN_APPS.get(app.strip().lower())
        if not candidates:
            return ToolResult.fail(f"unknown app: {app}. known: {sorted(_KNOWN_APPS)}")
        exe = next((c for c in candidates if shutil.which(c)), None)
        if not exe:
            # some are shell verbs / not on PATH
            exe = candidates[0]
        argv = [exe, *[_expand(a).__str__() if ("/" in a or "\\" in a) else a for a in (args or [])]]
        try:
            subprocess.Popen(argv, cwd=str(Path.home()))
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(f"launched {app}: {' '.join(argv)}")


class RunPowerShellTool(Tool):
    name = "run_powershell"
    description = (
        "Run a PowerShell script on the machine. HIGH risk - use only when no safer tool "
        "fits, and only for read/inspect or clearly-scoped actions. Always requires approval."
    )
    risk = RiskLevel.HIGH
    timeout_seconds = 120
    parameters = {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}

    async def run(self, ctx: ToolContext, script: str = "", **_: Any) -> ToolResult:
        if not script.strip():
            return ToolResult.fail("empty script")
        shell = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        try:
            proc = await asyncio.create_subprocess_exec(
                shell, "-NoProfile", "-NonInteractive", "-Command", script,
                cwd=str(Path.home()),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except TimeoutError:
            return ToolResult.fail("timed out", exit_code=124)
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult.fail(str(exc))
        return ToolResult(
            success=proc.returncode == 0,
            stdout=out.decode("utf-8", "replace")[:40000],
            stderr=err.decode("utf-8", "replace")[:20000],
            exit_code=proc.returncode,
        )
