from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SegmentUploadResponse(BaseModel):
    doc_id: str
    file_name: str
    file_size: int
    block_count: int
    chunks: list[dict[str, Any]]
    statistics: dict[str, Any]
    strategy: dict[str, Any]
    preprocess: dict[str, Any] | None = None


class SegmentIndexUploadResponse(SegmentUploadResponse):
    index: dict[str, Any]


class RagQueryRequest(BaseModel):
    doc_id: str
    query: str
    top_k: int = 5


class RagQueryResponse(BaseModel):
    doc_id: str
    query: str
    top_k: int
    hits: list[dict[str, Any]]
