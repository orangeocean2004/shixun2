"""Semantic vector store — drop-in replacement for InMemoryVectorStore.

Wraps EmbeddingStore (sentence-transformers) behind the same interface
as the TF-IDF store, so routes.py needs minimal changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .embedding_store import EmbeddingStore


@dataclass
class SemanticRetrievalHit:
    """Same shape as RetrievalHit from tfidf_store."""

    chunk_id: str
    content: str
    score: float
    title_path: list[str]
    chunk_type: str
    char_count: int
    source_refs: list[dict[str, Any]]
    quality_flags: list[str]


class SemanticVectorStore:
    """Embedding-based vector store with the same API as InMemoryVectorStore.

    Usage is identical to the TF-IDF store::

        store = SemanticVectorStore()
        store.upsert("doc1", chunks)
        hits = store.search("doc1", "query text", top_k=5)
    """

    def __init__(self) -> None:
        self._store = EmbeddingStore()

    def upsert(self, doc_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Index chunks. Returns summary compatible with index response."""
        result = self._store.add_chunks(doc_id, chunks)
        return {
            "doc_id": result["doc_id"],
            "chunk_count": result["chunk_count"],
            "embedding_backend": f"semantic:{result['embedding_model']}",
            "persisted": False,
            "dimension": result.get("dimension", 0),
        }

    def search(
        self, doc_id: str, query: str, top_k: int = 5
    ) -> list[SemanticRetrievalHit]:
        """Search by semantic similarity. Raises KeyError if doc_id unknown."""
        hits = self._store.search(doc_id, query, top_k=top_k)
        return [
            SemanticRetrievalHit(
                chunk_id=h.get("chunk_id", ""),
                content=h.get("content", ""),
                score=h.get("score", 0.0),
                title_path=h.get("title_path", []),
                chunk_type=h.get("chunk_type", "normal"),
                char_count=h.get("char_count", 0),
                source_refs=h.get("source_refs", []),
                quality_flags=h.get("quality_flags", []),
            )
            for h in hits
        ]

    def list_doc_ids(self) -> list[str]:
        """Return sorted list of indexed document IDs."""
        return self._store.list_docs()


# Module-level singleton (replaces the TF-IDF vector_store)
semantic_store = SemanticVectorStore()
