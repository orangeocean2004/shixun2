#!/usr/bin/env python
"""语义完整性人工评估工具。

用途：
  1. 从评估文档的 chunk 中随机抽样，生成 CSV 打分表
  2. 评估者填写 CSV 后，运行统计得到语义完整率

用法：
  # 生成打分表（默认每文档抽 10 个 chunk）
  python scripts/human_eval_semantic.py sample --output data/outputs/human_eval_samples.csv

  # 统计结果
  python scripts/human_eval_semantic.py score --input data/outputs/human_eval_samples.csv

评估标准（打分表中有详细说明）：
  1 = 语义完整（chunk 在自然语义边界结束，内容自洽）
  0 = 语义不完整（chunk 在句中截断、关键信息断裂、或依赖外部上下文才能理解）
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.document_loader import load_document
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.segmenting import SegmentConfig, segment_blocks

# ── 评估文档列表 ──────────────────────────────────────────

EVAL_DOCS = [
    {
        "doc_id": "eval_title",
        "path": "assets/title.md",
        "name": "title.md（技术标准文档）",
    },
    {
        "doc_id": "eval_survey",
        "path": "assets/同类开源方案调研报告.docx",
        "name": "同类开源方案调研报告.docx",
    },
    {
        "doc_id": "eval_open_report",
        "path": "assets/开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx",
        "name": "开题报告_课题11.docx",
    },
]

# ── 评分标准说明 ──────────────────────────────────────────

SCORING_GUIDE = """
=== 语义完整性评分标准 ===

请逐行阅读每个 chunk 的 content 列，根据以下标准打分：

1 分（语义完整）：
  - chunk 在一个自然的语义边界结束（如段落结束、小节结束）
  - chunk 内容自洽，不需要上下文就能理解其核心意思
  - 即使 chunk 末尾不是句号，内容仍然是一个完整的信息单元

0 分（语义不完整）：
  - chunk 在句中明显截断，关键句子被切断
  - chunk 内容严重依赖相邻 chunk 才能理解（孤立看不知所云）
  - chunk 末尾有明显的"未完待续"感（如以连词结尾、列表项不全等）

注意：
  - 只评价语义完整性，不评价标签/摘要质量
  - 表格 chunk 如果表头和数据行完整即算 1 分
  - 代码块如果函数/类完整即算 1 分
