"""Shared application state + authentication for the Vajra Local API.

Everything long-lived (event bus, model router, orchestrator, the agents, the
DB handle, in-flight run bookkeeping) is constructed here once and imported by
the routers. ``main.py`` only wires middleware + routers + lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import Depends, Header, HTTPException

from core.agents.assist_agent import AssistAgent
from core.agents.chat_agent import ChatAgent
from core.agents.complete_agent import CompletionAgent
from core.agents.computer_agent import ComputerAgent
from core.agents.osdev_agent import OsDevAgent
from core.agents.security_agent import SecurityAgent
from core.config import get_settings
from core.events import EventBus
from core.llm import ModelRouter
from core.orchestrator import Orchestrator
from core.orchestrator.approvals import ApprovalGate
from core.security.pairing import identity
from database import get_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("vajra.api")

settings = get_settings()

events = EventBus(settings.log_dir)
approvals = ApprovalGate()
#: chat / inline-assist / completion - the fast model.
model_router = ModelRouter()
#: autonomous multi-step agents - the stronger agent model (see VAJRA_AGENT_MODEL).
agent_router = ModelRouter(role="agent")
orchestrator = Orchestrator(events, approvals, settings, agent_router)
chat_agent = ChatAgent(model_router, orchestrator.registry)
assist_agent = AssistAgent(model_router)
completion_agent = CompletionAgent(model_router)
computer_agent = ComputerAgent(agent_router, approvals, events)
osdev_agent = OsDevAgent(agent_router, approvals, events)
security_agent = SecurityAgent(agent_router, approvals, events)
db = get_database()

#: in-flight background tasks / run snapshots, shared across agent routers
running: dict[str, asyncio.Task] = {}
computer_runs: dict[str, dict] = {}
osdev_runs: dict[str, dict] = {}
security_runs: dict[str, dict] = {}

#: per-IP mutating-request timestamps (rate limit middleware)
rate_buckets: dict[str, list[float]] = {}


# -- auth -----------------------------------------------------------
def authenticates(token: str | None) -> bool:
    """True if the token is the (secure) configured token, the auto-generated
    device secret, or a live per-device credential."""
    if not token:
        return False
    ident = identity()
    if ident.all_tokens_are_secure(settings.vajra_pairing_token) and token == settings.vajra_pairing_token:
        return True
    return ident.accepts(token)


def require_token(
    authorization: str | None = Header(default=None),
    x_vajra_token: str | None = Header(default=None),
) -> None:
    presented = None
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization.split(" ", 1)[1].strip()
    presented = presented or x_vajra_token
    if not authenticates(presented):
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")


AUTH = [Depends(require_token)]


# -- event persistence (started by the lifespan handler) ----------
async def persist_events() -> None:
    async for event in events.subscribe():
        with contextlib.suppress(Exception):
            await db.record_event(event.model_dump())
            if event.kind == "tool.result":
                p = event.payload
                await db.record_tool_call(
                    event.goal_id, event.task_id, p.get("tool"), p.get("success"), p.get("exit_code")
                )
                for path in p.get("changed_files", []) or []:
                    await db.record_file_change(event.goal_id, event.task_id, path)
