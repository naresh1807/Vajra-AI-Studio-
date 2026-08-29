"""OS-development support: build-step runner, serial scan, VM adapter, tools."""

from __future__ import annotations

import shutil
import sys

import pytest

from core.osdev import providers_available, run_step, scan_serial
from core.osdev.vm import VmSpec, boot_and_capture
from core.tools import ToolCall, ToolContext, build_osdev_registry


def test_providers_available_shape():
    p = providers_available()
    assert isinstance(p, dict) and "x86_64" in p
    assert all(isinstance(v, bool) for v in p.values())


def test_scan_serial_detects_panic_and_ready():
    assert scan_serial("... Kernel panic - not syncing: VFS") == (True, False)
    assert scan_serial("boot ok\nVAJRA-OK\n", "VAJRA-OK") == (False, True)
    assert scan_serial("nothing interesting") == (False, False)


async def test_run_step_success(tmp_path):
    res = await run_step("hello", [sys.executable, "-c", "print('built')"], str(tmp_path))
    assert res.ok and res.exit_code == 0 and "built" in res.output


async def test_run_step_nonzero(tmp_path):
    res = await run_step("fail", [sys.executable, "-c", "import sys; sys.exit(3)"], str(tmp_path))
    assert not res.ok and res.exit_code == 3


async def test_run_step_bad_cwd():
    res = await run_step("x", ["echo", "hi"], "/no/such/dir/xyz")
    assert not res.ok and "not a directory" in res.output


async def test_run_step_timeout(tmp_path):
    res = await run_step("slow", [sys.executable, "-c", "import time; time.sleep(5)"], str(tmp_path), timeout=0.5)
    assert res.timed_out and not res.ok


async def test_boot_without_qemu_returns_reason():
    # arch that will not have a qemu binary on the test machine
    res = await boot_and_capture(VmSpec(arch="s390x", kernel=None))
    assert not res.booted and res.error


async def test_boot_missing_kernel_path():
    res = await boot_and_capture(VmSpec(kernel="/definitely/not/here/vmlinuz"))
    assert not res.booted
    assert "not found" in res.error or "qemu-system" in res.error


def test_osdev_registry_wiring():
    reg = build_osdev_registry()
    assert {"osdev_providers", "osdev_build", "osdev_boot", "osdev_make_image"} <= set(reg.names())
    ctx = ToolContext(workspace_root="")
    # build + boot run without approval; image allocation is approval-gated
    assert not reg.check(ToolCall(tool_name="osdev_build", arguments={}), ctx).requires_approval
    assert not reg.check(ToolCall(tool_name="osdev_boot", arguments={}), ctx).requires_approval
    assert reg.check(ToolCall(tool_name="osdev_make_image", arguments={}), ctx).requires_approval


async def test_osdev_providers_tool_runs():
    reg = build_osdev_registry()
    res = await reg.execute(ToolCall(tool_name="osdev_providers", arguments={}), ToolContext(workspace_root=""))
    assert res.success and "qemu" in res.stdout


async def test_osdev_make_image_tool(tmp_path):
    reg = build_osdev_registry()
    target = tmp_path / "disk.img"
    res = await reg.execute(
        ToolCall(tool_name="osdev_make_image", arguments={"path": str(target), "size_mib": 2}),
        ToolContext(workspace_root=""),
        approved=True,
    )
    assert res.success and target.stat().st_size == 2 * 1024 * 1024


@pytest.mark.skipif(shutil.which("qemu-system-x86_64") is None, reason="qemu-system-x86_64 not installed")
async def test_real_qemu_boot_no_media_times_out_or_halts():
    res = await boot_and_capture(VmSpec(arch="x86_64", disk=None, iso=None, kernel=None, boot_timeout=8))
    # nothing to boot -> adapter refuses before launching qemu
    assert not res.booted and "nothing to boot" in res.error
