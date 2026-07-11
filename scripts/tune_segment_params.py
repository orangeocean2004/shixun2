# -*- coding: utf-8 -*-
"""Quick grid search for optimal chunking params on LongBench.

Usage:
    python scripts/tune_segment_params.py
    python scripts/tune_segment_params.py --max-samples 30 --datasets dureader multifieldqa_zh
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.segmenting import SegmentConfig, segment_text
from backend.app.services.evaluation import fixed_length_segment
from backend.app.services.retrieval import EmbeddingStore

LONGBENCH_DIR = (
    Path(__file__).resolve().parents[1]
    / "data" / "benchmarks" / "longbench" / "data" / "data"
)


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


def evaluate_config(
    config: SegmentConfig,
    samples: list[dict],
    config_label: str,
    fixed_recalls: list[float] | None = None,
) -> dict[str, float]:
    """Evaluate one config on given samples, return avg Recall@5 and gain vs Fixed."""
    smart_recalls: list[float] = []
    if fixed_recalls is None:
        fixed_recalls = []

    compute_fixed = (len(fixed_recalls) == 0)

    for i, sample in enumerate(samples):
        context = sample.get("context", "")
        question = sample.get("input", "")
        answers = sample.get("answers", [])

        if not context.strip() or not question.strip() or not answers:
            continue

        try:
            smart_result = segment_text(context, doc_id="tune_smart", config=config)
            smart_chunks = smart_result["chunks"]
        except Exception:
            continue

        if compute_fixed:
            try:
                fixed_objs = fixed_length_segment(context, doc_id="tune_fixed")
                fixed_chunks = [
                    {
                        "chunk_id": c.chunk_id, "content": c.content,
                        "char_count": c.char_count,
                    }
                    for c in fixed_objs
                ]
            except Exception:
                continue

        store = EmbeddingStore()

        # Smart retrieval
        store.add_chunks("tune_smart", smart_chunks)
        smart_hits = store.search("tune_smart", question, top_k=5)
        smart_hit = answer_in_chunks(smart_hits, answers)
        smart_recalls.append(1.0 if smart_hit else 0.0)

        # Fixed retrieval (only need to compute once, for baseline config)
        if compute_fixed:
            store.add_chunks("tune_fixed", fixed_chunks)
            fixed_hits = store.search("tune_fixed", question, top_k=5)
            fixed_hit = answer_in_chunks(fixed_hits, answers)
            fixed_recalls.append(1.0 if fixed_hit else 0.0)

    avg_smart = sum(smart_recalls) / len(smart_recalls) if smart_recalls else 0.0
    avg_fixed = sum(fixed_recalls) / len(fixed_recalls) if fixed_recalls else 0.0
    gain = (avg_smart - avg_fixed) / avg_fixed * 100 if avg_fixed > 0 else 0.0

    return {
        "smart_r5": round(avg_smart, 4),
        "fixed_r5": round(avg_fixed, 4),
        "gain_pct": round(gain, 1),
        "label": config_label,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-samples", type=int, default=30)
    parser.add_argument("--datasets", nargs="+", default=["multifieldqa_zh", "dureader"])
    args = parser.parse_args()

    # Load samples
    all_samples: list[dict] = []
    for ds in args.datasets:
        path = LONGBENCH_DIR / f"{ds}.jsonl"
        if not path.exists():
            print(f"SKIP: {path} not found")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_samples.append(json.loads(line))
        print(f"Loaded {ds}: {len(all_samples)} samples so far")

    if args.max_samples and args.max_samples < len(all_samples):
        all_samples = all_samples[:args.max_samples]
    print(f"Total samples: {len(all_samples)}")

    # ── Baseline: current defaults ──
    default_config = SegmentConfig()
    print(f"\nBaseline config: target={default_config.target_chars}, max={default_config.max_chars}, "
          f"overlap={default_config.overlap_sentences}, threshold={default_config.semantic_boundary_threshold}")

    # ── Grid ──
    grid = []
    for target_chars in [700, 900, 1100]:
        for max_chars in [1000, 1200, 1500]:
            if max_chars <= target_chars:
                continue
            for threshold in [0.40, 0.55]:
                config = SegmentConfig(
                    target_chars=target_chars,
                    max_chars=max_chars,
                    min_chars=max(150, target_chars // 4),
                    overlap_sentences=3,
                    semantic_boundary_threshold=threshold,
                )
                grid.append((config, f"t{target_chars}_m{max_chars}_th{threshold}"))

    # Also test with semantic boundary disabled entirely
    grid.append((
        SegmentConfig(
            target_chars=700, max_chars=1000, min_chars=200,
            overlap_sentences=3, enable_semantic_boundary=False,
        ),
        "t700_m1000_nosemantic"
    ))
    grid.append((
        SegmentConfig(
            target_chars=900, max_chars=1200, min_chars=250,
            overlap_sentences=3, enable_semantic_boundary=False,
        ),
        "t900_m1200_nosemantic"
    ))

    print(f"\nTesting {len(grid)} configs on {len(all_samples)} samples...\n")

    results = []
    fixed_recalls: list[float] = []
    for config, label in grid:
        r = evaluate_config(config, all_samples, label, fixed_recalls)
        results.append(r)
        print(f"  {label:<30} Smart R@5={r['smart_r5']:.3f}  Fixed R@5={r['fixed_r5']:.3f}  Gain={r['gain_pct']:+.1f}%")

    # ── Best ──
    results.sort(key=lambda x: x["gain_pct"], reverse=True)
    print(f"\n{'='*60}")
    print("TOP 5 CONFIGS (by gain vs Fixed):")
    for i, r in enumerate(results[:5]):
        print(f"  {i+1}. {r['label']:<30} Smart R@5={r['smart_r5']:.3f}  "
              f"Fixed R@5={r['fixed_r5']:.3f}  Gain={r['gain_pct']:+.1f}%")

    best = results[0]
    print(f"\nBest config: {best['label']}")
    print(f"  Smart R@5: {best['smart_r5']:.3f}")
    print(f"  Fixed R@5: {best['fixed_r5']:.3f}")
    print(f"  Gain: {best['gain_pct']:+.1f}%")
    if best["gain_pct"] >= 10:
        print("  VERDICT: PASS")
    else:
        print("  VERDICT: BELOW TARGET")


if __name__ == "__main__":
    main()
