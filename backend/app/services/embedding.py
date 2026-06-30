"""Shared embedding helpers for segmentation, retrieval, and evaluation."""

from __future__ import annotations

import threading
import zlib
from typing import Any

import numpy as np

DEFAULT_EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
FALLBACK_EMBEDDING_MODEL_NAME = "fallback-tfidf"


class EmbeddingEncoder:
    """Lazy sentence-transformers encoder with a deterministic local fallback."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
        *,
        local_files_only: bool = True,
    ) -> None:
        self._lock = threading.Lock()
        self._model: Any | None | bool = None
        self._model_name = model_name
        self._local_files_only = local_files_only

    @property
    def model_name(self) -> str:
        return self._model_name if self._ensure_model() else FALLBACK_EMBEDDING_MODEL_NAME

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.encode_with_model(texts)
        if vectors is not None:
            return vectors
        return fallback_encode(texts)

    def encode_with_model(self, texts: list[str]) -> np.ndarray | None:
        model = self._ensure_model()
        if not model or model is False:
            return None
        try:
            return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        except Exception:
            return None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self._model_name,
                    local_files_only=self._local_files_only,
                )
            except Exception:
                self._model = False
            return self._model


_DEFAULT_ENCODER = EmbeddingEncoder()


def get_default_encoder() -> EmbeddingEncoder:
    return _DEFAULT_ENCODER


def embedding_similarity(
    left: str,
    right: str,
    *,
    encoder: EmbeddingEncoder | None = None,
    use_fallback: bool = True,
) -> float | None:
    """Return cosine similarity for two texts, optionally without fallback vectors."""

    active_encoder = encoder or get_default_encoder()
    vectors = (
        active_encoder.encode([left, right])
        if use_fallback
        else active_encoder.encode_with_model([left, right])
    )
    if vectors is None:
        return None
    left_vec = vectors[0]
    right_vec = vectors[1]
    denom = float(np.linalg.norm(left_vec) * np.linalg.norm(right_vec))
    if denom == 0:
        return 0.0
    return round(float(np.dot(left_vec, right_vec) / denom), 6)


def fallback_encode(texts: list[str]) -> np.ndarray:
    """Character 3-gram vectors used when sentence-transformers is unavailable."""

    dim = 256
    vectors = np.zeros((len(texts), dim), dtype=np.float32)

    for i, text in enumerate(texts):
        normalized = (text or "").lower()
        for j in range(len(normalized) - 2):
            ngram = normalized[j : j + 3]
            bucket = zlib.crc32(ngram.encode("utf-8")) % dim
            vectors[i, bucket] += 1.0

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


__all__ = [
    "DEFAULT_EMBEDDING_MODEL_NAME",
    "FALLBACK_EMBEDDING_MODEL_NAME",
    "EmbeddingEncoder",
    "embedding_similarity",
    "fallback_encode",
    "get_default_encoder",
]
