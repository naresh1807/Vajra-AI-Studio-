"""Agent base. Agents hold reasoning policy; they propose tool calls and never
execute anything directly. A single LLM turn with tools is the core primitive.
"""

from __future__ import annotations

import json
from abc import ABC

from pydantic import BaseModel

from core.llm import ChatMessage, ModelRouter
from core.tools import ToolCall, ToolContext, ToolRegistry


class AgentContext(BaseModel):
    goal: str
    workspace_root: str
    workspace_summary: str = ""
    memory_context: str = ""
    task_instruction: str = ""
    scratch: dict = {}


class AgentAction(BaseModel):
    reasoning: str = ""
    tool_calls: list[ToolCall] = []
    final_message: str = ""

    @property
    def is_terminal(self) -> bool:
        return not self.tool_calls


class Agent(ABC):
    name: str
    system_prompt: str
    #: tool names this agent is allowed to call; empty = all
    allowed_tools: tuple[str, ...] = ()
    max_tokens: int = 2048
    temperature: float = 0.2

    def __init__(self, router: ModelRouter, registry: ToolRegistry) -> None:
        self.router = router
        self.registry = registry

    def _tool_specs(self):
        specs = self.registry.specs()
        if self.allowed_tools:
            specs = [s for s in specs if s.name in self.allowed_tools]
        return specs

    def _build_messages(self, ctx: AgentContext, history: list[ChatMessage]) -> list[ChatMessage]:
        preamble = (
            f"{self.system_prompt}\n\n"
            f"# Goal\n{ctx.goal}\n\n"
            f"# Workspace\n{ctx.workspace_summary or '(not yet profiled)'}\n\n"
            f"# Project memory\n{ctx.memory_context or '(empty)'}\n\n"
            f"# Your task\n{ctx.task_instruction}\n\n"
            "Propose tool calls to make progress. When the task's success criteria are met, "
            "reply with a short final summary and no tool calls."
        )
        return [ChatMessage(role="system", content=preamble), *history]

    async def propose_action(
        self, ctx: AgentContext, history: list[ChatMessage] | None = None
    ) -> AgentAction:
        messages = self._build_messages(ctx, history or [])
        resp = await self.router.complete(
            messages,
            tools=self._tool_specs() or None,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        calls = [ToolCall(tool_name=c.name, arguments=c.arguments) for c in resp.tool_calls]
        return AgentAction(reasoning=resp.text, tool_calls=calls, final_message=resp.text)

    @staticmethod
    def tool_result_message(call: ToolCall, result_json: str) -> ChatMessage:
        return ChatMessage(
            role="user",
            content=f"[tool:{call.tool_name}] result:\n{result_json}",
        )

    @staticmethod
    def dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)[:8000]

    def to_tool_context(self, ctx: AgentContext, goal_id: str, task_id: str) -> ToolContext:
        return ToolContext(workspace_root=ctx.workspace_root, goal_id=goal_id, task_id=task_id)
