"""Minimal VM adapter for the OS-development agent (manual v3.0 Phase 9).

Boots a kernel / raw disk / ISO under QEMU with the serial console wired to our
stdout, so a build -> boot -> inspect loop is fully scriptable, and scans the
serial log for panics and a caller-supplied ready marker. QEMU is resolved from
PATH; if it is absent, a boot returns ``booted=False`` with a clear reason
instead of raising. Runs with ``-no-reboot -nic none`` and TCG (software) by
default so the guest stays contained.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

_PANIC_MARKERS = (
    "kernel panic",
    "-- system halted",
    "!!!! x86 mmu",
    "panic:",
    "not syncing",
    "double fault",
    "unhandled exception",
    "no bootable device",
)

_ARCHES = ("x86_64", "i386", "aarch64", "arm", "riscv64")

_MAX_SERIAL = 512 * 1024


@dataclass
class VmSpec:
    name: str = "vm"
    arch: str = "x86_64"
    kernel: str | None = None
    initrd: str | None = None
    append: str = ""
    disk: str | None = None
    iso: str | None = None
    memory_mb: int = 512
    boot_timeout: float = 60.0
    ready_marker: str = ""
    network: bool = False
    accel: bool = False  # nested virt is often unavailable; default to TCG
    extra_args: list[str] = field(default_factory=list)


@dataclass
class BootResult:
    booted: bool
    timed_out: bool = False
    panic: bool = False
    ready: bool = False
    exit_code: int | None = None
    duration_s: float = 0.0
    serial: str = ""
    argv: list[str] = field(default_factory=list)
    error: str = ""


_QEMU_DIRS = (
    Path("C:/Program Files/qemu"),
    Path("C:/Program Files (x86)/qemu"),
    Path.home() / "scoop" / "apps" / "qemu" / "current",
)


def qemu_binary(arch: str) -> str | None:
    name = f"qemu-system-{arch}"
    found = shutil.which(name)
    if found:
        return found
    for d in _QEMU_DIRS:
        for ext in ("", ".exe"):
            cand = d / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
    return None


def providers_available() -> dict[str, bool]:
    return {a: qemu_binary(a) is not None for a in _ARCHES}


def scan_serial(text: str, ready_marker: str = "") -> tuple[bool, bool]:
    """(panic, ready) — case-insensitive marker scan over a serial capture."""
    low = text.lower()
    panic = any(m in low for m in _PANIC_MARKERS)
    ready = bool(ready_marker) and ready_marker.lower() in low
    return panic, ready


def _build_argv(spec: VmSpec, qemu: str) -> list[str]:
    argv = [
        qemu, "-nographic", "-serial", "mon:stdio", "-no-reboot",
        "-m", str(spec.memory_mb),
        "-accel", "kvm:whpx:hvf:tcg" if spec.accel else "tcg",
    ]
    if not spec.network:
        argv += ["-nic", "none"]
    if spec.kernel:
        argv += ["-kernel", spec.kernel]
    if spec.initrd:
        argv += ["-initrd", spec.initrd]
    if spec.append:
        argv += ["-append", spec.append]
    if spec.iso:
        argv += ["-cdrom", spec.iso]
    if spec.disk:
        argv += ["-drive", f"file={spec.disk},format=raw,if=ide"]
    argv += list(spec.extra_args)
    return argv


async def boot_and_capture(spec: VmSpec) -> BootResult:
    # Validate the request before probing the environment, so a caller error is
    # reported the same way whether or not QEMU happens to be installed.
    if not (spec.kernel or spec.disk or spec.iso):
        return BootResult(booted=False, error="nothing to boot: set kernel, disk or iso")
    qemu = qemu_binary(spec.arch)
    if not qemu:
        return BootResult(booted=False, error=f"qemu-system-{spec.arch} not found on PATH")
    for label, p in (
        ("kernel", spec.kernel), ("initrd", spec.initrd),
        ("disk", spec.disk), ("iso", spec.iso),
    ):
        if p and not Path(p).expanduser().exists():
            return BootResult(booted=False, error=f"{label} not found: {p}")

    argv = _build_argv(spec, qemu)
    started = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return BootResult(booted=False, error=str(exc), argv=argv)

    chunks: list[bytes] = []
    size = 0
    settled = ""  # "ready" | "panic" -> stop early instead of waiting the timeout

    async def _pump() -> None:
        nonlocal size, settled
        assert proc.stdout
        while True:
            data = await proc.stdout.read(4096)
            if not data:
                break
            if size < _MAX_SERIAL:
                chunks.append(data)
                size += len(data)
            if not settled:
                text = b"".join(chunks).decode("utf-8", "replace")
                p, r = scan_serial(text, spec.ready_marker)
                if r:
                    settled = "ready"
                elif p:
                    settled = "panic"
                if settled:
                    with contextlib.suppress(ProcessLookupError):
                        proc.terminate()

    pump = asyncio.create_task(_pump())
    timed_out = False
    try:
        await asyncio.wait_for(proc.wait(), timeout=spec.boot_timeout)
    except TimeoutError:
        timed_out = True
        proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
    await pump

    serial = b"".join(chunks).decode("utf-8", "replace")[-_MAX_SERIAL:]
    panic, ready = scan_serial(serial, spec.ready_marker)
    # early-terminate on a ready marker isn't a timeout
    if settled == "ready":
        timed_out = False
    duration = round(time.monotonic() - started, 1)

    if spec.ready_marker:
        booted = ready
    else:
        booted = not timed_out and not panic and proc.returncode == 0

    return BootResult(
        booted=booted, timed_out=timed_out, panic=panic, ready=ready,
        exit_code=proc.returncode, duration_s=duration, serial=serial, argv=argv,
    )
