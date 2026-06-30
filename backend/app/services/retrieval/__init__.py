"""In-memory retrieval backend used by offline evaluation scripts."""

from .embedding_store import EmbeddingStore

__all__ = [
    "EmbeddingStore",
]
