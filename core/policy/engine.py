"""Policy engine - the gate between an agent's proposed action and execution.

Maps the manual's sandboxing/permission model (section 19) onto concrete checks:

    Low       read / search / git status            -> allow
    Medium    edit workspace files, run tests/builds -> allow inside active workspace
    Elevated  install deps, write outside workspace  -> policy dependent
    High      delete many files, modify boot/system  -> deny by default (needs approval)
    Critical  format disks, disable protections      -> blocked

The engine never executes anything; it only returns a decision.
"""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

from pydantic import BaseModel


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    ELEVATED = 3
    HIGH = 4
    CRITICAL = 5


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    risk: RiskLevel
    reason: str


class ToolAction(BaseModel):
    tool_name: str
    arguments: dict
    risk_level: RiskLevel
    workspace_root: str | None = None
    #: computer-agent actions are expected to act outside any workspace
    outside_workspace_ok: bool = False


# Substrings that force CRITICAL regardless of the tool's declared risk.
# These are blocked outright (manual handling) - the master prompt's P23 list.
_CRITICAL_MARKERS = (
    # format / wipe drives
    "format ", "mkfs", "diskpart", "rm -rf /", "rmdir /s c:\\", "del /f /s /q c:\\",
    # boot config / shutdown during work
    "shutdown", "bcdedit", "reboot ",
    # firewall / security software
    "netsh advfirewall set", "disable-windowsdefender",
    "set-mppreference -disablerealtimemonitoring", "ufw disable", "systemctl stop firewalld",
    # force-push git history
    "push --force", "push -f ", "push --f ", "push origin +", "reset --hard origin",
    # drop a database
    "drop database", "dropdb ", "drop schema",
    # credential / privilege changes
    "net user ", "net localgroup administ", "usermod -ag", "chpasswd", "set-localuser",
    "icacls c:\\ ", "takeown /f c:\\",
)


class PolicyEngine:
    def __init__(self, autonomy_enabled: bool = True) -> None:
        self.autonomy_enabled = autonomy_enabled

    def validate(self, action: ToolAction) -> PolicyDecision:
        blob = f"{action.tool_name} {action.arguments}".lower()

        if any(marker in blob for marker in _CRITICAL_MARKERS):
            return PolicyDecision(
                allowed=False,
                requires_approval=True,
                risk=RiskLevel.CRITICAL,
                reason="Matches a blocked critical-action pattern; manual handling required.",
            )

        if action.risk_level >= RiskLevel.HIGH:
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                risk=action.risk_level,
                reason="High-risk action: runs only after explicit user approval.",
            )

        if action.risk_level == RiskLevel.ELEVATED:
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                risk=action.risk_level,
                reason="Elevated action: requires approval before it runs.",
            )

        if (
            action.risk_level == RiskLevel.MEDIUM
            and not action.outside_workspace_ok
            and not self._writes_inside_workspace(action)
        ):
            return PolicyDecision(
                allowed=True,
                requires_approval=True,
                risk=RiskLevel.ELEVATED,
                reason="Write target is outside the active workspace; requires approval.",
            )

        return PolicyDecision(
            allowed=True,
            requires_approval=False,
            risk=action.risk_level,
            reason="Within default-allow envelope for the active workspace.",
        )

    @staticmethod
    def _writes_inside_workspace(action: ToolAction) -> bool:
        if not action.workspace_root:
            return True
        root = Path(action.workspace_root).resolve()
        for key in ("path", "file_path", "target", "dst", "directory"):
            raw = action.arguments.get(key)
            if not raw:
                continue
            try:
                candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            except (OSError, ValueError):
                return False
            if root not in candidate.parents and candidate != root:
                return False
        return True
