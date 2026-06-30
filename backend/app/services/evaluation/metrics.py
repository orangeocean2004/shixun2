"""RAG retrieval evaluation metrics.

Provides semantic relevance judgment (embedding similarity instead of
keyword matching) and standard IR metrics: Recall@k, Precision@k,
MRR, nDCG.

Architecture:
    EmbeddingRelevance  — judges relevance via embedding cosine similarity
    compute_ir_metrics  — computes Recall/Precision/MRR/nDCG from ranked hits
    compare_segmenters  — runs a full side-by-side comparison
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from backend.app.services.embedding import EmbeddingEncoder, get_default_encoder


# ── Relevance judge ─────────────────────────────────────

KEYWORD_RELEVANCE_THRESHOLD = 0.34
"""At least one third of expected keywords is strong direct evidence."""

KEYWORD_SEMANTIC_THRESHOLD = 0.57
"""Use a stricter semantic cutoff when keyword hints are available."""


@dataclass
class EmbeddingRelevance:
    """Judge chunk relevance by embedding similarity to reference text.

    Instead of exact keyword matching (which penalizes synonyms),
    this encodes the reference text and each chunk into the same
    embedding space and uses cosine similarity as the relevance score.

    A chunk is "relevant" if similarity >= threshold.
    """

    threshold: float = 0.45
    """Cosine similarity threshold for relevance (0..1).

    With the MiniLM-L12-v2 model, 0.45 is a conservative threshold
    that captures semantic relatedness without too many false positives.
    """

    _reference_vec: np.ndarray | None = field(default=None, repr=False, init=False)
    _reference_text: str = ""
    _keywords: list[str] = field(default_factory=list, repr=False, init=False)
    _encoder: EmbeddingEncoder = field(default_factory=get_default_encoder, repr=False)

    def set_reference(self, text: str, keywords: list[str] | None = None) -> None:
        """Set the reference answer text to compare chunks against.

        Typically this is the concatenation of answer_keywords from
        the evaluation dataset.
        """
        normalized_keywords = [keyword.strip() for keyword in keywords or [] if keyword.strip()]
        if (
            text == self._reference_text
            and normalized_keywords == self._keywords
            and self._reference_vec is not None
        ):
            return
        self._reference_text = text
        self._keywords = normalized_keywords
        vecs = self._encoder.encode([text])
        self._reference_vec = vecs[0]

    def score(self, chunk_content: str) -> float:
        """Return relevance score (cosine similarity) for a chunk."""
        if self._reference_vec is None:
            return 0.0
        chunk_vec = self._encoder.encode([chunk_content])[0]
        # Cosine similarity
        dot = float(np.dot(self._reference_vec, chunk_vec))
        ref_norm = float(np.linalg.norm(self._reference_vec))
        chunk_norm = float(np.linalg.norm(chunk_vec))
        if ref_norm == 0 or chunk_norm == 0:
            return 0.0
        return dot / (ref_norm * chunk_norm)

    def keyword_score(self, chunk_content: str) -> float:
        """Return the share of expected answer keywords found in the chunk."""

        if not self._keywords:
            return 0.0
        normalized = normalize_for_keyword_match(chunk_content)
        hits = 0
        for keyword in self._keywords:
            if normalize_for_keyword_match(keyword) in normalized:
                hits += 1
        return hits / len(self._keywords)

    def is_relevant(self, chunk_content: str) -> bool:
        """True if the chunk is semantically relevant to the reference."""
        keyword_score = self.keyword_score(chunk_content)
        if keyword_score >= KEYWORD_RELEVANCE_THRESHOLD:
            return True
        if keyword_score > 0 and contains_number_or_metric(chunk_content):
            return True
        semantic_threshold = self._semantic_threshold()
        return self.score(chunk_content) >= semantic_threshold

    def judge_batch(self, chunks: list[dict[str, Any]]) -> list[bool]:
        """Return relevance labels for a batch of chunks."""
        contents = [c.get("content", "") for c in chunks]
        if not contents:
            return []

        labels = [False] * len(contents)
        semantic_indexes: list[int] = []
        for index, content in enumerate(contents):
            keyword_score = self.keyword_score(content)
            if keyword_score >= KEYWORD_RELEVANCE_THRESHOLD:
                labels[index] = True
            elif keyword_score > 0 and contains_number_or_metric(content):
                labels[index] = True
            else:
                semantic_indexes.append(index)

        if self._reference_vec is None or not semantic_indexes:
            return labels

        semantic_threshold = self._semantic_threshold()
        semantic_contents = [contents[index] for index in semantic_indexes]
        chunk_vectors = self._encoder.encode(semantic_contents)
        ref_norm = float(np.linalg.norm(self._reference_vec))
        if ref_norm == 0:
            return labels

        for vector_index, chunk_index in enumerate(semantic_indexes):
            chunk_vec = chunk_vectors[vector_index]
            chunk_norm = float(np.linalg.norm(chunk_vec))
            if chunk_norm == 0:
                continue
            score = float(np.dot(self._reference_vec, chunk_vec)) / (ref_norm * chunk_norm)
            labels[chunk_index] = score >= semantic_threshold
        return labels

    def _semantic_threshold(self) -> float:
        if self._keywords:
            return max(self.threshold, KEYWORD_SEMANTIC_THRESHOLD)
        return self.threshold


# ── IR metrics ──────────────────────────────────────────

def compute_ir_metrics(
    retrieved_chunks: list[dict[str, Any]],
    relevance_judge: EmbeddingRelevance,
    *,
    all_chunks: list[dict[str, Any]] | None = None,
    k_values: tuple[int, ...] = (1, 3, 5),
) -> dict[str, float]:
    """Compute Recall@k, Precision@k, MRR, and nDCG@k.

    Args:
        retrieved_chunks: Ranked list of retrieved chunk dicts.
        relevance_judge: Configured EmbeddingRelevance instance with
                         reference text already set.
        all_chunks: Full corpus used to count all relevant chunks.
        k_values: Which cut-off ranks to compute metrics for.

    Returns:
        Dict mapping metric name → value.
    """

    relevance = relevance_judge.judge_batch(retrieved_chunks)
    if all_chunks is None:
        total_relevant = sum(relevance)
    else:
        total_relevant = sum(relevance_judge.judge_batch(all_chunks))

    metrics: dict[str, float] = {}

    for k in k_values:
        effective_k = min(k, len(relevance))
        rel_at_k = relevance[:effective_k]

        # Recall@k
        metrics[f"recall@{k}"] = (
            sum(rel_at_k) / total_relevant if total_relevant > 0 else 0.0
        )

        # Precision@k
        metrics[f"precision@{k}"] = sum(rel_at_k) / effective_k if effective_k > 0 else 0.0

        # nDCG@k: binary relevance gain, so irrelevant high-score hits do not look perfect.
        dcg = 0.0
        idcg = 0.0
        for i in range(effective_k):
            gain = 1.0 if relevance[i] else 0.0
            denom = math.log2(i + 2)
            dcg += gain / denom
        ideal_relevant = min(total_relevant, effective_k)
        for i in range(ideal_relevant):
            idcg += 1.0 / math.log2(i + 2)
        metrics[f"ndcg@{k}"] = dcg / idcg if idcg > 0 else 0.0

    # MRR
    for rank, rel in enumerate(relevance, start=1):
        if rel:
            metrics["mrr"] = 1.0 / rank
            break
    else:
        metrics["mrr"] = 0.0

    return metrics


def normalize_for_keyword_match(text: str) -> str:
    """Normalize text for robust Chinese/English keyword containment."""

    return re.sub(r"\s+", "", (text or "").lower())


def contains_number_or_metric(text: str) -> bool:
    """Detect chunks that contain numeric metric evidence."""

    return bool(re.search(r"(\d+%|≥|≤|>=|<=|Recall@|nDCG|MRR|命中率|准确率|完整率)", text or ""))


# ── Segmenter comparison ────────────────────────────────

@dataclass
class SegmenterComparison:
    """Result of comparing two segmenters on one document."""

    doc_id: str
    smart_chunk_count: int
    baseline_chunk_count: int
    questions: list[_QuestionResult] = field(default_factory=list)

    @property
    def smart_wins(self) -> int:
        return sum(1 for q in self.questions if q.winner == "smart")

    @property
    def baseline_wins(self) -> int:
        return sum(1 for q in self.questions if q.winner == "baseline")

    @property
    def ties(self) -> int:
        return sum(1 for q in self.questions if q.winner == "tie")


@dataclass
class _QuestionResult:
    question: str
    smart_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    winner: str  # "smart", "baseline", or "tie"


def run_segmenter_comparison(
    doc_id: str,
    questions: list[tuple[str, str]],
    smart_chunks: list[dict[str, Any]],
    baseline_chunks: list[dict[str, Any]],
    retrieval_fn: Callable[[str, str, int], list[dict[str, Any]]],
    relevance_threshold: float = 0.45,
) -> SegmenterComparison:
    """Run a head-to-head comparison between smart and baseline segmentation.

    Args:
        doc_id: Document identifier.
        questions: List of (question_text, reference_answer_text) tuples.
        smart_chunks: Chunks from the smart segmenter.
        baseline_chunks: Chunks from the fixed-length baseline.
        retrieval_fn: Function(query, doc_id_suffix, top_k) → ranked hits.
        relevance_threshold: Cosine similarity threshold for relevance.

    Returns:
        SegmenterComparison with per-question and aggregate results.
    """
    comparison = SegmenterComparison(
        doc_id=doc_id,
        smart_chunk_count=len(smart_chunks),
        baseline_chunk_count=len(baseline_chunks),
    )

    judge = EmbeddingRelevance(threshold=relevance_threshold)

    for question, reference in questions:
        judge.set_reference(reference)

        # Smart retrieval
        smart_hits = retrieval_fn(question, f"{doc_id}_smart", 5)
        smart_metrics = compute_ir_metrics(smart_hits, judge)

        # Baseline retrieval
        baseline_hits = retrieval_fn(question, f"{doc_id}_baseline", 5)
        baseline_metrics = compute_ir_metrics(baseline_hits, judge)

        # Determine winner by recall@5
        if smart_metrics["recall@5"] > baseline_metrics["recall@5"]:
            winner = "smart"
        elif baseline_metrics["recall@5"] > smart_metrics["recall@5"]:
            winner = "baseline"
        else:
            winner = "tie"

        comparison.questions.append(
            _QuestionResult(
                question=question,
                smart_metrics=smart_metrics,
                baseline_metrics=baseline_metrics,
                winner=winner,
            )
        )

    return comparison
