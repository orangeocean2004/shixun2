from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile

from backend.app.core.config import (
    ALLOWED_UPLOAD_SUFFIXES,
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_CHARS,
    DEFAULT_OVERLAP_SENTENCES,
    DEFAULT_RETRIEVE_TOP_K,
    DEFAULT_TARGET_CHARS,
)
from backend.app.models.schemas import (
    ChunkListResponse,
    ModelSettingsPayload,
    ModelSettingsResponse,
    QueryRequest,
    QueryResponse,
    SegmentUploadResponse,
)
from backend.app.services.document_loader import DocumentLoaderError
from backend.app.services.model_settings import get_model_settings, update_model_settings
from backend.app.services.qa_quality import get_qa_quality_evaluator
from backend.app.services.rag_store import ingest_document, list_all_chunks, retrieve_chunks
from backend.app.services.rag_store.service import (
    RAGDocumentBusyError,
    RAGDocumentNotFoundError,
    RAGDocumentNotReadyError,
    RAGValidationError,
)
from backend.app.services.segmenting.keyword_extraction import (
    DEFAULT_KEYWORD_STRATEGY,
    list_keyword_strategies,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/settings/model", response_model=ModelSettingsResponse)
def get_model_settings_api() -> ModelSettingsResponse:
    return ModelSettingsResponse(**get_model_settings())


@router.put("/api/settings/model", response_model=ModelSettingsResponse)
def update_model_settings_api(payload: ModelSettingsPayload) -> ModelSettingsResponse:
    saved = update_model_settings(payload.model_dump(exclude_unset=True, exclude_none=True))
    return ModelSettingsResponse(**saved)


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

    try:
        payload = await file.read()
        result_doc_id = doc_id.strip() if doc_id and doc_id.strip() else safe_doc_id(Path(filename).stem)
        result = ingest_document(
            file_name=filename,
            payload=payload,
            doc_id=result_doc_id,
            min_chars=min_chars,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_sentences=overlap_sentences,
            keyword_strategy=normalized_keyword_strategy,
        )

        return SegmentUploadResponse(
            doc_id=result["doc_id"],
            file_name=result["file_name"],
            file_size=result["file_size"],
            block_count=result["block_count"],
            chunks=result["chunks"],
            statistics=result["statistics"],
            strategy=result["strategy"],
        )
    except DocumentLoaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RAGValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RAGDocumentBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"处理文件失败：{exc}") from exc
    finally:
        await file.close()


@router.post("/api/query", response_model=QueryResponse)
def query_retrieved_chunks(payload: QueryRequest) -> QueryResponse:
    try:
        top_k = payload.top_k if payload.top_k > 0 else DEFAULT_RETRIEVE_TOP_K
        result = retrieve_chunks(
            question=payload.question,
            top_k=top_k,
        )
        answer = ""

        # 尝试用 LLM 根据检索到的 chunk 生成回答
        try:
            from backend.app.services.organizer.model_client import LLMClient

            settings = get_model_settings()
            llm = LLMClient(
                api_key=settings["OPENAI_API_KEY"],
                base_url=settings["OPENAI_BASE_URL"],
                model=settings["LLM_MODEL"],
            )
            if llm.is_available and result.get("chunks"):
                context_parts = []
                for c in result["chunks"]:
                    title = " > ".join(c.get("title_path", [])) or "无标题"
                    context_parts.append(f"[{title}]\n{c.get('content', '')[:800]}")
                context = "\n\n---\n\n".join(context_parts)

                answer = llm.generate(
                    f"根据以下文档片段回答问题。如果片段中没有足够信息，请如实说明。\n\n"
                    f"文档片段：\n{context}\n\n"
                    f"问题：{payload.question}\n\n"
                    f"回答：",
                    system_prompt="你是基于文档的问答助手。只根据提供的文档片段回答，不添加外部知识。",
                    temperature=0.3,
                    max_tokens=512,
                ).strip()
        except Exception:
            pass  # LLM 生成失败不影响检索结果返回

        return QueryResponse(
            question=payload.question,
            top_k=top_k or DEFAULT_RETRIEVE_TOP_K,
            answer=answer,
            chunks=result.get("chunks", []),
        )
    except RAGValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RAGDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RAGDocumentNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"检索失败：{exc}") from exc


@router.get("/api/chunks/all", response_model=ChunkListResponse)
def get_all_chunks(doc_id: str = Query(..., min_length=1)) -> ChunkListResponse:
    try:
        result = list_all_chunks(doc_id.strip())
        return ChunkListResponse(**result)
    except RAGDocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取 chunks 失败：{exc}") from exc


@router.get("/api/images/{doc_id}/{filename}")
def serve_image(doc_id: str, filename: str):
    """提供从文档中提取的图片。"""
    from pathlib import Path as _Path
    from fastapi.responses import FileResponse

    image_path = _Path(__file__).resolve().parents[3] / "data" / "images" / doc_id / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(str(image_path))


@router.post("/api/synthesize-qa")
def synthesize_qa(payload: dict = Body(...)):
    import json
    import re

    from backend.app.services.organizer.model_client import LLMClient

    chunks = payload.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="chunks 不能为空")

    settings = get_model_settings()
    llm = LLMClient(
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
        model=settings["LLM_MODEL"],
    )
    if not llm.is_available:
        raise HTTPException(status_code=400, detail="请先在设置页配置 OPENAI_API_KEY")

    evaluator_name = settings.get("QA_QUALITY_EVALUATOR")
    evaluator = get_qa_quality_evaluator(evaluator_name)

    _system = (
        "你是问答对生成器。根据文档片段生成1-2个问答对。"
        "严格输出 JSON 数组：[{\"question\":\"...\",\"answer\":\"...\"}]"
    )

    qa_pairs = []
    for chunk in chunks:
        content = (chunk.get("content") or "")[:2000].strip()
        if not content:
            continue
        title = " > ".join(chunk.get("title_path") or []) or "未分类"

        raw = llm.generate(
            prompt=f"标题：{title}\n\n内容：{content}",
            system_prompt=_system,
            temperature=0.7,
            max_tokens=512,
        )
        if not raw:
            continue

        # 解析 LLM 返回的 JSON
        raw = raw.strip()
        # 去掉可能的 markdown 代码块包裹
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("\n", 1)[0]

        try:
            pairs = json.loads(raw)
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组部分
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if not m:
                continue
            try:
                pairs = json.loads(m.group())
            except json.JSONDecodeError:
                continue

        if not isinstance(pairs, list):
            continue

        for pair in pairs:
            question = (pair.get("question") or "").strip()
            answer = (pair.get("answer") or "").strip()
            if not question or not answer:
                continue

            quality = evaluator.evaluate(question=question, answer=answer, content=content)

            qa_pairs.append({
                "id": f"qa_{len(qa_pairs) + 1:04d}",
                "question": question,
                "answer": answer,
                "source_chunk_id": chunk.get("chunk_id", ""),
                "title_path": chunk.get("title_path", []),
                "answerable": quality.answerable,
                "answerable_score": quality.answerable_score,
                "faithful": quality.faithful,
                "faithful_score": quality.faithful_score,
                "quality_score": quality.quality_score,
            })

    return {"qa_pairs": qa_pairs, "total": len(qa_pairs)}


def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"
