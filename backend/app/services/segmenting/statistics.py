from __future__ import annotations

import re
from typing import Any

from .models import Chunk, SegmentConfig


TOKEN_PATTERN = re.compile(r"[一-鿿]|[A-Za-z0-9_]+|[^\s]")

# 句子结束标点：句号、问号、叹号、省略号、分号、右引号/括号类
_SENTENCE_END_PATTERN = re.compile(
    r"[。！？…~；;」』】》）\"'`\s]$"
)

# 需要保证不被截断的特殊块类型（与 splitter 中的 PROTECTED_BLOCK_TYPES 保持一致）
_PROTECTED_BLOCK_TYPES = frozenset({"table", "formula", "code"})


def build_statistics(chunks: list[Chunk], config: SegmentConfig) -> dict[str, Any]:
    """生成分段质量统计，供接口响应和前端展示使用。

    统计项说明：
    - no_break_sentence_rate: 不破句率。chunk 在有效句子边界结束的比例
    - table_code_formula_intact_rate: 表格/公式/代码整体成块率
    - target_length_hit_rate: 目标长度区间命中率
    - source_ref_complete_rate: 原文回链完整率
    """

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
            "no_break_sentence_rate": 0,
            "table_code_formula_intact_rate": 0,
        }

    target_hits = [chunk for chunk in chunks if config.min_chars <= chunk.char_count <= config.max_chars]
    complete_refs = [chunk for chunk in chunks if chunk.source_refs]
    token_counts = [count_tokens(chunk.content) for chunk in chunks]
    token_hits = [
        chunk for chunk, token_count in zip(chunks, token_counts)
        if config.min_tokens <= token_count <= config.max_tokens
    ]

    # 不破句率：chunk 末尾是否在合法句子边界结束
    no_break_chunks = [chunk for chunk in chunks if _ends_at_sentence_boundary(chunk.content)]

    # 表格/公式/代码整体成块率
    protected_chunks = [chunk for chunk in chunks if chunk.chunk_type in _PROTECTED_BLOCK_TYPES]
    intact_protected = [chunk for chunk in protected_chunks if _is_protected_block_intact(chunk)]

    return {
        "chunk_count": len(chunks),
        "avg_chars": round(sum(chunk.char_count for chunk in chunks) / len(chunks), 2),
        "avg_tokens": round(sum(token_counts) / len(token_counts), 2),
        "target_length_hit_rate": round(len(target_hits) / len(chunks), 4),
        "target_token_length_hit_rate": round(len(token_hits) / len(chunks), 4),
        "oversized_count": sum("oversized" in chunk.quality_flags for chunk in chunks),
        "undersized_count": sum("undersized" in chunk.quality_flags for chunk in chunks),
        "source_ref_complete_rate": round(len(complete_refs) / len(chunks), 4),
        "no_break_sentence_rate": round(len(no_break_chunks) / len(chunks), 4),
        "table_code_formula_intact_rate": (
            round(len(intact_protected) / len(protected_chunks), 4)
            if protected_chunks else 1.0
        ),
    }


def _ends_at_sentence_boundary(content: str) -> bool:
    """判断 chunk 的文本内容是否在合法的句子边界结束。

    合法边界包括：句号、问号、叹号、省略号、分号、右引号/右括号、
    空白字符、以及内容结尾。
    """
    if not content:
        return True
    stripped = content.rstrip()
    if not stripped:
        return True
    return bool(_SENTENCE_END_PATTERN.search(stripped))


def _is_protected_block_intact(chunk: Chunk) -> bool:
    """判断特殊块（表格/公式/代码）是否整体成块未被截断。

    当前分段策略在 splitter 中已保证 PROTECTED_BLOCK_TYPES 不会被切分，
    此函数作为校验层检查是否存在异常截断标记。
    """
    if not chunk.content.strip():
        return False

    split_indicators = {"split", "truncated", "fragmented"}
    for flag in chunk.quality_flags:
        if flag.lower() in split_indicators or "split" in flag.lower():
            return False

    return True


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """把 Chunk dataclass 转成可 JSON 序列化的 dict。"""

    return {
        "chunk_id": chunk.chunk_id,
        "chunk_type": chunk.chunk_type,
        "title_path": chunk.title_path,
        "content": chunk.content,
        "retrieval_text": chunk.retrieval_text,
        "char_count": chunk.char_count,
        "source_refs": chunk.source_refs,
        "strategy_info": chunk.strategy_info,
        "quality_flags": chunk.quality_flags,
        "label": chunk.label,
        "summary": chunk.summary,
        "entity_tags": chunk.entity_tags,
        "backlink": chunk.backlink,
    }


def count_tokens(text: str) -> int:
    """用轻量正则估算 token 数。"""

    return len(TOKEN_PATTERN.findall(text or ""))
