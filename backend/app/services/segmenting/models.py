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
    # 标题边界 flush 阈值：当前 chunk 字符数达到此值才在新标题处收束。
    # 低于此值时，新标题会并入当前 chunk，抑制多标题文档的碎片化。
    heading_flush_min_chars: int = 300
    # token 默认值以 tiktoken cl100k_base 为基准校准：
    #   中文 ≈1.09 t/c → 900c≈980t, 1200c≈1300t
    #   英文 ≈0.25 t/c → 900c≈225t,  1200c≈300t
    # 双目标取较小者：中文受 token 约束（~825c 触发），英文受 char 约束
    # min_tokens=100：英文 100t≈400c，中文 100t≈90c，两者均由 min_chars=300 实际约束
    min_tokens: int = 100
    target_tokens: int = 900
    max_tokens: int = 1200
    include_heading_in_content: bool = True
    enable_semantic_boundary: bool = True
    # 语义边界阈值。当前优先使用 sentence-transformers embedding，
    # 失败时回退 token 计数余弦；0.35 在课程样例上能抑制过度碎片化。
    semantic_boundary_threshold: float = 0.35
    recursive_separators: tuple[str, ...] = (
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        "；",
        ";",
        ". ",
        ".",
        "，",
        "、",
        ",",
        ":",
        "：",
        " ",
        "",
    )


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
    asset_refs: list[dict[str, str]] = field(default_factory=list)


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
    section_titles: list[str] = field(default_factory=list)
    retrieval_text: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    entity_labels: list[dict[str, str]] = field(default_factory=list)
    asset_refs: list[dict[str, str]] = field(default_factory=list)


CandidateChunk = dict[str, Any]
