"""Disk cache of bge-m3 embeddings for training and evaluation (git-ignored).

Keyed by the sha256 of the exact text that `analyze()` would embed, so a cached vector is the
one production would compute.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ..embed import embed_texts
from ..llm import OllamaClient

log = logging.getLogger(__name__)
BATCH = 16


def _key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\0{text}".encode()).hexdigest()


class EmbeddingCache:
    """Append-only JSONL file of {key: vector}."""

    def __init__(self, path: Path) -> None:
        """Load an existing cache file (if any)."""
        self.path = path
        self.vectors: dict[str, list[float]] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.vectors[row["k"]] = row["v"]

    def get_many(
        self, texts: list[str], client: OllamaClient | None, model: str
    ) -> list[list[float] | None]:
        """Cached vectors; misses are embedded with Ollama when a client is given."""
        keys = [_key(model, t) for t in texts]
        missing = sorted(
            {k: t for k, t in zip(keys, texts, strict=True) if k not in self.vectors}.items()
        )
        if missing and client is not None:
            log.info("embedding %d texts with %s", len(missing), model)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                for i in range(0, len(missing), BATCH):
                    chunk = missing[i : i + BATCH]
                    vectors = embed_texts([t for _, t in chunk], client, model)
                    for (k, _), v in zip(chunk, vectors, strict=True):
                        self.vectors[k] = [round(x, 6) for x in v]
                        fh.write(json.dumps({"k": k, "v": self.vectors[k]}) + "\n")
        return [self.vectors.get(k) for k in keys]
