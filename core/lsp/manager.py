"""Pools one language server per (workspace root, language)."""

from __future__ import annotations

import asyncio
import logging

from core.lsp.client import LspClient
from core.lsp.config import lsp_language_id, server_for

log = logging.getLogger("vajra.lsp")


class LspManager:
    def __init__(self) -> None:
        self._clients: dict[tuple[str, str], LspClient] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _lock(self, key: tuple[str, str]) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    async def client(self, root: str, language: str) -> LspClient | None:
        argv = server_for(language)
        if not argv:
            return None
        key = (root, language if language in ("python",) else "ts")
        async with self._lock(key):
            client = self._clients.get(key)
            if client and client.alive:
                return client
            client = LspClient(argv, root)
            try:
                await asyncio.wait_for(client.start(), timeout=25)
            except Exception:  # noqa: BLE001
                log.exception("failed to start language server for %s", language)
                await client.stop()
                return None
            self._clients[key] = client
            return client

    async def sync(self, root: str, path: str, content: str, language: str) -> LspClient | None:
        client = await self.client(root, language)
        if client:
            await client.sync(path, content, lsp_language_id(language))
        return client

    async def shutdown_all(self) -> None:
        for client in list(self._clients.values()):
            await client.stop()
        self._clients.clear()

    def status(self) -> list[dict]:
        return [
            {"root": r, "language": lang, "alive": c.alive}
            for (r, lang), c in self._clients.items()
        ]


lsp_manager = LspManager()
