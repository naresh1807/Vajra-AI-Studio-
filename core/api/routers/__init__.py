"""All API routers, registered by main.py in this order."""

from core.api.routers import (
    agent,
    approvals,
    assist,
    computer,
    debug,
    files,
    git,
    health,
    lsp,
    memory,
    osdev,
    projects,
    security,
    terminal,
    testing,
)

ALL = [
    health.router,
    projects.router,
    files.router,
    assist.router,
    lsp.router,
    testing.router,
    memory.router,
    terminal.router,
    debug.router,
    git.router,
    agent.router,
    computer.router,
    osdev.router,
    security.router,
    approvals.router,
]
