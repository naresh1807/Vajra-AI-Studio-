"""Project playbooks: a whole-app goal must produce a whole-app plan, not one file."""

from __future__ import annotations

import pytest

from core.agents.playbooks import detect_playbook, playbook_for, slugify


@pytest.mark.parametrize(
    "goal",
    [
        "build an android app that scans bluetooth devices",
        "make me a flutter todo app",
        "create an android application for notes",
        "build an apk that shows the weather",
    ],
)
def test_android_goals_pick_the_flutter_playbook(goal):
    pb = detect_playbook(goal)
    assert pb is not None and "Flutter" in pb.name
    text = pb.render(goal)
    assert "flutter create" in text
    assert "pubspec.yaml" in text
    assert "flutter build apk" in text
    assert "lib/main.dart" in text


def test_non_project_goals_have_no_playbook():
    assert detect_playbook("fix the failing test in calc.py") is None
    assert detect_playbook("refactor the auth module") is None
    assert playbook_for("add a docstring to add()") == ""


def test_fastapi_and_react_are_recognized():
    assert "FastAPI" in detect_playbook("build a rest api for users").name
    assert "React" in detect_playbook("build a react app dashboard").name


def test_slugify_makes_a_valid_dart_package_name():
    assert slugify("build me a Bluetooth Scanner android app") == "bluetooth_scanner"
    assert slugify("123 app") == "app_123" or slugify("123 app")[0].isalpha()
    assert " " not in slugify("My Weather App")


@pytest.mark.asyncio
async def test_build_context_injects_the_playbook(tmp_path):
    from core.agents.context import build_context

    ctx = await build_context("build an android app for reminders", str(tmp_path))
    assert "Project playbook" in ctx.playbook
    assert "flutter create" in ctx.prompt_context()


def test_run_command_routes_windows_bat_through_the_shell(monkeypatch):
    import core.tools.process_tools as pt

    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setattr("core.lsp.config._which", lambda n: r"C:\dev\flutter\bin\flutter.bat")
    argv, use_shell = pt._resolve(["flutter", "create", "."])
    assert use_shell is True
    assert argv[0].endswith("flutter.bat")


def test_run_command_keeps_exec_for_a_plain_binary(monkeypatch):
    import core.tools.process_tools as pt

    monkeypatch.setattr("core.lsp.config._which", lambda n: "/usr/bin/python3")
    argv, use_shell = pt._resolve(["python3", "-c", "print(1)"])
    assert use_shell is False
    assert argv == ["/usr/bin/python3", "-c", "print(1)"]


def test_default_plan_is_playbook_aware_for_an_app_goal():
    from core.agents.specialists import PlannerAgent

    tasks = PlannerAgent._default_plan("build an android app that scans bluetooth")
    titles = [t.title for t in tasks]
    assert titles == ["checkpoint", "scaffold", "implement", "build", "review"]
    blob = " ".join(t.instruction.lower() for t in tasks)
    assert "flutter create" in blob
    assert "pubspec.yaml" in blob and "main.dart" in blob


def test_default_plan_stays_generic_for_a_plain_goal():
    from core.agents.specialists import PlannerAgent

    tasks = PlannerAgent._default_plan("fix the failing test in calc.py")
    assert [t.title for t in tasks] == ["checkpoint", "implement", "test", "review"]


def test_parse_plan_survives_fences_and_reasoning():
    from core.agents.specialists import PlannerAgent

    reply = (
        "Let me reason about {this} first.\n"
        '```json\n{"tasks": [{"title": "scaffold", "agent": "tester", '
        '"instruction": "flutter create ."}]}\n```\nHope that helps."'
    )
    plan = PlannerAgent._parse_plan(reply)
    assert plan and plan["tasks"][0]["title"] == "scaffold"


class _PlanRouter:
    def __init__(self, text):
        self.text = text

    def describe(self):
        return {"primary": "stub", "fallback": "stub"}

    async def complete(self, messages, tools=None, temperature=0.2, max_tokens=2048):
        from core.llm import LLMResponse

        return LLMResponse(text=self.text, model="m", provider="p")


async def _graph_for(text, goal="fix the failing test in calc.py"):
    from core.agents.base import AgentContext
    from core.agents.specialists import PlannerAgent
    from core.tools import build_default_registry

    planner = PlannerAgent(_PlanRouter(text), build_default_registry())
    ctx = AgentContext(goal=goal, workspace_root=".")
    return await planner.create_task_graph("g1", ctx, max_retries=2)


async def test_planner_survives_tasks_as_bare_strings():
    # a weak model returns titles only, no agent -> fall back to the default plan
    g = await _graph_for('{"tasks": ["write calc.py", "run the tests"]}')
    assert [t.agent for t in g.tasks] == ["git", "coder", "tester", "reviewer"]


async def test_planner_uses_a_real_model_dag_when_given_one():
    g = await _graph_for(
        '{"tasks": [{"title": "impl", "agent": "coder", "depends_on": []},'
        ' {"title": "check", "agent": "tester", "depends_on": ["impl"]}]}'
    )
    assert [t.title for t in g.tasks] == ["impl", "check"]
    assert g.tasks[1].depends_on == [g.tasks[0].id]
