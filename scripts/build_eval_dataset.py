# -*- coding: utf-8 -*-
"""Build a self-built evaluation dataset from downloaded benchmark documents.

For each document, use LLM to generate QA pairs that test whether the
segmentation strategy keeps relevant information intact within chunks.

Output: an EvalDocument list ready for eval_rag.py

Usage:
    python scripts/build_eval_dataset.py
    python scripts/build_eval_dataset.py --max-docs 6 --qa-per-doc 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.organizer.model_client import LLMClient
from backend.app.core.model_settings import get_model_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = PROJECT_ROOT / "data" / "benchmarks" / "docs" / "zh"
ASSETS_DIR = PROJECT_ROOT / "assets"

# ── Selected documents (diverse types, good structure, reasonable size) ──
SELECTED_DOCS: list[dict] = [
    # Original self-built (课题相关)
    {
        "path": str(ASSETS_DIR / "title.md"),
        "doc_id": "eval_title",
        "type": "课题描述",
    },
    # Technical tutorials (结构化中文技术文档)
    {
        "path": str(BENCHMARK_DIR / "d2l_zh_intro.md"),
        "doc_id": "eval_d2l_intro",
        "type": "技术教程（深度学习）",
    },
    {
        "path": str(BENCHMARK_DIR / "vue3_guide_intro.txt"),
        "doc_id": "eval_vue3",
        "type": "前端框架文档",
    },
    {
        "path": str(BENCHMARK_DIR / "rust_zh_ownership.txt"),
        "doc_id": "eval_rust",
        "type": "编程语言教程",
    },
    # Open-source project README
    {
        "path": str(BENCHMARK_DIR / "dbgpt_readme.md"),
        "doc_id": "eval_dbgpt",
        "type": "开源项目README",
    },
    {
        "path": str(BENCHMARK_DIR / "paddleocr_readme.md"),
        "doc_id": "eval_paddleocr",
        "type": "开源项目README（AI模型）",
    },
    # Markdown / technical writing guide
    {
        "path": str(BENCHMARK_DIR / "markdown_zh_guide.txt"),
        "doc_id": "eval_markdown",
        "type": "技术写作指南",
    },
    # React frontend docs
    {
        "path": str(BENCHMARK_DIR / "react_zh_learn.txt"),
        "doc_id": "eval_react",
        "type": "前端框架文档（React）",
    },
]

QA_SYSTEM = (
    "你是问答对生成专家。阅读以下文档，生成与文档内容相关的问答对。"
    "每个问答对的问题应该是一个自然语言问题，答案应该明确在文档中可以找到。"
    "问题应覆盖文档的不同部分，避免集中在同一段落。"
    "答案的关键词必须能在文档原文中找到。"
    "严格输出 JSON 数组：[{\"question\":\"...\",\"answer_keywords\":[\"词1\",\"词2\"]}]"
    "answer_keywords 是答案中的3-6个核心关键词，用于评测检索命中率。"
)


def generate_qa_pairs(llm: LLMClient, doc_text: str, n_pairs: int = 4) -> list[dict]:
    """Generate QA pairs for a document."""
    # Take first 8000 chars for context (LLM context limit)
    snippet = doc_text[:8000] if len(doc_text) > 8000 else doc_text

    prompt = (
        f"请为以下文档生成{n_pairs}个问答对：\n\n"
        f"{snippet}\n\n"
        f"生成{n_pairs}个问答对。"
    )

    raw = llm.generate(
        prompt,
        system_prompt=QA_SYSTEM,
        temperature=0.3,
        max_tokens=1024,
    )

    if not raw.strip():
        return []

    # Extract JSON
    try:
        pairs = json.loads(raw)
        if isinstance(pairs, list):
            return pairs
    except json.JSONDecodeError:
        pass

    # Try regex extraction
    import re
    match = re.search(r"\[[\s\S]*\]", raw)
    if match:
        try:
            pairs = json.loads(match.group(0))
            if isinstance(pairs, list):
                return pairs
        except json.JSONDecodeError:
            pass

    return []


def build_eval_module(dataset: list[dict], output_path: Path) -> None:
    """Write the eval dataset as a Python module."""
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""Auto-generated self-built evaluation dataset."""',
        '',
        'from __future__ import annotations',
        'from dataclasses import dataclass, field',
        '',
        '',
        '@dataclass',
        'class EvalQuestion:',
        '    question: str',
        '    answer_keywords: list[str]',
        '',
        '',
        '@dataclass',
        'class EvalDocument:',
        '    doc_path: str',
        '    doc_id: str',
        '    questions: list[EvalQuestion] = field(default_factory=list)',
        '',
        '',
        'EVAL_DATASET: list[EvalDocument] = [',
    ]

    for doc in dataset:
        lines.append(f'    EvalDocument(')
        lines.append(f'        doc_path=r"{doc["path"]}",')
        lines.append(f'        doc_id="{doc["doc_id"]}",')
        lines.append(f'        questions=[')
        for qa in doc.get("questions", []):
            keywords = json.dumps(qa["answer_keywords"], ensure_ascii=False)
            lines.append(f'            EvalQuestion(')
            lines.append(f'                question="{qa["question"]}",')
            lines.append(f'                answer_keywords={keywords},')
            lines.append(f'            ),')
        lines.append(f'        ],')
        lines.append(f'    ),')

    lines.append(']')
    lines.append('')

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written to: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-docs", type=int, default=8)
    parser.add_argument("--qa-per-doc", type=int, default=4)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    settings = get_model_settings()
    llm = LLMClient(
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
        model=settings["LLM_MODEL"],
    )
    if not llm.is_available:
        print("ERROR: No LLM API key configured")
        sys.exit(1)

    docs = SELECTED_DOCS[:args.max_docs]
    dataset: list[dict] = []

    print(f"Generating QA pairs for {len(docs)} documents using {settings['LLM_MODEL']}...\n")

    for i, doc in enumerate(docs):
        path = Path(doc["path"])
        if not path.exists():
            print(f"  [{i+1}/{len(docs)}] SKIP: {path.name} (not found)")
            continue

        text = path.read_text(encoding="utf-8")
        print(f"  [{i+1}/{len(docs)}] {doc['doc_id']} ({doc['type']}) — {len(text):,} chars")

        qa_pairs = generate_qa_pairs(llm, text, args.qa_per_doc)
        if not qa_pairs:
            print(f"         WARNING: No QA pairs generated")

        doc_entry = {
            "path": doc["path"],
            "doc_id": doc["doc_id"],
            "questions": qa_pairs,
        }
        dataset.append(doc_entry)

        for j, qa in enumerate(qa_pairs):
            print(f"         Q{j+1}: {qa.get('question', '?')[:80]}...")

    # Write output
    output_path = Path(args.output) if args.output else (
        PROJECT_ROOT / "backend" / "tests" / "eval_dataset_self_built.py"
    )
    build_eval_module(dataset, output_path)

    total_qa = sum(len(d["questions"]) for d in dataset)
    print(f"\n{'='*60}")
    print(f"Dataset summary: {len(dataset)} documents, {total_qa} QA pairs")
    for d in dataset:
        print(f"  {d['doc_id']}: {len(d['questions'])} QA pairs")


if __name__ == "__main__":
    main()
