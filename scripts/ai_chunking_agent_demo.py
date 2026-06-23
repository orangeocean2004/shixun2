from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from langchain_openai import ChatOpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.document_loader import load_document


SYSTEM_PROMPT = (
    "你是一个文档分段智能体。"
    "你会根据标题边界、主题连续性和长度约束，把连续的文本块分成多个 chunk。"
    "输出必须是 JSON，不要输出任何解释。"
)
DEFAULT_API_KEY = "KQ7nwixd3svlWvVH7jOFZgavykY1KCqwV0GOK9dy2Ev1vTLb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI chunking demo for long documents")
    parser.add_argument("input", help="Input file path, e.g. assets/研发计划.pdf")
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON path, default: data/outputs/<input_stem>_ai_chunks.json",
    )
    parser.add_argument("--doc-id", help="Document id prefix for chunk ids")
    parser.add_argument("--model", default=os.getenv("AI_MODEL", "agnes-2.0-flash"), help="LLM model name")
    parser.add_argument(
        "--base-url",
        default=os.getenv("AI_BASE_URL", "https://apihub.agnes-ai.com/v1"),
        help="OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="API key",
    )
    parser.add_argument("--min-chars", type=int, default=300)
    parser.add_argument("--target-chars", type=int, default=900)
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--preview-chars", type=int, default=180, help="Chars kept per block in prompt")
    parser.add_argument("--timeout", type=int, default=120, help="LLM timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM call and use rule fallback")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = Path(args.input)
    doc_id = args.doc_id or safe_doc_id(input_path.stem)
    output_path = Path(args.output) if args.output else default_output_path(input_path)

    blocks = load_document(input_path)
    if not blocks:
        raise ValueError("输入文档没有可用文本块")

    if args.dry_run:
        ranges = build_rule_ranges(blocks, args.target_chars)
        model_used = "rule-fallback"
    else:
        if not args.api_key.strip():
            raise ValueError("缺少 API Key。请通过 --api-key 或 AI_API_KEY 提供。")
        ranges = call_chunking_agent(
            blocks=blocks,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key.strip(),
            min_chars=args.min_chars,
            target_chars=args.target_chars,
            max_chars=args.max_chars,
            preview_chars=args.preview_chars,
            timeout=args.timeout,
        )
        model_used = args.model

    chunks = materialize_chunks(
        blocks=blocks,
        ranges=ranges,
        doc_id=doc_id,
        max_chars=args.max_chars,
    )

    result = {
        "doc_id": doc_id,
        "source_file": str(input_path),
        "model": model_used,
        "chunk_count": len(chunks),
        "strategy": {
            "name": "ai_agent_chunking",
            "min_chars": args.min_chars,
            "target_chars": args.target_chars,
            "max_chars": args.max_chars,
        },
        "chunks": chunks,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Loaded blocks: {len(blocks)}")
    print(f"Generated chunks: {len(chunks)}")
    print(f"Output written: {output_path}")


def call_chunking_agent(
    blocks: list[Any],
    model: str,
    base_url: str,
    api_key: str,
    min_chars: int,
    target_chars: int,
    max_chars: int,
    preview_chars: int,
    timeout: int,
) -> list[dict[str, Any]]:
    prompt = build_user_prompt(blocks, min_chars, target_chars, max_chars, preview_chars)

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
        timeout=timeout,
    )

    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", prompt),
    ]

    try:
        response = llm.bind(response_format={"type": "json_object"}).invoke(messages)
    except Exception:
        response = llm.invoke(messages)

    content = extract_message_text(response.content)
    data = parse_json_content(content)

    raw_chunks = data.get("chunks")
    if not isinstance(raw_chunks, list):
        raise ValueError("模型返回缺少 chunks 数组")

    return sanitize_ranges(raw_chunks, len(blocks))


def extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    return str(content)


def build_user_prompt(
    blocks: list[Any],
    min_chars: int,
    target_chars: int,
    max_chars: int,
    preview_chars: int,
) -> str:
    lines: list[str] = []
    for i, block in enumerate(blocks):
        text = normalize_text(block.text)
        short = text[:preview_chars]
        lines.append(
            f"[{i}] page={block.page or 0} type={block.block_type} text={short}"
        )

    block_text = "\n".join(lines)
    return (
        "请把下列文本块按语义分成连续 chunk。\n"
        "要求：\n"
        f"1) 每个 chunk 建议长度 {min_chars}-{max_chars} 字符，目标约 {target_chars} 字符。\n"
        "2) chunk 必须覆盖所有 block，且按原顺序连续，不重叠、不跳号。\n"
        "3) 标题尽量作为新 chunk 的开头。\n"
        "4) 输出 JSON 对象，格式如下：\n"
        '{"chunks":[{"start":0,"end":3,"title":"小标题","reason":"一句话说明"}]}\n'
        "下面是 block 列表：\n"
        f"{block_text}"
    )


