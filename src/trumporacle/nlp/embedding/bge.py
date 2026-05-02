"""BGE embeddings (1024-d) for pgvector storage."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("BAAI/bge-large-en-v1.5")


def encode_texts(texts: Iterable[str], *, batch_size: int = 32) -> np.ndarray:
    """Return float32 matrix (n, 1024)."""

    model = _model()
    return model.encode(list(texts), batch_size=batch_size, normalize_embeddings=True)
