from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    ordinal: int | None = None
    chunk_type: str
    content: str
    summary: str = ""
    char_count: int
    title_path: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    backlink: dict[str, Any] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)
    strategy_info: dict[str, Any] = Field(default_factory=dict)
    label: list[str] = Field(default_factory=list)
    entity_tags: list[str] = Field(default_factory=list)
    section_titles: list[str] = Field(default_factory=list)
    retrieval_text: str = ""
    score: float | None = None


class SegmentUploadResponse(BaseModel):
    doc_id: str
    file_name: str
    file_size: int
    block_count: int
    chunks: list[dict[str, Any]]
    statistics: dict[str, Any]
    strategy: dict[str, Any]


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)


class QueryResponse(BaseModel):
    question: str
    top_k: int
    answer: str = ""
    chunks: list[RetrievedChunk]


class ChunkListResponse(BaseModel):
    doc_id: str
    total: int
    chunks: list[RetrievedChunk]


class ModelSettingsPayload(BaseModel):
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = Field(min_length=1)
    LLM_MODEL: str = Field(min_length=1)
    QA_QUALITY_EVALUATOR: str | None = None


class ModelSettingsResponse(BaseModel):
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = Field(min_length=1)
    LLM_MODEL: str = Field(min_length=1)
    QA_QUALITY_EVALUATOR: str = "lexical_overlap_v1"


# ── /strategies ──────────────────────────────────────────

class StrategyInfo(BaseModel):
    name: str
    label: str
    description: str


class StrategiesResponse(BaseModel):
    segmentation_strategies: list[StrategyInfo]
    keyword_strategies: list[str]
    default_config: dict[str, Any]


# ── /organize ────────────────────────────────────────────

class OrganizeChunkInput(BaseModel):
    chunk_id: str = ""
    content: str


class OrganizeRequest(BaseModel):
    doc_id: str = ""
    chunks: list[OrganizeChunkInput]
    keyword_strategy: str = "jieba_tfidf"


class OrganizeChunkOutput(BaseModel):
    chunk_id: str
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    entity_labels: list[dict[str, str]] = Field(default_factory=list)


class OrganizeResponse(BaseModel):
    doc_id: str
    doc_summary: str = ""
    chunks: list[OrganizeChunkOutput]


# ── /evaluate ────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    doc_id: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class StrategyMetrics(BaseModel):
    strategy: str
    chunk_count: int
    avg_chunk_size: float
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    precision_at_5: float = 0.0
    ndcg_at_5: float = 0.0
    mrr: float = 0.0


class EvaluateResponse(BaseModel):
    doc_id: str
    top_k: int
    strategies: list[StrategyMetrics]
