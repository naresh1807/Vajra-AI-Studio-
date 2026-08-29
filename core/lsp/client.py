"""Minimal async LSP client over a language server's stdio.

Handles Content-Length framing, the initialize handshake, textDocument sync,
and request/response for completion / hover / definition. Diagnostics arrive as
`textDocument/publishDiagnostics` notifications and are cached per-URI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import pathname2url

log = logging.getLogger("vajra.lsp")

_REQUEST_TIMEOUT = 12.0


def path_to_uri(path: str) -> str:
    return "file:" + pathname2url(str(Path(path).resolve()))


def uri_to_path(uri: str) -> str:
    return str(Path(unquote(urlparse(uri).path.lstrip("/"))))


def _key(path_or_uri: str) -> str:
    """Canonical key for a document, tolerant of file-URI drive-letter and
    percent-encoding differences between us and the language server."""
    p = uri_to_path(path_or_uri) if path_or_uri.startswith("file:") else path_or_uri
    try:
        resolved = str(Path(p).resolve())
    except (OSError, ValueError):
        resolved = p
    return resolved.lower() if len(resolved) > 1 and resolved[1] == ":" else resolved


class LspClient:
    def __init__(self, argv: list[str], root: str) -> None:
        self.argv = argv
        self.root = str(Path(root).resolve())
        self.proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._diagnostics: dict[str, list[dict]] = {}
        self._open: dict[str, int] = {}  # uri -> version
        self._ready = asyncio.Event()
        self._reader_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    # -- lifecycle ------------------------------------------------------
    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            *self.argv,
            cwd=self.root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._request(
            "initialize",
            {
                "processId": None,
                "rootUri": path_to_uri(self.root),
                "capabilities": {
                    "textDocument": {
                        "synchronization": {"didSave": True, "dynamicRegistration": False},
                        "publishDiagnostics": {"relatedInformation": True},
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "hover": {"contentFormat": ["markdown", "plaintext"]},
                        "definition": {"linkSupport": False},
                    }
                },
                "workspaceFolders": [{"uri": path_to_uri(self.root), "name": Path(self.root).name}],
            },
        )
        self._notify("initialized", {})
        self._ready.set()

    async def stop(self) -> None:
        if not self.proc:
            return
        with contextlib.suppress(Exception):
            self._notify("shutdown", None)
            self._notify("exit", None)
        if self._reader_task:
            self._reader_task.cancel()
        with contextlib.suppress(Exception):
            self.proc.terminate()
            await asyncio.wait_for(self.proc.wait(), timeout=3)

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    # -- protocol io --------------------------------------------------
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
                    line = line.decode("ascii", "replace").strip()
                    if not line:
                        break
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip().lower()] = v.strip()
                length = int(headers.get("content-length", 0))
                if not length:
                    continue
                body = await stream.readexactly(length)
                self._dispatch(json.loads(body.decode("utf-8")))
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            return
        except Exception:  # noqa: BLE001
            log.exception("lsp read loop crashed")

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.pop(msg["id"], None)
            if fut and not fut.done():
                fut.set_result(msg.get("result") if "error" not in msg else {"_error": msg["error"]})
            return
        method = msg.get("method")
        if method == "textDocument/publishDiagnostics":
            p = msg["params"]
            self._diagnostics[_key(p["uri"])] = p.get("diagnostics", [])
        elif method and "id" in msg:
            # server -> client request we don't implement; answer with null
            self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    def _send(self, payload: dict) -> None:
        if not (self.proc and self.proc.stdin):
            return
        raw = json.dumps(payload).encode("utf-8")
        self.proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)

    def _notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method: str, params: Any) -> Any:
        self._id += 1
        rid = self._id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        except TimeoutError:
            self._pending.pop(rid, None)
            return None

    # -- document sync ---------------------------------------------
    async def sync(self, path: str, content: str, language_id: str) -> None:
        await self._ready.wait()
        uri = path_to_uri(path)
        async with self._lock:
            if uri not in self._open:
                self._open[uri] = 1
                self._notify(
                    "textDocument/didOpen",
                    {"textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": content}},
                )
            else:
                self._open[uri] += 1
                self._notify(
                    "textDocument/didChange",
                    {
                        "textDocument": {"uri": uri, "version": self._open[uri]},
                        "contentChanges": [{"text": content}],
                    },
                )

    def diagnostics(self, path: str) -> list[dict]:
        return self._diagnostics.get(_key(path), [])

    # -- language features ----------------------------------------
    async def completion(self, path: str, line: int, character: int) -> list[dict]:
        res = await self._request(
            "textDocument/completion",
            {"textDocument": {"uri": path_to_uri(path)}, "position": {"line": line, "character": character}},
        )
        if not res:
            return []
        items = res.get("items", res) if isinstance(res, dict) else res
        return items or []

    async def hover(self, path: str, line: int, character: int) -> str | None:
        res = await self._request(
            "textDocument/hover",
            {"textDocument": {"uri": path_to_uri(path)}, "position": {"line": line, "character": character}},
        )
        if not res or not res.get("contents"):
            return None
        c = res["contents"]
        if isinstance(c, dict):
            return c.get("value")
        if isinstance(c, list):
            return "\n\n".join(x.get("value", x) if isinstance(x, dict) else str(x) for x in c)
        return str(c)

    async def definition(self, path: str, line: int, character: int) -> list[dict]:
        res = await self._request(
            "textDocument/definition",
            {"textDocument": {"uri": path_to_uri(path)}, "position": {"line": line, "character": character}},
        )
        if not res:
            return []
        locs = res if isinstance(res, list) else [res]
        out = []
        for loc in locs:
            uri = loc.get("uri") or loc.get("targetUri")
            rng = loc.get("range") or loc.get("targetSelectionRange")
            if uri and rng:
                out.append({"path": uri_to_path(uri), "range": rng})
        return out
