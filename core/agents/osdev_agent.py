"""OS-Development Agent (manual v3.0 Phase 9).

Runs a bounded compile -> boot -> inspect loop for kernels, bootloaders and
small operating systems: build with the cross-toolchain, boot the artifact
under QEMU with the serial console captured, read the panic / log, fix, repeat.
Shares the Computer Agent's tool loop and approval gate.
"""

from __future__ import annotations

from core.agents.computer_agent import ComputerAgent
from core.events import EventBus
from core.llm import ModelRouter
from core.orchestrator.approvals import ApprovalGate
from core.tools import ToolRegistry
from core.tools.registry import build_osdev_registry

_SYSTEM = (
    "You are Vajra's OS-Development Agent. You build and boot operating systems, "
    "kernels and bootloaders on the user's machine.\n"
    "\n"
    "Method:\n"
    "1. Call osdev_providers first to see which qemu-system-* backends and build "
    "tools are installed. If the toolchain you need is missing, say so and stop.\n"
    "2. Build with osdev_build (one step per call, argv arrays, absolute cwd).\n"
    "3. Boot the artifact with osdev_boot - pass a kernel/disk/iso, and a "
    "ready_marker string your kernel prints on success so a clean boot is "
    "detected. Keep boot_timeout small (15-60s).\n"
    "4. Read the returned serial log. On a panic or timeout, diagnose from the "
    "log, adjust the source or build, and iterate. Allocate a disk image with "
    "osdev_make_image only when needed (it needs approval).\n"
    "\n"
    "Rules: never guess paths. Do only what was asked. Stop after a clean boot "
    "or after ~6 build/boot attempts, and reply with a one-line status plus the "
    "key line from the serial log."
)

_MAX_TURNS = 14


class OsDevAgent(ComputerAgent):
    def __init__(
        self,
        router: ModelRouter,
        approvals: ApprovalGate,
        events: EventBus,
        registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(router, approvals, events, registry or build_osdev_registry())
        self.system_prompt = _SYSTEM
        self.kind = "osdev"
        self.max_turns = _MAX_TURNS
