# -*- coding: utf-8 -*-
"""QA synthesis quality evaluation: answerability and faithfulness.

Generates QA pairs from document chunks using LLM, then evaluates each pair
with LLM-as-judge for answerability (can the question be answered from content?)
and faithfulness (does the answer hallucinate?).

Usage:
    python scripts/eval_qa_synthesis.py
    python scripts/eval_qa_synthesis.py --max-chunks 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.segmenting import SegmentConfig, segment_text
from backend.app.services.organizer.model_client import LLMClient
from backend.app.core.model_settings import get_model_settings
from backend.app.services.qa_quality.evaluator import LLMQualityEvaluator, QAQualityResult

QA_SYSTEM_PROMPT = (
    "你是问答对生成器。根据文档片段生成1-2个问答对。"
    "严格输出 JSON 数组：[{\"question\":\"...\",\"answer\":\"...\"}]"
    "答案必须完全基于原文，不添加原文没有的信息。"
)


def generate_qa_pairs(llm: LLMClient, content: str) -> list[dict]:
    """Generate QA pairs from a chunk of content."""
    snippet = content if len(content) <= 2000 else content[:2000]
    raw = llm.generate(
        f"文档片段：\n{snippet}",
        system_prompt=QA_SYSTEM_PROMPT,
        temperature=0.3,
        max_tokens=512,
    )
    if not raw.strip():
        return []

    # Extract JSON array
    try:
        # Try direct parse
        pairs = json.loads(raw)
        if isinstance(pairs, list):
            return pairs
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code block
    import re
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        try:
            pairs = json.loads(match.group(0))
            if isinstance(pairs, list):
                return pairs
        except json.JSONDecodeError:
            pass

    return []


def main():
    parser = argparse.ArgumentParser(description="QA synthesis quality evaluation")
    parser.add_argument("--max-chunks", type=int, default=20,
                        help="Max chunks to generate QA pairs from")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    # Load settings
    settings = get_model_settings()
    llm = LLMClient(
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
        model=settings["LLM_MODEL"],
    )
    if not llm.is_available:
        print("ERROR: No LLM API key configured")
        sys.exit(1)

    # ── Use self-built benchmark docs as test content ──
    project_root = Path(__file__).resolve().parents[1]
    doc_files = [
        project_root / "assets" / "title.md",
        project_root / "assets" / "task_book_page_27.txt",
        project_root / "assets" / "task_book_page_28.txt",
    ]

    all_chunks: list[dict] = []
    for doc_path in doc_files:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        result = segment_text(text, doc_id=f"qa_eval_{doc_path.stem}")
        all_chunks.extend(result["chunks"])

    if args.max_chunks and len(all_chunks) > args.max_chunks:
        all_chunks = all_chunks[:args.max_chunks]

    print(f"Loaded {len(all_chunks)} chunks from {len(doc_files)} documents")
    print(f"LLM: {settings['LLM_MODEL']} @ {settings['OPENAI_BASE_URL']}")

    # ── Generate QA pairs ──
    print(f"\n{'='*60}")
    print("Phase 1: Generate QA pairs")
    print(f"{'='*60}")

    all_qa_pairs: list[dict] = []
    for i, chunk in enumerate(all_chunks):
        content = chunk.get("content", "")
        if len(content) < 100:
            continue
        pairs = generate_qa_pairs(llm, content)
        for pair in pairs:
            pair["_chunk_idx"] = i
            pair["_content"] = content[:500]
        all_qa_pairs.extend(pairs)
        if pairs:
            print(f"  Chunk {i+1}: generated {len(pairs)} QA pair(s)")

    if not all_qa_pairs:
        print("ERROR: No QA pairs generated")
        sys.exit(1)

    print(f"\nTotal: {len(all_qa_pairs)} QA pairs generated")

    # ── Evaluate quality ──
    print(f"\n{'='*60}")
    print("Phase 2: Evaluate answerability & faithfulness (LLM-as-judge)")
    print(f"{'='*60}")

    evaluator = LLMQualityEvaluator(llm_client=llm)

    answerable_count = 0
    faithful_count = 0
    total = len(all_qa_pairs)

    for i, pair in enumerate(all_qa_pairs):
        question = pair.get("question", "")
        answer = pair.get("answer", "")
        content = pair.get("_content", "")

        result = evaluator.evaluate(question, answer, content)
        pair["_answerable"] = result.answerable
        pair["_faithful"] = result.faithful

        if result.answerable:
            answerable_count += 1
        if result.faithful:
            faithful_count += 1

        status = f"A={'Y' if result.answerable else 'N'} F={'Y' if result.faithful else 'N'}"
        print(f"  [{i+1}/{total}] Q: {question[:60]}...  {status}")

    answerable_rate = answerable_count / total * 100 if total > 0 else 0
    faithful_rate = faithful_count / total * 100 if total > 0 else 0

    # ── Report ──
    print(f"\n{'='*60}")
    print("QA SYNTHESIS QUALITY REPORT")
    print(f"{'='*60}")
    print(f"  QA pairs generated:  {total}")
    print(f"  Answerable:          {answerable_count}/{total} = {answerable_rate:.1f}%")
    print(f"  Faithful:            {faithful_count}/{total} = {faithful_rate:.1f}%")
    print(f"  Target:              answerable >= 90%, faithful >= 90%")
    print()

    if answerable_rate >= 90 and faithful_rate >= 90:
        print("  VERDICT: PASS - Both metrics meet targets")
    else:
        if answerable_rate < 90:
            print(f"  Answerability {answerable_rate:.1f}% < 90% target - BELOW")
        if faithful_rate < 90:
            print(f"  Faithfulness {faithful_rate:.1f}% < 90% target - BELOW")

    if args.json:
        output = {
            "total_qa_pairs": total,
            "answerable_rate": round(answerable_rate, 1),
            "faithful_rate": round(faithful_rate, 1),
            "qa_pairs": [
                {
                    "question": p.get("question", ""),
                    "answer": p.get("answer", ""),
                    "answerable": p.get("_answerable", False),
                    "faithful": p.get("_faithful", False),
                }
                for p in all_qa_pairs
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
