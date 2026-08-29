"""Tool registry - validates against policy, executes, returns typed results."""

from __future__ import annotations

import asyncio
import logging

from core.llm.client import ToolSpec
from core.policy.engine import PolicyDecision, PolicyEngine, ToolAction
from core.tools.base import Tool, ToolCall, ToolContext, ToolResult

log = logging.getLogger("vajra.tools")


class ToolRegistry:
    def __init__(self, policy: PolicyEngine) -> None:
        self._tools: dict[str, Tool] = {}
        self._policy = policy

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=t.name, description=t.description, parameters=t.parameters)
            for t in self._tools.values()
        ]

    def check(self, call: ToolCall, ctx: ToolContext) -> PolicyDecision:
        tool = self._tools.get(call.tool_name)
        if tool is None:
            return PolicyDecision(
                allowed=False, requires_approval=False, risk=1,
                reason=f"unknown tool: {call.tool_name}",
            )
        action = ToolAction(
            tool_name=call.tool_name,
            arguments=call.arguments,
            risk_level=tool.risk,
            workspace_root=ctx.workspace_root,
        )
        return self._policy.validate(action)

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(call.tool_name)
        if tool is None:
            return ToolResult.fail(f"unknown tool: {call.tool_name}")
        decision = self.check(call, ctx)
        if not decision.allowed:
            return ToolResult.fail(
                f"policy blocked {call.tool_name}: {decision.reason}",
                metadata={"policy": decision.model_dump()},
            )
        try:
            return await asyncio.wait_for(
                tool.run(ctx, **call.arguments), timeout=tool.timeout_seconds
            )
        except TimeoutError:
            return ToolResult.fail(f"{call.tool_name} timed out", exit_code=124)
        except Exception as exc:  # noqa: BLE001 - surface tool errors as results
            log.exception("tool %s crashed", call.tool_name)
            return ToolResult.fail(f"{type(exc).__name__}: {exc}")


def build_default_registry(policy: PolicyEngine | None = None) -> ToolRegistry:
    from core.tools.fs_tools import (
        CreateDirectoryTool,
        PatchFileTool,
        ReadFileTool,
        WriteFileTool,
    )
    from core.tools.git_tools import (
        GitCheckpointTool,
        GitDiffTool,
        GitRestoreTool,
        GitStatusTool,
    )
    from core.tools.process_tools import RunCommandTool
    from core.tools.quality_tools import RunBuildTool, RunLinterTool, RunTestsTool
    from core.tools.search_tools import ProjectTreeTool, SearchTextTool

    registry = ToolRegistry(policy or PolicyEngine())
    for tool_cls in (
        ReadFileTool,
        WriteFileTool,
        PatchFileTool,
        CreateDirectoryTool,
        SearchTextTool,
        ProjectTreeTool,
        RunCommandTool,
        RunTestsTool,
        RunLinterTool,
        RunBuildTool,
        GitStatusTool,
        GitDiffTool,
        GitCheckpointTool,
        GitRestoreTool,
    ):
        registry.register(tool_cls())
    return registry
