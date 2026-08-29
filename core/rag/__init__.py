"""RAG: local semantic index over the workspace (manual v3.0 core/rag).

Offline by default (lexical vectors); point ``VAJRA_EMBED_BASE_URL`` at any
OpenAI-compatible /embeddings endpoint for real embeddings.
"""

from __future__ import annotations

import asyncio

from core.rag.index import Hit, RagIndex

__all__ = ["Hit", "RagIndex", "RagManager", "rag_manager"]


class RagManager:
    """Pools one RagIndex per workspace root."""

    def __init__(self) -> None:
        self._indexes: dict[str, RagIndex] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _key(self, root: str) -> str:
        from pathlib import Path

        return str(Path(root).resolve())

    def index(self, root: str) -> RagIndex:
        key = self._key(root)
        idx = self._indexes.get(key)
        if idx is None:
            idx = RagIndex(root)
            self._indexes[key] = idx
        return idx

    async def reindex(self, root: str) -> dict:
        key = self._key(root)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            idx = self.index(root)
            return await asyncio.to_thread(idx.reindex)

    async def retrieve(self, root: str, query: str, k: int = 6) -> list[Hit]:
        idx = self.index(root)
        return await asyncio.to_thread(idx.search, query, k)

    def status(self, root: str) -> dict:
        return self.index(root).status()


rag_manager = RagManager()
