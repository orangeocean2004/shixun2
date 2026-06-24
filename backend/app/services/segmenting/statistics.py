from __future__ import annotations

from typing import Any

from .models import Chunk, SegmentConfig
from .splitter import count_tokens


def build_statistics(chunks: list[Chunk], config: SegmentConfig) -> dict[str, Any]:
    """生成分段质量统计，供接口响应和前端展示使用。"""

    if not chunks:
        return {
            "chunk_count": 0,
            "avg_chars": 0,
            "avg_tokens": 0,
            "target_length_hit_rate": 0,
            "target_token_length_hit_rate": 0,
            "oversized_count": 0,
            "undersized_count": 0,
            "source_ref_complete_rate": 0,
        }

    target_hits = [chunk for chunk in chunks if config.min_chars <= chunk.char_count <= config.max_chars]
    complete_refs = [chunk for chunk in chunks if chunk.source_refs]
    token_counts = [count_tokens(chunk.content) for chunk in chunks]
    token_hits = [
        chunk for chunk, token_count in zip(chunks, token_counts)
        if config.min_tokens <= token_count <= config.max_tokens
    ]

    return {
        "chunk_count": len(chunks),
        "avg_chars": round(sum(chunk.char_count for chunk in chunks) / len(chunks), 2),
        "avg_tokens": round(sum(token_counts) / len(token_counts), 2),
        "target_length_hit_rate": round(len(target_hits) / len(chunks), 4),
        "target_token_length_hit_rate": round(len(token_hits) / len(chunks), 4),
        "oversized_count": sum("oversized" in chunk.quality_flags for chunk in chunks),
        "undersized_count": sum("undersized" in chunk.quality_flags for chunk in chunks),
        "source_ref_complete_rate": round(len(complete_refs) / len(chunks), 4),
    }


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """把 Chunk dataclass 转成可 JSON 序列化的 dict。"""

    return {
        "chunk_id": chunk.chunk_id,
        "chunk_type": chunk.chunk_type,
        "title_path": chunk.title_path,
        "content": chunk.content,
        "char_count": chunk.char_count,
        "source_refs": chunk.source_refs,
        "strategy_info": chunk.strategy_info,
        "quality_flags": chunk.quality_flags,
    }
