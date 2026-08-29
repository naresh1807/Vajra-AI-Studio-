"""Computer Agent (manual v3.0 section 11).

Turns a natural-language computer request into safe local actions *outside* the
project workspace: resolve known folders, create folders/files, find files,
open paths/apps, inspect processes, and (last resort) run a PowerShell script.
Every mutating action is approval-gated through the same gate the developer
agent uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.orchestrator.approvals import ApprovalGate
from core.tools import ToolCall, ToolContext, ToolRegistry, build_computer_registry

_SYSTEM = (
    "You are Vajra's Computer Agent. You operate the user's own machine to carry out "
    "computer tasks that are outside any code project.\n"
    "\n"
    "Method, in priority order: prefer a native tool (resolve_known_folder, create_folder, "
    "write_desktop_file, open_path, open_app, find_files, list_dir, computer_list_processes). "
    "Use run_powershell only when nothing else fits, and keep the script minimal and scoped.\n"
    "\n"
    "Rules: never guess an absolute path - resolve known folders (desktop, documents, "
    "downloads, home) with resolve_known_folder first. Do exactly what was asked, nothing "
    "more. Mutating actions will pause for the user's approval; that is expected. When the "
    "task is done, reply with a one-line confirmation of what you did and no tool calls."
)

_MAX_TURNS = 8


@dataclass
class ComputerResult:
    reply: str
    actions: list[dict] = field(default_factory=list)
    succeeded: bool = True


class ComputerAgent:
    def __init__(
        self,
        router: ModelRouter,
        approvals: ApprovalGate,
        events: EventBus,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.router = router
        self.approvals = approvals
        self.events = events
        self.registry = registry or build_computer_registry()
        self.system_prompt = _SYSTEM
        self.kind = "computer"
        self.max_turns = _MAX_TURNS

    async def run(self, run_id: str, instruction: str) -> ComputerResult:
        ctx = ToolContext(workspace_root="", goal_id=run_id)
        history: list[ChatMessage] = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=instruction),
        ]
        result = ComputerResult(reply="")
        await self.events.record("goal.created", goal_id=run_id, goal=instruction, kind_hint=self.kind)

        for _turn in range(self.max_turns):
            resp = await self.router.complete(history, tools=self.registry.specs(), max_tokens=1200)
            result.reply = resp.text.strip() or result.reply
            if not resp.tool_calls:
                break
            history.append(ChatMessage(role="assistant", content=resp.text or ""))
            for raw in resp.tool_calls:
                call = ToolCall(tool_name=raw.name, arguments=raw.arguments)
                await self.events.record(
                    "tool.call", goal_id=run_id, tool=call.tool_name, arguments=call.arguments
                )
                decision = self.registry.check(call, ctx)
                approved = True
                if decision.requires_approval:
                    approved = await self._approve(run_id, call, decision.reason)
                if not approved:
                    payload = {"success": False, "error": "user rejected the action"}
                else:
                    res = await self.registry.execute(call, ctx, approved=True)
                    payload = res.model_dump()
                    result.actions.append(
                        {"tool": call.tool_name, "arguments": call.arguments, "success": res.success}
                    )
                await self.events.record(
                    "tool.result", goal_id=run_id, tool=call.tool_name,
                    success=payload.get("success"), changed_files=payload.get("changed_files", []),
                )
                summary = json.dumps(payload, default=str)[:5000]
                history.append(
                    ChatMessage(role="user", content=f"[tool:{call.tool_name}] {summary}")
                )

        result.succeeded = all(a["success"] for a in result.actions) if result.actions else True
        await self.events.record(
            "report", goal_id=run_id, succeeded=result.succeeded,
            actions=[a["tool"] for a in result.actions],
        )
        return result

    async def _approve(self, run_id: str, call: ToolCall, reason: str) -> bool:
        pa = self.approvals.create(run_id, "computer", call.tool_name, call.arguments, reason)
        await self.events.record(
            "approval.requested", goal_id=run_id, approval_id=pa.id,
            tool=call.tool_name, reason=reason, arguments=call.arguments,
        )
        verdict = await self.approvals.wait(pa.id)
        await self.events.record("approval.resolved", goal_id=run_id, approval_id=pa.id, verdict=verdict)
        return verdict == "approved"
