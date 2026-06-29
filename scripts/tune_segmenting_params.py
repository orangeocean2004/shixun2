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

from backend.app.services.evaluation import EmbeddingRelevance, compute_ir_metrics
from backend.app.services.retrieval import EmbeddingStore
from backend.app.services.segmenting import SegmentConfig
from backend.tests.eval_dataset import EVAL_DATASET
from scripts.eval_rag import METRICS, _load_and_segment


SEARCH_SPACE = {
    "min_chars": [220, 260, 300],
    "target_chars": [650, 750, 900],
    "max_chars": [900, 1000, 1200],
    "heading_flush_min_chars": [120, 180, 240, 300],
    "semantic_boundary_threshold": [0.35, 0.45, 0.55],
    "overlap_sentences": [0, 1, 2],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tune segmentation params for RAG retrieval.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of configs to test.")
    parser.add_argument("--top", type=int, default=10, help="How many best configs to print.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results: list[dict[str, Any]] = []

    for index, config in enumerate(iter_configs(), start=1):
        if args.limit and index > args.limit:
            break
        metrics = evaluate_config(config)
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


def evaluate_config(config: SegmentConfig) -> dict[str, float]:
    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)
    smart_values: dict[str, list[float]] = {metric: [] for metric in METRICS}
    baseline_values: dict[str, list[float]] = {metric: [] for metric in METRICS}

    for eval_doc in EVAL_DATASET:
        if not Path(eval_doc.doc_path).exists():
            continue
        smart_chunks, baseline_chunks, _ = _load_and_segment(eval_doc, config)
        store.add_chunks(f"{eval_doc.doc_id}_smart", smart_chunks)
        store.add_chunks(f"{eval_doc.doc_id}_baseline", baseline_chunks)

        for question in eval_doc.questions:
            judge.set_reference(" ".join(question.answer_keywords), question.answer_keywords)
            smart_hits = store.search(f"{eval_doc.doc_id}_smart", question.question, top_k=5)
            baseline_hits = store.search(f"{eval_doc.doc_id}_baseline", question.question, top_k=5)
            smart_metrics = compute_ir_metrics(smart_hits, judge, all_chunks=smart_chunks)
            baseline_metrics = compute_ir_metrics(baseline_hits, judge, all_chunks=baseline_chunks)
            for metric in METRICS:
                smart_values[metric].append(smart_metrics[metric])
                baseline_values[metric].append(baseline_metrics[metric])

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
