"""Agent-side P9: read_file tracks a sha; write_file / patch_file refuse to
clobber a file that changed on disk since the agent read it."""

from __future__ import annotations

from core.tools import ToolCall, ToolContext, build_default_registry


async def _exec(reg, ctx, name, **args):
    return await reg.execute(ToolCall(tool_name=name, arguments=args), ctx, approved=True)


async def test_write_refuses_after_external_edit(tmp_path):
    (tmp_path / "app.py").write_text("v1\n", encoding="utf-8")
    reg = build_default_registry()
    ctx = ToolContext(workspace_root=str(tmp_path))

    r = await _exec(reg, ctx, "read_file", path="app.py")
    assert r.success and r.stdout.strip() == "v1"
    assert ctx.file_shas["app.py"]

    # a user edits the file underneath the agent
    (tmp_path / "app.py").write_text("v1 + user edit\n", encoding="utf-8")

    w = await _exec(reg, ctx, "write_file", path="app.py", content="v2 from agent\n")
    assert not w.success and "changed on disk" in w.stderr
    assert (tmp_path / "app.py").read_text() == "v1 + user edit\n"  # untouched


async def test_patch_refuses_after_external_edit(tmp_path):
    (tmp_path / "m.py").write_text("keep\nold\n", encoding="utf-8")
    reg = build_default_registry()
    ctx = ToolContext(workspace_root=str(tmp_path))
    await _exec(reg, ctx, "read_file", path="m.py")
    (tmp_path / "m.py").write_text("keep\nold\nMORE\n", encoding="utf-8")
    p = await _exec(reg, ctx, "patch_file", path="m.py", find="old", replace="new")
    assert not p.success and "changed on disk" in p.stderr


async def test_write_ok_when_agent_owns_the_change(tmp_path):
    (tmp_path / "f.py").write_text("start\n", encoding="utf-8")
    reg = build_default_registry()
    ctx = ToolContext(workspace_root=str(tmp_path))
    await _exec(reg, ctx, "read_file", path="f.py")
    w1 = await _exec(reg, ctx, "write_file", path="f.py", content="step1\n")
    assert w1.success
    # the agent's own write updated the tracked sha, so a follow-up write is fine
    w2 = await _exec(reg, ctx, "write_file", path="f.py", content="step2\n")
    assert w2.success and (tmp_path / "f.py").read_text() == "step2\n"


async def test_write_new_file_needs_no_prior_read(tmp_path):
    reg = build_default_registry()
    ctx = ToolContext(workspace_root=str(tmp_path))
    w = await _exec(reg, ctx, "write_file", path="new.py", content="hi\n")
    assert w.success
