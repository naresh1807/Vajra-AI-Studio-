"""Text embeddings for the RAG index.

Uses an OpenAI-compatible ``/embeddings`` endpoint when one is configured
(``VAJRA_EMBED_BASE_URL``); otherwise falls back to a deterministic offline
lexical vector (feature-hashed token counts) so retrieval always works with no
network and no heavy local dependency.
"""

from __future__ import annotations

import hashlib
import math
import os
import re

import httpx

from core.config import get_settings

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")
_LEXICAL_DIM = 512


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _tokens(text: str) -> list[str]:
    raw: list[str] = []
    for m in _TOKEN.findall(text):
        raw.append(m)
        # split snake_case / camelCase into subtokens too
        for part in re.split(r"_|(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", m):
            if len(part) > 2 and part != m:
                raw.append(part)
    out: list[str] = []
    for w in raw:
        w = w.lower()
        if len(w) > 2:
            out.append(_stem(w))
    return out


def _lexical_vector(text: str) -> list[float]:
    vec = [0.0] * _LEXICAL_DIM
    for tok in _tokens(text):
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=4).digest(), "little")
        idx = h % _LEXICAL_DIM
        sign = 1.0 if (h >> 31) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


class Embedder:
    def __init__(self) -> None:
        s = get_settings()
        self.base_url = (s.vajra_embed_base_url or "").rstrip("/")
        self.model = s.vajra_embed_model
        self.api_key = os.environ.get(s.vajra_embed_api_key_env or "", "")
        self.kind = "remote" if self.base_url else "lexical"
        self.dim = 0 if self.base_url else _LEXICAL_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.base_url:
            return [_lexical_vector(t) for t in texts]
        return self._embed_remote(texts)

    def _embed_remote(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        vectors: list[list[float]] = []
        with httpx.Client(timeout=60) as client:
            for i in range(0, len(texts), 64):
                batch = [t[:8000] for t in texts[i : i + 64]]
                try:
                    r = client.post(
                        f"{self.base_url}/embeddings",
                        headers=headers,
                        json={"model": self.model, "input": batch},
                    )
                    r.raise_for_status()
                    data = sorted(r.json()["data"], key=lambda d: d["index"])
                    vectors.extend(d["embedding"] for d in data)
                except (httpx.HTTPError, KeyError, ValueError):
                    # degrade to lexical for this batch rather than fail the index
                    vectors.extend(_lexical_vector(t) for t in batch)
        if vectors:
            self.dim = len(vectors[0])
        return vectors
