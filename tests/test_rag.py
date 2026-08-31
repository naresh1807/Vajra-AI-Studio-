"""RAG: chunking, offline lexical embedding, incremental index, retrieval."""

from __future__ import annotations

import pytest

from core.rag.chunker import chunk_text
from core.rag.embed import Embedder, cosine
from core.rag.index import RagIndex


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch):
    """These tests exercise the deterministic offline path - pin it on even when
    the machine's .env points VAJRA_EMBED_BASE_URL at a real endpoint."""
    from core.config import get_settings

    monkeypatch.setenv("VAJRA_EMBED_BASE_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_chunk_text_windows_and_overlap():
    text = "\n".join(f"line {i}" for i in range(1, 121))
    chunks = chunk_text("a.py", text, window=50, overlap=10)
    assert chunks[0].start_line == 1 and chunks[0].end_line == 50
    assert chunks[1].start_line == 41  # step = window - overlap
    assert chunks[-1].end_line == 120
    assert all(c.path == "a.py" for c in chunks)


def test_lexical_embedder_is_offline_and_deterministic():
    e = Embedder()
    # no VAJRA_EMBED_BASE_URL in the test env
    assert e.kind == "lexical" and e.dim == 512
    v1 = e.embed(["def resolve_known_folder(name): ..."])[0]
    v2 = e.embed(["def resolve_known_folder(name): ..."])[0]
    assert v1 == v2
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6  # L2-normalised


def test_lexical_similarity_ranks_related_text_higher():
    e = Embedder()
    q = e.embed(["ProcessManager start stop terminate the managed process"])[0]
    close = e.embed(["class ProcessManager:\n    def stop(self):\n        self.process.terminate()"])[0]
    far = e.embed(["the quick brown fox jumps over the lazy dog"])[0]
    assert cosine(q, close) > cosine(q, far)


def test_index_build_search_and_incremental(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "auth.py").write_text(
        "def verify_token(tok):\n    return tok == SECRET  # pairing token check\n", encoding="utf-8"
    )
    (tmp_path / "pkg" / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    idx = RagIndex(tmp_path)
    stats = idx.reindex()
    assert stats["files"] == 2 and stats["chunks"] >= 2 and stats["changed"] == 2

    hits = idx.search("token authentication check", k=2)
    assert hits and hits[0].path == "pkg/auth.py"
    assert hits[0].start_line >= 1 and hits[0].text

    # unchanged -> nothing re-embedded
    assert idx.reindex()["changed"] == 0

    # edit one file -> only it re-embeds; deleting one is reflected
    (tmp_path / "pkg" / "auth.py").write_text("def verify_token(tok):\n    return False\n", encoding="utf-8")
    (tmp_path / "pkg" / "math_utils.py").unlink()
    s2 = idx.reindex()
    assert s2["changed"] == 1 and s2["removed"] == 1 and s2["files"] == 1


def test_index_persists_across_instances(tmp_path):
    (tmp_path / "m.py").write_text("x = 1\n" * 10, encoding="utf-8")
    RagIndex(tmp_path).reindex()
    fresh = RagIndex(tmp_path)
    assert fresh.files and fresh.chunk_count >= 1
    assert (tmp_path / ".vajra" / "rag" / "index.json").exists()
