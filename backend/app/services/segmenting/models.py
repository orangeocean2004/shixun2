from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SegmentConfig:
    """分段参数。

    当前以字符数做默认长度约束，同时保留 token 级近似参数，
    方便在不引入真实 tokenizer 的前提下模拟更稳健的分段策略。
    """

    min_chars: int = 300
    target_chars: int = 900
    max_chars: int = 1200
    overlap_sentences: int = 1
    min_tokens: int = 180
    target_tokens: int = 512
    max_tokens: int = 900
    include_heading_in_content: bool = True
    enable_semantic_boundary: bool = True
    semantic_boundary_threshold: float = 0.72
    keyword_strategy: str = "jieba_tfidf"


@dataclass
class DocumentBlock:
    """文档的最小结构单元。

    上游如果已经解析出标题、段落、表格、页码等信息，可以直接构造这个对象。
    """

    block_id: str
    text: str
    block_type: str = "paragraph"
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """最终输出给 RAG 入库或前端展示的分段结果。"""

    chunk_id: str
    content: str
    title_path: list[str]
    chunk_type: str
    char_count: int
    source_refs: list[dict[str, Any]]
    strategy_info: dict[str, Any]
    quality_flags: list[str] = field(default_factory=list)
    label: list[str] = field(default_factory=list)
    summary: str = ""
    entity_tags: list[str] = field(default_factory=list)
    backlink: dict[str, Any] = field(default_factory=dict)


CandidateChunk = dict[str, Any]
