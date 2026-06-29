from __future__ import annotations

import re
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
        texts = [chunk.get("retrieval_text") or chunk.get("content", "") for chunk in chunks]
        self.matrix = self.vectorizer.fit_transform(texts)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        top_k = max(1, min(top_k, len(self.chunks)))
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix)[0]
        adjusted_scores = rerank_scores(query, self.chunks, scores)
        ranked_indices = adjusted_scores.argsort()[::-1][:top_k]

        hits: list[RetrievalHit] = []
        for index in ranked_indices:
            chunk = self.chunks[int(index)]
            hits.append(
                RetrievalHit(
                    chunk_id=chunk["chunk_id"],
                    content=chunk["content"],
                    score=round(float(adjusted_scores[index]), 6),
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


def rerank_scores(query: str, chunks: list[dict[str, Any]], scores: Any) -> Any:
    query_terms = extract_query_terms(query)
    if not query_terms:
        return scores
    adjusted = scores.copy()
    metric_query = is_metric_query(query)
    for index, chunk in enumerate(chunks):
        text = normalize_text(str(chunk.get("retrieval_text") or chunk.get("content", "")))
        matches = sum(1 for term in query_terms if term in text)
        if matches:
            adjusted[index] += min(0.08, 0.025 * matches)
        if metric_query and chunk.get("chunk_type") == "metric":
            adjusted[index] += 0.05
    return adjusted


def extract_query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9_@.+-]{1,}|[\u4e00-\u9fff]{2,}", query or ""):
        value = normalize_text(term)
        if len(value) >= 2 and value not in terms:
            terms.append(value)
    return terms


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def is_metric_query(query: str) -> bool:
    return bool(re.search(r"(验收|指标|命中率|准确率|完整率|Recall|nDCG|MRR|%|多少)", query or "", re.I))
