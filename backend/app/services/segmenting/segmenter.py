from __future__ import annotations

from typing import Any

from backend.app.services.organizer import ContentOrganizer, OrganizeResult

from .models import CandidateChunk, Chunk, DocumentBlock, SegmentConfig
from .parser import parse_plain_text
from .splitter import build_candidate_chunks, split_oversized_chunks, merge_short_chunks
from .statistics import build_statistics, chunk_to_dict


def segment_text(
    text: str,
    doc_id: str = "doc",
    config: SegmentConfig | None = None,
    organizer: ContentOrganizer | None = None,
) -> dict[str, Any]:
    """纯文本分段入口。

    前端直接上传文本时可调用这个函数；如果已有结构化 block，则调用 segment_blocks。
    """

    blocks = parse_plain_text(text)
    return segment_blocks(blocks, doc_id=doc_id, config=config, organizer=organizer)


def segment_blocks(
    blocks: list[DocumentBlock],
    doc_id: str = "doc",
    config: SegmentConfig | None = None,
    organizer: ContentOrganizer | None = None,
) -> dict[str, Any]:
    """结构化文档分段入口。

    主流程：
    1. 标题/段落生成候选 chunk
    2. 超长 chunk 继续按句子拆
    3. 过短 chunk 尝试合并
    4. 补全 ID、来源回链、质量标记和统计信息
    5. （可选）内容打标、摘要生成、实体标注
    """

    config = config or SegmentConfig()
    candidate_chunks = build_candidate_chunks(blocks, config)
    normalized_chunks = split_oversized_chunks(candidate_chunks, config)
    merged_chunks = merge_short_chunks(normalized_chunks, config)
    chunks, doc_summary = finalize_chunks(merged_chunks, doc_id, config, organizer)

    return {
        "doc_id": doc_id,
        "chunks": [chunk_to_dict(chunk) for chunk in chunks],
        "statistics": build_statistics(chunks, config),
        "strategy": {
            "name": "heading_recursive_semantic_rule",
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
            "recursive_separators": list(config.recursive_separators),
        },
        "document_summary": doc_summary,
    }


def finalize_chunks(
    candidates: list[CandidateChunk],
    doc_id: str,
    config: SegmentConfig,
    organizer: ContentOrganizer | None = None,
) -> tuple[list[Chunk], str]:
    """把候选 chunk 转成最终 Chunk，并可选的进行内容打标/摘要。

    这里负责生成稳定 chunk_id、source_refs 和 quality_flags。
    如果提供了 organizer，则在所有 chunk 构建完成后批量执行
    标签提取、摘要生成和实体标注。
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
        if candidate["chunk_type"] == "metric":
            quality_flags.append("contains_metric")

        section_titles = list(candidate.get("section_titles", []))
        retrieval_text = build_retrieval_text(candidate)

        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}_chunk_{index:04d}",
                content=candidate["content"],
                title_path=candidate["title_path"],
                chunk_type=candidate["chunk_type"],
                char_count=char_count,
                source_refs=build_source_refs(candidate["source_blocks"]),
                asset_refs=build_asset_refs(candidate["source_blocks"]),
                strategy_info=candidate["strategy_info"],
                quality_flags=quality_flags,
                section_titles=section_titles,
                retrieval_text=retrieval_text,
            )
        )

    # ── content organisation (optional) ──
    document_summary = ""
    if organizer:
        org_results, document_summary = organizer.organize_batch(candidates, doc_id)
        for chunk, org in zip(chunks, org_results):
            chunk.tags = org.tags
            chunk.summary = org.summary
            chunk.entity_labels = org.entity_labels

    return chunks, document_summary


def build_retrieval_text(candidate: CandidateChunk) -> str:
    """构造专供检索使用的增强文本，不改变原文 content。"""

    parts: list[str] = []
    title_path = candidate.get("title_path") or []
    section_titles = candidate.get("section_titles") or []
    metric_keywords = candidate.get("metric_keywords") or []

    if title_path:
        parts.append("标题路径: " + " > ".join(str(item) for item in title_path if str(item).strip()))
    if section_titles:
        parts.append("包含小节: " + "；".join(str(item) for item in section_titles if str(item).strip()))
    if metric_keywords:
        parts.append("关键指标: " + "；".join(str(item) for item in metric_keywords if str(item).strip()))
    if candidate.get("chunk_type") == "metric":
        parts.append("内容类型: 技术指标 验收标准 评价指标 百分比 阈值")
    parts.append(str(candidate.get("content", "")))
    return "\n".join(part for part in parts if part.strip()).strip()


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


def build_asset_refs(blocks: list[DocumentBlock]) -> list[dict[str, str]]:
    """聚合上游 block 已标注的外置资产引用（图片/附件等）。

    去重规则：相同 path 的资产只保留首次出现。
    """
    seen: set[str] = set()
    refs: list[dict[str, str]] = []
    for block in blocks:
        for asset in block.asset_refs:
            path = asset.get("path", "")
            if path and path not in seen:
                seen.add(path)
                refs.append(dict(asset))
    return refs
