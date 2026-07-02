# -*- coding: utf-8 -*-
"""RAG segmentation evaluation: smart vs fixed-length vs heading-based baseline.

Three-strategy comparison required by the development plan:
- Smart:     heading + semantic boundary + special block protection + overlap
- Heading:   heading + length control only (no semantic boundary, no overlap)
- Fixed:     uniform 512-char chunks, no structure awareness

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
    heading_based_segment,
)
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.retrieval import EmbeddingStore
from backend.tests.eval_dataset import EVAL_DATASET, EvalDocument, EvalQuestion


# ── Strategy labels ─────────────────────────────────────

STRATEGIES = ["smart", "heading", "fixed"]
STRATEGY_LABELS = {
    "smart":   "Smart (heading+semantic+protect+overlap)",
    "heading": "Heading-based (heading+length only)",
    "fixed":   "Fixed-length (512-char uniform)",
}

# ── Helpers ──────────────────────────────────────────────

def _load_and_segment(
    eval_doc: EvalDocument,
    config: SegmentConfig,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """Load a document and segment it with all three strategies.

    Returns: (strategy_chunks_dict, raw_text)
        strategy_chunks_dict: {"smart": [...], "heading": [...], "fixed": [...]}
    """

    doc_path = Path(eval_doc.doc_path)
    suffix = doc_path.suffix.lower()

    # ── Load document ──────────────────────────────────
    blocks = None
    if suffix in (".txt", ".md"):
        raw_text = doc_path.read_text(encoding="utf-8")
    else:
        blocks = load_document(str(doc_path))
        cleaned, _ = preprocess_document_blocks(blocks)
        raw_text = "\n\n".join(b.text for b in cleaned)

    strategy_chunks: dict[str, list[dict[str, Any]]] = {}

    # ── Smart segmentation (full pipeline) ──────────────
    if blocks is not None and suffix not in (".txt", ".md"):
        cleaned, _ = preprocess_document_blocks(blocks)
        smart_result = segment_blocks(cleaned, doc_id=eval_doc.doc_id, config=config)
    else:
        smart_result = segment_text(raw_text, doc_id=eval_doc.doc_id, config=config)
    strategy_chunks["smart"] = smart_result["chunks"]

    # ── Heading-based baseline (structure only) ─────────
    heading_chunk_objects = heading_based_segment(
        raw_text,
        doc_id=f"{eval_doc.doc_id}_heading",
        min_chars=config.min_chars,
        target_chars=config.target_chars,
        max_chars=config.max_chars,
    )
    strategy_chunks["heading"] = _chunks_to_dicts(heading_chunk_objects)

    # ── Fixed-length baseline (no structure) ────────────
    fixed_chunk_objects = fixed_length_segment(
        raw_text, doc_id=f"{eval_doc.doc_id}_fixed"
    )
    strategy_chunks["fixed"] = _chunks_to_dicts(fixed_chunk_objects)

    return strategy_chunks, raw_text


def _chunks_to_dicts(chunk_objects: list[Any]) -> list[dict[str, Any]]:
    """Convert Chunk dataclass objects to dicts for EmbeddingStore."""
    result: list[dict[str, Any]] = []
    for c in chunk_objects:
        if isinstance(c, dict):
            result.append(c)
        else:
            result.append({
                "chunk_id": c.chunk_id,
                "content": c.content,
                "title_path": c.title_path,
                "chunk_type": c.chunk_type,
                "char_count": c.char_count,
                "source_refs": c.source_refs,
                "quality_flags": c.quality_flags,
            })
    return result


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

        # Segment with all three strategies
        strategy_chunks, _ = _load_and_segment(eval_doc, config)
        for strategy in STRATEGIES:
            chunks = strategy_chunks[strategy]
            print(
                f"  {STRATEGY_LABELS[strategy]}: "
                f"{len(chunks)} chunks, "
                f"avg {sum(c['char_count'] for c in chunks) / max(1, len(chunks)):.0f}c"
            )

        # Index all strategies
        for strategy in STRATEGIES:
            store.add_chunks(f"{eval_doc.doc_id}_{strategy}", strategy_chunks[strategy])

        # Per-question evaluation
        doc_results: dict[str, list[dict[str, float]]] = {
            strategy: [] for strategy in STRATEGIES
        }

        for qi, question in enumerate(eval_doc.questions, start=1):
            judge.set_reference(
                " ".join(question.answer_keywords), question.answer_keywords
            )

            # Retrieve and score for each strategy
            scores: dict[str, dict[str, float]] = {}
            for strategy in STRATEGIES:
                hits = store.search(
                    f"{eval_doc.doc_id}_{strategy}", question.question, top_k=5
                )
                metrics = compute_ir_metrics(
                    hits, judge, all_chunks=strategy_chunks[strategy]
                )
                doc_results[strategy].append(metrics)
                scores[strategy] = metrics

            # Winner by Recall@5
            r5_smart = scores["smart"]["recall@5"]
            r5_heading = scores["heading"]["recall@5"]
            r5_fixed = scores["fixed"]["recall@5"]
            best = max(r5_smart, r5_heading, r5_fixed)
            winners = []
            if r5_smart == best:
                winners.append("S")
            if r5_heading == best:
                winners.append("H")
            if r5_fixed == best:
                winners.append("F")

            print(
                f"  Q{qi:02d}: R@5 S={r5_smart:.2f} H={r5_heading:.2f} "
                f"F={r5_fixed:.2f}  [{'+'.join(winners)}]"
            )

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
    print("SUMMARY: Three-Strategy Comparison")
    print("Retrieval: embedding (MiniLM)  |  Relevance: keyword + embedding")
    print(f"{'='*70}")

    all_strategy: dict[str, dict[str, list[float]]] = {
        strategy: {m: [] for m in METRICS} for strategy in STRATEGIES
    }

    for doc_id, doc_results in results.items():
        print(f"\n  [{doc_id}]")
        header = f"  {'Metric':<14}"
        for strategy in STRATEGIES:
            header += f" {strategy:>8}"
        header += f" {'S-H':>8} {'S-F':>8}"
        print(header)
        print(f"  {'-'*56}")

        for metric in METRICS:
            row = f"  {metric:<14}"
            vals: dict[str, float] = {}
            for strategy in STRATEGIES:
                sv = [q[metric] for q in doc_results[strategy]]
                avg = sum(sv) / len(sv) if sv else 0
                vals[strategy] = avg
                all_strategy[strategy][metric].extend(sv)
                row += f" {avg:>8.4f}"
            s_h = vals["smart"] - vals["heading"]
            s_f = vals["smart"] - vals["fixed"]
            row += f" {s_h:>+8.4f} {s_f:>+8.4f}"
            print(row)

    # Overall
    print(f"\n  [OVERALL]")
    header = f"  {'Metric':<14}"
    for strategy in STRATEGIES:
        header += f" {strategy:>8}"
    header += f" {'S vs H':>9} {'S vs F':>9}"
    print(header)
    print(f"  {'-'*58}")

    for metric in METRICS:
        row = f"  {metric:<14}"
        vals: dict[str, float] = {}
        for strategy in STRATEGIES:
            sv = all_strategy[strategy][metric]
            avg = sum(sv) / len(sv) if sv else 0
            vals[strategy] = avg
            row += f" {avg:>8.4f}"

        # Smart vs Heading: how much does semantic boundary add?
        s_vs_h = (
            (vals["smart"] - vals["heading"]) / vals["heading"] * 100
            if vals["heading"] > 0
            else 0
        )
        # Smart vs Fixed: how much does structure+semantic add?
        s_vs_f = (
            (vals["smart"] - vals["fixed"]) / vals["fixed"] * 100
            if vals["fixed"] > 0
            else 0
        )
        row += f" {s_vs_h:>+8.1f}% {s_vs_f:>+8.1f}%"
        print(row)

    # Verdicts
    print(f"\n{'='*70}")
    print("VERDICTS:")
    for strategy in STRATEGIES:
        r5 = (
            sum(all_strategy[strategy]["recall@5"])
            / len(all_strategy[strategy]["recall@5"])
            if all_strategy[strategy]["recall@5"]
            else 0
        )
        print(f"  {STRATEGY_LABELS[strategy]}: Recall@5 = {r5:.4f}")

    r5_s = (
        sum(all_strategy["smart"]["recall@5"]) / len(all_strategy["smart"]["recall@5"])
        if all_strategy["smart"]["recall@5"]
        else 0
    )
    r5_f = (
        sum(all_strategy["fixed"]["recall@5"]) / len(all_strategy["fixed"]["recall@5"])
        if all_strategy["fixed"]["recall@5"]
        else 0
    )
    r5_h = (
        sum(all_strategy["heading"]["recall@5"]) / len(all_strategy["heading"]["recall@5"])
        if all_strategy["heading"]["recall@5"]
        else 0
    )

    improvement_vs_fixed = (r5_s - r5_f) / r5_f * 100 if r5_f > 0 else 0
    semantic_gain = (r5_s - r5_h) / r5_h * 100 if r5_h > 0 else 0
    structure_gain = (r5_h - r5_f) / r5_f * 100 if r5_f > 0 else 0

    print(f"\n  Semantic boundary gain (Smart vs Heading): {semantic_gain:+.1f}%")
    print(f"  Structure gain          (Heading vs Fixed): {structure_gain:+.1f}%")
    print(f"  Total improvement       (Smart vs Fixed):   {improvement_vs_fixed:+.1f}%")

    target = 10.0
    if improvement_vs_fixed >= target:
        print(f"\n  VERDICT: PASS — Recall@5 improvement +{improvement_vs_fixed:.1f}% >= +{target:.0f}% target")
    else:
        print(f"\n  VERDICT: BELOW TARGET — Recall@5 improvement {improvement_vs_fixed:+.1f}% < +{target:.0f}% target")
    print(f"{'='*70}")


if __name__ == "__main__":
    results = run_evaluation()
    print_summary(results)
