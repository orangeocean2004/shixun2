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
