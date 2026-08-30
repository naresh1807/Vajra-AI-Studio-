"""Long-running process manager for dev servers and watchers.

`run_command` blocks until a command exits - useless for `npm run dev`,
`flask run`, `uvicorn --reload`, etc. Those go through here: started detached,
output captured in a ring buffer, stopped on request or on Core shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import shlex
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])(?::\d+)?[^\s\"'>]*", re.I)
_PORT_RE = re.compile(r"(?:port|:)\s*(\d{2,5})\b", re.I)
_MAX_LINES = 800


def _list2line(argv: list[str]) -> str:
    import subprocess
    import sys

    return subprocess.list2cmdline(argv) if sys.platform == "win32" else shlex.join(argv)


def _as_argv(command: list[str] | str) -> list[str]:
    if isinstance(command, list):
        return [str(c) for c in command]
    return shlex.split(str(command), posix=False)


@dataclass
class ManagedProcess:
    id: str
    argv: list[str]
    cwd: str
    label: str
    proc: asyncio.subprocess.Process
    started_at: float = field(default_factory=time.time)
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=_MAX_LINES))
    exit_code: int | None = None
    _pump: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.exit_code is None and self.proc.returncode is None

    @property
    def url(self) -> str | None:
        for line in reversed(self.lines):
            m = _URL_RE.search(line)
            if m:
                return m.group(0).rstrip(".,)")
        for line in reversed(self.lines):
            m = _PORT_RE.search(line)
            if m and 1024 <= int(m.group(1)) <= 65535:
                return f"http://localhost:{m.group(1)}"
        return None

    def snapshot(self, tail: int = 120) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "argv": self.argv,
            "cwd": self.cwd,
            "running": self.running,
            "exit_code": self.exit_code if not self.running else None,
            "url": self.url,
            "uptime_s": round(time.time() - self.started_at, 1),
            "output": "\n".join(list(self.lines)[-tail:]),
        }


class ProcessManager:
    def __init__(self) -> None:
        self._procs: dict[str, ManagedProcess] = {}

    async def start(
        self, command: list[str] | str, cwd: str, label: str | None = None, *, shell: bool | None = None
    ) -> ManagedProcess:
        argv = _as_argv(command)
        # dev servers are usually shell commands (npm/vite/uvicorn --reload/...):
        # route a bare string through the shell so PATHEXT (.cmd) + && + pipes work.
        use_shell = isinstance(command, str) if shell is None else shell
        common = {
            "cwd": cwd,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
            "stdin": asyncio.subprocess.DEVNULL,
        }
        if use_shell:
            line = command if isinstance(command, str) else _list2line(argv)
            proc = await asyncio.create_subprocess_shell(line, **common)
        else:
            proc = await asyncio.create_subprocess_exec(*argv, **common)
        mp = ManagedProcess(
            id=str(uuid.uuid4())[:8],
            argv=argv,
            cwd=cwd,
            label=label or (command if isinstance(command, str) else " ".join(argv))[:60],
            proc=proc,
        )
        mp._pump = asyncio.create_task(self._pump(mp))
        self._procs[mp.id] = mp
        return mp

    async def _pump(self, mp: ManagedProcess) -> None:
        assert mp.proc.stdout is not None
        try:
            async for raw in mp.proc.stdout:
                mp.lines.append(raw.decode("utf-8", "replace").rstrip("\n"))
        except Exception:  # noqa: BLE001
            pass
        mp.exit_code = await mp.proc.wait()

    def get(self, proc_id: str) -> ManagedProcess | None:
        return self._procs.get(proc_id)

    def list(self) -> list[ManagedProcess]:
        return list(self._procs.values())

    async def stop(self, proc_id: str, timeout: float = 5.0) -> bool:
        mp = self._procs.get(proc_id)
        if not mp:
            return False
        if mp.running:
            try:
                mp.proc.terminate()
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(mp.proc.wait(), timeout=timeout)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError, OSError):
                    mp.proc.kill()
        if mp._pump:
            mp._pump.cancel()
        return True

    async def stop_all(self) -> None:
        for pid in list(self._procs):
            await self.stop(pid, timeout=2.0)

    def prune(self) -> None:
        """Drop finished processes that have been read at least once."""
        for pid, mp in list(self._procs.items()):
            if not mp.running and time.time() - mp.started_at > 3600:
                del self._procs[pid]


process_manager = ProcessManager()
