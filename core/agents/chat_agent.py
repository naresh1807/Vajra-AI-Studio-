"""Conversational agent - the Claude Code-style chat surface.

Multi-turn. Given the conversation history and (optionally) a workspace, it can
use READ-ONLY tools to look at the code before answering. Anything that writes
files or runs commands goes through the autonomous goal path instead, so chat
stays safe to run without approval prompts.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from core.llm import ChatMessage, ModelRouter, ToolSpec
from core.tools import ToolCall, ToolContext, ToolRegistry

READ_ONLY_TOOLS = (
    "read_file", "search_text", "semantic_search", "project_tree", "git_status", "git_diff",
)

_SYSTEM = (
    "You are Vajra, a personal engineering assistant embedded in the Vajra AI Studio IDE. "
    "Be concise and direct, like a senior engineer pairing over the shoulder.\n"
    "\n"
    "RESPONSE FORMAT: reply in plain conversational prose. Use short paragraphs and, when "
    "helpful, markdown bullet points or a fenced code block for actual code. Never answer "
    "with a JSON object, a YAML/JSON task plan, or a tool-call schema - the user wants a "
    "human answer, not a machine payload.\n"
    "\n"
    "CAPABILITIES: you have read-only tools to inspect the currently open workspace - use "
    "them before answering questions about the code. From this chat you CANNOT edit files, "
    "run commands, or act on the computer. If the user asks you to make a change or perform "
    "an action, briefly say what you would do in one or two sentences and tell them to "
    "switch this panel to Agent mode (top-right) and send the same request there."
)

_MAX_TOOL_HOPS = 5


@dataclass
class ChatTurn:
    reply: str
    tool_calls: list[dict]
    model: str
    provider: str


class ChatAgent:
    def __init__(self, router: ModelRouter, registry: ToolRegistry) -> None:
        self.router = router
        self.registry = registry

    def _specs(self, workspace_root: str | None) -> list[ToolSpec] | None:
        if not workspace_root:
            return None
        return [s for s in self.registry.specs() if s.name in READ_ONLY_TOOLS]

    def _prime(self, history: list[ChatMessage], workspace_summary: str) -> list[ChatMessage]:
        sys = _SYSTEM
        if workspace_summary:
            sys += f"\n\n# Current workspace\n{workspace_summary}"
        return [ChatMessage(role="system", content=sys), *history]

    async def _retrieve(self, workspace_root: str | None, history: list[ChatMessage]) -> str:
        """Pull the most relevant workspace chunks for the latest user turn."""
        if not workspace_root:
            return ""
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
        if len(last_user.strip()) < 8:
            return ""
        try:
            from core.rag import rag_manager

            hits = await rag_manager.retrieve(workspace_root, last_user, k=4)
        except Exception:  # noqa: BLE001 - retrieval is best-effort
            return ""
        hits = [h for h in hits if h.score > 0.15]
        if not hits:
            return ""
        blocks = "\n\n".join(f"# {h.ref}\n{h.text}" for h in hits)
        return (
            "Relevant code from the workspace (retrieved automatically - cite paths, "
            "and read the full file if you need more):\n\n" + blocks
        )

    async def respond(
        self,
        history: list[ChatMessage],
        workspace_root: str | None = None,
        workspace_summary: str = "",
    ) -> ChatTurn:
        turn = ChatTurn(reply="", tool_calls=[], model="", provider="")
        messages = self._prime(history, workspace_summary)
        specs = self._specs(workspace_root)
        tool_ctx = ToolContext(workspace_root=workspace_root) if workspace_root else None

        retrieved = await self._retrieve(workspace_root, history)
        if retrieved:
            messages.insert(1, ChatMessage(role="user", content=retrieved))

        for _hop in range(_MAX_TOOL_HOPS):
            resp = await self.router.complete(messages, tools=specs, max_tokens=1200)
            turn.model, turn.provider = resp.model, resp.provider
            if not resp.tool_calls:
                turn.reply = resp.text.strip()
                return turn

            messages.append(ChatMessage(role="assistant", content=resp.text or ""))
            for call in resp.tool_calls:
                tc = ToolCall(tool_name=call.name, arguments=call.arguments)
                result = (
                    await self.registry.execute(tc, tool_ctx)
                    if tool_ctx and call.name in READ_ONLY_TOOLS
                    else None
                )
                payload = (
                    result.model_dump()
                    if result
                    else {"success": False, "error": "tool not available in chat"}
                )
                turn.tool_calls.append({"tool": call.name, "arguments": call.arguments,
                                        "success": bool(payload.get("success"))})
                messages.append(
                    ChatMessage(
                        role="user",
                        content=f"[tool:{call.name}] -> {json.dumps(payload, default=str)[:6000]}",
                    )
                )

        # ran out of hops - ask for a plain answer
        messages.append(ChatMessage(role="user", content="Answer now in plain text, no more tools."))
        final = await self.router.complete(messages, max_tokens=1000)
        turn.reply = final.text.strip()
        return turn

    async def stream_events(
        self, history: list[ChatMessage], workspace_root: str | None, workspace_summary: str
    ) -> AsyncIterator[dict]:
        """Coarse-grained streaming: emits tool activity then the final reply."""
        turn = await self.respond(history, workspace_root, workspace_summary)
        for tc in turn.tool_calls:
            yield {"type": "tool", **tc}
        yield {"type": "reply", "text": turn.reply, "model": f"{turn.provider}:{turn.model}"}
