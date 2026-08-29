"""Specialist agents. Prompts encode each role's policy from the manual (section 9).

The Planner additionally exposes create_task_graph(), which asks the model for a
JSON task DAG and falls back to a deterministic default plan if parsing fails.
"""

from __future__ import annotations

import json
import re

from core.agents.base import Agent, AgentContext
from core.llm import ChatMessage, ModelRouter
from core.orchestrator.task_graph import Task, TaskGraph
from core.tools import ToolRegistry

_JSON_BLOCK = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


class PlannerAgent(Agent):
    name = "planner"
    system_prompt = (
        "You are Vajra's Planner. Decompose the goal into the smallest coherent set of tasks. "
        "Assign each task to one agent: coder, tester, debugger, reviewer, or git. "
        "Define dependencies and a concrete success criterion per task. Prefer: checkpoint -> "
        "implement -> test -> review."
    )
    allowed_tools = ("project_tree", "read_file", "search_text", "git_status")

    async def create_task_graph(self, goal_id: str, ctx: AgentContext, max_retries: int = 2) -> TaskGraph:
        schema_hint = (
            'Return ONLY JSON: {"tasks":[{"title":str,"agent":'
            '"coder|tester|debugger|reviewer|git","instruction":str,'
            '"depends_on":[title,...],"success_criteria":str}]}'
        )
        messages = [
            ChatMessage(role="system", content=self.system_prompt + "\n" + schema_hint),
            ChatMessage(
                role="user",
                content=f"Goal: {ctx.goal}\n\nWorkspace:\n{ctx.workspace_summary}\n\n{schema_hint}",
            ),
        ]
        try:
            resp = await self.router.complete(messages, temperature=0.1, max_tokens=1500)
            plan = self._parse_plan(resp.text)
        except Exception:
            plan = None

        graph = TaskGraph(goal_id=goal_id, goal=ctx.goal, max_retries=max_retries)
        if plan and plan.get("tasks"):
            title_to_id: dict[str, str] = {}
            for raw in plan["tasks"]:
                task = Task(
                    title=raw.get("title", "task"),
                    agent=raw.get("agent", "coder"),
                    instruction=raw.get("instruction", raw.get("title", "")),
                    success_criteria=raw.get("success_criteria", ""),
                )
                title_to_id[task.title] = task.id
                graph.tasks.append(task)
            for raw, task in zip(plan["tasks"], graph.tasks, strict=False):
                task.depends_on = [
                    title_to_id[d] for d in raw.get("depends_on", []) if d in title_to_id
                ]
        else:
            graph.tasks = self._default_plan()
        return graph

    @staticmethod
    def _parse_plan(text: str) -> dict | None:
        match = _JSON_BLOCK.search(text or "")
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else {"tasks": data}

    @staticmethod
    def _default_plan() -> list[Task]:
        t_ckpt = Task(title="checkpoint", agent="git",
                      instruction="Create a git checkpoint before making changes.",
                      success_criteria="a vajra/* tag exists")
        t_impl = Task(title="implement", agent="coder", depends_on=[t_ckpt.id],
                      instruction="Implement the smallest change that satisfies the goal.",
                      success_criteria="files written and no syntax errors")
        t_test = Task(title="test", agent="tester", depends_on=[t_impl.id],
                      instruction="Run tests / build and report pass/fail.",
                      success_criteria="test or build command exits 0")
        t_rev = Task(title="review", agent="reviewer", depends_on=[t_test.id],
                     instruction="Review the diff for correctness and regressions.",
                     success_criteria="reviewer reports no blocking issues")
        return [t_ckpt, t_impl, t_test, t_rev]


class CoderAgent(Agent):
    name = "coder"
    system_prompt = (
        "You are Vajra's Coder. Make the smallest coherent change. Prefer patch_file over "
        "full rewrites for existing files. Match the surrounding code style. Do not run tests "
        "yourself - that is the Tester's job."
    )
    allowed_tools = (
        "read_file", "write_file", "patch_file", "create_file", "create_directory",
        "search_text", "project_tree",
    )


class TesterAgent(Agent):
    name = "tester"
    system_prompt = (
        "You are Vajra's Tester / runner. Run focused tests, builds and linters and report "
        "the exact failing output. To start a dev server or any long-running process use "
        "start_process (never run_command - it waits forever), then read_process_output to "
        "check it booted and note the URL, and stop_process when done. Do not edit source files."
    )
    allowed_tools = (
        "run_tests", "run_linter", "run_build", "run_command",
        "start_process", "read_process_output", "stop_process", "list_processes",
        "read_file", "project_tree",
    )


class DebuggerAgent(Agent):
    name = "debugger"
    system_prompt = (
        "You are Vajra's Debugger. Read the failing output, find the root cause, and apply the "
        "minimal fix with patch_file. Explain the root cause in one sentence."
    )
    allowed_tools = ("read_file", "patch_file", "write_file", "search_text", "run_command", "run_tests")


class ReviewerAgent(Agent):
    name = "reviewer"
    system_prompt = (
        "You are Vajra's Reviewer. Inspect the working-tree diff for correctness, maintainability "
        "and regression risk. Reply with either 'APPROVED' plus notes, or 'CHANGES REQUIRED' plus "
        "a specific list."
    )
    allowed_tools = ("git_diff", "git_status", "read_file")


class GitAgent(Agent):
    name = "git"
    system_prompt = (
        "You are Vajra's Git Agent. Create checkpoints and commits for Vajra-owned changes. "
        "Use git_checkpoint with a short label to commit and tag the current state. Never touch "
        "unrelated user changes."
    )
    allowed_tools = ("git_status", "git_diff", "git_checkpoint", "git_restore")


def build_agent_team(router: ModelRouter, registry: ToolRegistry) -> dict[str, Agent]:
    return {
        a.name: a
        for a in (
            PlannerAgent(router, registry),
            CoderAgent(router, registry),
            TesterAgent(router, registry),
            DebuggerAgent(router, registry),
            ReviewerAgent(router, registry),
            GitAgent(router, registry),
        )
    }
