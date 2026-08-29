"""The autonomous execution loop.

    OBSERVE -> UNDERSTAND -> PLAN -> SELECT AGENT+TOOL -> POLICY CHECK -> EXECUTE
    -> VERIFY -> (pass: record + next) / (fail: diagnose -> patch/re-plan -> retry)

Bounded retries; never an infinite loop. Every step emits a structured event.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from core.agents.base import AgentContext
from core.config import Settings, get_settings
from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.memory import WorkspaceMemory
from core.orchestrator.approvals import ApprovalGate
from core.orchestrator.task_graph import Task, TaskGraph, TaskState
from core.policy.engine import PolicyEngine
from core.tools import ToolCall, ToolContext, ToolRegistry, build_default_registry
from core.workspace import discover_workspace

log = logging.getLogger("vajra.orchestrator")

_MAX_AGENT_TURNS = 6
_MAX_GRAPH_STEPS = 24
_MAX_DEBUG_ROUNDS = 2
_TEST_TOOLS = {"run_tests", "run_build", "run_command", "start_process"}


@dataclass
class TaskOutcome:
    passed: bool
    summary: str
    changed_files: list[str] = field(default_factory=list)
    tests_green: bool | None = None  # None = no test tool ran
    infra_error: str | None = None


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
        # Imported here (not at module top) to avoid a core.agents <-> core.orchestrator cycle.
        from core.agents.specialists import PlannerAgent, build_agent_team

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
                outcome = await self._run_task(goal_id, task, ctx)
            except Exception as exc:  # noqa: BLE001
                outcome = TaskOutcome(False, f"{type(exc).__name__}: {exc}", infra_error=str(exc))
                log.exception("task %s crashed", task.id)
            changed_files.extend(outcome.changed_files)

            if outcome.passed:
                graph.mark_passed(task, outcome.summary)
                await self.events.record(
                    "task.completed", goal_id=goal_id, task_id=task.id,
                    summary=outcome.summary, tests_green=outcome.tests_green,
                )
                # A tester step that reports RED *after* a fix was attempted ->
                # one bounded debug round. Red before any fix is expected, not a failure.
                fix_attempted = any(
                    t.agent in ("coder", "debugger") and t.state == TaskState.PASSED
                    for t in graph.tasks
                )
                if (
                    task.agent == "tester"
                    and outcome.tests_green is False
                    and fix_attempted
                    and graph.debug_rounds < _MAX_DEBUG_ROUNDS
                    and not task.title.startswith(("debug:", "retest:"))
                ):
                    await self._insert_debug_round(graph, task, outcome.summary)
            else:
                disposition = graph.mark_failed(task, outcome.summary)
                await self.events.record(
                    "task.failed", goal_id=goal_id, task_id=task.id,
                    error=outcome.summary, disposition=disposition,
                )

        final_green = await self._final_gate(goal_id, ctx)
        succeeded = final_green if final_green is not None else graph.succeeded
        result = {
            "goal_id": goal_id,
            "succeeded": succeeded,
            "final_tests_green": final_green,
            "progress": graph.progress(),
            "changed_files": sorted(set(changed_files)),
            "tasks": [t.model_dump() for t in graph.tasks],
        }
        self._learn(memory, graph, succeeded)
        memory.record_task(goal, "passed" if succeeded else "failed", result["changed_files"])
        await self.events.record(
            "report", goal_id=goal_id, succeeded=succeeded,
            final_tests_green=final_green, progress=result["progress"],
            changed_files=result["changed_files"],
        )
        self._cancelled.discard(goal_id)
        return result

    # -- internals ----------------------------------------------------------
    async def _run_task(self, goal_id: str, task: Task, ctx: AgentContext) -> TaskOutcome:
        agent = self.agents.get(task.agent)
        if agent is None:
            return TaskOutcome(False, f"no agent named {task.agent}", infra_error="no agent")
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
        test_results: list[bool] = []
        infra_error: str | None = None

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
                approved = True
                if decision.requires_approval:
                    approved = await self._request_approval(goal_id, task.id, call, decision.reason)
                    if not approved:
                        history.append(agent.tool_result_message(
                            call, agent.dumps({"success": False, "error": "approval rejected"})
                        ))
                        continue
                result = await self.registry.execute(call, tool_ctx, approved=approved)
                changed.extend(result.changed_files)
                if call.tool_name == "start_process":
                    test_results.append(bool(result.metadata.get("running")))
                elif call.tool_name in _TEST_TOOLS:
                    test_results.append(result.success and (result.exit_code in (0, None)))
                if not result.success and result.metadata.get("policy"):
                    infra_error = f"policy blocked {call.tool_name}"
                await self.events.record(
                    "tool.result", goal_id=goal_id, task_id=task.id,
                    tool=call.tool_name, success=result.success,
                    exit_code=result.exit_code, changed_files=result.changed_files,
                )
                history.append(agent.tool_result_message(call, agent.dumps(result.model_dump())))

        tests_green = test_results[-1] if test_results else None
        summary = (last_text or "").strip()[:500] or "done"
        passed, infra = self._verify(task, tests_green, infra_error, bool(changed))
        return TaskOutcome(
            passed=passed,
            summary=summary if not infra else f"{summary} [{infra}]",
            changed_files=changed,
            tests_green=tests_green,
            infra_error=infra,
        )

    @staticmethod
    def _verify(
        task: Task, tests_green: bool | None, infra_error: str | None, made_changes: bool
    ) -> tuple[bool, str | None]:
        """Structural verification.

        Task failure == infrastructure/agent failure only. A RED test is *data*
        (surfaced via TaskOutcome.tests_green), not a task failure - the graph
        decides whether to spin a debug round.
        """
        if infra_error:
            return False, infra_error
        if task.agent == "reviewer":
            # Non-blocking: the reviewer's verdict is advisory here.
            return True, None
        if task.agent == "tester":
            # Passing the task just means the tester actually ran a check.
            if tests_green is None:
                return False, "tester ran no test/build command"
            return True, None
        # coder / debugger / git: succeeded if the agent finished without infra errors.
        return True, None

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

    async def _insert_debug_round(self, graph: TaskGraph, tester_task: Task, failing: str) -> None:
        graph.debug_rounds += 1
        debug = Task(
            title=f"debug: {tester_task.title}",
            agent="debugger",
            instruction=(
                "The test/build run is RED. Read the failing output, find the root cause, "
                f"and apply the minimal fix with patch_file. Failing run summary:\n{failing}"
            ),
            success_criteria="root cause fixed",
        )
        retest = Task(
            title=f"retest: {tester_task.title}",
            agent="tester",
            depends_on=[debug.id],
            instruction="Re-run the test/build command and report whether it is now green.",
            success_criteria="test/build command runs",
        )
        graph.tasks += [debug, retest]
        await self.events.record(
            "plan.created", goal_id=graph.goal_id,
            note=f"debug round {graph.debug_rounds}", tasks=[debug.title, retest.title],
        )

    @staticmethod
    def _learn(memory: WorkspaceMemory, graph: TaskGraph, succeeded: bool) -> None:
        """Fold what happened this run into .vajra/ so future runs start smarter
        (manual v3.0 section 14: decisions + known recurring errors)."""
        if not succeeded:
            return
        # a debug round that then went green -> a known error + its fix
        for t in graph.tasks:
            if t.title.startswith("debug:") and t.state == TaskState.PASSED and t.instruction:
                sig = t.instruction.split("\n", 1)[0][:200]
                fix = (t.result_summary or "root cause fixed")[:300]
                memory.record_known_error(sig, fix)
        # the reviewer's verdict -> an architecture/decision note
        for t in graph.tasks:
            if t.agent == "reviewer" and t.state == TaskState.PASSED and t.result_summary:
                memory.record_decision(f"{graph.goal[:120]}", t.result_summary[:400])
                break

    async def _final_gate(self, goal_id: str, ctx: AgentContext) -> bool | None:
        """Run the workspace test/build once at the end. Returns green/red, or
        None if the workspace has no detectable test or build command."""
        tool_ctx = ToolContext(workspace_root=ctx.workspace_root, goal_id=goal_id)
        for tool_name in ("run_tests", "run_build"):
            result = await self.registry.execute(ToolCall(tool_name=tool_name), tool_ctx)
            if result.metadata.get("gate") and "no " not in result.stderr[:40]:
                green = result.success and result.exit_code in (0, None)
                await self.events.record(
                    "report", goal_id=goal_id, note=f"final {tool_name}",
                    green=green, exit_code=result.exit_code,
                )
                return green
        return None

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
