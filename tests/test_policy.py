from core.policy.engine import PolicyEngine, RiskLevel, ToolAction


def test_low_risk_allowed():
    d = PolicyEngine().validate(ToolAction(tool_name="read_file", arguments={}, risk_level=RiskLevel.LOW))
    assert d.allowed and not d.requires_approval


def test_high_risk_runs_only_after_approval():
    d = PolicyEngine().validate(
        ToolAction(tool_name="git_restore", arguments={"tag": "vajra/1"}, risk_level=RiskLevel.HIGH)
    )
    # allowed to run, but the runtime must not execute it without approval
    assert d.allowed and d.requires_approval


def test_critical_pattern_blocked():
    d = PolicyEngine().validate(
        ToolAction(tool_name="run_command", arguments={"command": "format C:"}, risk_level=RiskLevel.MEDIUM)
    )
    assert not d.allowed and d.risk == RiskLevel.CRITICAL


def test_medium_write_outside_workspace_escalates(tmp_path):
    d = PolicyEngine().validate(
        ToolAction(
            tool_name="write_file",
            arguments={"path": "C:/Windows/system32/x.txt"},
            risk_level=RiskLevel.MEDIUM,
            workspace_root=str(tmp_path),
        )
    )
    # a workspace-scoped tool writing outside the workspace is escalated to approval
    assert d.requires_approval and d.risk == RiskLevel.ELEVATED


def test_computer_tool_writes_outside_workspace_by_design(tmp_path):
    d = PolicyEngine().validate(
        ToolAction(
            tool_name="create_folder",
            arguments={"path": str(tmp_path / "x")},
            risk_level=RiskLevel.ELEVATED,
            outside_workspace_ok=True,
        )
    )
    assert d.allowed and d.requires_approval


def test_elevated_requires_approval_but_can_propose():
    d = PolicyEngine(autonomy_enabled=True).validate(
        ToolAction(tool_name="run_command", arguments={"command": ["pip", "install", "x"]}, risk_level=RiskLevel.ELEVATED)
    )
    assert d.allowed and d.requires_approval
