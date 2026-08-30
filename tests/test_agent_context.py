"""PRIORITY 18 - focused context assembly, not whole-repo dumps."""

from __future__ import annotations

import pytest

from core.agents.context import build_context


@pytest.mark.asyncio
async def test_build_context_is_bounded_and_focused(tmp_workspace):
    (tmp_workspace / "src" / "auth.py").write_text(
        "def login(user, password):\n    return check_password(user, password)\n",
        encoding="utf-8",
    )
    from core.rag import rag_manager

    await rag_manager.reindex(str(tmp_workspace))

    ctx = await build_context(
        "fix the login password check",
        str(tmp_workspace),
        focus="src/auth.py: def login(user, password)",
    )

    assert ctx.goal == "fix the login password check"
    assert ctx.workspace_root == str(tmp_workspace)
    assert "src/auth.py" in ctx.focus
    # summary is a short profile line, never a file dump
    assert "languages=" in ctx.workspace_summary
    assert len(ctx.workspace_summary) < 2000

    rendered = ctx.prompt_context()
    assert "# Project" in rendered
    assert "# Open in the editor" in rendered
    # retrieved code is size-capped
    assert len(ctx.retrieved) <= 6200


@pytest.mark.asyncio
async def test_build_context_survives_missing_sources(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    ctx = await build_context("do a thing", str(empty))
    assert ctx.goal == "do a thing"
    assert ctx.working_diff == ""  # not a git repo - no crash
