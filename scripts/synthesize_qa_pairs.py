#!/usr/bin/env python
"""面向微调的 QA 对合成工具（进阶功能）。

基于分段后的 chunk 内容，用 LLM 生成高质量问答对，并对每条
问答对做可答性和忠实度校验，输出 JSONL 训练语料。

用法：
  # 生成 QA 对（需要 API Key）
  export OPENAI_API_KEY="sk-xxx"
  export OPENAI_BASE_URL="https://api.deepseek.com"
  python scripts/synthesize_qa_pairs.py

  # 指定输出路径和每 chunk 生成数量
  python scripts/synthesize_qa_pairs.py --output data/outputs/qa_pairs.jsonl --pairs-per-chunk 2

  # 只处理部分文档
  python scripts/synthesize_qa_pairs.py --docs eval_title eval_open_report

输出格式（JSONL，每行一个 QA 对）：
{
  "id": "qa_0001",
  "question": "...",
  "answer": "...",
  "source_chunk_id": "eval_open_report_chunk_0003",
  "source_doc": "开题报告_课题11.docx",
  "title_path": ["1.4 研究目标与内容"],
  "answerable": true,
  "answerable_confidence": 0.95,
  "faithful": true,
  "faithfulness_reason": "答案内容全部可在原文中找到依据",
  "quality_score": 0.93
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.document_loader import load_document
from backend.app.services.model_client import LLMClient
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.segmenting import SegmentConfig, segment_blocks

# ── 预过滤：跳过不适合生成 QA 的 chunk ──────────────────

import re as _re

# 这些 chunk 类型不适合生成 QA 对
_SKIP_PATTERNS = [
    (_re.compile(r"^(http|www\.|git)", _re.I), "以URL开头"),       # 参考列表
    (_re.compile(r"^[-\s]*\d+\.?\s"), "枚举/编号列表"),            # 编号列表
    (_re.compile(r"\|\s*---\s*\|"), "Markdown表格"),               # 表格
]


def _is_qa_worthy(chunk: dict) -> bool:
    """判断一个 chunk 是否适合生成 QA 对。"""
    content = chunk.get("content", "").strip()

    # 太短的不适合
    if len(content) < 300:
        return False

    # URL 密度过高的不适合（参考列表类）
    url_count = len(_re.findall(r"https?://", content))
    if url_count >= 3:
        return False

    # 纯表格/代码块
    if chunk.get("chunk_type") in {"table", "code"}:
        return False

    # 行太短太多的不适合（纯列表/引用）
    lines = [l for l in content.split("\n") if l.strip()]
    if len(lines) >= 8:
        avg_len = sum(len(l) for l in lines) / len(lines)
        if avg_len < 40:
            return False

    return True


# ── 配置 ──────────────────────────────────────────────────

EVAL_DOCS = {
    "eval_title": {
        "path": "assets/title.md",
        "name": "title.md",
    },
    "eval_survey": {
        "path": "assets/同类开源方案调研报告.docx",
        "name": "同类开源方案调研报告.docx",
    },
    "eval_open_report": {
        "path": "assets/开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx",
        "name": "开题报告_课题11.docx",
    },
}

# ── QA 生成 Prompt ────────────────────────────────────────

_QA_GENERATE_SYSTEM = (
    "你是一个高质量的问答对生成器。你的任务是基于给定的文档片段，生成可用于"
    "微调大模型的问答对。生成的问答对必须满足：\n"
    "1. 问题必须能仅从该片段内容中回答（可答性）\n"
    "2. 答案必须忠实于片段内容，不编造任何原文没有的信息\n"
    "3. 问题应覆盖不同类型的理解：事实提取、概念解释、关系推理、数值对比\n"
    "4. 答案应简洁准确，使用原文中的术语和表述\n"
    "5. 每个片段生成{max_pairs}个问答对"
)

_QA_GENERATE_PROMPT = (
    "文档章节：{title_path}\n\n"
    "片段内容：\n{content}\n\n"
    "请基于以上片段内容生成 {max_pairs} 个问答对。"
    "返回纯 JSON 数组（不要 markdown 代码块包裹），每个元素格式：\n"
    '{{"question": "问题文本", "answer": "答案文本"}}\n'
    "确保每个问题都可以仅从上述片段内容中完整回答。"
)

# ── 校验 Prompt ───────────────────────────────────────────

_QA_VALIDATE_SYSTEM = (
    "你是一个问答对质量校验器。你需要判断给定的问答对是否满足两个标准：\n"
    "1. 可答性 (answerable_score 0-10)：仅凭提供的文档片段内容，能否完整回答该问题？"
    "10分=完全可以仅从片段回答；5分=需要额外常识但片段覆盖了核心信息；0分=完全无法回答\n"
    "2. 忠实度 (faithful_score 0-10)：答案中的所有事实断言是否都能在片段中找到原文依据？"
    "10分=全部有依据；5分=主要事实有依据但有轻微推断；0分=大量编造\n\n"
    "返回纯 JSON 对象（不要 markdown 代码块包裹）：\n"
    '{{"answerable_score": 0-10, "faithful_score": 0-10, '
    '"brief_reason": "一句话说明评分理由"}}'
)

_QA_VALIDATE_PROMPT = (
    "文档片段：\n{content}\n\n"
    "问题：{question}\n\n"
    "答案：{answer}\n\n"
    "请对以上问答对的可答性和忠实度分别打分（0-10）。"
)


# ── 核心逻辑 ──────────────────────────────────────────────

def generate_qa_pairs(
    content: str,
    title_path: str,
    llm_client: LLMClient,
    max_pairs: int = 3,
) -> list[dict]:
    """为一个 chunk 生成 QA 对。"""
    system = _QA_GENERATE_SYSTEM.replace("{max_pairs}", str(max_pairs))
    prompt = _QA_GENERATE_PROMPT.format(
        title_path=title_path,
        content=content[:2000],
        max_pairs=max_pairs,
    )

    raw = llm_client.generate(prompt, system_prompt=system, temperature=0.7, max_tokens=1024)
    if not raw:
        return []

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        pairs = json.loads(raw)
        if isinstance(pairs, list):
            return [
                {"question": p.get("question", ""), "answer": p.get("answer", "")}
                for p in pairs
                if isinstance(p, dict) and p.get("question") and p.get("answer")
            ]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []


def validate_qa_pair(
    question: str,
    answer: str,
    content: str,
    llm_client: LLMClient,
    threshold: int = 7,
) -> dict:
    """校验一个 QA 对的可答性和忠实度。使用 0-10 打分制，threshold 分算通过。"""
    prompt = _QA_VALIDATE_PROMPT.format(
        content=content[:1500],
        question=question,
        answer=answer,
    )

    raw = llm_client.generate(prompt, system_prompt=_QA_VALIDATE_SYSTEM, temperature=0.01, max_tokens=256)
    if not raw:
        return {"answerable": False, "faithful": False, "error": "LLM 校验失败"}

    try:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        result = json.loads(raw)
        if isinstance(result, dict):
            ans_score = int(result.get("answerable_score", 0))
            faith_score = int(result.get("faithful_score", 0))
            return {
                "answerable": ans_score >= threshold,
                "answerable_score": ans_score,
                "answerable_reason": result.get("brief_reason", ""),
                "faithful": faith_score >= threshold,
                "faithful_score": faith_score,
                "faithfulness_reason": result.get("brief_reason", ""),
            }
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {"answerable": False, "faithful": False, "error": "JSON 解析失败"}


# ── 主流程 ────────────────────────────────────────────────

def synthesize(
    output_path: str,
    pairs_per_chunk: int = 3,
    doc_filter: list[str] | None = None,
) -> None:
    """完整的 QA 对合成管线。"""
    # ── 检查 API Key ──
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")

    if not api_key:
        print("[ERROR] 未设置 OPENAI_API_KEY 环境变量。")
        print("  export OPENAI_API_KEY='sk-xxx'")
        print("  export OPENAI_BASE_URL='https://api.deepseek.com'")
        sys.exit(1)

    llm_client = LLMClient(api_key=api_key, base_url=base_url, model="deepseek-chat")
    if not llm_client.is_available:
        print("[ERROR] LLM 客户端不可用")
        sys.exit(1)

    print(f"[INFO] LLM 模式: deepseek-chat")
    print(f"[INFO] 每 chunk 生成 {pairs_per_chunk} 个 QA 对")

    # ── 加载文档并分段 ──
    config = SegmentConfig(min_chars=300, target_chars=900, max_chars=1200)
    all_chunks: list[dict] = []

    for doc_id, doc_info in EVAL_DOCS.items():
        if doc_filter and doc_id not in doc_filter:
            continue

        doc_path = PROJECT_ROOT / doc_info["path"]
        if not doc_path.exists():
            print(f"  [WARN] 跳过: {doc_path}")
            continue

        print(f"\n  [加载] {doc_info['name']}")
        blocks = load_document(doc_path)
        cleaned, _ = preprocess_document_blocks(blocks)
        result = segment_blocks(cleaned, doc_id=doc_id, config=config)
        chunks = result["chunks"]

        for chunk in chunks:
            all_chunks.append({
                "chunk_id": chunk["chunk_id"],
                "doc_id": doc_id,
                "doc_name": doc_info["name"],
                "title_path": " > ".join(chunk.get("title_path", [])),
                "content": chunk["content"],
            })

    print(f"\n  总计 {len(all_chunks)} 个 chunk，预计生成 "
          f"{len(all_chunks) * pairs_per_chunk} 个 QA 对")

    # ── 生成 + 校验 ──
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_generated = 0
    total_valid = 0
    total_answerable = 0
    total_faithful = 0
    start_time = time.perf_counter()

    with open(output_path, "w", encoding="utf-8") as f_out:
        for i, chunk in enumerate(all_chunks):
            cid = chunk["chunk_id"]

            # 预过滤：跳过不适合生成 QA 对的 chunk
            if not _is_qa_worthy(chunk):
                print(f"\n  [{i+1}/{len(all_chunks)}] {cid} [SKIP] 不适合生成QA")
                continue

            print(f"\n  [{i+1}/{len(all_chunks)}] {cid} "
                  f"({chunk['title_path'][:40]})")

            # 生成 QA 对
            pairs = generate_qa_pairs(
                chunk["content"], chunk["title_path"],
                llm_client, max_pairs=pairs_per_chunk,
            )

            if not pairs:
                print(f"    -> 未生成有效 QA 对")
                continue

            total_generated += len(pairs)
            chunk_valid = 0

            # 逐个校验
            for j, pair in enumerate(pairs):
                validation = validate_qa_pair(
                    pair["question"], pair["answer"],
                    chunk["content"], llm_client,
                )

                answerable = validation.get("answerable", False)
                faithful = validation.get("faithful", False)
                is_valid = answerable and faithful

                if answerable:
                    total_answerable += 1
                if faithful:
                    total_faithful += 1
                if is_valid:
                    total_valid += 1
                    chunk_valid += 1

                # 计算综合质量分
                quality_score = (
                    (1.0 if answerable else 0.0) * 0.5
                    + (1.0 if faithful else 0.0) * 0.5
                )

                record = {
                    "id": f"qa_{total_generated - len(pairs) + j + 1:05d}",
                    "question": pair["question"],
                    "answer": pair["answer"],
                    "source_chunk_id": chunk["chunk_id"],
                    "source_doc": chunk["doc_name"],
                    "title_path": chunk["title_path"],
                    "answerable": answerable,
                    "answerable_reason": validation.get("answerable_reason", ""),
                    "answerable_confidence": 0.90 if answerable else 0.30,
                    "faithful": faithful,
                    "faithfulness_reason": validation.get("faithfulness_reason", ""),
                    "quality_score": round(quality_score, 2),
                }

                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

                status = "[OK]" if is_valid else "[FAIL]"
                print(f"    {status} Q: {pair['question'][:50]}... "
                      f"(可答={answerable}, 忠实={faithful})")

    elapsed = time.perf_counter() - start_time

    # ── 统计输出 ──
    print()
    print("=" * 60)
    print("  QA 对合成 — 统计报告")
    print("=" * 60)
    print(f"  总 chunk 数:       {len(all_chunks)}")
    print(f"  总生成 QA 对:      {total_generated}")
    print(f"  有效 QA 对:        {total_valid} ({total_valid/max(total_generated,1)*100:.1f}%)")
    print(f"  可答率:            {total_answerable}/{total_generated} "
          f"({total_answerable/max(total_generated,1)*100:.1f}%)")
    print(f"  忠实率:            {total_faithful}/{total_generated} "
          f"({total_faithful/max(total_generated,1)*100:.1f}%)")
    print(f"  耗时:              {elapsed:.0f}s")
    print(f"  输出文件:          {output_path}")

    target = 90.0
    answerable_rate = total_answerable / max(total_generated, 1) * 100
    faithful_rate = total_faithful / max(total_generated, 1) * 100

    print(f"\n  可答性: {answerable_rate:.1f}% "
          f"{'[PASS]' if answerable_rate >= target else '[FAIL]'} "
          f"(目标 >= {target:.0f}%)")
    print(f"  忠实度: {faithful_rate:.1f}% "
          f"{'[PASS]' if faithful_rate >= target else '[FAIL]'} "
          f"(目标 >= {target:.0f}%)")

    # 保存统计 JSON
    stats = {
        "total_chunks": len(all_chunks),
        "total_generated": total_generated,
        "total_valid": total_valid,
        "total_answerable": total_answerable,
        "total_faithful": total_faithful,
        "answerable_rate": round(answerable_rate / 100, 4),
        "faithful_rate": round(faithful_rate / 100, 4),
        "elapsed_seconds": round(elapsed, 1),
        "output_file": str(output_path),
    }
    stats_path = output_path.with_suffix(".stats.json")
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  统计文件:          {stats_path}")


# ── CLI ────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="面向微调的 QA 对合成工具")
    parser.add_argument("--output", default="data/outputs/qa_pairs.jsonl", help="JSONL 输出路径")
    parser.add_argument("--pairs-per-chunk", type=int, default=3, help="每 chunk 生成 QA 对数 (默认3)")
    parser.add_argument("--docs", nargs="*", default=None,
                        help="指定文档 (eval_title, eval_survey, eval_open_report)")
    args = parser.parse_args()

    synthesize(args.output, args.pairs_per_chunk, args.docs)


if __name__ == "__main__":
    main()
