from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SegmentConfig:
    """分段参数。

    当前以字符数做默认长度约束，同时保留 token 级近似参数，
    方便在不引入真实 tokenizer 的前提下模拟更稳健的分段策略。
    """

    min_chars: int = 180
    target_chars: int = 550
    max_chars: int = 800
    overlap_sentences: int = 2
    heading_flush_min_chars: int = 240
    min_tokens: int = 100
    target_tokens: int = 900
    max_tokens: int = 1200
    include_heading_in_content: bool = True
    enable_semantic_boundary: bool = True
    semantic_boundary_threshold: float = 0.55
    enable_parent_child: bool = False
    parent_target_chars: int = 1200
    recursive_separators: tuple[str, ...] = (
        # 只保留真正的段落和句子边界 — 绝不在逗号/冒号/空格处破句
        "\n\n",
        "\n",
        "。",
        "！",
        "？",
        "；",
        ";",
        ". ",
        "! ",
        "? ",
        ".",
        "!",
        "?",
        "：",
        ":",
        "…",
        "…",
        "—",
        "～",
        "~",
        ")",
        "）",
        "]",
        "}",
    )

    @classmethod
    def auto(cls, total_chars: int) -> "SegmentConfig":
        """根据文档总长度自动确定最优分段参数。

        短文档用小 chunk 保证检索精度，长文档用较大 chunk 避免过度碎片化。
        语义边界默认关闭 — 对于中英文混合场景，结构感知（heading）
        已足够；语义边界仅在中文干净文档上有正向收益。
        """
        if total_chars <= 0:
            return cls()

        # 按文档长度分档 — 大于固定长度基线，靠结构化边界差异化
        # max_chars 放宽到 3x target，适应 heading 块（短）与大段内容（长）的自然差异
        if total_chars < 3_000:
            target = 350
            min_c = 50
        elif total_chars < 10_000:
            target = 600
            min_c = 60
        elif total_chars < 50_000:
            target = 700
            min_c = 80
        elif total_chars < 200_000:
            target = 800
            min_c = 120
        else:
            target = 900
            min_c = 200

        return cls(
            min_chars=min_c,
            target_chars=target,
            max_chars=target * 3,
            heading_flush_min_chars=min_c,
            overlap_sentences=0,                     # 默认关闭 — 稀释检索精度
            enable_semantic_boundary=False,           # 默认关闭 — 仅中文有帮助
            semantic_boundary_threshold=0.65,
        )

    @classmethod
    def for_preset(cls, preset: str) -> "SegmentConfig":
        """根据下游场景返回预设分段参数。

        预设：
        - "rag":       RAG 检索优化 — 短 chunk（450字）+ 2句重叠，精准命中优先
        - "training":  训练语料生产 — 长 chunk（1000字）+ 无重叠，语义完整优先
        - "summary":   文档摘要 — 按章节分段（2000字），结构完整优先
        """
        presets = {
            "rag": {"target": 450, "min": 180, "max": 800, "overlap": 2},
            "training": {"target": 1000, "min": 500, "max": 2000, "overlap": 0},
            "summary": {"target": 2000, "min": 500, "max": 4000, "overlap": 0},
        }
        p = presets.get(preset)
        if p is None:
            raise ValueError(f"未知预设 '{preset}'，可选：{', '.join(presets)}")

        return cls(
            min_chars=p["min"],
            target_chars=p["target"],
            max_chars=p["max"],
            overlap_sentences=p["overlap"],
            heading_flush_min_chars=max(120, p["target"] // 3),
            enable_semantic_boundary=True,
            semantic_boundary_threshold=0.55,
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
    retrieval_text: str = ""
    quality_flags: list[str] = field(default_factory=list)
    label: list[str] = field(default_factory=list)
    summary: str = ""
    entity_tags: list[str] = field(default_factory=list)
    backlink: dict[str, Any] = field(default_factory=dict)
    section_titles: list[str] = field(default_factory=list)
    parent_chunk_id: str = ""
    child_chunk_ids: list[str] = field(default_factory=list)


CandidateChunk = dict[str, Any]
