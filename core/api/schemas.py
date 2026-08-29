from __future__ import annotations

from pydantic import BaseModel, Field


class OpenProjectRequest(BaseModel):
    root_path: str
    name: str | None = None
    create: bool = False  # mkdir the folder if it does not exist


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


class SearchRequest(BaseModel):
    root: str
    query: str
    is_regex: bool = False
    case_sensitive: bool = False
    glob: str = "*"
    max_hits: int = 400


class FileWriteRequest(BaseModel):
    root: str
    path: str
    content: str


class EditorOpenRequest(BaseModel):
    root: str
    path: str


class AssistRequest(BaseModel):
    root: str
    path: str
    action: str  # explain | fix | refactor | optimize | tests | document | security | edit
    selection: str | None = None
    instruction: str | None = None
    language: str = ""


class AssistResponse(BaseModel):
    kind: str  # "prose" | "edit"
    text: str = ""
    new_content: str | None = None
    diff: str | None = None


class InlineCompleteRequest(BaseModel):
    root: str
    path: str
    prefix: str
    suffix: str = ""
    language: str = ""


# -- language server -------------------------------------------------
class LspRequest(BaseModel):
    root: str
    path: str
    content: str
    language: str
    line: int = 0
    character: int = 0


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


class ProcStartRequest(BaseModel):
    root: str
    command: list[str] | str
    label: str | None = None


class ProcStopRequest(BaseModel):
    process_id: str


# -- git -------------------------------------------------------------
class GitRequest(BaseModel):
    root: str
    path: str | None = None
    staged: bool = False


class GitPathsRequest(BaseModel):
    root: str
    paths: list[str] = []


class GitCommitRequest(BaseModel):
    root: str
    message: str


class GitRestoreRequest(BaseModel):
    root: str
    target: str


class GitCheckpointRequest(BaseModel):
    root: str
    label: str = "manual checkpoint"


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