def parse_json_content(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if not match:
            raise
        return json.loads(match.group(0))


def sanitize_ranges(raw_chunks: list[dict[str, Any]], total_blocks: int) -> list[dict[str, Any]]:
    if total_blocks <= 0:
        return []

    ranges: list[dict[str, Any]] = []
    cursor = 0

    for item in raw_chunks:
        start = to_int(item.get("start"), cursor)
        end = to_int(item.get("end"), start)
        title = str(item.get("title") or "")
        reason = str(item.get("reason") or "")

        if start < cursor:
            start = cursor
        if end < start:
            continue
        if start >= total_blocks:
            break
        if end >= total_blocks:
            end = total_blocks - 1

        if start > cursor:
            ranges.append({"start": cursor, "end": start - 1, "title": "补充段", "reason": "补全缺口"})

        ranges.append({"start": start, "end": end, "title": title, "reason": reason})
        cursor = end + 1
        if cursor >= total_blocks:
            break

    if cursor < total_blocks:
        ranges.append({"start": cursor, "end": total_blocks - 1, "title": "补充段", "reason": "补全结尾"})

    return ranges


def materialize_chunks(
    blocks: list[Any],
    ranges: list[dict[str, Any]],
    doc_id: str,
    max_chars: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    chunk_index = 1

    for item in ranges:
        start = item["start"]
        end = item["end"]
        title = item.get("title") or "未命名分段"
        reason = item.get("reason") or ""

        piece_texts: list[str] = []
        piece_refs: list[dict[str, Any]] = []
        piece_chars = 0
        split_part = 1

        for i in range(start, end + 1):
            block = blocks[i]
            text = normalize_text(block.text)
            if not text:
                continue

            delta = len(text) + (2 if piece_texts else 0)
            if piece_texts and piece_chars + delta > max_chars:
                output.append(
                    build_chunk_record(
                        doc_id=doc_id,
                        chunk_index=chunk_index,
                        title=title,
                        split_part=split_part,
                        reason=reason,
                        piece_texts=piece_texts,
                        piece_refs=piece_refs,
                    )
                )
                chunk_index += 1
                split_part += 1
                piece_texts = []
                piece_refs = []
                piece_chars = 0

            piece_texts.append(text)
            piece_refs.append(
                {
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "page": block.page,
                }
            )
            piece_chars += len(text) + (2 if len(piece_texts) > 1 else 0)

        if piece_texts:
            output.append(
                build_chunk_record(
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    title=title,
                    split_part=split_part,
                    reason=reason,
                    piece_texts=piece_texts,
                    piece_refs=piece_refs,
                )
            )
            chunk_index += 1

    return output


def build_chunk_record(
    doc_id: str,
    chunk_index: int,
    title: str,
    split_part: int,
    reason: str,
    piece_texts: list[str],
    piece_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    content = "\n\n".join(piece_texts)
    chunk_title = title if split_part == 1 else f"{title}（续{split_part}）"
    return {
        "chunk_id": f"{doc_id}_ai_chunk_{chunk_index:04d}",
        "chunk_title": chunk_title,
        "chunk_summary": reason,
        "char_count": len(content),
        "content": content,
        "source_refs": piece_refs,
    }


def build_rule_ranges(blocks: list[Any], target_chars: int) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    start = 0
    current = 0

    for i, block in enumerate(blocks):
        text = normalize_text(block.text)
        next_size = len(text) + (2 if current > 0 else 0)
        if i > start and current + next_size >= target_chars:
            ranges.append({"start": start, "end": i - 1, "title": "规则分段", "reason": "dry-run"})
            start = i
            current = len(text)
        else:
            current += next_size

    if start < len(blocks):
        ranges.append({"start": start, "end": len(blocks) - 1, "title": "规则分段", "reason": "dry-run"})

    return ranges


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def default_output_path(input_path: Path) -> Path:
    return PROJECT_ROOT / "data" / "outputs" / f"{safe_doc_id(input_path.stem)}_ai_chunks.json"


def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"


def to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    main()
