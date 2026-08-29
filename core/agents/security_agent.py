"""Authorized-Security Agent (manual v3.0 Phase 10).

Defensive posture only. Runs dependency / secret / config audits against the
open project freely; any active check (port scan, HTTP audit) requires a named,
non-expired scope profile that lists the target and is approval-gated. The
agent has no exploitation, DoS, brute-force, persistence or evasion tools and
must decline requests for them.
"""

from __future__ import annotations

from core.agents.computer_agent import ComputerAgent
from core.events import EventBus
from core.llm import ModelRouter
from core.orchestrator.approvals import ApprovalGate
from core.tools import ToolRegistry
from core.tools.registry import build_security_registry

_SYSTEM = (
    "You are Vajra's Authorized-Security Agent. You do defensive security work: "
    "auditing and hardening the user's own project, and connect-only checks "
    "against systems the user is explicitly authorized to test.\n"
    "\n"
    "Method:\n"
    "1. For the open project, run dependency_audit, secret_scan and config_audit "
    "and summarize the findings with concrete fixes.\n"
    "2. For any check against a host or URL, first call security_scopes. Only "
    "proceed with port_scan / http_audit if a valid scope profile lists that "
    "target; pass the scope name. These pause for approval - that is expected.\n"
    "\n"
    "Refuse, clearly, any request to exploit, brute-force, disrupt (DoS), gain "
    "persistence, move laterally, exfiltrate data, or evade detection - and any "
    "test of a system that is not in an authorized scope. Offer the defensive "
    "alternative instead. End with a short findings summary, no tool calls."
)

_MAX_TURNS = 12


class SecurityAgent(ComputerAgent):
    def __init__(
        self,
        router: ModelRouter,
        approvals: ApprovalGate,
        events: EventBus,
        registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(router, approvals, events, registry or build_security_registry())
        self.system_prompt = _SYSTEM
        self.kind = "security"
        self.max_turns = _MAX_TURNS
