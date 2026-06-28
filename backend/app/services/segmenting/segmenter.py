from __future__ import annotations

from typing import Any

from .enrichment import build_backlink, build_label, build_summary, extract_entity_tags
from .keyword_extraction import get_keyword_strategy
from .models import CandidateChunk, Chunk, DocumentBlock, SegmentConfig
from .parser import parse_plain_text
from .splitter import build_candidate_chunks, merge_short_chunks, split_oversized_chunks
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
            "name": "heading_sentence_semantic_rule",
            "min_chars": config.min_chars,
            "target_chars": config.target_chars,
            "max_chars": config.max_chars,
            "overlap_sentences": config.overlap_sentences,
            "min_tokens": config.min_tokens,
            "target_tokens": config.target_tokens,
            "max_tokens": config.max_tokens,
            "include_heading_in_content": config.include_heading_in_content,
            "enable_semantic_boundary": config.enable_semantic_boundary,
            "semantic_boundary_threshold": config.semantic_boundary_threshold,
            "keyword_strategy": config.keyword_strategy,
            "keyword_tokenizer": "jieba",
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
    keyword_strategy = get_keyword_strategy(config.keyword_strategy)

    for index, candidate in enumerate(candidates, start=1):
        chunk_id = f"{doc_id}_chunk_{index:04d}"
        content = candidate["content"]
        char_count = len(content)
        source_refs = build_source_refs(candidate["source_blocks"])

        quality_flags: list[str] = []
        if char_count > config.max_chars:
            quality_flags.append("oversized")
        if char_count < config.min_chars:
            quality_flags.append("undersized")
        if not candidate["source_blocks"]:
            quality_flags.append("missing_source_ref")
        if candidate["chunk_type"] in {"table", "formula", "code"}:
            quality_flags.append(f'contains_{candidate["chunk_type"]}')
        if any(block.block_type == "image" for block in candidate["source_blocks"]):
            quality_flags.append("contains_image")

        strategy_info = dict(candidate["strategy_info"])
        strategy_info["enrichment"] = "deterministic_v1"
        strategy_info["keyword_strategy"] = config.keyword_strategy

        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                content=content,
                title_path=candidate["title_path"],
                chunk_type=candidate["chunk_type"],
                char_count=char_count,
                source_refs=source_refs,
                strategy_info=strategy_info,
                quality_flags=quality_flags,
                label=build_label(
                    candidate["title_path"],
                    candidate["chunk_type"],
                    content,
                    keyword_strategy=keyword_strategy,
                ),
                summary=build_summary(content),
                entity_tags=extract_entity_tags(content),
                backlink=build_backlink(doc_id, chunk_id, source_refs),
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
