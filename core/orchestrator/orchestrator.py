"""The autonomous execution loop.

    OBSERVE -> UNDERSTAND -> PLAN -> SELECT AGENT+TOOL -> POLICY CHECK -> EXECUTE
    -> VERIFY -> (pass: record + next) / (fail: diagnose -> patch/re-plan -> retry)

Bounded retries; never an infinite loop. Every step emits a structured event.
"""

from __future__ import annotations

import asyncio
import logging

from core.agents.base import AgentContext
from core.agents.specialists import PlannerAgent, build_agent_team
from core.config import Settings, get_settings
from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.memory import WorkspaceMemory
from core.orchestrator.approvals import ApprovalGate
from core.orchestrator.task_graph import TaskGraph, TaskState
from core.policy.engine import PolicyEngine
from core.tools import ToolCall, ToolContext, ToolRegistry, build_default_registry
from core.workspace import discover_workspace

log = logging.getLogger("vajra.orchestrator")

_MAX_AGENT_TURNS = 6
_MAX_GRAPH_STEPS = 60


class Orchestrator:
    def __init__(
        self,
        events: EventBus,
        approvals: ApprovalGate,
        settings: Settings | None = None,
        router: ModelRouter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.events = events
        self.approvals = approvals
        self.router = router or ModelRouter()
        self.policy = PolicyEngine(autonomy_enabled=self.settings.vajra_autonomy_enabled)
        self.registry: ToolRegistry = build_default_registry(self.policy)
        self.agents = build_agent_team(self.router, self.registry)
        self.planner = PlannerAgent(self.router, self.registry)
        self._graphs: dict[str, TaskGraph] = {}
        self._cancelled: set[str] = set()

    # -- public API -----------------------------------------------------------
    def graph(self, goal_id: str) -> TaskGraph | None:
        return self._graphs.get(goal_id)

    def cancel(self, goal_id: str) -> bool:
        if goal_id in self._graphs:
            self._cancelled.add(goal_id)
            return True
        return False

    async def execute_goal(self, goal_id: str, goal: str, workspace_root: str) -> dict:
        profile = discover_workspace(workspace_root)
        memory = WorkspaceMemory(workspace_root)
        summary = self._summarize(profile)
        await self.events.record(
            "goal.created", goal_id=goal_id, goal=goal, workspace=workspace_root, stack=summary
        )

        ctx = AgentContext(
            goal=goal,
            workspace_root=workspace_root,
            workspace_summary=summary,
            memory_context=memory.recent_context(),
        )
        graph = await self.planner.create_task_graph(
            goal_id, ctx, max_retries=self.settings.vajra_max_retries
        )
        self._graphs[goal_id] = graph
        await self.events.record(
            "plan.created", goal_id=goal_id,
            tasks=[{"id": t.id, "title": t.title, "agent": t.agent} for t in graph.tasks],
        )

        steps = 0
        changed_files: list[str] = []
        while not graph.complete and steps < _MAX_GRAPH_STEPS:
            if goal_id in self._cancelled:
                await self.events.record("task.failed", goal_id=goal_id, reason="cancelled by user")
                break
            task = graph.next_ready_task()
            if task is None:
                break
            steps += 1
            graph.mark_running(task)
            await self.events.record(
                "task.started", goal_id=goal_id, task_id=task.id,
                title=task.title, agent=task.agent, attempt=task.attempts,
            )
            try:
                ok, note, files = await self._run_task(goal_id, task, ctx)
                changed_files.extend(files)
            except Exception as exc:  # noqa: BLE001
                ok, note = False, f"{type(exc).__name__}: {exc}"
                log.exception("task %s crashed", task.id)

            if ok:
                graph.mark_passed(task, note)
                await self.events.record(
                    "task.completed", goal_id=goal_id, task_id=task.id, summary=note
                )
            else:
                disposition = graph.mark_failed(task, note)
                await self.events.record(
                    "task.failed", goal_id=goal_id, task_id=task.id,
                    error=note, disposition=disposition,
                )
                if disposition == "replan":
                    await self._insert_debug_task(graph, task)

        result = {
            "goal_id": goal_id,
            "succeeded": graph.succeeded,
            "progress": graph.progress(),
            "changed_files": sorted(set(changed_files)),
            "tasks": [t.model_dump() for t in graph.tasks],
        }
        memory.record_task(goal, "passed" if graph.succeeded else "failed", result["changed_files"])
        await self.events.record("report", goal_id=goal_id, **result)
        self._cancelled.discard(goal_id)
        return result

    # -- internals ----------------------------------------------------------
    async def _run_task(
        self, goal_id: str, task, ctx: AgentContext
    ) -> tuple[bool, str, list[str]]:
        agent = self.agents.get(task.agent)
        if agent is None:
            return False, f"no agent named {task.agent}", []
        task_ctx = AgentContext(
            **{
                **ctx.model_dump(),
                "task_instruction": f"{task.instruction}\nSuccess: {task.success_criteria}",
            }
        )
        tool_ctx = ToolContext(workspace_root=ctx.workspace_root, goal_id=goal_id, task_id=task.id)
        history: list[ChatMessage] = []
        changed: list[str] = []
        last_text = ""

        for _turn in range(_MAX_AGENT_TURNS):
            action = await agent.propose_action(task_ctx, history)
            last_text = action.final_message or last_text
            if action.is_terminal:
                break
            for call in action.tool_calls:
                await self.events.record(
                    "tool.call", goal_id=goal_id, task_id=task.id,
                    tool=call.tool_name, arguments=call.arguments,
                )
                decision = self.registry.check(call, tool_ctx)
                if decision.requires_approval:
                    granted = await self._request_approval(goal_id, task.id, call, decision.reason)
                    if not granted:
                        history.append(agent.tool_result_message(
                            call, agent.dumps({"success": False, "error": "approval rejected"})
                        ))
                        continue
                result = await self.registry.execute(call, tool_ctx)
                changed.extend(result.changed_files)
                await self.events.record(
                    "tool.result", goal_id=goal_id, task_id=task.id,
                    tool=call.tool_name, success=result.success,
                    exit_code=result.exit_code, changed_files=result.changed_files,
                )
                history.append(agent.tool_result_message(call, agent.dumps(result.model_dump())))

        ok = self._verify(task, history, last_text)
        return ok, (last_text or "").strip()[:500] or "done", changed

    def _verify(self, task, history: list[ChatMessage], last_text: str) -> bool:
        blob = "\n".join(m.content for m in history) + "\n" + last_text
        lowered = blob.lower()
        if task.agent == "reviewer":
            return "approved" in lowered and "changes required" not in lowered
        if task.agent in ("tester", "debugger"):
            if '"success": false' in lowered or '"exit_code": 1' in lowered:
                return False
            return '"success": true' in lowered or "exit_code': 0" in lowered or "passed" in lowered
        # coder / git: success if at least one tool call succeeded and none failed hard
        return '"success": true' in lowered

    async def _request_approval(self, goal_id: str, task_id: str, call: ToolCall, reason: str) -> bool:
        pa = self.approvals.create(goal_id, task_id, call.tool_name, call.arguments, reason)
        await self.events.record(
            "approval.requested", goal_id=goal_id, task_id=task_id,
            approval_id=pa.id, tool=call.tool_name, reason=reason,
        )
        verdict = await self.approvals.wait(pa.id)
        await self.events.record(
            "approval.resolved", goal_id=goal_id, task_id=task_id,
            approval_id=pa.id, verdict=verdict,
        )
        return verdict == "approved"

    async def _insert_debug_task(self, graph: TaskGraph, failed_task) -> None:
        from core.orchestrator.task_graph import Task

        debug = Task(
            title=f"debug: {failed_task.title}",
            agent="debugger",
            instruction=f"Fix the failure in '{failed_task.title}': {failed_task.last_error}",
            success_criteria="root cause fixed and the failing check passes",
        )
        graph.tasks.append(debug)
        retest = Task(
            title=f"retest: {failed_task.title}",
            agent="tester",
            depends_on=[debug.id],
            instruction="Re-run the previously failing check.",
            success_criteria="check exits 0",
        )
        graph.tasks.append(retest)
        failed_task.state = TaskState.SKIPPED
        await self.events.record(
            "plan.created", goal_id=graph.goal_id,
            note="inserted debug+retest tasks", tasks=[debug.title, retest.title],
        )

    @staticmethod
    def _summarize(profile) -> str:
        return (
            f"languages={profile.languages} frameworks={profile.frameworks} "
            f"pkg={profile.package_managers} commands={profile.commands} "
            f"db={profile.database} docker={profile.has_docker} git={profile.has_git} "
            f"entrypoints={profile.entrypoints} dirs={profile.important_dirs}"
        )


async def _demo() -> None:  # pragma: no cover - manual smoke helper
    settings = get_settings()
    events = EventBus(settings.log_dir)
    orch = Orchestrator(events, ApprovalGate(), settings)
    print(await orch.execute_goal("demo", "print hello", "."))


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_demo())
