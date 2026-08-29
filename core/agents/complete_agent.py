"""Inline (ghost-text) completions - manual v3.0 section 3.4.

Given the text before and after the cursor, ask the model for a short
continuation. Kept deliberately small and fast: low temperature, tight token
cap, trimmed to at most a few lines, with an in-memory cache so identical
cursor contexts don't re-hit the model.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict

from core.llm import ChatMessage, ModelRouter

_MAX_PREFIX = 2500
_MAX_SUFFIX = 700
_MAX_NEW_TOKENS = 160
_CACHE_SIZE = 200

_SYSTEM = (
    "You are an inline code completion engine inside an IDE. Continue the code at the "
    "cursor. Output ONLY the raw code that should be inserted - no markdown fences, no "
    "explanation, no repetition of the text before the cursor. Prefer completing the "
    "current statement or a small block. If nothing sensible should be inserted, output "
    "nothing."
)

# Reasoning-model chatter we must never surface as a suggestion.
_REASON_START = re.compile(
    r"^\s*(here'?s a thinking|let'?s|we need to|the user|okay,|first,|i (?:need|should|will)|"
    r"\d+\.\s|analy[sz]e|step \d|to (?:complete|solve|implement))",
    re.IGNORECASE,
)
_THINK_TAG = re.compile(r"</think>|</reasoning>|\bfinal answer:\s*", re.IGNORECASE)


class CompletionAgent:
    def __init__(self, router: ModelRouter) -> None:
        self.router = router
        self._cache: OrderedDict[str, str] = OrderedDict()

    @staticmethod
    def _key(prefix: str, suffix: str, language: str) -> str:
        h = hashlib.sha1(f"{language}\0{prefix[-400:]}\0{suffix[:200]}".encode()).hexdigest()
        return h

    def _cache_get(self, key: str) -> str | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)

    async def complete(
        self, prefix: str, suffix: str, language: str = "", path: str = "", max_lines: int = 6
    ) -> str:
        prefix = prefix[-_MAX_PREFIX:]
        suffix = suffix[:_MAX_SUFFIX]
        if not prefix.strip():
            return ""
        key = self._key(prefix, suffix, language)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        user = (
            f"File: {path or 'untitled'} ({language or 'text'})\n"
            f"<code_before_cursor>\n{prefix}\n</code_before_cursor>\n"
            f"<code_after_cursor>\n{suffix}\n</code_after_cursor>\n"
            "Insert code at the cursor:"
        )
        try:
            resp = await self.router.complete(
                [ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=user)],
                temperature=0.05,
                max_tokens=_MAX_NEW_TOKENS,
            )
        except Exception:  # noqa: BLE001
            return ""

        text = _strip(resp.text or "")
        # if the model echoed the tail of the prefix, drop the overlap
        tail = prefix[-40:]
        if tail and text.startswith(tail):
            text = text[len(tail):]
        lines = text.split("\n")
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines])
        self._cache_put(key, text)
        return text


def _strip(text: str) -> str:
    text = text or ""
    # if the model emitted reasoning then an answer, keep only what's after the marker
    if _THINK_TAG.search(text):
        text = _THINK_TAG.split(text)[-1]
    # pull a fenced block if present
    fence = re.search(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).rstrip()
    text = text.strip("\n")
    # reject leaked chain-of-thought
    if _REASON_START.match(text):
        return ""
    return text.rstrip()
