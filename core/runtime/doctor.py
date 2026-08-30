"""Environment diagnostics (master-prompt P36).

Reports what's available without ever failing the product for a *missing
optional* tool. Used by the first-run wizard, the Vajra: Health Check command,
and CI.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    status: str          # "ok" | "missing" | "error"
    detail: str = ""
    required: bool = False

    def as_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail, "required": self.required}


async def _version(cmd: list[str], timeout: float = 6.0) -> tuple[bool, str]:
    exe = shutil.which(cmd[0])
    if not exe:
        # also probe the well-known toolchain dirs the LSP config uses
        from core.lsp.config import _which  # noqa: PLC0415

        exe = _which(cmd[0])
        if not exe:
            return False, ""
    try:
        # On Windows resolve .bat/.cmd/extension-less launchers through the shell
        # (the command list is fixed here - no injection surface).
        if sys.platform == "win32":
            line = subprocess.list2cmdline([exe, *cmd[1:]])
            proc = await asyncio.create_subprocess_shell(
                line, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                exe, *cmd[1:], stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        text = out.decode("utf-8", "replace").strip()
        return True, (text.splitlines()[0][:120] if text else exe)
    except (OSError, TimeoutError) as exc:
        return False, str(exc)


async def _tool(name: str, cmd: list[str], required: bool) -> Check:
    found, detail = await _version(cmd)
    return Check(name, "ok" if found else "missing", detail, required)


async def _model_api() -> Check:
    from core.llm.model_router import ModelRouter

    try:
        r = ModelRouter()
        d = r.describe()
        # a describe() with an empty key/base_url is a config problem, not an outage
        cfg = r.config.primary
        if not cfg.base_url:
            return Check("Model API", "error", "no base_url configured for the primary model")
        return Check("Model API", "ok", f"primary {d['primary']} / fallback {d['fallback']}")
    except Exception as exc:  # noqa: BLE001
        return Check("Model API", "error", str(exc))


async def run_doctor() -> dict:
    checks = await asyncio.gather(
        _tool("Python", [sys.executable, "--version"], required=True),
        _tool("Git", ["git", "--version"], required=True),
        _tool("Node.js", ["node", "--version"], required=False),
        _tool("npm", ["npm", "--version"], required=False),
        _tool("Rust (cargo)", ["cargo", "--version"], required=False),
        _tool("Go", ["go", "version"], required=False),
        _tool("clang", ["clang", "--version"], required=False),
        _tool("Flutter", ["flutter", "--version"], required=False),
        _tool("Docker", ["docker", "--version"], required=False),
        _tool("QEMU (x86_64)", ["qemu-system-x86_64", "--version"], required=False),
        _model_api(),
    )
    checks = list(checks)
    ok = all(c.status == "ok" for c in checks if c.required)
    return {"ok": ok, "checks": [c.as_dict() for c in checks]}
