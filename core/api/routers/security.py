"""Authorized-security agent — scope profiles + defensive audits + scoped checks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, events, security_agent, security_runs
from core.api.routers._runref import launch, status
from core.api.schemas import ComputerRunResult, SecurityRunRequest, SecurityScopeIn

router = APIRouter()


@router.get("/api/security/scopes", dependencies=AUTH)
async def security_scopes(root: str) -> dict:
    from core.security.scope import ScopeStore

    return {"scopes": [s.to_dict() for s in ScopeStore(root).list()]}


@router.post("/api/security/scopes", dependencies=AUTH)
async def security_scope_save(req: SecurityScopeIn) -> dict:
    from core.security.scope import ScopeProfile, ScopeStore

    if not req.root:
        raise HTTPException(400, "root is required")
    profile = ScopeProfile(
        name=req.name, authorized_targets=req.authorized_targets,
        authorized_ports=req.authorized_ports, techniques=req.techniques,
        authorization_ref=req.authorization_ref, expires_at=req.expires_at, notes=req.notes,
    )
    path = ScopeStore(req.root).save(profile)
    await events.record("report", note=f"security scope '{req.name}' saved")
    return {"saved": str(path), "scope": profile.to_dict()}


@router.post("/api/security/run", dependencies=AUTH)
async def security_run(req: SecurityRunRequest) -> dict:
    security_agent.workspace_root = req.root or ""
    return await launch(security_runs, "sec", security_agent, req.instruction)


@router.get("/api/security/runs/{run_id}", dependencies=AUTH)
async def security_run_status(run_id: str) -> ComputerRunResult:
    return status(security_runs, run_id, "security")
