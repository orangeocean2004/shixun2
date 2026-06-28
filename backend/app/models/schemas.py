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
    doc_id: str | None = None
    question: str
    top_k: int = 5


class QueryResponse(BaseModel):
    doc_id: str | None = None
    question: str
    top_k: int
    chunks: list[RetrievedChunk]


class ChunkListResponse(BaseModel):
    doc_id: str
    total: int
    chunks: list[RetrievedChunk]
