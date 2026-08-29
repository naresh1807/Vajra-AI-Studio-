from __future__ import annotations

from pydantic import BaseModel, Field


class OpenProjectRequest(BaseModel):
    root_path: str
    name: str | None = None


class ProjectInfo(BaseModel):
    id: str
    name: str
    root_path: str
    profile: dict = {}


class CreateGoalRequest(BaseModel):
    text: str = Field(min_length=1)
    project_id: str | None = None
    workspace_root: str | None = None
    autostart: bool = True


class GoalStatus(BaseModel):
    id: str
    text: str
    status: str
    progress: dict[str, int] = {}
    tasks: list[dict] = []
    changed_files: list[str] = []


class ChatMessageIn(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessageIn] = []
    workspace_root: str | None = None
    goal_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict] = []
    model: dict[str, str] = {}


class ApproveRequest(BaseModel):
    approval_id: str
    verdict: str = "approved"


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str = ""
