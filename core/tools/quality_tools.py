"""Quality-gate tools: detect and run tests / linters / builds for the workspace."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from core.policy.engine import RiskLevel
from core.tools.base import Tool, ToolContext, ToolResult
from core.tools.process_tools import RunCommandTool


def _python_for(root: Path) -> str:
    """The interpreter to run pytest/ruff with: the workspace venv if it has one,
    else the interpreter running the Core (which has pytest/ruff from [dev])."""
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python", "venv/Scripts/python.exe", "venv/bin/python"):
        cand = root / rel
        if cand.exists():
            return str(cand)
    return sys.executable


def _has_pytest_layout(root: Path) -> bool:
    return (
        (root / "pyproject.toml").exists()
        or (root / "pytest.ini").exists()
        or (root / "tox.ini").exists()
        or (root / "setup.cfg").exists()
        or (root / "tests").is_dir()
        or any(root.glob("test_*.py"))
        or any(root.glob("*_test.py"))
        or any(root.glob("*/test_*.py"))
    )


def _detect(root: Path) -> dict[str, list[str]]:
    cmds: dict[str, list[str]] = {}
    if _has_pytest_layout(root):
        py = _python_for(root)
        cmds["test"] = [py, "-m", "pytest", "-q"]
        cmds["lint"] = [py, "-m", "ruff", "check", "."]
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
