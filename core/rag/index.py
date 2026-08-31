"""Per-workspace semantic index: chunk source files, embed, retrieve.

The index lives at ``<root>/.vajra/rag/index.json`` and is incremental - only
files whose content hash changed are re-embedded on ``reindex()``.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from core.rag.chunker import chunk_text
from core.rag.embed import Embedder, cosine

_IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".vajra", ".pytest_cache", ".ruff_cache", ".idea", ".next",
    ".gradle", "Pods", ".dart_tool",
}
_CODE_EXT = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs", ".go",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".java", ".kt", ".rb", ".php",
    ".swift", ".dart", ".lua", ".sh", ".ps1", ".sql", ".html", ".css", ".scss",
    ".vue", ".svelte", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json",
    ".gradle", ".cmake", ".mk", ".proto", ".graphql",
}
_MAX_FILE_BYTES = 256_000
_MAX_FILES = 4000


@dataclass
class Hit:
    ref: str
    path: str
    start_line: int
    end_line: int
    score: float
    text: str


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8", "replace"), digest_size=16).hexdigest()


class RagIndex:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.dir = self.root / ".vajra" / "rag"
        self.path = self.dir / "index.json"
        self.embedder = Embedder()
        # files: {relpath: {"hash": str, "chunks": [{"s","e","text","vec"}]}}
        self.files: dict[str, dict] = {}
        self.embedder_kind = self.embedder.kind
        self.updated_at = 0.0
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return
        if data.get("embedder_kind") != self.embedder.kind:
            return  # embeddings from a different model are not comparable
        self.files = data.get("files", {})
        self.embedder_kind = data.get("embedder_kind", self.embedder.kind)
        self.updated_at = data.get("updated_at", 0.0)

    def _save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "embedder_kind": self.embedder.kind,
            "model": self.embedder.model if self.embedder.kind == "remote" else "lexical",
            "updated_at": self.updated_at,
            "files": self.files,
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    # -- indexing -----------------------------------------------------
    def _iter_files(self):
        count = 0
        for p in sorted(self.root.rglob("*")):
            if count >= _MAX_FILES:
                return
            if p.is_dir():
                continue
            if any(part in _IGNORE_DIRS for part in p.relative_to(self.root).parts):
                continue
            if p.suffix.lower() not in _CODE_EXT:
                continue
            try:
                if p.stat().st_size > _MAX_FILE_BYTES:
                    continue
                yield p, p.read_text("utf-8")
                count += 1
            except (OSError, UnicodeDecodeError):
                continue

    def reindex(self) -> dict:
        seen: set[str] = set()
        changed = 0
        pending: list[tuple[str, list]] = []  # (rel, chunks) needing embedding
        for path, text in self._iter_files():
            rel = path.relative_to(self.root).as_posix()
            seen.add(rel)
            h = _hash(text)
            if self.files.get(rel, {}).get("hash") == h:
                continue
            chunks = chunk_text(rel, text)
            pending.append((rel, chunks))
            self.files[rel] = {"hash": h, "chunks": []}
            changed += 1

        # batch-embed every new chunk in one call
        flat_texts = [f"{rel}\n{c.text}" for rel, chunks in pending for c in chunks]
        vectors = self.embedder.embed(flat_texts) if flat_texts else []
        vi = 0
        for rel, chunks in pending:
            recs = []
            for c in chunks:
                recs.append({"s": c.start_line, "e": c.end_line, "text": c.text, "vec": vectors[vi]})
                vi += 1
            self.files[rel]["chunks"] = recs

        removed = [rel for rel in self.files if rel not in seen]
        for rel in removed:
            del self.files[rel]

        self.embedder_kind = self.embedder.kind
        self.updated_at = time.time()
        self._save()
        return {
            "files": len(self.files), "chunks": self.chunk_count,
            "changed": changed, "removed": len(removed), "embedder": self.embedder.kind,
            "paths": sorted(self.files),
        }

    # -- query ------------------------------------------------------
    @property
    def chunk_count(self) -> int:
        return sum(len(f["chunks"]) for f in self.files.values())

    def search(self, query: str, k: int = 6) -> list[Hit]:
        if not query.strip() or not self.files:
            return []
        qv = self.embedder.embed([query], input_type="query")[0]
        scored: list[Hit] = []
        for rel, f in self.files.items():
            for c in f["chunks"]:
                scored.append(Hit(
                    ref=f"{rel}:{c['s']}-{c['e']}", path=rel,
                    start_line=c["s"], end_line=c["e"],
                    score=cosine(qv, c["vec"]), text=c["text"],
                ))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:k]

    def status(self) -> dict:
        return {
            "root": str(self.root),
            "indexed": bool(self.files),
            "files": len(self.files),
            "chunks": self.chunk_count,
            "embedder": self.embedder.kind,
            "model": self.embedder.model if self.embedder.kind == "remote" else "lexical",
            "updated_at": self.updated_at,
        }
