"""A single Debug Adapter Protocol session over debugpy's stdio adapter.

Covers the manual's Run/debug feature group for Python: launch, breakpoints,
stop/continue/step, call stack, scoped variables, and repl evaluate. Output and
state-change events are pushed to a callback so the API can relay them over
/ws/events.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

log = logging.getLogger("vajra.dap")

_TIMEOUT = 15.0
EventCb = Callable[[dict], Awaitable[None]] | None


class DapSession:
    def __init__(self, root: str, program: str, args: list[str] | None, on_event: EventCb = None) -> None:
        self.id = str(uuid.uuid4())[:8]
        self.root = str(Path(root).resolve())
        self.program = program
        self.args = args or []
        self.on_event = on_event
        self.proc: asyncio.subprocess.Process | None = None
        self._seq = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader: asyncio.Task | None = None
        self._event_task: asyncio.Task | None = None
        self._event_q: asyncio.Queue[dict] = asyncio.Queue()
        self._breakpoints: dict[str, list[int]] = {}
        self._configured = asyncio.Event()

        self.state = "starting"  # starting | running | stopped | terminated
        self.stopped_reason = ""
        self.thread_id: int | None = None
        self.frames: list[dict] = []
        self.output: list[str] = []

    # -- lifecycle ---------------------------------------------------
    async def start(self, breakpoints: dict[str, list[int]] | None = None) -> None:
        self._breakpoints = {str(Path(k).resolve()): v for k, v in (breakpoints or {}).items()}
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "debugpy.adapter",
            cwd=self.root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader = asyncio.create_task(self._read_loop())
        self._event_task = asyncio.create_task(self._event_loop())
        await self._request("initialize", {
            "clientID": "vajra", "adapterID": "debugpy", "linesStartAt1": True,
            "columnsStartAt1": True, "pathFormat": "path", "supportsRunInTerminalRequest": False,
        })
        await self._request("launch", {
            "request": "launch", "type": "python", "program": str(Path(self.root) / self.program),
            "args": self.args, "cwd": self.root, "console": "internalConsole",
            "justMyCode": False, "redirectOutput": True,
        })
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._configured.wait(), timeout=_TIMEOUT)
        self.state = "running"

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            await self._request("disconnect", {"terminateDebuggee": True}, timeout=3)
        for task in (self._reader, self._event_task):
            if task:
                task.cancel()
        if self.proc:
            with contextlib.suppress(Exception):
                if self.proc.stdin:
                    self.proc.stdin.close()
            if self.proc.returncode is None:
                with contextlib.suppress(ProcessLookupError, OSError):
                    self.proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.proc.wait(), timeout=3)
        self.state = "terminated"

    # -- protocol io ----------------------------------------------
    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        stream = self.proc.stdout
        try:
            while True:
                headers: dict[str, str] = {}
                while True:
                    line = await stream.readline()
                    if not line:
                        return
                    s = line.decode("ascii", "replace").strip()
                    if not s:
                        break
                    if ":" in s:
                        k, v = s.split(":", 1)
                        headers[k.strip().lower()] = v.strip()
                n = int(headers.get("content-length", 0))
                if not n:
                    continue
                body = await stream.readexactly(n)
                await self._dispatch(json.loads(body.decode("utf-8")))
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            return
        except Exception:  # noqa: BLE001
            log.exception("dap read loop crashed")

    async def _dispatch(self, msg: dict) -> None:
        """Runs in the reader loop - must not block. Responses resolve futures
        immediately; events/requests are queued for _event_loop so their
        handlers can issue further requests without deadlocking the reader."""
        mtype = msg.get("type")
        if mtype == "response":
            fut = self._pending.pop(msg.get("request_seq"), None)
            if fut and not fut.done():
                fut.set_result(msg if msg.get("success") else {"_error": msg.get("message"), **msg})
        else:
            self._event_q.put_nowait(msg)

    async def _event_loop(self) -> None:
        try:
            while True:
                msg = await self._event_q.get()
                try:
                    if msg.get("type") == "event":
                        await self._on_event(msg.get("event", ""), msg.get("body") or {})
                    elif msg.get("type") == "request":
                        await self._send({
                            "type": "response", "request_seq": msg.get("seq"), "success": False,
                            "command": msg.get("command"), "seq": self._next_seq(),
                        })
                except Exception:  # noqa: BLE001
                    log.exception("dap event handler failed: %s", msg.get("event"))
        except asyncio.CancelledError:
            return

    async def _on_event(self, event: str, body: dict) -> None:
        if event == "initialized":
            for src, lines in self._breakpoints.items():
                await self._request("setBreakpoints", {
                    "source": {"path": src}, "breakpoints": [{"line": ln} for ln in lines],
                })
            await self._request("configurationDone", {})
            self._configured.set()
        elif event == "stopped":
            self.state = "stopped"
            self.stopped_reason = body.get("reason", "")
            self.thread_id = body.get("threadId")
            await self._load_stack()
        elif event == "continued":
            self.state = "running"
            self.frames = []
        elif event == "output":
            text = body.get("output", "")
            self.output.append(text)
            self.output[:] = self.output[-500:]
        elif event in ("terminated", "exited"):
            self.state = "terminated"
        await self._emit({"type": "dap.event", "session": self.id, "event": event, "body": body,
                          "state": self.state})

    async def _emit(self, payload: dict) -> None:
        if self.on_event:
            with contextlib.suppress(Exception):
                await self.on_event(payload)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def _send(self, payload: dict) -> None:
        if not (self.proc and self.proc.stdin):
            return
        raw = json.dumps(payload).encode("utf-8")
        self.proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)

    async def _request(self, command: str, arguments: dict, timeout: float = _TIMEOUT) -> dict:
        seq = self._next_seq()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[seq] = fut
        await self._send({"type": "request", "seq": seq, "command": command, "arguments": arguments})
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            self._pending.pop(seq, None)
            return {"_error": "timeout"}

    # -- debug operations ---------------------------------------
    async def _load_stack(self) -> None:
        if self.thread_id is None:
            return
        res = await self._request("stackTrace", {"threadId": self.thread_id, "levels": 20})
        raw = (res.get("body") or {}).get("stackFrames", [])
        self.frames = [
            {
                "id": f["id"],
                "name": f.get("name"),
                "path": (f.get("source") or {}).get("path"),
                "line": f.get("line"),
            }
            for f in raw
        ]

    async def variables(self, frame_id: int | None = None) -> list[dict]:
        fid = frame_id if frame_id is not None else (self.frames[0]["id"] if self.frames else None)
        if fid is None:
            return []
        scopes = (await self._request("scopes", {"frameId": fid})).get("body", {}).get("scopes", [])
        out: list[dict] = []
        for scope in scopes[:2]:  # Locals, Globals
            ref = scope.get("variablesReference")
            if not ref:
                continue
            vres = await self._request("variables", {"variablesReference": ref})
            for v in vres.get("body", {}).get("variables", [])[:80]:
                out.append({"scope": scope.get("name"), "name": v.get("name"),
                            "value": v.get("value"), "type": v.get("type")})
        return out

    async def _thread_op(self, command: str) -> dict:
        if self.thread_id is None:
            return {"_error": "no active thread"}
        self.state = "running"
        self.frames = []
        return await self._request(command, {"threadId": self.thread_id})

    async def continue_(self) -> dict:
        return await self._thread_op("continue")

    async def next(self) -> dict:
        return await self._thread_op("next")

    async def step_in(self) -> dict:
        return await self._thread_op("stepIn")

    async def step_out(self) -> dict:
        return await self._thread_op("stepOut")

    async def pause(self) -> dict:
        if self.thread_id is None:
            # ask for threads first
            tr = await self._request("threads", {})
            threads = tr.get("body", {}).get("threads", [])
            if threads:
                self.thread_id = threads[0]["id"]
        return await self._request("pause", {"threadId": self.thread_id})

    async def set_breakpoints(self, path: str, lines: list[int]) -> list[dict]:
        src = str(Path(path).resolve())
        self._breakpoints[src] = lines
        res = await self._request("setBreakpoints", {
            "source": {"path": src}, "breakpoints": [{"line": ln} for ln in lines],
        })
        return res.get("body", {}).get("breakpoints", [])

    async def evaluate(self, expr: str) -> dict:
        fid = self.frames[0]["id"] if self.frames else None
        res = await self._request("evaluate", {"expression": expr, "frameId": fid, "context": "repl"})
        body = res.get("body") or {}
        return {"result": body.get("result"), "type": body.get("type"), "error": res.get("_error")}

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "stopped_reason": self.stopped_reason,
            "program": self.program,
            "frames": self.frames,
            "output": "".join(self.output)[-8000:],
            "breakpoints": {k: v for k, v in self._breakpoints.items()},
        }
