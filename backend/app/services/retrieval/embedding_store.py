"""Embedding-based vector store for semantic retrieval.

Replaces TF-IDF char n-gram with sentence-transformers embeddings
and cosine similarity. Uses pure numpy — no FAISS, no ChromaDB.

Why this module exists:
    TF-IDF char n-gram systematically favors longer chunks (more n-gram
    overlap with queries). This makes the smart segmenter look worse than
    fixed-length baselines, even when its chunks are semantically better.
    Embedding-based retrieval eliminates this length bias.

Model:
    paraphrase-multilingual-MiniLM-L12-v2 (lightweight, 118 MB, 384-dim)
    Supports 50+ languages including Chinese and English.
    Falls back gracefully if sentence-transformers is not installed.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .embedding import EmbeddingEncoder, get_default_encoder


class EmbeddingStore:
    """Semantic vector store backed by numpy + sentence-transformers.

    Usage::

        store = EmbeddingStore()
        store.add_chunks("doc1", chunks)
        hits = store.search("doc1", "What is RAG?", top_k=5)
        # hits: list of {chunk_id, content, score, ...}
    """

    def __init__(
        self,
        encoder: EmbeddingEncoder | None = None,
        ranker: LexicalBoostRanker | None = None,
    ) -> None:
        self._indexes: dict[str, _EmbeddingIndex] = {}
        self._encoder = encoder or get_default_encoder()
        self._ranker = ranker or LexicalBoostRanker()

    # ── public API ──────────────────────────────────────

    def add_chunks(self, doc_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Index a list of chunks (same dict format as the segmenter output).

        Returns a summary dict with doc_id, chunk_count, and model info.
        """
        if not chunks:
            raise ValueError("chunks list is empty")

        texts = [_enrich_text(chunk) for chunk in chunks]
        embeddings = self._encoder.encode(texts)

        index = _EmbeddingIndex(doc_id=doc_id, chunks=chunks, embeddings=embeddings)
        self._indexes[doc_id] = index

        return {
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "embedding_model": self._encoder.model_name,
            "dimension": embeddings.shape[1] if embeddings.shape[0] > 0 else 0,
        }

    def search(
        self,
        doc_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Search a document's chunks by cosine similarity.

        Raises KeyError if doc_id is unknown.
        """
        index = self._indexes.get(doc_id)
        if index is None:
            known = ", ".join(sorted(self._indexes)) or "(none)"
            raise KeyError(f"Unknown doc_id: {doc_id}. Known: {known}")

        query_vec = self._encoder.encode([query])
        scores = index.similarity(query_vec[0])
        reranked = self._ranker.rerank(query, index.chunks, scores)
        ranked = reranked.argsort()[::-1][:top_k]

        hits: list[dict[str, Any]] = []
        for idx in ranked:
            chunk = index.chunks[int(idx)]
            hits.append(
                {
                    "chunk_id": chunk.get("chunk_id", ""),
                    "content": chunk.get("content", ""),
                    "score": round(float(reranked[idx]), 6),
                    "embedding_score": round(float(scores[idx]), 6),
                    "title_path": chunk.get("title_path", []),
                    "chunk_type": chunk.get("chunk_type", "normal"),
                    "char_count": chunk.get("char_count", 0),
                    "source_refs": chunk.get("source_refs", []),
                    "quality_flags": chunk.get("quality_flags", []),
                }
            )
        return hits

    def list_docs(self) -> list[str]:
        """Return sorted list of indexed document IDs."""
        return sorted(self._indexes)


# ── internal helpers ────────────────────────────────────


def _enrich_text(chunk: dict[str, Any]) -> str:
    """Build a semantically rich text for embedding, using all available metadata.

    Priority:
    1. Pre-built retrieval_text (smart segmenter) — already has labels, metrics, titles
    2. Title path + section titles + summary + entity tags + content
    3. Content only (fallback for baseline segmenters)

    This gives smart-segmented chunks richer embeddings that capture their
    semantic role within the document, improving retrieval precision.
    """
    # Smart segmenter provides pre-built retrieval_text
    retrieval_text = chunk.get("retrieval_text")
    if isinstance(retrieval_text, str) and retrieval_text.strip():
        return retrieval_text

    # Build enriched text from available metadata
    title_path = chunk.get("title_path", [])
    section_titles = chunk.get("section_titles", [])
    content = chunk.get("content", "")

    parts: list[str] = []

    if title_path:
        parts.append("标题: " + " > ".join(str(t) for t in title_path if str(t).strip()))

    if section_titles:
        parts.append("小节: " + "；".join(str(s) for s in section_titles if str(s).strip()))

    # Include summary as a concentrated preview (helps embedding quality)
    summary = (chunk.get("summary") or "").strip()
    if summary:
        parts.append("摘要: " + summary[:300])

    # Include entity tags for keyword-level enrichment
    entity_tags = chunk.get("entity_tags") or chunk.get("entity_tags_json")
    if isinstance(entity_tags, str):
        import json as _json
        try:
            entity_tags = _json.loads(entity_tags)
        except Exception:
            entity_tags = []
    if isinstance(entity_tags, list) and entity_tags:
        parts.append("实体: " + "，".join(str(e) for e in entity_tags[:5]))

    # Include labels
    label = chunk.get("label") or chunk.get("label_json")
    if isinstance(label, str):
        import json as _json
        try:
            label = _json.loads(label)
        except Exception:
            label = []
    if isinstance(label, list) and label:
        parts.append("标签: " + "，".join(str(l) for l in label[:5]))

    if parts:
        parts.append("正文: " + (content or ""))
        return "\n".join(p.strip() for p in parts if p.strip())

    return content or ""


class LexicalBoostRanker:
    """Apply small lexical and metric boosts after embedding similarity."""

    def rerank(self, query: str, chunks: list[dict[str, Any]], scores: np.ndarray) -> np.ndarray:
        query_terms = extract_query_terms(query)
        if not query_terms:
            return scores

        adjusted = scores.astype(np.float32, copy=True)
        metric_query = is_metric_query(query)
        for index, chunk in enumerate(chunks):
            retrieval_text = _enrich_text(chunk)
            normalized = normalize_text(retrieval_text)
            matches = sum(1 for term in query_terms if term in normalized)
            if matches:
                adjusted[index] += min(0.14, 0.03 * matches)
            if metric_query and chunk.get("chunk_type") == "metric":
                adjusted[index] += 0.05
        return adjusted


def rerank_scores(query: str, chunks: list[dict[str, Any]], scores: np.ndarray) -> np.ndarray:
    """Backward-compatible wrapper for callers that use the old helper."""

    return LexicalBoostRanker().rerank(query, chunks, scores)


def extract_query_terms(query: str) -> list[str]:
    """Extract stable terms from Chinese/English natural-language queries."""

    normalized_query = normalize_text(query)
    terms: list[str] = []

    for term in re.findall(r"[A-Za-z][A-Za-z0-9_@.+-]{1,}", query or ""):
        value = normalize_text(term)
        if len(value) >= 2 and value not in terms:
            terms.append(value)

    chinese_text = "".join(re.findall(r"[\u4e00-\u9fff]+", query or ""))
    if chinese_text:
        try:
            import jieba
            candidates = jieba.lcut(chinese_text)
        except Exception:
            candidates = re.findall(r"[\u4e00-\u9fff]{2,6}", chinese_text)
        stopwords = {"什么", "哪些", "如何", "为什么", "多少", "根据", "本文", "文章", "这个", "这些", "以及", "是否", "进行", "使用", "提供"}
        for term in candidates:
            value = normalize_text(term)
            if len(value) >= 2 and value not in stopwords and value not in terms:
                terms.append(value)

    for term in re.findall(r"[\u4e00-\u9fff]{4,}", query or ""):
        value = normalize_text(term)
        if value not in terms:
            terms.append(value)

    for phrase in (
        "技术难点",
        "验收标准",
        "评价指标",
        "技术方案",
        "项目创新点",
        "差异化优势",
        "固定长度",
        "语义感知",
        "结构感知",
        "下游检索",
        "闭环评估",
    ):
        value = normalize_text(phrase)
        if value in normalized_query and value not in terms:
            terms.append(value)
    return terms

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def is_metric_query(query: str) -> bool:
    return bool(re.search(r"(验收|指标|命中率|准确率|完整率|Recall|nDCG|MRR|%|多少)", query or "", re.I))


class _EmbeddingIndex:
    """One document's chunk embeddings."""

    __slots__ = ("doc_id", "chunks", "embeddings", "_norms")

    def __init__(
        self,
        doc_id: str,
        chunks: list[dict[str, Any]],
        embeddings: np.ndarray,
    ) -> None:
        self.doc_id = doc_id
        self.chunks = chunks
        self.embeddings = embeddings
        # Pre-compute L2 norms for fast cosine similarity
        self._norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        self._norms[self._norms == 0] = 1.0  # avoid div-by-zero

    def similarity(self, query_vec: np.ndarray) -> np.ndarray:
        """Return cosine similarity scores for all chunks."""
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            query_norm = 1.0
        return (self.embeddings @ query_vec) / (self._norms.flatten() * query_norm)

