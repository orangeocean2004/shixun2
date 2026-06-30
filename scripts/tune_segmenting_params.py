"""Grid search segmentation parameters against the bundled RAG eval set.

Usage:
    python scripts/tune_segmenting_params.py --limit 20
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.document_loader import load_document
from backend.app.services.evaluation import EmbeddingRelevance, compute_ir_metrics, fixed_length_segment
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.retrieval import EmbeddingStore
from backend.app.services.segmenting import SegmentConfig, segment_blocks, segment_text
from backend.tests.eval_dataset import EVAL_DATASET
from scripts.eval_rag import METRICS


SEARCH_SPACE = {
    "min_chars": [180, 220, 260, 300],
    "target_chars": [550, 650, 750, 900],
    "max_chars": [800, 900, 1000, 1200],
    "heading_flush_min_chars": [80, 120, 180, 240, 300],
    "semantic_boundary_threshold": [0.30, 0.35, 0.45, 0.55],
    "overlap_sentences": [0, 1],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune segmentation params for RAG retrieval.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of configs to test.")
    parser.add_argument("--top", type=int, default=10, help="How many best configs to print.")
    parser.add_argument(
        "--strict-missing-docs",
        action="store_true",
        help="Fail instead of warning when an eval document path is missing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    corpus = load_eval_corpus(strict_missing_docs=args.strict_missing_docs)
    baseline_metrics = evaluate_baseline(corpus)
    results: list[dict[str, Any]] = []

    for index, config in enumerate(iter_configs(), start=1):
        if args.limit and index > args.limit:
            break
        metrics = evaluate_config(config, corpus, baseline_metrics)
        row = {"config": config, **metrics}
        results.append(row)
        print(
            f"[{index:03d}] R5={metrics['recall@5']:.4f} "
            f"B={metrics['baseline_recall@5']:.4f} "
            f"improve={metrics['recall@5_improvement_pct']:+.1f}% "
            f"P5={metrics['precision@5']:.4f} MRR={metrics['mrr']:.4f} "
            f"{format_config(config)}"
        )

    print("\nBEST CONFIGS")
    for rank, row in enumerate(sorted(results, key=rank_key, reverse=True)[: args.top], start=1):
        print(
            f"{rank:02d}. R5={row['recall@5']:.4f} "
            f"improve={row['recall@5_improvement_pct']:+.1f}% "
            f"P5={row['precision@5']:.4f} MRR={row['mrr']:.4f} "
            f"{format_config(row['config'])}"
        )


def iter_configs() -> list[SegmentConfig]:
    keys = list(SEARCH_SPACE)
    configs: list[SegmentConfig] = []
    for values in itertools.product(*(SEARCH_SPACE[key] for key in keys)):
        params = dict(zip(keys, values))
        if params["target_chars"] > params["max_chars"]:
            continue
        configs.append(SegmentConfig(**params))
    return configs


def load_eval_corpus(*, strict_missing_docs: bool = False) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for eval_doc in EVAL_DATASET:
        doc_path = Path(eval_doc.doc_path)
        if not doc_path.exists():
            message = f"missing eval document: {eval_doc.doc_id} ({doc_path})"
            if strict_missing_docs:
                raise FileNotFoundError(message)
            print(f"WARNING: {message}", file=sys.stderr)
            continue

        blocks = None
        suffix = doc_path.suffix.lower()
        if suffix in (".txt", ".md"):
            raw_text = doc_path.read_text(encoding="utf-8")
        else:
            raw_blocks = load_document(str(doc_path))
            blocks, _ = preprocess_document_blocks(raw_blocks)
            raw_text = "\n\n".join(block.text for block in blocks)

        baseline_chunks = [
            {
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "title_path": chunk.title_path,
                "chunk_type": chunk.chunk_type,
                "char_count": chunk.char_count,
                "source_refs": chunk.source_refs,
                "quality_flags": chunk.quality_flags,
            }
            for chunk in fixed_length_segment(raw_text, doc_id=f"{eval_doc.doc_id}_baseline")
        ]
        corpus.append(
            {
                "eval_doc": eval_doc,
                "blocks": blocks,
                "raw_text": raw_text,
                "baseline_chunks": baseline_chunks,
            }
        )
    return corpus


def build_smart_chunks(item: dict[str, Any], config: SegmentConfig) -> list[dict[str, Any]]:
    eval_doc = item["eval_doc"]
    blocks = item["blocks"]
    if blocks is not None:
        result = segment_blocks(blocks, doc_id=eval_doc.doc_id, config=config)
    else:
        result = segment_text(item["raw_text"], doc_id=eval_doc.doc_id, config=config)
    return result["chunks"]


def evaluate_baseline(corpus: list[dict[str, Any]]) -> dict[str, list[float]]:
    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)
    values: dict[str, list[float]] = {metric: [] for metric in METRICS}

    for item in corpus:
        eval_doc = item["eval_doc"]
        baseline_chunks = item["baseline_chunks"]
        doc_id = f"{eval_doc.doc_id}_baseline"
        store.add_chunks(doc_id, baseline_chunks)

        for question in eval_doc.questions:
            judge.set_reference(" ".join(question.answer_keywords), question.answer_keywords)
            hits = store.search(doc_id, question.question, top_k=5)
            metrics = compute_ir_metrics(hits, judge, all_chunks=baseline_chunks)
            for metric in METRICS:
                values[metric].append(metrics[metric])
    return values


def evaluate_config(
    config: SegmentConfig,
    corpus: list[dict[str, Any]] | None = None,
    baseline_values: dict[str, list[float]] | None = None,
) -> dict[str, float]:
    if corpus is None:
        corpus = load_eval_corpus()
    if baseline_values is None:
        baseline_values = evaluate_baseline(corpus)

    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)
    smart_values: dict[str, list[float]] = {metric: [] for metric in METRICS}

    for item in corpus:
        eval_doc = item["eval_doc"]
        smart_chunks = build_smart_chunks(item, config)
        store.add_chunks(f"{eval_doc.doc_id}_smart", smart_chunks)

        for question in eval_doc.questions:
            judge.set_reference(" ".join(question.answer_keywords), question.answer_keywords)
            smart_hits = store.search(f"{eval_doc.doc_id}_smart", question.question, top_k=5)
            smart_metrics = compute_ir_metrics(smart_hits, judge, all_chunks=smart_chunks)
            for metric in METRICS:
                smart_values[metric].append(smart_metrics[metric])

    metrics = {metric: average(values) for metric, values in smart_values.items()}
    for metric, values in baseline_values.items():
        metrics[f"baseline_{metric}"] = average(values)
    baseline_r5 = metrics["baseline_recall@5"]
    metrics["recall@5_improvement_pct"] = (
        ((metrics["recall@5"] - baseline_r5) / baseline_r5) * 100 if baseline_r5 else 0.0
    )
    return metrics


def rank_key(row: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        row["recall@5_improvement_pct"],
        row["recall@5"],
        row["precision@5"],
        row["mrr"],
    )


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_config(config: SegmentConfig) -> str:
    return (
        f"min={config.min_chars} target={config.target_chars} max={config.max_chars} "
        f"heading={config.heading_flush_min_chars} sem={config.semantic_boundary_threshold} "
        f"overlap={config.overlap_sentences}"
    )


if __name__ == "__main__":
    main()
