from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class RetrievalHit:
    chunk_id: str
    content: str
    score: float
    title_path: list[str]
    chunk_type: str
    char_count: int
    source_refs: list[dict[str, Any]]
    quality_flags: list[str]


class TfidfChunkIndex:
    """轻量本地向量索引。

    这是无 API Key 的第一版检索链路，适合先验证 chunk 是否能被召回。
    后续可以把这里替换成真实 embedding + FAISS/Chroma。
    """

    def __init__(self, doc_id: str, chunks: list[dict[str, Any]]) -> None:
        self.doc_id = doc_id
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(1, 4),
            lowercase=True,
            sublinear_tf=True,
        )
        texts = [chunk.get("content", "") for chunk in chunks]
        self.matrix = self.vectorizer.fit_transform(texts)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        top_k = max(1, min(top_k, len(self.chunks)))
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix)[0]
        ranked_indices = scores.argsort()[::-1][:top_k]

        hits: list[RetrievalHit] = []
        for index in ranked_indices:
            chunk = self.chunks[int(index)]
            hits.append(
                RetrievalHit(
                    chunk_id=chunk["chunk_id"],
                    content=chunk["content"],
                    score=round(float(scores[index]), 6),
                    title_path=list(chunk.get("title_path", [])),
                    chunk_type=chunk.get("chunk_type", "normal"),
                    char_count=chunk.get("char_count", len(chunk.get("content", ""))),
                    source_refs=list(chunk.get("source_refs", [])),
                    quality_flags=list(chunk.get("quality_flags", [])),
                )
            )
        return hits


class InMemoryVectorStore:
    """按 doc_id 保存当前进程内的文档索引。"""

    def __init__(self) -> None:
        self._indexes: dict[str, TfidfChunkIndex] = {}
        self._lock = Lock()

    def upsert(self, doc_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        if not chunks:
            raise ValueError("没有可入库的 chunk")
        index = TfidfChunkIndex(doc_id, chunks)
        with self._lock:
            self._indexes[doc_id] = index
        return {
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "embedding_backend": "tfidf_char_ngram",
            "persisted": False,
        }

    def search(self, doc_id: str, query: str, top_k: int = 5) -> list[RetrievalHit]:
        with self._lock:
            index = self._indexes.get(doc_id)
        if index is None:
            raise KeyError(doc_id)
        return index.search(query, top_k=top_k)

    def list_doc_ids(self) -> list[str]:
        with self._lock:
            return sorted(self._indexes)


vector_store = InMemoryVectorStore()
