"""Tracks active debug sessions."""

from __future__ import annotations

from core.dap.session import DapSession, EventCb


class DapManager:
    def __init__(self) -> None:
        self._sessions: dict[str, DapSession] = {}

    async def start(
        self,
        root: str,
        program: str,
        args: list[str] | None = None,
        breakpoints: dict[str, list[int]] | None = None,
        on_event: EventCb = None,
    ) -> DapSession:
        session = DapSession(root, program, args, on_event)
        await session.start(breakpoints)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> DapSession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[DapSession]:
        return list(self._sessions.values())

    async def stop(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        await session.stop()
        return True

    async def shutdown_all(self) -> None:
        for sid in list(self._sessions):
            await self.stop(sid)


dap_manager = DapManager()
