"""Recovering tool calls that a NIM model emitted in the message body."""

from core.llm.nemotron_client import _tool_calls_from_text


def test_recovers_fenced_json_tool_call():
    text = 'Sure, I will create the file.\n```json\n{"name": "write_file", "arguments": {"path": "calc.py", "content": "x = 1"}}\n```'
    calls, cleaned = _tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert calls[0].arguments["path"] == "calc.py"
    assert "```" not in cleaned and "{" not in cleaned


def test_recovers_multiple_bare_objects():
    text = (
        '{"name": "create_directory", "arguments": {"path": "src"}}\n'
        '{"name": "write_file", "arguments": {"path": "src/__init__.py", "content": ""}}'
    )
    calls, _ = _tool_calls_from_text(text)
    assert [c.name for c in calls] == ["create_directory", "write_file"]


def test_no_args_block_is_not_a_tool_call():
    calls, cleaned = _tool_calls_from_text('the field {"name": "widget"} is required')
    assert calls == [] and cleaned  # left untouched


def test_plan_shaped_json_is_ignored():
    # the planner returns {"tasks": [...]} - must not be read as a tool call
    calls, _ = _tool_calls_from_text('{"tasks": [{"title": "x", "agent": "coder"}]}')
    assert calls == []


def test_plain_prose_is_passed_through():
    calls, cleaned = _tool_calls_from_text("Just a normal answer, no JSON here.")
    assert calls == [] and cleaned == "Just a normal answer, no JSON here."


def test_dedupes_fence_and_bare_copy():
    obj = '{"name": "git_status", "arguments": {}}'
    calls, _ = _tool_calls_from_text(f"```json\n{obj}\n```")
    assert len(calls) == 1
