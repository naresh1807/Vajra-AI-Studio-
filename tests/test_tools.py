import pytest

from core.tools import ToolCall, ToolContext, build_default_registry


@pytest.fixture
def reg():
    return build_default_registry()


async def test_write_then_read(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    w = await reg.execute(ToolCall(tool_name="write_file", arguments={"path": "notes/x.txt", "content": "hello"}), ctx)
    assert w.success and "notes/x.txt" in w.changed_files
    r = await reg.execute(ToolCall(tool_name="read_file", arguments={"path": "notes/x.txt"}), ctx)
    assert r.success and r.stdout == "hello"


async def test_patch_file_unique(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(
        ToolCall(tool_name="patch_file", arguments={"path": "src/app.py", "find": "a + b", "replace": "a - b"}), ctx
    )
    assert res.success
    assert "a - b" in (tmp_workspace / "src" / "app.py").read_text()


async def test_patch_file_non_unique_fails(reg, tmp_workspace):
    (tmp_workspace / "src" / "app.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(
        ToolCall(tool_name="patch_file", arguments={"path": "src/app.py", "find": "x = 1", "replace": "x = 2"}), ctx
    )
    assert not res.success and "not unique" in res.stderr


async def test_path_escape_blocked(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(ToolCall(tool_name="read_file", arguments={"path": "../../secret.txt"}), ctx)
    assert not res.success


async def test_project_tree(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(ToolCall(tool_name="project_tree", arguments={}), ctx)
    assert res.success and "app.py" in res.stdout


async def test_run_command_echo(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(
        ToolCall(tool_name="run_command", arguments={"command": ["python", "-c", "print(2+2)"]}), ctx
    )
    assert res.success and res.stdout.strip() == "4"


async def test_unknown_tool(reg, tmp_workspace):
    ctx = ToolContext(workspace_root=str(tmp_workspace))
    res = await reg.execute(ToolCall(tool_name="nope", arguments={}), ctx)
    assert not res.success
