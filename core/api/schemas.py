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


# -- files / workspace ---------------------------------------------------
class TreeRequest(BaseModel):
    root: str
    max_depth: int = 6


class FileReadRequest(BaseModel):
    root: str
    path: str


class FileWriteRequest(BaseModel):
    root: str
    path: str
    content: str


class EditorOpenRequest(BaseModel):
    root: str
    path: str


# -- terminal ----------------------------------------------------------
class TerminalRunRequest(BaseModel):
    root: str
    command: list[str] | str
    timeout_seconds: int = 300


class TerminalRunResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int
    cwd: str
    command: list[str]


# -- git -------------------------------------------------------------
class GitRequest(BaseModel):
    root: str
    path: str | None = None
    staged: bool = False


# -- agent -----------------------------------------------------------
class ChatMessageIn(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessageIn] = []
    workspace_root: str | None = None
    run_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[dict] = []
    model: dict[str, str] = {}


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=1)
    workspace_root: str | None = None
    project_id: str | None = None
    autostart: bool = True


class AgentRunStatus(BaseModel):
    id: str
    goal: str
    status: str
    progress: dict[str, int] = {}
    tasks: list[dict] = []
    changed_files: list[str] = []


class AgentStopRequest(BaseModel):
    run_id: str


class ApproveRequest(BaseModel):
    approval_id: str
    verdict: str = "approved"


class SimpleOk(BaseModel):
    ok: bool = True
    detail: str = ""
