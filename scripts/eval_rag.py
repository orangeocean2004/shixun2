# -*- coding: utf-8 -*-
"""RAG segmentation evaluation: smart vs fixed-length baseline.

Uses embedding-based retrieval (EmbeddingStore) and semantic relevance
(EmbeddingRelevance) to fairly compare segmentation strategies without
the length bias inherent in TF-IDF and keyword matching.

Usage:
    python scripts/eval_rag.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.segmenting import SegmentConfig, segment_blocks, segment_text
from backend.app.services.document_loader import load_document
from backend.app.services.evaluation import (
    EmbeddingRelevance,
    compute_ir_metrics,
    fixed_length_segment,
)
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.retrieval import EmbeddingStore
from backend.tests.eval_dataset import EVAL_DATASET, EvalDocument, EvalQuestion


# ── Helpers ──────────────────────────────────────────────

def _load_and_segment(
    eval_doc: EvalDocument,
    config: SegmentConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Load a document and segment it with both smart and baseline methods.

    Returns: (smart_chunks, baseline_chunks, raw_text)
    """

    doc_path = Path(eval_doc.doc_path)
    suffix = doc_path.suffix.lower()

    # Load
    blocks = None
    if suffix in (".txt", ".md"):
        raw_text = doc_path.read_text(encoding="utf-8")
    else:
        blocks = load_document(str(doc_path))
        cleaned, _ = preprocess_document_blocks(blocks)
        raw_text = "\n\n".join(b.text for b in cleaned)

    # Smart segmentation
    if blocks is not None and suffix not in (".txt", ".md"):
        cleaned, _ = preprocess_document_blocks(blocks)
        smart_result = segment_blocks(cleaned, doc_id=eval_doc.doc_id, config=config)
    else:
        smart_result = segment_text(raw_text, doc_id=eval_doc.doc_id, config=config)
    smart_chunks = smart_result["chunks"]

    # Baseline (fixed-length) segmentation
    baseline_chunk_objects = fixed_length_segment(
        raw_text, doc_id=f"{eval_doc.doc_id}_fixed"
    )
    baseline_chunks = [
        {
            "chunk_id": c.chunk_id,
            "content": c.content,
            "title_path": c.title_path,
            "chunk_type": c.chunk_type,
            "char_count": c.char_count,
            "source_refs": c.source_refs,
            "quality_flags": c.quality_flags,
        }
        for c in baseline_chunk_objects
    ]

    return smart_chunks, baseline_chunks, raw_text


# ── Runner ───────────────────────────────────────────────

def run_evaluation() -> dict[str, Any]:
    config = SegmentConfig()
    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)

    all_results: dict[str, Any] = {}

    for eval_doc in EVAL_DATASET:
        if not Path(eval_doc.doc_path).exists():
            print(f"  SKIP {eval_doc.doc_id}: file not found")
            continue

        print(f"\n{'='*60}")
        print(f"Document: {eval_doc.doc_id}")
        print(f"{'='*60}")

        # Segment
        smart_chunks, baseline_chunks, _ = _load_and_segment(eval_doc, config)
        print(
            f"  Smart:    {len(smart_chunks)} chunks, "
            f"avg {sum(c['char_count'] for c in smart_chunks) / max(1, len(smart_chunks)):.0f}c"
        )
        print(
            f"  Baseline: {len(baseline_chunks)} chunks, "
            f"avg {sum(c['char_count'] for c in baseline_chunks) / max(1, len(baseline_chunks)):.0f}c"
        )

        # Index with embedding store
        store.add_chunks(f"{eval_doc.doc_id}_smart", smart_chunks)
        store.add_chunks(f"{eval_doc.doc_id}_baseline", baseline_chunks)

        doc_results: dict[str, list[dict[str, float]]] = {
            "smart": [],
            "baseline": [],
        }

        for qi, question in enumerate(eval_doc.questions, start=1):
            # Set reference for hybrid keyword + embedding relevance judgment
            judge.set_reference(" ".join(question.answer_keywords), question.answer_keywords)

            # Smart retrieval
            smart_hits = store.search(
                f"{eval_doc.doc_id}_smart", question.question, top_k=5
            )
            smart_metrics = compute_ir_metrics(smart_hits, judge, all_chunks=smart_chunks)

            # Baseline retrieval
            baseline_hits = store.search(
                f"{eval_doc.doc_id}_baseline", question.question, top_k=5
            )
            baseline_metrics = compute_ir_metrics(baseline_hits, judge, all_chunks=baseline_chunks)

            doc_results["smart"].append(smart_metrics)
            doc_results["baseline"].append(baseline_metrics)

            # Winner marker
            winner = "="
            if smart_metrics["recall@5"] > baseline_metrics["recall@5"]:
                winner = "S"
            elif baseline_metrics["recall@5"] > smart_metrics["recall@5"]:
                winner = "B"

            print(
                f"  Q{qi}: R@5 S={smart_metrics['recall@5']:.2f} "
                f"B={baseline_metrics['recall@5']:.2f}  [{winner}]"
            )
            if smart_metrics["recall@5"] < baseline_metrics["recall@5"]:
                print("     smart miss:", summarize_hit(smart_hits[0]) if smart_hits else "(no hit)")
                print("     base top:  ", summarize_hit(baseline_hits[0]) if baseline_hits else "(no hit)")

        all_results[eval_doc.doc_id] = doc_results

    return all_results


