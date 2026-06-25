"""Evaluation for content organisation quality.

Measures:
- Tag accuracy: whether each tag is semantically relevant to its chunk.
- Summary faithfulness: whether the summary stays true to the original.
- Entity precision: whether extracted entities actually appear in the text.

All evaluators reuse the existing sentence-transformers embedding model
via ``embedding_store._get_model()`` / ``_encode()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.app.services.retrieval.embedding_store import _encode, _get_model


# ── Tag accuracy ──────────────────────────────────────────


class TagAccuracyEvaluator:
    """Judge tag quality via embedding similarity to chunk content.

    A tag is "accurate" if its embedding is close enough to the
    chunk content embedding (cosine similarity >= threshold).
    """

    def __init__(self, threshold: float = 0.50) -> None:
        self.threshold = threshold

    def evaluate(
        self, tags: list[str], content: str
    ) -> dict[str, float]:
        """Return precision + average relevance for a set of tags."""
        if not tags or not content.strip():
            return {"precision": 0.0, "avg_relevance": 0.0}

        model = _get_model()
        if model is False:
            return self._fallback_evaluate_tags(tags, content)

        content_vec = _encode([content], model)[0]
        content_norm = float(np.linalg.norm(content_vec))
        if content_norm == 0:
            return {"precision": 0.0, "avg_relevance": 0.0}

        tag_vecs = _encode(tags, model)
        relevances: list[float] = []
        accurate_count = 0

        for tag_vec in tag_vecs:
            dot = float(np.dot(content_vec, tag_vec))
            tag_norm = float(np.linalg.norm(tag_vec))
            if tag_norm == 0:
                relevances.append(0.0)
                continue
            sim = dot / (content_norm * tag_norm)
            relevances.append(sim)
            if sim >= self.threshold:
                accurate_count += 1

        return {
            "precision": round(accurate_count / len(tags), 4),
            "avg_relevance": round(sum(relevances) / len(relevances), 4),
        }

    @staticmethod
    def _fallback_evaluate_tags(
        tags: list[str], content: str
    ) -> dict[str, float]:
        """Simple substring-match fallback when embeddings unavailable."""
        content_lower = content.lower()
        hits = sum(1 for tag in tags if tag.lower() in content_lower)
        return {
            "precision": round(hits / len(tags), 4) if tags else 0.0,
            "avg_relevance": 0.0,
        }


# ── Summary faithfulness ─────────────────────────────────


class SummaryFaithfulnessEvaluator:
    """Judge whether a summary faithfully reflects its source chunk.

    Faithfulness = cosine similarity between summary embedding and
    content embedding.  Higher is better; low scores may indicate
    hallucination or information loss.

    Also checks compression: a summary nearly as long as the content
    is flagged as a poor summary (verbatim copy).
    """

    def __init__(self, threshold: float = 0.55) -> None:
        self.threshold = threshold

    def evaluate(
        self, summary: str, content: str
    ) -> dict[str, float]:
        """Return faithfulness score for a single (summary, content) pair."""
        if not summary or not content.strip():
            return {"faithfulness": 0.0, "is_faithful": False, "compression": 0.0}

        compression = 1.0 - len(summary) / max(len(content), 1)
        # Penalise summaries that are nearly as long as the original.
        if compression < 0.3:
            return {
                "faithfulness": 0.3,
                "is_faithful": False,
                "compression": round(compression, 4),
            }

        model = _get_model()
        if model is False:
            return {
                "faithfulness": 0.5,
                "is_faithful": True,
                "compression": round(compression, 4),
            }

        vecs = _encode([content, summary], model)
        content_vec, summary_vec = vecs[0], vecs[1]

        dot = float(np.dot(content_vec, summary_vec))
        c_norm = float(np.linalg.norm(content_vec))
        s_norm = float(np.linalg.norm(summary_vec))

        if c_norm == 0 or s_norm == 0:
            return {"faithfulness": 0.0, "is_faithful": False, "compression": round(compression, 4)}

        sim = dot / (c_norm * s_norm)
        return {
            "faithfulness": round(sim, 4),
            "is_faithful": sim >= self.threshold,
            "compression": round(compression, 4),
        }

    def evaluate_batch(
        self, summaries: list[str], contents: list[str]
    ) -> dict[str, float]:
        """Return average faithfulness across a batch."""
        if not summaries:
            return {"avg_faithfulness": 0.0, "faithful_rate": 0.0}
        results = [
            self.evaluate(s, c) for s, c in zip(summaries, contents)
        ]
        avg = sum(r["faithfulness"] for r in results) / len(results)
        rate = sum(1 for r in results if r["is_faithful"]) / len(results)
        return {"avg_faithfulness": round(avg, 4), "faithful_rate": round(rate, 4)}


# ── Entity precision ─────────────────────────────────────


class EntityPrecisionEvaluator:
    """Check whether extracted entities actually appear in the text."""

    def evaluate(
        self, entities: list[dict[str, str]], content: str
    ) -> dict[str, float]:
        """Return exact-match rate for entity values."""
        if not entities:
            return {"entity_precision": 1.0, "entity_count": 0}

        content_lower = content.lower()
        hits = sum(
            1 for e in entities
            if e.get("value", "").lower() in content_lower
        )
        return {
            "entity_precision": round(hits / len(entities), 4),
            "entity_count": len(entities),
        }


# ── Aggregate report ────────────────────────────────────


@dataclass
class OrganizeEvaluationReport:
    """Full evaluation report for content-organised chunks."""

    doc_id: str = ""
    chunk_count: int = 0
    avg_tag_precision: float = 0.0
    avg_tag_relevance: float = 0.0
    avg_summary_faithfulness: float = 0.0
    summary_faithful_rate: float = 0.0
    avg_entity_precision: float = 0.0
    per_chunk: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_count": self.chunk_count,
            "avg_tag_precision": self.avg_tag_precision,
            "avg_tag_relevance": self.avg_tag_relevance,
            "avg_summary_faithfulness": self.avg_summary_faithfulness,
            "summary_faithful_rate": self.summary_faithful_rate,
            "avg_entity_precision": self.avg_entity_precision,
        }


def evaluate_organize_results(
    chunks: list[dict[str, Any]],
    doc_id: str = "",
) -> OrganizeEvaluationReport:
    """Run a full evaluation pass over content-organised chunk dicts.

    Each chunk dict is expected to contain:
    - ``content`` (str)
    - ``tags`` (list[str])
    - ``summary`` (str)
    - ``entity_labels`` (list[dict[str, str]])
    """
    tag_eval = TagAccuracyEvaluator()
    summary_eval = SummaryFaithfulnessEvaluator()
    entity_eval = EntityPrecisionEvaluator()

    report = OrganizeEvaluationReport(doc_id=doc_id, chunk_count=len(chunks))

    for chunk in chunks:
        content = chunk.get("content", "")
        tags = chunk.get("tags", [])
        summary = chunk.get("summary", "")
        entities = chunk.get("entity_labels", [])

        tag_r = tag_eval.evaluate(tags, content)
        sum_r = summary_eval.evaluate(summary, content)
        ent_r = entity_eval.evaluate(entities, content)

        report.per_chunk.append({
            "tag_precision": tag_r["precision"],
            "tag_relevance": tag_r["avg_relevance"],
            "summary_faithfulness": sum_r["faithfulness"],
            "entity_precision": ent_r["entity_precision"],
        })

    if report.per_chunk:
        n = len(report.per_chunk)
        report.avg_tag_precision = round(
            sum(c["tag_precision"] for c in report.per_chunk) / n, 4
        )
        report.avg_tag_relevance = round(
            sum(c["tag_relevance"] for c in report.per_chunk) / n, 4
        )
        report.avg_summary_faithfulness = round(
            sum(c["summary_faithfulness"] for c in report.per_chunk) / n, 4
        )
        report.summary_faithful_rate = round(
            sum(
                1 for c in report.per_chunk
                if c["summary_faithfulness"] >= 0.55
            ) / n, 4
        )
        report.avg_entity_precision = round(
            sum(c["entity_precision"] for c in report.per_chunk) / n, 4
        )

    return report
