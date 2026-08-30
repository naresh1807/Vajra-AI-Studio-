"""Tool primitives. Tools are small, deterministic, typed capabilities.

An agent proposes a ToolCall; the policy engine validates it; the registry
executes it and returns a ToolResult. Agents hold reasoning; tools hold execution.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.policy.engine import RiskLevel


class ToolContext(BaseModel):
    workspace_root: str
    goal_id: str | None = None
    task_id: str | None = None

    @property
    def root(self) -> Path:
        return Path(self.workspace_root).resolve()

    def resolve(self, relative: str, *, allow_outside: bool = False) -> Path:
        """Resolve a path. By default it must stay inside the workspace root
        (raises PathEscape otherwise); `system` tools that legitimately act on
        the wider machine pass allow_outside=True."""
        if allow_outside or not self.workspace_root:
            p = Path(relative)
            return (self.root / p).resolve() if not p.is_absolute() else p.resolve()
        from core.workspace.safepath import safe_resolve

        return safe_resolve(self.workspace_root, relative)


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: dict[str, Any] = {}


class ToolResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    changed_files: list[str] = []
    exit_code: int | None = None
    artifacts: list[str] = []
    metadata: dict[str, Any] = {}

    @classmethod
    def ok(cls, stdout: str = "", **kw: Any) -> ToolResult:
        return cls(success=True, stdout=stdout, **kw)

    @classmethod
    def fail(cls, stderr: str, exit_code: int | None = 1, **kw: Any) -> ToolResult:
        return cls(success=False, stderr=stderr, exit_code=exit_code, **kw)


class Tool(ABC):
    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW
    timeout_seconds: int = 60
    #: computer-agent tools that legitimately act outside any workspace
    system: bool = False
    #: JSON-schema for arguments (OpenAI function-calling compatible)
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    @abstractmethod
    async def run(self, ctx: ToolContext, **kwargs: Any) -> ToolResult: ...

    @property
    def requires_approval(self) -> bool:
        return self.risk >= RiskLevel.ELEVATED
