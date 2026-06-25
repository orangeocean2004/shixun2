from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.app.core.config import (
    ALLOWED_UPLOAD_SUFFIXES,
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    DEFAULT_OVERLAP_SENTENCES,
    DEFAULT_TARGET_CHARS,
)
from backend.app.models.schemas import RagQueryRequest, RagQueryResponse, SegmentIndexUploadResponse, SegmentUploadResponse
from backend.app.services.document_loader import DocumentLoaderError, load_document
from backend.app.services.model_client import LLMClient
from backend.app.services.organizer import ContentOrganizer
from backend.app.services.preprocessing import PreprocessReport, preprocess_document_blocks
from backend.app.services.retrieval import semantic_store as vector_store
from backend.app.services.segmenting import SegmentConfig, segment_blocks

router = APIRouter()

_IMAGES_BASE_DIR = Path("data/images")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/images/{doc_id}/{filename}")
def serve_image(doc_id: str, filename: str):
    """提供文档中提取的图片文件。"""
    # 安全检查：防止路径穿越
    if ".." in doc_id or "/" in doc_id or "\\" in doc_id:
        raise HTTPException(status_code=400, detail="非法的 doc_id")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法的 filename")

    image_path = _IMAGES_BASE_DIR / doc_id / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图片未找到")
    return FileResponse(str(image_path))


@router.post("/api/segment/upload", response_model=SegmentUploadResponse)
async def upload_and_segment(
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    min_chars: int = Form(DEFAULT_MIN_CHARS),
    target_chars: int = Form(DEFAULT_TARGET_CHARS),
    max_chars: int = Form(DEFAULT_MAX_CHARS),
    overlap_sentences: int = Form(DEFAULT_OVERLAP_SENTENCES),
) -> SegmentUploadResponse:
    return await process_upload_and_segment(
        file=file,
        doc_id=doc_id,
        min_chars=min_chars,
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_sentences=overlap_sentences,
    )


@router.post("/api/rag/index/upload", response_model=SegmentIndexUploadResponse)
async def upload_segment_and_index(
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    min_chars: int = Form(DEFAULT_MIN_CHARS),
    target_chars: int = Form(DEFAULT_TARGET_CHARS),
    max_chars: int = Form(DEFAULT_MAX_CHARS),
    overlap_sentences: int = Form(DEFAULT_OVERLAP_SENTENCES),
) -> SegmentIndexUploadResponse:
    result = await process_upload_and_segment(
        file=file,
        doc_id=doc_id,
        min_chars=min_chars,
        target_chars=target_chars,
        max_chars=max_chars,
        overlap_sentences=overlap_sentences,
    )
    index_summary = vector_store.upsert(result.doc_id, result.chunks)
    return SegmentIndexUploadResponse(**result.model_dump(), index=index_summary)


@router.post("/api/rag/query", response_model=RagQueryResponse)
def query_index(request: RagQueryRequest) -> RagQueryResponse:
    query = request.query.strip()
    doc_id = request.doc_id.strip()
    if not doc_id:
        raise HTTPException(status_code=400, detail="doc_id 不能为空")
    if not query:
        raise HTTPException(status_code=400, detail="query 不能为空")
    if request.top_k <= 0:
        raise HTTPException(status_code=400, detail="top_k 必须大于 0")

    try:
        hits = vector_store.search(doc_id, query, top_k=request.top_k)
    except KeyError as exc:
        available = ", ".join(vector_store.list_doc_ids()) or "无"
        raise HTTPException(status_code=404, detail=f"文档未入库：{doc_id}。当前已入库：{available}") from exc

    return RagQueryResponse(
        doc_id=doc_id,
        query=query,
        top_k=request.top_k,
        hits=[hit.__dict__ for hit in hits],
    )


async def process_upload_and_segment(
    file: UploadFile,
    doc_id: Optional[str],
    min_chars: int,
    target_chars: int,
    max_chars: int,
    overlap_sentences: int,
) -> SegmentUploadResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"暂不支持的文件类型：{suffix or '无后缀'}")

    if min_chars <= 0 or target_chars <= 0 or max_chars <= 0 or overlap_sentences < 0:
        raise HTTPException(status_code=400, detail="分段参数必须为正数，且 overlap_sentences 不能小于 0")
    if not (min_chars <= target_chars <= max_chars):
        raise HTTPException(status_code=400, detail="分段参数需满足 min_chars <= target_chars <= max_chars")

    temp_path: str | None = None
    try:
        payload = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            temp_path = temp_file.name

        result_doc_id = doc_id.strip() if doc_id and doc_id.strip() else safe_doc_id(Path(filename).stem)

        # 创建图片存储目录
        image_dir = str(_IMAGES_BASE_DIR / result_doc_id)
        os.makedirs(image_dir, exist_ok=True)

        blocks = load_document(temp_path, doc_id=result_doc_id, image_dir=image_dir)
        preprocess_report: PreprocessReport | None = None
        cleaned_blocks, preprocess_report = preprocess_document_blocks(blocks)
        config = SegmentConfig(
            min_chars=min_chars,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_sentences=overlap_sentences,
        )

        # Build content organiser — LLM if API key configured, else rule-based.
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        openai_base_url = os.environ.get("OPENAI_BASE_URL")
        llm_client = None
        if openai_api_key:
            llm_client = LLMClient(
                api_key=openai_api_key,
                base_url=openai_base_url,
            )
        organizer = ContentOrganizer(llm_client=llm_client)

        result = segment_blocks(cleaned_blocks, doc_id=result_doc_id, config=config, organizer=organizer)

        return SegmentUploadResponse(
            doc_id=result["doc_id"],
            file_name=filename,
            file_size=len(payload),
            block_count=len(cleaned_blocks),
            chunks=result["chunks"],
            statistics=result["statistics"],
            strategy=result["strategy"],
            preprocess=preprocess_report.to_dict(),
            document_summary=result.get("document_summary", ""),
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
