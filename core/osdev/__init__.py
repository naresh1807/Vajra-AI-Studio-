"""OS-development support: VM adapter + build-step runner for the compile ->
boot -> inspect loop (manual v3.0 Phase 9)."""

from core.osdev.build import StepResult, run_step
from core.osdev.vm import BootResult, VmSpec, boot_and_capture, providers_available, scan_serial

__all__ = [
    "BootResult",
    "StepResult",
    "VmSpec",
    "boot_and_capture",
    "providers_available",
    "run_step",
    "scan_serial",
]
