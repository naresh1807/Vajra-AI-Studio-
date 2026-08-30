"""Focused-context assembly for agents (manual v3.0 PRIORITY 18).

Do not send whole repositories to the model. Build the smallest useful context:

    Task -> semantic search -> relevant files -> uncommitted diff -> editor focus
         -> project memory -> profiled summary

Every source is best-effort: a failure in one never blocks a run.
"""

from __future__ import annotations

import contextlib
import logging

from core.agents.base import AgentContext
from core.memory import WorkspaceMemory
from core.rag import rag_manager
from core.runtime import git as gitsvc
from core.security.redaction import redact_secrets
from core.workspace import discover_workspace

log = logging.getLogger("vajra.agents.context")

_MAX_RETRIEVED_CHARS = 6000
_MAX_DIFF_CHARS = 4000
_MAX_FOCUS_CHARS = 4000


def _summarize(profile) -> str:
    return (
        f"languages={profile.languages} frameworks={profile.frameworks} "
        f"pkg={profile.package_managers} commands={profile.commands} "
        f"db={profile.database} docker={profile.has_docker} git={profile.has_git} "
        f"entrypoints={profile.entrypoints} dirs={profile.important_dirs}"
    )


def _format_hits(hits) -> str:
    out: list[str] = []
    budget = _MAX_RETRIEVED_CHARS
    for h in hits:
        snippet = redact_secrets(h.text.strip(), h.path)[0]
        block = f"## {h.path}:{h.start_line}-{h.end_line}\n{snippet}\n"
        if len(block) > budget:
            break
        out.append(block)
        budget -= len(block)
    return "\n".join(out)


async def build_context(
    goal: str,
    workspace_root: str,
    *,
    focus: str = "",
    task_instruction: str = "",
    retrieve_query: str | None = None,
) -> AgentContext:
    """Assemble an :class:`AgentContext` with focused, size-bounded context."""
    summary = ""
    with contextlib.suppress(Exception):
        summary = _summarize(discover_workspace(workspace_root))

    memory_context = ""
    with contextlib.suppress(Exception):
        memory_context = WorkspaceMemory(workspace_root).recent_context()

    retrieved = ""
    try:
        hits = await rag_manager.retrieve(workspace_root, retrieve_query or goal, k=6)
        retrieved = _format_hits(hits)
    except Exception as exc:  # noqa: BLE001
        log.debug("rag retrieve failed: %s", exc)

    working_diff = ""
    try:
        raw_diff = (await gitsvc.diff(workspace_root))[:_MAX_DIFF_CHARS]
        working_diff = redact_secrets(raw_diff)[0]
    except Exception as exc:  # noqa: BLE001
        log.debug("git diff failed: %s", exc)

    return AgentContext(
        goal=goal,
        workspace_root=workspace_root,
        workspace_summary=summary,
        memory_context=memory_context,
        task_instruction=task_instruction,
        retrieved=retrieved,
        working_diff=working_diff,
        focus=(focus or "")[:_MAX_FOCUS_CHARS],
    )
