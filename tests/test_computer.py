import pytest

from core.policy.engine import PolicyEngine, RiskLevel, ToolAction
from core.tools import ToolCall, ToolContext, build_computer_registry


@pytest.fixture
def reg():
    return build_computer_registry()


async def test_resolve_and_list_are_low_risk(reg):
    ctx = ToolContext(workspace_root="")
    d = reg.check(ToolCall(tool_name="resolve_known_folder", arguments={"name": "desktop"}), ctx)
    assert d.allowed and not d.requires_approval
    res = await reg.execute(ToolCall(tool_name="resolve_known_folder", arguments={"name": "home"}), ctx)
    assert res.success and res.stdout


async def test_create_folder_needs_approval(reg, tmp_path):
    ctx = ToolContext(workspace_root="")
    call = ToolCall(tool_name="create_folder", arguments={"path": str(tmp_path / "new")})
    d = reg.check(call, ctx)
    assert d.requires_approval and d.risk == RiskLevel.ELEVATED
    # without approval -> refused
    blocked = await reg.execute(call, ctx)
    assert not blocked.success and blocked.metadata.get("needs_approval")
    # with approval -> runs
    ok = await reg.execute(call, ctx, approved=True)
    assert ok.success and (tmp_path / "new").is_dir()


async def test_powershell_is_high_risk(reg):
    ctx = ToolContext(workspace_root="")
    d = reg.check(ToolCall(tool_name="run_powershell", arguments={"script": "echo hi"}), ctx)
    assert d.allowed and d.requires_approval and d.risk == RiskLevel.HIGH


async def test_find_files(reg, tmp_path):
    (tmp_path / "a.iso").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    ctx = ToolContext(workspace_root="")
    res = await reg.execute(
        ToolCall(tool_name="find_files", arguments={"root": str(tmp_path), "pattern": "*.iso"}), ctx
    )
    assert res.success and "a.iso" in res.stdout and "b.txt" not in res.stdout


def test_critical_still_blocked():
    d = PolicyEngine().validate(
        ToolAction(tool_name="run_powershell", arguments={"script": "format C: /y"},
                   risk_level=RiskLevel.HIGH, outside_workspace_ok=True)
    )
    assert not d.allowed and d.risk == RiskLevel.CRITICAL
