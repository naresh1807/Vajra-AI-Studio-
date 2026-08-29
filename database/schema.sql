-- Vajra Core local store. SQLite for the personal MVP; access goes through
-- repositories so PostgreSQL can be adopted later without touching agent logic.

CREATE TABLE IF NOT EXISTS projects (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    root_path    TEXT NOT NULL UNIQUE,
    profile_json TEXT,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    goal_id     TEXT REFERENCES goals(id),
    title       TEXT NOT NULL,
    agent       TEXT NOT NULL,
    state       TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    summary     TEXT,
    updated_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id     TEXT NOT NULL,
    depends_on  TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id          TEXT PRIMARY KEY,
    goal_id     TEXT,
    task_id     TEXT,
    tool_name   TEXT NOT NULL,
    success     INTEGER,
    exit_code   INTEGER,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS file_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id     TEXT,
    task_id     TEXT,
    path        TEXT NOT NULL,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id          TEXT PRIMARY KEY,
    goal_id     TEXT,
    task_id     TEXT,
    tool_name   TEXT,
    reason      TEXT,
    verdict     TEXT,
    created_at  REAL NOT NULL,
    resolved_at REAL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    goal_id     TEXT,
    task_id     TEXT,
    payload_json TEXT,
    ts          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_events_goal ON audit_events(goal_id);
CREATE INDEX IF NOT EXISTS idx_toolcalls_goal ON tool_calls(goal_id);
