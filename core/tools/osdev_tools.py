"""OS-development tools (manual v3.0 Phase 9).

These drive a compile -> boot -> inspect loop for kernels, bootloaders and
small operating systems. They act outside any project workspace, so they are
marked ``system``. Building and booting are MEDIUM (the user has explicitly
pointed the agent at an OS project and QEMU runs contained: ``-no-reboot
-nic none``, software CPU); allocating a disk image writes a large file
outside the workspace and is ELEVATED (approval-gated).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from core.osdev import build as buildsvc
from core.osdev import vm as vmsvc
from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult

_BUILD_TOOLS = (
    "make", "gcc", "g++", "clang", "clang++", "ld", "ld.lld", "lld",
    "nasm", "as", "objcopy", "objdump", "gdb", "cargo", "rustc",
    "xorriso", "grub-mkrescue", "mtools", "qemu-img", "dd",
)

_SERIAL_IN_PAYLOAD = 16000


class OsDevProvidersTool(Tool):
    name = "osdev_providers"
    description = (
        "Report which virtualization backends (qemu-system-*) and OS-dev build "
        "tools (make, gcc, clang, ld, nasm, cargo, xorriso, grub-mkrescue, ...) "
        "are installed on this machine. Call this first."
    )
    risk = RiskLevel.LOW

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        qemu = vmsvc.providers_available()
        tools = {name: bool(shutil.which(name)) for name in _BUILD_TOOLS}
        lines = ["qemu:"]
        lines += [f"  qemu-system-{a}: {'yes' if ok else 'no'}" for a, ok in qemu.items()]
        lines.append("build tools:")
        lines += [f"  {n}: {'yes' if ok else 'no'}" for n, ok in tools.items()]
        return ToolResult.ok("\n".join(lines), metadata={"qemu": qemu, "tools": tools})


class OsDevBuildTool(Tool):
    name = "osdev_build"
    description = (
        "Run one build step (a toolchain command) in a directory and return its "
        "combined output, exit code and duration. Pass 'command' as an argument "
        "array (preferred) or a string. Use for `make`, cross-compiler invocations, "
        "linker scripts, image assembly, etc."
    )
    risk = RiskLevel.MEDIUM
    timeout_seconds = 1800
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "short label for the step"},
            "command": {
                "type": "array",
                "items": {"type": "string"},
                "description": "argv, e.g. [\"make\", \"-j4\", \"iso\"]",
            },
            "cwd": {"type": "string", "description": "absolute path to run in"},
            "timeout_seconds": {"type": "integer"},
        },
        "required": ["command", "cwd"],
    }

    async def run(
        self, ctx: ToolContext, name: str = "build", command: Any = None,
        cwd: str = "", timeout_seconds: int = 900, **_: Any,
    ) -> ToolResult:
        if not command:
            return ToolResult.fail("command is required")
        res = await buildsvc.run_step(name, command, cwd, timeout=float(timeout_seconds))
        head = f"[{res.name}] exit={res.exit_code} {res.duration_s}s"
        if res.timed_out:
            head += " (TIMED OUT)"
        body = f"{head}\n$ {' '.join(res.argv)}\n{res.output}"
        return ToolResult(
            success=res.ok, stdout=body[:60000], exit_code=res.exit_code,
            metadata={"name": res.name, "duration_s": res.duration_s, "timed_out": res.timed_out},
        )


class OsDevBootTool(Tool):
    name = "osdev_boot"
    description = (
        "Boot a kernel / raw disk / ISO under QEMU with the serial console captured, "
        "then return the serial log plus whether it panicked, timed out, or hit the "
        "ready marker. Contained: -no-reboot, no network, software CPU. Set "
        "'ready_marker' to a string your kernel prints on success."
    )
    risk = RiskLevel.MEDIUM
    timeout_seconds = 1800
    parameters = {
        "type": "object",
        "properties": {
            "arch": {"type": "string", "description": "x86_64 (default), i386, aarch64, arm, riscv64"},
            "kernel": {"type": "string"},
            "initrd": {"type": "string"},
            "append": {"type": "string", "description": "kernel command line"},
            "disk": {"type": "string", "description": "raw disk image path"},
            "iso": {"type": "string"},
            "memory_mb": {"type": "integer"},
            "boot_timeout": {"type": "number", "description": "seconds before the guest is killed"},
            "ready_marker": {"type": "string"},
        },
    }

    async def run(
        self, ctx: ToolContext, arch: str = "x86_64", kernel: str = "", initrd: str = "",
        append: str = "", disk: str = "", iso: str = "", memory_mb: int = 512,
        boot_timeout: float = 60.0, ready_marker: str = "", **_: Any,
    ) -> ToolResult:
        spec = vmsvc.VmSpec(
            arch=arch or "x86_64",
            kernel=kernel or None, initrd=initrd or None, append=append,
            disk=disk or None, iso=iso or None, memory_mb=memory_mb,
            boot_timeout=min(float(boot_timeout or 60.0), 600.0),
            ready_marker=ready_marker,
        )
        res = await vmsvc.boot_and_capture(spec)
        if res.error:
            return ToolResult.fail(res.error, metadata={"argv": res.argv})
        verdict = (
            "ready" if res.ready else
            "panic" if res.panic else
            "timeout" if res.timed_out else
            "clean-exit" if res.booted else "unknown"
        )
        tail = res.serial[-_SERIAL_IN_PAYLOAD:]
        body = (
            f"boot: {verdict}  exit={res.exit_code}  {res.duration_s}s\n"
            f"$ {' '.join(res.argv)}\n--- serial (tail) ---\n{tail}"
        )
        return ToolResult(
            success=res.booted, stdout=body,
            metadata={
                "verdict": verdict, "booted": res.booted, "panic": res.panic,
                "timed_out": res.timed_out, "ready": res.ready,
                "duration_s": res.duration_s, "serial_len": len(res.serial),
            },
        )


class OsDevMakeImageTool(Tool):
    name = "osdev_make_image"
    description = (
        "Allocate a zero-filled raw disk image of a given size (MiB) at a path. "
        "Writes a large file outside the project - requires approval."
    )
    risk = RiskLevel.ELEVATED
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "size_mib": {"type": "integer", "description": "1 - 8192"},
        },
        "required": ["path", "size_mib"],
    }

    async def run(self, ctx: ToolContext, path: str = "", size_mib: int = 0, **_: Any) -> ToolResult:
        if not path or size_mib <= 0:
            return ToolResult.fail("path and a positive size_mib are required")
        if size_mib > 8192:
            return ToolResult.fail("size_mib capped at 8192 (8 GiB)")
        target = Path(path).expanduser()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fh:
                fh.truncate(size_mib * 1024 * 1024)
        except OSError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(
            f"allocated {size_mib} MiB at {target}",
            changed_files=[str(target)], metadata={"bytes": size_mib * 1024 * 1024},
        )
