from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.app.core.config import (
    ALLOWED_UPLOAD_SUFFIXES,
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    DEFAULT_OVERLAP_SENTENCES,
    DEFAULT_TARGET_CHARS,
)
from backend.app.models.schemas import SegmentUploadResponse
from backend.app.services.document_loader import DocumentLoaderError, load_document
from backend.app.services.segmenter import SegmentConfig, segment_blocks
from backend.app.services.segmenting.keyword_extraction import (
    DEFAULT_KEYWORD_STRATEGY,
    list_keyword_strategies,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/segment/upload", response_model=SegmentUploadResponse)
async def upload_and_segment(
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    min_chars: int = Form(DEFAULT_MIN_CHARS),
    target_chars: int = Form(DEFAULT_TARGET_CHARS),
    max_chars: int = Form(DEFAULT_MAX_CHARS),
    overlap_sentences: int = Form(DEFAULT_OVERLAP_SENTENCES),
    keyword_strategy: str = Form(DEFAULT_KEYWORD_STRATEGY),
) -> SegmentUploadResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"暂不支持的文件类型：{suffix or '无后缀'}")

    if min_chars <= 0 or target_chars <= 0 or max_chars <= 0 or overlap_sentences < 0:
        raise HTTPException(status_code=400, detail="分段参数必须为正数，且 overlap_sentences 不能小于 0")
    if not (min_chars <= target_chars <= max_chars):
        raise HTTPException(status_code=400, detail="分段参数需满足 min_chars <= target_chars <= max_chars")

    normalized_keyword_strategy = (keyword_strategy or "").strip().lower() or DEFAULT_KEYWORD_STRATEGY
    supported_keyword_strategies = set(list_keyword_strategies())
    if normalized_keyword_strategy not in supported_keyword_strategies:
        raise HTTPException(
            status_code=400,
            detail=(
                "keyword_strategy 不支持，当前可选："
                + ", ".join(sorted(supported_keyword_strategies))
            ),
        )

    temp_path: str | None = None
    try:
        payload = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            temp_path = temp_file.name

        blocks = load_document(temp_path)
        config = SegmentConfig(
            min_chars=min_chars,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_sentences=overlap_sentences,
            keyword_strategy=normalized_keyword_strategy,
        )
        result_doc_id = doc_id.strip() if doc_id and doc_id.strip() else safe_doc_id(Path(filename).stem)
        result = segment_blocks(blocks, doc_id=result_doc_id, config=config)

        return SegmentUploadResponse(
            doc_id=result["doc_id"],
            file_name=filename,
            file_size=len(payload),
            block_count=len(blocks),
            chunks=result["chunks"],
            statistics=result["statistics"],
            strategy=result["strategy"],
        )
    except DocumentLoaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"处理文件失败：{exc}") from exc
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"
