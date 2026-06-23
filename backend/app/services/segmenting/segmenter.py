from __future__ import annotations

from typing import Any

from .models import CandidateChunk, Chunk, DocumentBlock, SegmentConfig
from .parser import parse_plain_text
from .splitter import build_candidate_chunks, split_oversized_chunks, merge_short_chunks
from .statistics import build_statistics, chunk_to_dict


def segment_text(
    text: str,
    doc_id: str = "doc",
    config: SegmentConfig | None = None,
) -> dict[str, Any]:
    """纯文本分段入口。

    前端直接上传文本时可调用这个函数；如果已有结构化 block，则调用 segment_blocks。
    """

    blocks = parse_plain_text(text)
    return segment_blocks(blocks, doc_id=doc_id, config=config)


def segment_blocks(
    blocks: list[DocumentBlock],
    doc_id: str = "doc",
    config: SegmentConfig | None = None,
) -> dict[str, Any]:
    """结构化文档分段入口。

    主流程：
    1. 标题/段落生成候选 chunk
    2. 超长 chunk 继续按句子拆
    3. 过短 chunk 尝试合并
    4. 补全 ID、来源回链、质量标记和统计信息
    """

    config = config or SegmentConfig()
    candidate_chunks = build_candidate_chunks(blocks, config)
    normalized_chunks = split_oversized_chunks(candidate_chunks, config)
    merged_chunks = merge_short_chunks(normalized_chunks, config)
    chunks = finalize_chunks(merged_chunks, doc_id, config)

    return {
        "doc_id": doc_id,
        "chunks": [chunk_to_dict(chunk) for chunk in chunks],
        "statistics": build_statistics(chunks, config),
        "strategy": {
            "name": "heading_paragraph_rule",
            "min_chars": config.min_chars,
            "target_chars": config.target_chars,
            "max_chars": config.max_chars,
            "overlap_sentences": config.overlap_sentences,
        },
    }


def finalize_chunks(
    candidates: list[CandidateChunk],
    doc_id: str,
    config: SegmentConfig,
) -> list[Chunk]:
    """把候选 chunk 转成最终 Chunk。

    这里负责生成稳定 chunk_id、source_refs 和 quality_flags。
    """

    chunks: list[Chunk] = []

    for index, candidate in enumerate(candidates, start=1):
        char_count = len(candidate["content"])
        quality_flags: list[str] = []
        if char_count > config.max_chars:
            quality_flags.append("oversized")
        if char_count < config.min_chars:
            quality_flags.append("undersized")
        if not candidate["source_blocks"]:
            quality_flags.append("missing_source_ref")
        if candidate["chunk_type"] in {"table", "formula", "code"}:
            quality_flags.append(f'contains_{candidate["chunk_type"]}')

        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}_chunk_{index:04d}",
                content=candidate["content"],
                title_path=candidate["title_path"],
                chunk_type=candidate["chunk_type"],
                char_count=char_count,
                source_refs=build_source_refs(candidate["source_blocks"]),
                strategy_info=candidate["strategy_info"],
                quality_flags=quality_flags,
            )
        )

    return chunks


def build_source_refs(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    """生成 chunk 到原文 block 的回链信息。"""

    refs: list[dict[str, Any]] = []
    for block in blocks:
        refs.append(
            {
                "block_id": block.block_id,
                "block_type": block.block_type,
                "page": block.page,
                "metadata": block.metadata,
            }
        )
    return refs
