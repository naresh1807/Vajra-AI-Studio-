"""The Run button (master-prompt P14): turn a workspace profile into the
command that starts the project.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.workspace import discover_workspace


@dataclass
class RunPlan:
    command: str
    cwd: str
    framework: str | None
    port: int | None
    kind: str            # "run" | "build" | "test"
    alternatives: dict


def plan(root: str, kind: str = "run") -> RunPlan:
    prof = discover_workspace(root)
    cmd = prof.commands.get(kind)
    if not cmd and kind == "run":
        # last resort: run an entrypoint or the build
        cmd = (
            (f"python {prof.entrypoints[0]}" if prof.entrypoints else None)
            or prof.commands.get("build")
        )
    return RunPlan(
        command=cmd or "",
        cwd=root,
        framework=prof.frameworks[0] if prof.frameworks else None,
        port=prof.run_port,
        kind=kind,
        alternatives={k: v for k, v in prof.commands.items() if k != kind},
    )