"""


# ── 抽样 ──────────────────────────────────────────────────

def sample_chunks(samples_per_doc: int = 10, seed: int = 42) -> list[dict[str, Any]]:
    """从所有评估文档中随机抽样 chunk，返回打分表行列表。"""
    random.seed(seed)
    config = SegmentConfig(min_chars=300, target_chars=900, max_chars=1200)

    all_rows: list[dict[str, Any]] = []

    for doc_info in EVAL_DOCS:
        doc_path = PROJECT_ROOT / doc_info["path"]
        if not doc_path.exists():
            print(f"  [WARN] 跳过不存在的文档: {doc_path}")
            continue

        print(f"  加载: {doc_info['name']}")
        blocks = load_document(doc_path)
        cleaned, _ = preprocess_document_blocks(blocks)
        result = segment_blocks(cleaned, doc_id=doc_info["doc_id"], config=config)

        chunks = result["chunks"]
        n_sample = min(samples_per_doc, len(chunks))
        sampled = random.sample(chunks, n_sample)

        for chunk in sampled:
            all_rows.append({
                "doc_id": doc_info["doc_id"],
                "doc_name": doc_info["name"],
                "chunk_id": chunk["chunk_id"],
                "title_path": " > ".join(chunk.get("title_path", [])),
                "chunk_type": chunk.get("chunk_type", ""),
                "char_count": chunk.get("char_count", 0),
                "content_preview": chunk["content"][:200].replace("\n", " "),
                "full_content": chunk["content"],
                "score": "",  # 待评估者填写: 1 或 0
                "evaluator": "",  # 评估者姓名
                "comment": "",  # 可选备注
            })

    print(f"\n  共抽样 {len(all_rows)} 个 chunk（{len(EVAL_DOCS)} 文档）")
    return all_rows


# ── 生成 CSV ──────────────────────────────────────────────

def generate_csv(output_path: str, samples_per_doc: int = 10) -> None:
    """生成语义完整性评估打分表 CSV。"""
    rows = sample_chunks(samples_per_doc)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "doc_id", "doc_name", "chunk_id", "title_path", "chunk_type",
        "char_count", "content_preview", "full_content",
        "score", "evaluator", "comment",
    ]

    with open(output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n  打分表已生成: {output}")
    print(f"  请用 Excel/WPS 打开，填写 score (1/0)、evaluator (姓名)、comment (可选)")
    print(f"  填写完成后运行: python scripts/human_eval_semantic.py score --input {output_path}")
    print(SCORING_GUIDE)


# ── 统计 ──────────────────────────────────────────────────

def calculate_scores(input_path: str) -> None:
    """从填写完成的 CSV 统计语义完整率。"""
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"  [ERROR] 文件不存在: {input_path}")
        sys.exit(1)

    rows: list[dict] = []
    with open(input_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # 过滤出已打分的行
    scored = [r for r in rows if r.get("score", "").strip() in {"0", "1"}]
    unscored = [r for r in rows if r.get("score", "").strip() not in {"0", "1"}]

    if not scored:
        print("  [ERROR] 没有找到已打分的行。请在 CSV 的 score 列填写 1 或 0。")
        sys.exit(1)

    # 按文档统计
    by_doc: dict[str, dict] = {}
    for r in scored:
        doc = r.get("doc_id", "unknown")
        if doc not in by_doc:
            by_doc[doc] = {"total": 0, "complete": 0, "evaluators": set()}
        by_doc[doc]["total"] += 1
        if r["score"] == "1":
            by_doc[doc]["complete"] += 1
        if r.get("evaluator", "").strip():
            by_doc[doc]["evaluators"].add(r["evaluator"].strip())

    # 按评估者统计
    by_evaluator: dict[str, dict] = {}
    for r in scored:
        ev = r.get("evaluator", "").strip() or "未署名"
        if ev not in by_evaluator:
            by_evaluator[ev] = {"total": 0, "complete": 0}
        by_evaluator[ev]["total"] += 1
        if r["score"] == "1":
            by_evaluator[ev]["complete"] += 1

    # 输出
    print()
    print("=" * 60)
    print("  语义完整性人工评估 — 统计报告")
    print("=" * 60)

    print(f"\n  总抽样: {len(rows)} 个 chunk")
    print(f"  已打分: {len(scored)} 个")
    print(f"  未打分: {len(unscored)} 个")

    print(f"\n  --- 按文档 ---")
    for doc_id in sorted(by_doc.keys()):
        d = by_doc[doc_id]
        rate = d["complete"] / d["total"] * 100
        ev_list = ", ".join(sorted(d["evaluators"])) if d["evaluators"] else "未署名"
        print(f"  {doc_id}: {d['complete']}/{d['total']} = {rate:.1f}%  (评估者: {ev_list})")

    overall = sum(d["complete"] for d in by_doc.values())
    overall_total = sum(d["total"] for d in by_doc.values())
    overall_rate = overall / overall_total * 100

    print(f"\n  --- 总览 ---")
    print(f"  语义完整率: {overall}/{overall_total} = {overall_rate:.1f}%")

    target = 85.0
    if overall_rate >= target:
        print(f"  [PASS] 达标 (需 >= {target:.0f}%)")
    else:
        print(f"  [FAIL] 未达标 (需 >= {target:.0f}%, 差 {target - overall_rate:.1f}%)")

    if by_evaluator:
        print(f"\n  --- 按评估者 ---")
        for ev in sorted(by_evaluator.keys()):
            d = by_evaluator[ev]
            rate = d["complete"] / d["total"] * 100
            print(f"  {ev}: {d['complete']}/{d['total']} = {rate:.1f}%")

    # 列出不完整的 chunk
    incomplete = [r for r in scored if r["score"] == "0"]
    if incomplete:
        print(f"\n  --- 不完整 chunk 列表 ({len(incomplete)} 个) ---")
        for r in incomplete:
            preview = r["content_preview"][:80]
            comment = f" — {r['comment']}" if r.get("comment", "").strip() else ""
            print(f"  [{r['chunk_id']}] {preview}...{comment}")

    # 保存 JSON 报告
    report = {
        "evaluation_type": "human_semantic_completeness",
        "total_sampled": len(rows),
        "total_scored": len(scored),
        "total_unscored": len(unscored),
        "by_document": {
            doc_id: {
                "total": by_doc[doc_id]["total"],
                "complete": by_doc[doc_id]["complete"],
                "rate": round(by_doc[doc_id]["complete"] / by_doc[doc_id]["total"], 4),
            }
            for doc_id in by_doc
        },
        "by_evaluator": {
            ev: {
                "total": by_evaluator[ev]["total"],
                "complete": by_evaluator[ev]["complete"],
                "rate": round(by_evaluator[ev]["complete"] / by_evaluator[ev]["total"], 4),
            }
            for ev in by_evaluator
        },
        "overall_rate": round(overall_rate / 100, 4),
        "overall_complete": overall,
        "overall_total": overall_total,
        "pass": overall_rate >= target,
    }

    report_path = input_file.parent / "human_eval_semantic_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  JSON 报告已保存: {report_path}")


# ── CLI ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="语义完整性人工评估工具")
    sub = parser.add_subparsers(dest="command")

    p_sample = sub.add_parser("sample", help="生成打分表 CSV")
    p_sample.add_argument("--output", default="data/outputs/human_eval_samples.csv", help="CSV 输出路径")
    p_sample.add_argument("--samples", type=int, default=10, help="每文档抽样数")

    p_score = sub.add_parser("score", help="统计打分结果")
    p_score.add_argument("--input", default="data/outputs/human_eval_samples.csv", help="填写完成的 CSV")

    args = parser.parse_args()

    if args.command == "sample":
        generate_csv(args.output, args.samples)
    elif args.command == "score":
        calculate_scores(args.input)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
