"""Split a source file into overlapping line-window chunks for indexing."""

from __future__ import annotations

from dataclasses import dataclass

_WINDOW = 50
_OVERLAP = 12
_MAX_CHUNK_CHARS = 4000


@dataclass(frozen=True)
class Chunk:
    path: str          # workspace-relative, forward slashes
    start_line: int    # 1-based, inclusive
    end_line: int      # 1-based, inclusive
    text: str

    @property
    def ref(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


def chunk_text(path: str, text: str, window: int = _WINDOW, overlap: int = _OVERLAP) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return []
    step = max(1, window - overlap)
    chunks: list[Chunk] = []
    for start in range(0, len(lines), step):
        block = lines[start : start + window]
        if not block:
            break
        body = "\n".join(block)[:_MAX_CHUNK_CHARS]
        if body.strip():
            chunks.append(Chunk(path, start + 1, start + len(block), body))
        if start + window >= len(lines):
            break
    return chunks
