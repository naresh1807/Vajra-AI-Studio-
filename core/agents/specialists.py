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


def _balanced_spans(text: str) -> list[str]:
    """Every top-level balanced {...}/[...] substring, in order (string-aware)."""
    spans: list[str] = []
    opens = {"{": "}", "[": "]"}
    i = 0
    while i < len(text):
        if text[i] in opens:
            close = opens[text[i]]
            depth = 0
            in_str = False
            esc = False
            j = i
            while j < len(text):
                c = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == text[i]:
                    depth += 1
                elif c == close:
                    depth -= 1
                    if depth == 0:
                        spans.append(text[i:j + 1])
                        i = j
                        break
                j += 1
        i += 1
    return spans


class PlannerAgent(Agent):
    name = "planner"
    system_prompt = (
        "You are Vajra's Planner. Decompose the goal into a coherent set of tasks. "
        "Assign each task to one agent: coder, tester, debugger, reviewer, or git. "
        "Define dependencies and a concrete success criterion per task. Prefer: checkpoint -> "
        "implement -> test -> review.\n"
        "If a '# Project playbook' section is present, it describes a whole project type "
        "(e.g. a Flutter app), not a single file. Honour it: when the playbook gives a scaffold "
        "command, make the FIRST task (agent: tester) run that command to create the skeleton; "
        "then add coder tasks that fill in every file the layout lists; finish with a tester "
        "task that runs the playbook's build/test command. Never collapse a whole-app goal into "
        "one file."
    )
    allowed_tools = ("project_tree", "read_file", "search_text", "semantic_search", "git_status")

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
                content=f"Goal: {ctx.goal}\n\n{ctx.prompt_context()}\n\n{schema_hint}",
            ),
        ]
        try:
            resp = await self.router.complete(messages, temperature=0.1, max_tokens=1500)
            plan = self._parse_plan(resp.text)
        except Exception:
            plan = None

        graph = TaskGraph(goal_id=goal_id, goal=ctx.goal, max_retries=max_retries)
        # a weaker model may return tasks as bare strings, or a mix - coerce.
        raw_tasks = [
            {"title": t} if isinstance(t, str) else t
            for t in (plan.get("tasks") if isinstance(plan, dict) else None) or []
            if isinstance(t, (str, dict))
        ]
        # if the model never assigned an agent, it didn't really give us a task
        # DAG - the deterministic (playbook-aware) default plan is better.
        if not any(isinstance(t, dict) and t.get("agent") for t in raw_tasks):
            raw_tasks = []
        if raw_tasks:
            title_to_id: dict[str, str] = {}
            for raw in raw_tasks:
                task = Task(
                    title=str(raw.get("title") or raw.get("name") or "task"),
                    agent=raw.get("agent", "coder"),
                    instruction=raw.get("instruction", raw.get("title", "")),
                    success_criteria=raw.get("success_criteria", ""),
                )
                title_to_id[task.title] = task.id
                graph.tasks.append(task)
            for raw, task in zip(raw_tasks, graph.tasks, strict=False):
                task.depends_on = [
                    title_to_id[d] for d in raw.get("depends_on", []) if d in title_to_id
                ]
        else:
            graph.tasks = self._default_plan(ctx.goal)
        return graph

    @staticmethod
    def _parse_plan(text: str) -> dict | None:
        """Pull a task plan out of a reply that may be wrapped in ```json fences or
        preceded by the model's reasoning. Tries fenced blocks, then a
        brace/bracket-balanced scan, and keeps the first candidate that has tasks."""
        text = text or ""
        candidates: list[str] = []
        for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text):
            candidates.append(m.group(1))
        candidates.extend(_balanced_spans(text))
        for cand in candidates:
            try:
                data = json.loads(cand)
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                data = {"tasks": data}
            if isinstance(data, dict) and data.get("tasks"):
                return data
        return None

    @staticmethod
    def _default_plan(goal: str = "") -> list[Task]:
        """Deterministic fallback when the model's plan is unusable. Playbook-aware:
        an app goal still gets scaffold -> fill files -> build, not a one-file edit."""
        from core.agents.playbooks import detect_playbook, slugify

        t_ckpt = Task(title="checkpoint", agent="git",
                      instruction="Create a git checkpoint before making changes.",
                      success_criteria="a vajra/* tag exists")
        tasks = [t_ckpt]
        pb = detect_playbook(goal) if goal else None

        if pb:
            prev = t_ckpt
            if pb.scaffold:
                scaffold_cmd = pb.scaffold.format(slug=slugify(goal))
                t_scaffold = Task(
                    title="scaffold", agent="tester", depends_on=[prev.id],
                    instruction=f"Create the project skeleton by running: {scaffold_cmd}",
                    success_criteria="the scaffold command exits 0 and the project files exist",
                )
                tasks.append(t_scaffold)
                prev = t_scaffold
            t_impl = Task(
                title="implement", agent="coder", depends_on=[prev.id],
                instruction=(
                    f"Build a complete {pb.name} for: {goal}. Create/fill every file in this "
                    f"layout — not one file:\n{pb.layout}\nAdd every package you import to the "
                    "manifest. " + pb.guidance
                ),
                success_criteria="all listed files exist and are internally consistent",
            )
            t_build = Task(
                title="build", agent="tester", depends_on=[t_impl.id],
                instruction=(f"Build/test the app: {pb.test or pb.build}. Report the exact "
                             "failing output if it fails."),
                success_criteria="the build/test command exits 0",
            )
            t_rev = Task(title="review", agent="reviewer", depends_on=[t_build.id],
                         instruction="Review the project for correctness and completeness.",
                         success_criteria="reviewer reports no blocking issues")
            return [*tasks, t_impl, t_build, t_rev]

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
        "You are Vajra's Coder. For a change to an existing file, make the smallest coherent "
        "edit and prefer patch_file over a full rewrite. For a NEW project (a '# Project "
        "playbook' is shown, or the folder is nearly empty), instead create EVERY file the "
        "playbook's layout lists — a complete, runnable project, not a single file — and add "
        "each dependency you import to the manifest (pubspec.yaml / package.json / "
        "requirements.txt). Match the surrounding code style. Do not run tests yourself - that "
        "is the Tester's job."
    )
    allowed_tools = (
        "read_file", "write_file", "patch_file", "create_file", "create_directory",
        "search_text", "semantic_search", "project_tree",
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
        "You are Vajra's Git Agent. Call git_checkpoint EXACTLY ONCE with a short label to "
        "commit and tag the current state, then reply with a one-line confirmation and NO "
        "further tool calls. Do not create more than one checkpoint and never touch unrelated "
        "user changes. git_checkpoint succeeding once means your task is done."
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
