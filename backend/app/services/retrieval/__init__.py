"""Retrieval backends.

    TF-IDF (tfidf_store):       Lightweight char n-gram, no dependencies.
    Semantic (semantic_store):  Embedding-based, sentence-transformers (default).
"""

from .embedding_store import EmbeddingStore
from .semantic_store import SemanticVectorStore, semantic_store
from .tfidf_store import InMemoryVectorStore, vector_store

__all__ = [
    "EmbeddingStore",
    "InMemoryVectorStore",
    "SemanticVectorStore",
    "semantic_store",
    "vector_store",
]
