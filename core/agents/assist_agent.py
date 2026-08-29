"""Assisted-coding operations (manual v3.0 section 3.4).

The user selects code (or a whole file) and asks for one of a fixed set of
actions. For edit actions the agent returns a *proposed* full-file rewrite plus a
unified diff - it never writes. The Studio shows the diff and the user accepts
(-> /api/files/write) or rejects. Explain / Security Review return prose only.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Literal

from core.llm import ChatMessage, ModelRouter

AssistAction = Literal[
    "explain", "fix", "refactor", "optimize", "tests", "document", "security", "edit"
]

_PROSE_ACTIONS = {"explain", "security"}

_ACTION_BRIEF: dict[str, str] = {
    "explain": "Explain what the selected code does, clearly and concisely.",
    "fix": "Find and fix bugs or errors in the selected code. Keep the change minimal.",
    "refactor": "Refactor the selected code for clarity and structure without changing behaviour.",
    "optimize": "Optimize the selected code for performance without changing behaviour.",
    "tests": "Write focused unit tests for the selected code. Add them in the most idiomatic place.",
    "document": "Add or improve docstrings / comments for the selected code. Do not change logic.",
    "security": "Review the selected code for security issues and describe them with severity and fixes.",
    "edit": "Apply the user's instruction to the selected code.",
}

_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\n(.*?)```", re.DOTALL)


def _match_newlines(text: str, reference: str) -> str:
    """Rewrite `text` to use whatever newline style dominates `reference`,
    so a model reply (always \\n) diffs cleanly against a CRLF file."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if reference.count("\r\n") > reference.count("\n") - reference.count("\r\n"):
        return normalized.replace("\n", "\r\n")
    return normalized


@dataclass
class AssistResult:
    kind: Literal["prose", "edit"]
    text: str = ""              # prose answer, or a short note for edits
    new_content: str | None = None
    diff: str | None = None


class AssistAgent:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    async def run(
        self,
        action: AssistAction,
        path: str,
        file_content: str,
        selection: str | None = None,
        instruction: str | None = None,
        language: str = "",
    ) -> AssistResult:
        brief = _ACTION_BRIEF.get(action, _ACTION_BRIEF["edit"])
        target = selection.strip() if selection else ""
        scope = "the selected snippet" if target else "the whole file"

        if action in _PROSE_ACTIONS:
            sys = (
                "You are Vajra's assisted-coding helper. Answer in clear prose with short "
                "markdown bullets where useful. Do not return the file or a diff."
            )
            user = (
                f"File: {path} ({language or 'unknown'})\n\n"
                f"{brief}\nScope: {scope}.\n\n"
                f"```\n{target or file_content}\n```"
            )
            resp = await self.router.complete(
                [ChatMessage(role="system", content=sys), ChatMessage(role="user", content=user)],
                max_tokens=900,
            )
            return AssistResult(kind="prose", text=resp.text.strip())

        # edit actions -> propose a full-file rewrite
        sys = (
            "You are Vajra's assisted-coding editor. You will be given a source file and a "
            "task. Return the COMPLETE updated file inside a single fenced code block and "
            "nothing else - no explanation before or after. Preserve unrelated code, "
            "imports, formatting and the file's existing style exactly."
        )
        instr = f"{brief}"
        if instruction:
            instr += f"\nUser instruction: {instruction}"
        if target:
            instr += f"\n\nFocus on this selection:\n```\n{target}\n```"
        user = f"Task: {instr}\n\nFile `{path}`:\n```{language}\n{file_content}\n```"

        resp = await self.router.complete(
            [ChatMessage(role="system", content=sys), ChatMessage(role="user", content=user)],
            temperature=0.1,
            max_tokens=4000,
        )
        new_content = self._extract_file(resp.text, fallback=file_content)
        new_content = _match_newlines(new_content, file_content)
        if new_content == file_content:
            return AssistResult(kind="edit", text="No change proposed.", new_content=None, diff="")
        diff = "".join(
            difflib.unified_diff(
                file_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return AssistResult(kind="edit", text=f"Proposed {action}", new_content=new_content, diff=diff)

    @staticmethod
    def _extract_file(text: str, fallback: str) -> str:
        blocks = _FENCE.findall(text or "")
        if blocks:
            # the largest fenced block is almost always the file
            return max(blocks, key=len).rstrip("\n") + "\n"
        stripped = (text or "").strip()
        return stripped + "\n" if stripped else fallback
