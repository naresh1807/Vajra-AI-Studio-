"""Quality-gate tools: detect and run tests / linters / builds for the workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult
from core.tools.process_tools import RunCommandTool


def _detect(root: Path) -> dict[str, list[str]]:
    cmds: dict[str, list[str]] = {}
    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
        cmds["test"] = ["python", "-m", "pytest", "-q"]
        cmds["lint"] = ["python", "-m", "ruff", "check", "."]
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        if "test" in scripts:
            cmds.setdefault("test", ["npm", "test", "--silent"])
        if "lint" in scripts:
            cmds.setdefault("lint", ["npm", "run", "lint", "--silent"])
        if "build" in scripts:
            cmds.setdefault("build", ["npm", "run", "build", "--silent"])
    if (root / "Cargo.toml").exists():
        cmds.setdefault("test", ["cargo", "test"])
        cmds.setdefault("build", ["cargo", "build"])
    return cmds


class _QualityTool(Tool):
    gate: str = "test"
    risk = RiskLevel.MEDIUM
    timeout_seconds = 600
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        cmds = _detect(ctx.root)
        argv = cmds.get(self.gate)
        if not argv:
            return ToolResult.fail(f"no {self.gate} command detected for this workspace")
        runner = RunCommandTool()
        result = await runner.run(ctx, command=argv, timeout_seconds=self.timeout_seconds)
        result.metadata["gate"] = self.gate
        return result


class RunTestsTool(_QualityTool):
    name = "run_tests"
    description = "Detect and run the workspace test suite."
    gate = "test"


class RunLinterTool(_QualityTool):
    name = "run_linter"
    description = "Detect and run the workspace linter."
    gate = "lint"


class RunBuildTool(_QualityTool):
    name = "run_build"
    description = "Detect and run the workspace build."
    gate = "build"
