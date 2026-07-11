# -*- coding: utf-8 -*-
"""RAG evaluation on self-built Chinese document dataset.

Usage:
    python scripts/eval_self_built.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.segmenting import SegmentConfig, segment_text
from backend.app.services.evaluation import (
    EmbeddingRelevance,
    compute_ir_metrics,
    fixed_length_segment,
)
from backend.app.services.retrieval import EmbeddingStore
from backend.tests.eval_dataset_self_built import EVAL_DATASET


def _chunks_to_dicts(chunk_objects):
    result = []
    for c in chunk_objects:
        if isinstance(c, dict):
            result.append(c)
        else:
            result.append({
                "chunk_id": c.chunk_id, "content": c.content,
                "title_path": c.title_path, "chunk_type": c.chunk_type,
                "char_count": c.char_count, "source_refs": c.source_refs,
                "quality_flags": c.quality_flags,
            })
    return result


def main():
    config = SegmentConfig()
    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)

    all_smart: list[float] = []
    all_fixed: list[float] = []
    all_smart_ndcg: list[float] = []
    all_fixed_ndcg: list[float] = []

    for doc in EVAL_DATASET:
        doc_path = Path(doc.doc_path)
        if not doc_path.exists():
            print(f"SKIP {doc.doc_id}: file not found")
            continue

        text = doc_path.read_text(encoding="utf-8")

        # Segment
        smart_result = segment_text(text, doc_id=doc.doc_id, config=config)
        smart_chunks = smart_result["chunks"]

        fixed_objs = fixed_length_segment(text, doc_id=f"{doc.doc_id}_fixed")
        fixed_chunks = _chunks_to_dicts(fixed_objs)

        print(f"\n{doc.doc_id}: Smart={len(smart_chunks)} chunks, Fixed={len(fixed_chunks)} chunks")

        # Evaluate
        for qi, qa in enumerate(doc.questions):
            question = qa.question
            reference = " ".join(qa.answer_keywords)
            judge.set_reference(reference, qa.answer_keywords)

            # Smart
            store.add_chunks(doc.doc_id, smart_chunks)
            smart_hits = store.search(doc.doc_id, question, top_k=5)
            smart_metrics = compute_ir_metrics(smart_hits, judge, all_chunks=smart_chunks)

            # Fixed
            store.add_chunks(f"{doc.doc_id}_fixed", fixed_chunks)
            fixed_hits = store.search(f"{doc.doc_id}_fixed", question, top_k=5)
            fixed_metrics = compute_ir_metrics(fixed_hits, judge, all_chunks=fixed_chunks)

            all_smart.append(smart_metrics["recall_at_5"])
            all_fixed.append(fixed_metrics["recall_at_5"])
            all_smart_ndcg.append(smart_metrics["ndcg_at_5"])
            all_fixed_ndcg.append(fixed_metrics["ndcg_at_5"])

            r5s = smart_metrics["recall_at_5"]
            r5f = fixed_metrics["recall_at_5"]
            winner = "S" if r5s > r5f else ("F" if r5f > r5s else "=")
            print(f"  Q{qi+1}: R@5 S={r5s:.2f} F={r5f:.2f} [{winner}]")

    # Summary
    avg_smart_r5 = sum(all_smart) / len(all_smart) if all_smart else 0
    avg_fixed_r5 = sum(all_fixed) / len(all_fixed) if all_fixed else 0
    avg_smart_ndcg = sum(all_smart_ndcg) / len(all_smart_ndcg) if all_smart_ndcg else 0
    avg_fixed_ndcg = sum(all_fixed_ndcg) / len(all_fixed_ndcg) if all_fixed_ndcg else 0

    r5_gain = (avg_smart_r5 - avg_fixed_r5) / avg_fixed_r5 * 100 if avg_fixed_r5 > 0 else 0
    ndcg_gain = (avg_smart_ndcg - avg_fixed_ndcg) / avg_fixed_ndcg * 100 if avg_fixed_ndcg > 0 else 0

    print(f"\n{'='*60}")
    print(f"SELF-BUILT DATASET RESULTS ({len(all_smart)} QA pairs, {len(EVAL_DATASET)} docs)")
    print(f"{'='*60}")
    print(f"  Smart  Recall@5: {avg_smart_r5:.4f}")
    print(f"  Fixed  Recall@5: {avg_fixed_r5:.4f}")
    print(f"  Recall@5 Gain:   {r5_gain:+.1f}%")
    print(f"  Smart  NDCG@5:   {avg_smart_ndcg:.4f}")
    print(f"  Fixed  NDCG@5:   {avg_fixed_ndcg:.4f}")
    print(f"  NDCG@5 Gain:     {ndcg_gain:+.1f}%")
    print()

    if r5_gain >= 10:
        print(f"  VERDICT: Recall@5 +{r5_gain:.1f}%  >= +10%  PASS")
    else:
        print(f"  VERDICT: Recall@5 {r5_gain:+.1f}%  <  +10%  BELOW TARGET")
    if ndcg_gain >= 10:
        print(f"  VERDICT: NDCG@5   +{ndcg_gain:.1f}%  >= +10%  PASS")
    else:
        print(f"  VERDICT: NDCG@5   {ndcg_gain:+.1f}%  <  +10%  BELOW TARGET")


if __name__ == "__main__":
    main()