def summarize_hit(hit: dict[str, Any]) -> str:
    """Compact one retrieved hit for failure analysis output."""

    content = str(hit.get("content", "")).replace("\n", " ")
    content = " ".join(content.split())
    return f"{hit.get('chunk_id', '')} score={hit.get('score', 0):.4f} {content[:120]}"


# ── Report ───────────────────────────────────────────────

METRICS = ["recall@1", "recall@3", "recall@5", "precision@5", "ndcg@5", "mrr"]


def print_summary(results: dict[str, Any]) -> None:
    print(f"\n{'='*70}")
    print("SUMMARY: Smart vs Baseline (Fixed-512)")
    print("Retrieval: embedding (MiniLM)  |  Relevance: keyword + embedding over all chunks")
    print(f"{'='*70}")

    all_smart: dict[str, list[float]] = {m: [] for m in METRICS}
    all_baseline: dict[str, list[float]] = {m: [] for m in METRICS}

    for doc_id, doc_results in results.items():
        print(f"\n  [{doc_id}]")
        print(f"  {'Metric':<14} {'Smart':>8} {'Baseline':>8} {'Delta':>9}")
        print(f"  {'-'*40}")

        for metric in METRICS:
            sv = [q[metric] for q in doc_results["smart"]]
            bv = [q[metric] for q in doc_results["baseline"]]
            sa = sum(sv) / len(sv) if sv else 0
            ba = sum(bv) / len(bv) if bv else 0
            delta = sa - ba
            sign = "+" if delta >= 0 else ""
            print(f"  {metric:<14} {sa:>8.4f} {ba:>8.4f} {sign}{delta:>8.4f}")
            all_smart[metric].extend(sv)
            all_baseline[metric].extend(bv)

    # Overall
    print(f"\n  [OVERALL]")
    print(f"  {'Metric':<14} {'Smart':>8} {'Baseline':>8} {'Delta':>8} {'Change':>10}")
    print(f"  {'-'*50}")

    for metric in METRICS:
        sa = sum(all_smart[metric]) / len(all_smart[metric]) if all_smart[metric] else 0
        ba = sum(all_baseline[metric]) / len(all_baseline[metric]) if all_baseline[metric] else 0
        delta = sa - ba
        pct = (delta / ba * 100) if ba > 0 else float("inf")
        sign = "+" if delta >= 0 else ""
        print(f"  {metric:<14} {sa:>8.4f} {ba:>8.4f} {sign}{delta:>7.4f} {sign}{pct:>8.1f}%")

    # Verdict
    r5_s = sum(all_smart["recall@5"]) / len(all_smart["recall@5"]) if all_smart["recall@5"] else 0
    r5_b = sum(all_baseline["recall@5"]) / len(all_baseline["recall@5"]) if all_baseline["recall@5"] else 0
    improvement = (r5_s - r5_b) / r5_b * 100 if r5_b > 0 else 0

    print(f"\n{'='*70}")
    if improvement >= 10:
        print(f"VERDICT: PASS  --  Recall@5 improvement +{improvement:.1f}%  >=  10% target")
    else:
        print(f"VERDICT: BELOW TARGET  --  Recall@5 improvement {improvement:+.1f}%  <  10% target")
        print(f"  Next: tune semantic_threshold, target_chars, overlap_sentences")
    print(f"{'='*70}")


if __name__ == "__main__":
    results = run_evaluation()
    print_summary(results)
