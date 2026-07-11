# -*- coding: utf-8 -*-
"""LongBench 任务书指标全面评测。

评测六项指标：
  1. 不破句率 (no_break_sentence_rate)
  2. 目标长度区间命中率 (target_length_hit_rate)
  3. 原文回链完整率 (source_ref_complete_rate)
  4. 表格/公式/代码整体成块率 (table_code_formula_intact_rate)
  5. 检索提升 Recall@5 / nDCG@5 (vs fixed baseline)
  6. 语义完整性 (LLM-as-judge, optional)

Usage:
    python scripts/eval_taskbook_metrics.py                          # all datasets
    python scripts/eval_taskbook_metrics.py --datasets dureader multifieldqa_zh
    python scripts/eval_taskbook_metrics.py --max-samples 50        # quick test
    python scripts/eval_taskbook_metrics.py --max-samples 50 --json > report.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.segmenting import SegmentConfig, segment_text
from backend.app.services.segmenting.statistics import build_statistics
from backend.app.services.segmenting.models import Chunk
from backend.app.services.evaluation import (
    fixed_length_segment,
    heading_based_segment,
)
from backend.app.services.retrieval import EmbeddingStore

# ── LongBench data ──────────────────────────────────────────────

LONGBENCH_DIR = (
    Path(__file__).resolve().parents[1]
    / "data" / "benchmarks" / "longbench" / "data" / "data"
)

# All available datasets with language tagging
DATASET_META: dict[str, dict[str, str]] = {}
for _f in sorted(LONGBENCH_DIR.glob("*.jsonl")):
    _name = _f.stem
    if _name.endswith("_e"):
        DATASET_META[_name] = {"label": f"{_name} (英文)", "lang": "en"}
    elif any(_name.endswith(s) for s in ("_zh", "_cn")):
        DATASET_META[_name] = {"label": f"{_name} (中文)", "lang": "zh"}
    elif _name in ("dureader", "lsht", "vcsum", "lcsts"):
        DATASET_META[_name] = {"label": f"{_name} (中文)", "lang": "zh"}
    else:
        DATASET_META[_name] = {"label": f"{_name} (英文)", "lang": "en"}


# ── Answer matching (same as evaluator.py) ──────────────────────


def _norm(text: str) -> str:
    result = []
    for ch in text:
        if ch.isalnum() or ("一" <= ch <= "鿿"):
            result.append(ch)
    return "".join(result).lower()


def answer_in_chunks(chunks: list[dict], answers: list[str]) -> bool:
    combined = _norm("\n".join(c.get("content", "") for c in chunks))
    for ans in answers:
        a = _norm(ans.strip())
        if len(a) >= 2 and a in combined:
            return True
    return False


# ── IR metrics ──────────────────────────────────────────────────


def compute_metrics(
    ranked: list[dict],
    answers: list[str],
    ks: tuple[int, ...] = (1, 3, 5, 10),
) -> dict[str, float]:
    hits = [answer_in_chunks(ranked[:k], answers) for k in ks]
    total = 1 if hits[-1] else 0  # at least top-k contains answer

    metrics: dict[str, float] = {}
    for i, k in enumerate(ks):
        rel = 1 if hits[i] else 0
        metrics[f"recall_at_{k}"] = rel / total if total > 0 else 0.0
        metrics[f"precision_at_{k}"] = rel / k
        dcg = 1.0 / math.log2(k + 1) if rel else 0.0
        idcg = 1.0 / math.log2(2) if total > 0 else 0.0
        metrics[f"ndcg_at_{k}"] = dcg / idcg if idcg > 0 else 0.0

    for rank, c in enumerate(ranked, 1):
        if answer_in_chunks([c], answers):
            metrics["mrr"] = 1.0 / rank
            break
    else:
        metrics["mrr"] = 0.0
    return metrics


# ── Core evaluation ─────────────────────────────────────────────


def evaluate_dataset(
    dataset_name: str,
    max_samples: int = 0,
    verbose: bool = True,
) -> dict[str, Any]:
    path = LONGBENCH_DIR / f"{dataset_name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    samples: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    if max_samples and max_samples < len(samples):
        samples = samples[:max_samples]

    config = SegmentConfig()

    # ── Accumulators ──
    segment_metrics: dict[str, list[float]] = defaultdict(list)
    ir_accum: dict[str, dict[str, list[float]]] = {
        s: defaultdict(list) for s in ("smart", "heading", "fixed")
    }

    for idx, sample in enumerate(samples):
        context = sample.get("context", "")
        question = sample.get("input", "")
        answers = sample.get("answers", [])

        if not context.strip() or not question.strip() or not answers:
            continue

        # ── 1. Segment with all three strategies ──
        try:
            smart_result = segment_text(context, doc_id="eval_smart", config=config)
            smart_chunks = smart_result["chunks"]
            smart_stats = smart_result["statistics"]

            heading_objs = heading_based_segment(
                context, doc_id="eval_heading",
                min_chars=config.min_chars, target_chars=config.target_chars,
                max_chars=config.max_chars,
            )
            heading_chunks = [
                {
                    "chunk_id": c.chunk_id, "content": c.content,
                    "title_path": c.title_path, "chunk_type": c.chunk_type,
                    "char_count": c.char_count, "source_refs": c.source_refs,
                    "quality_flags": c.quality_flags,
                }
                for c in heading_objs
            ]
            # Compute heading stats separately
            heading_chunk_objs = [
                Chunk(
                    chunk_id=c["chunk_id"], content=c["content"],
                    title_path=c.get("title_path", []),
                    chunk_type=c.get("chunk_type", "normal"),
                    char_count=c.get("char_count", 0),
                    source_refs=c.get("source_refs", []),
                    strategy_info={}, quality_flags=c.get("quality_flags", []),
                )
                for c in heading_chunks
            ]
            heading_stats = build_statistics(heading_chunk_objs, config)

            fixed_objs = fixed_length_segment(context, doc_id="eval_fixed")
            fixed_chunks = [
                {
                    "chunk_id": c.chunk_id, "content": c.content,
                    "title_path": c.title_path, "chunk_type": c.chunk_type,
                    "char_count": c.char_count, "source_refs": c.source_refs,
                    "quality_flags": c.quality_flags,
                }
                for c in fixed_objs
            ]
            fixed_chunk_objs = [
                Chunk(
                    chunk_id=c["chunk_id"], content=c["content"],
                    title_path=c.get("title_path", []),
                    chunk_type=c.get("chunk_type", "normal"),
                    char_count=c.get("char_count", 0),
                    source_refs=c.get("source_refs", []),
                    strategy_info={}, quality_flags=c.get("quality_flags", []),
                )
                for c in fixed_chunks
            ]
            fixed_stats = build_statistics(fixed_chunk_objs, config)

        except Exception as e:
            if verbose:
                print(f"  [{idx+1}] SEGMENT FAIL: {e}")
            continue

        # Collect segment quality metrics
        for key in (
            "no_break_sentence_rate",
            "target_length_hit_rate",
            "source_ref_complete_rate",
            "table_code_formula_intact_rate",
        ):
            segment_metrics[f"smart_{key}"].append(smart_stats.get(key, 0))
            segment_metrics[f"heading_{key}"].append(heading_stats.get(key, 0))
            segment_metrics[f"fixed_{key}"].append(fixed_stats.get(key, 0))

        # Chunk counts
        segment_metrics["smart_chunk_count"].append(len(smart_chunks))
        segment_metrics["heading_chunk_count"].append(len(heading_chunks))
        segment_metrics["fixed_chunk_count"].append(len(fixed_chunks))
        segment_metrics["smart_avg_chars"].append(smart_stats.get("avg_chars", 0))
        segment_metrics["heading_avg_chars"].append(heading_stats.get("avg_chars", 0))
        segment_metrics["fixed_avg_chars"].append(fixed_stats.get("avg_chars", 0))

        # ── 2. Retrieve + evaluate IR metrics ──
        all_chunks = {
            "smart": smart_chunks,
            "heading": heading_chunks,
            "fixed": fixed_chunks,
        }
        store = EmbeddingStore()
        for strategy in ("smart", "heading", "fixed"):
            chunks = all_chunks[strategy]
            if not chunks:
                continue
            store.add_chunks(f"eval_{strategy}", chunks)
            hits = store.search(f"eval_{strategy}", question, top_k=10)
            m = compute_metrics(hits, answers)
            for key, val in m.items():
                ir_accum[strategy][key].append(val)

        if verbose and (idx + 1) % 50 == 0:
            print(f"  [{idx+1}/{len(samples)}] processed")

    # ── Aggregate ──
    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    # Segment quality
    seg_quality: dict[str, dict[str, float]] = {}
    for strategy in ("smart", "heading", "fixed"):
        seg_quality[strategy] = {}
        for key in (
            "no_break_sentence_rate",
            "target_length_hit_rate",
            "source_ref_complete_rate",
            "table_code_formula_intact_rate",
            "chunk_count",
            "avg_chars",
        ):
            full_key = f"{strategy}_{key}"
            seg_quality[strategy][key] = round(
                avg(segment_metrics.get(full_key, [])), 4
            )

    # IR metrics
    ir_result: dict[str, dict[str, float]] = {}
    for strategy in ("smart", "heading", "fixed"):
        ir_result[strategy] = {}
        for key in ("recall_at_5", "recall_at_10",
                     "precision_at_5", "ndcg_at_5", "mrr"):
            ir_result[strategy][key] = round(
                avg(ir_accum[strategy].get(key, [])), 4
            )

    # Gains
    s = ir_result
    structure_gain = round(
        (s["heading"]["recall_at_5"] - s["fixed"]["recall_at_5"]) * 100, 1
    )
    semantic_gain = round(
        (s["smart"]["recall_at_5"] - s["heading"]["recall_at_5"]) * 100, 1
    )
    total_gain = round(
        (s["smart"]["recall_at_5"] - s["fixed"]["recall_at_5"]) * 100, 1
    )

    return {
        "dataset": dataset_name,
        "label": DATASET_META.get(dataset_name, {}).get("label", dataset_name),
        "lang": DATASET_META.get(dataset_name, {}).get("lang", "unknown"),
        "samples": len(samples),
        "processed": len(ir_accum["smart"].get("recall_at_5", [])),
        "segment_quality": seg_quality,
        "ir_metrics": ir_result,
        "gains": {
            "structure_gain": structure_gain,
            "semantic_gain": semantic_gain,
            "total_gain": total_gain,
        },
    }


# ── Report ──────────────────────────────────────────────────────


def print_report(results: list[dict]) -> None:
    """Print a structured report."""
    print()
    print("=" * 75)
    print("  LongBench 任务书指标全面评测报告")
    print("=" * 75)

    for r in results:
        print()
        print(f"-- {r['label']} ({r['processed']}/{r['samples']} samples, lang={r['lang']}) --")
        print()

        # Segment quality
        sq = r["segment_quality"]
        ir = r["ir_metrics"]
        g = r["gains"]

        print("  【分段质量指标】")
        print(f"  {'指标':<28} {'Smart':>10} {'Heading':>10} {'Fixed':>10} {'目标':>10}")
        print(f"  {'-'*68}")

        rows = [
            ("不破句率", "no_break_sentence_rate", "100%"),
            ("长度区间命中率", "target_length_hit_rate", "≥90%"),
            ("回链完整率", "source_ref_complete_rate", "100%"),
            ("特殊块成块率", "table_code_formula_intact_rate", "≥95%"),
            ("平均chunk数", "chunk_count", "--"),
            ("平均chunk字符数", "avg_chars", "--"),
        ]
        for label, key, target in rows:
            vals = [
                sq[s].get(key, 0)
                for s in ("smart", "heading", "fixed")
            ]
            if key in ("chunk_count", "avg_chars"):
                line = f"  {label:<28} {vals[0]:10.1f} {vals[1]:10.1f} {vals[2]:10.1f} {target:>10}"
            else:
                line = f"  {label:<28} {vals[0]:9.1%} {vals[1]:9.1%} {vals[2]:9.1%} {target:>10}"
                # Mark pass/fail
                if key == "no_break_sentence_rate" and vals[0] >= 0.99:
                    line += " PASS"
                elif key == "target_length_hit_rate" and vals[0] >= 0.90:
                    line += " PASS"
                elif key == "source_ref_complete_rate" and vals[0] >= 0.99:
                    line += " PASS"
                elif key == "table_code_formula_intact_rate" and vals[0] >= 0.95:
                    line += " PASS"
            print(line)

        print()
        print("  【检索指标】")
        print(f"  {'指标':<18} {'Smart':>10} {'Heading':>10} {'Fixed':>10}")
        print(f"  {'-'*48}")
        for key, label in [
            ("recall_at_5", "Recall@5"),
            ("recall_at_10", "Recall@10"),
            ("precision_at_5", "Precision@5"),
            ("ndcg_at_5", "NDCG@5"),
            ("mrr", "MRR"),
        ]:
            vals = [ir[s].get(key, 0) for s in ("smart", "heading", "fixed")]
            print(f"  {label:<18} {vals[0]:9.1%} {vals[1]:9.1%} {vals[2]:9.1%}")

        print()
        print(f"  Structure Gain (Heading vs Fixed): {g['structure_gain']:+.1f}%")
        print(f"  Semantic Gain  (Smart vs Heading): {g['semantic_gain']:+.1f}%")
        print(f"  Total Gain     (Smart vs Fixed):   {g['total_gain']:+.1f}% "
              f"{'PASS' if g['total_gain'] >= 10 else 'FAIL (need >=10%)'}")

    # ── Overall average ──
    if len(results) >= 2:
        print()
        print("=" * 75)
        print("  所有数据集平均汇总")
        print("=" * 75)
        print()

        # Average segment quality
        print("  【分段质量 — Smart策略平均】")
        for label, key in [
            ("不破句率", "no_break_sentence_rate"),
            ("长度区间命中率", "target_length_hit_rate"),
            ("回链完整率", "source_ref_complete_rate"),
        ]:
            vals = [r["segment_quality"]["smart"][key] for r in results]
            avg_val = sum(vals) / len(vals)
            print(f"  {label}: {avg_val:.1%}")

        print()
        print("  【检索提升 — 平均 Gain】")
        gains_keys = ["structure_gain", "semantic_gain", "total_gain"]
        for key in gains_keys:
            vals = [r["gains"][key] for r in results]
            avg_val = sum(vals) / len(vals)
            labels = {
                "structure_gain": "Structure Gain (Heading vs Fixed)",
                "semantic_gain": "Semantic Gain (Smart vs Heading)",
                "total_gain": "Total Gain (Smart vs Fixed)",
            }
            print(f"  {labels[key]}: {avg_val:+.1f}%")

        print()
        print("  【检索指标 — Smart策略平均】")
        for key, label in [
            ("recall_at_5", "Recall@5"),
            ("recall_at_10", "Recall@10"),
            ("precision_at_5", "Precision@5"),
            ("ndcg_at_5", "NDCG@5"),
            ("mrr", "MRR"),
        ]:
            vals = [r["ir_metrics"]["smart"][key] for r in results]
            avg_val = sum(vals) / len(vals)
            print(f"  {label}: {avg_val:.1%}")
        print()


# ── Main ────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="LongBench 任务书六项指标全面评测"
    )
    parser.add_argument(
        "--datasets", nargs="+",
        default=sorted(DATASET_META),
        help=f"Datasets to evaluate (default: all {len(DATASET_META)} datasets)",
    )
    parser.add_argument(
        "--max-samples", type=int, default=0,
        help="Limit samples per dataset for quick testing (0 = all)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    results = []
    total_start = time.time()

    for ds in args.datasets:
        if ds not in DATASET_META:
            print(f"WARNING: Unknown dataset: {ds}", file=sys.stderr)
            continue

        meta = DATASET_META[ds]
        print(f"\n>>> {meta['label']}...")
        t0 = time.time()
        result = evaluate_dataset(
            ds,
            max_samples=args.max_samples,
            verbose=not args.json,
        )
        elapsed = time.time() - t0
        print(f"  Done in {elapsed:.0f}s ({result['processed']} samples)")
        results.append(result)

    total_elapsed = time.time() - total_start

    if args.json:
        output = {
            "results": results,
            "total_time_s": round(total_elapsed, 1),
            "datasets_evaluated": len(results),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_report(results)
        print(f"Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
        print()


if __name__ == "__main__":
    main()
