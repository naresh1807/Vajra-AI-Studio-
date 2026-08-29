"""Assembles the message list sent to the model: a base system prompt plus
titled context sections (workspace summary, retrieved code, tool notes) and the
conversation history. Keeps prompt construction in one place instead of ad-hoc
string concatenation in every agent.
"""

from __future__ import annotations

from core.llm.nemotron_client import ChatMessage


class PromptBuilder:
    def __init__(self, system: str) -> None:
        self._system = system.rstrip()
        self._sections: list[tuple[str, str]] = []

    def add_section(self, title: str, body: str) -> PromptBuilder:
        if body and body.strip():
            self._sections.append((title, body.strip()))
        return self

    def system_message(self) -> ChatMessage:
        text = self._system
        for title, body in self._sections:
            text += f"\n\n# {title}\n{body}"
        return ChatMessage(role="system", content=text)

    def build(self, history: list[ChatMessage]) -> list[ChatMessage]:
        return [self.system_message(), *history]
