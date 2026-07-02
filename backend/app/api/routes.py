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
    EvaluateRequest,
    EvaluateResponse,
    ModelSettingsPayload,
    ModelSettingsResponse,
    OrganizeChunkInput,
    OrganizeRequest,
    OrganizeResponse,
    QueryRequest,
    QueryResponse,
    SegmentUploadResponse,
    StrategiesResponse,
    StrategyInfo,
    StrategyMetrics,
)
from backend.app.services.document_loader import DocumentLoaderError
from backend.app.core.model_settings import get_model_settings, update_model_settings
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


# ── /strategies ──────────────────────────────────────────


@router.get("/api/strategies", response_model=StrategiesResponse)
def list_strategies() -> StrategiesResponse:
    """列出可用的分段策略、关键词策略和默认配置。"""
    from backend.app.services.segmenting import SegmentConfig

    config = SegmentConfig()
    return StrategiesResponse(
        segmentation_strategies=[
            StrategyInfo(
                name="smart",
                label="Smart (heading+semantic+protect+overlap)",
                description="标题感知 + 语义边界 + 特殊块保护 + 上下文重叠，最终智能策略",
            ),
            StrategyInfo(
                name="heading",
                label="Heading-based (heading+length only)",
                description="仅标题边界 + 长度控制，不做语义检测和重叠，验证结构信息价值",
            ),
            StrategyInfo(
                name="fixed",
                label="Fixed-length (512-char uniform)",
                description="固定 512 字符均匀切分，无结构感知，作为基线对照",
            ),
        ],
        keyword_strategies=list(list_keyword_strategies()),
        default_config={
            "min_chars": config.min_chars,
            "target_chars": config.target_chars,
            "max_chars": config.max_chars,
            "overlap_sentences": config.overlap_sentences,
            "enable_semantic_boundary": config.enable_semantic_boundary,
            "semantic_boundary_threshold": config.semantic_boundary_threshold,
            "keyword_strategy": config.keyword_strategy,
        },
    )


# ── /organize ────────────────────────────────────────────


@router.post("/api/organize", response_model=OrganizeResponse)
def organize_chunks(payload: OrganizeRequest) -> OrganizeResponse:
    """对已有 chunks 独立执行内容组织（标签、摘要、实体）。"""
    from backend.app.services.organizer.organizer import ContentOrganizer

    if not payload.chunks:
        raise HTTPException(status_code=400, detail="chunks 不能为空")

    organizer = ContentOrganizer()
    chunk_dicts = [{"chunk_id": c.chunk_id, "content": c.content} for c in payload.chunks]
    results, doc_summary = organizer.organize_batch(chunk_dicts, doc_id=payload.doc_id)

    organized = []
    for inp, res in zip(payload.chunks, results):
        organized.append({
            "chunk_id": inp.chunk_id,
            "tags": res.tags,
            "summary": res.summary,
            "entity_labels": res.entity_labels,
        })

    return OrganizeResponse(
        doc_id=payload.doc_id,
        doc_summary=doc_summary,
        chunks=organized,
    )


# ── /evaluate ────────────────────────────────────────────


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@router.post("/api/evaluate", response_model=EvaluateResponse)
def evaluate_document(payload: EvaluateRequest) -> EvaluateResponse:
    """对已上传的文档运行三策略对比评测，返回检索指标。"""
    from backend.app.services.evaluation import (
        EmbeddingRelevance,
        compute_ir_metrics,
        fixed_length_segment,
        heading_based_segment,
    )
    from backend.app.services.rag_store.sqlite_store import get_chunks_by_doc, get_document
    from backend.app.services.retrieval import EmbeddingStore
    from backend.app.services.segmenting import SegmentConfig, segment_text

    # 验证文档存在且就绪
    doc = get_document(payload.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{payload.doc_id}")
    if doc["status"] != "ready":
        raise HTTPException(status_code=409, detail=f"文档未就绪，当前状态：{doc['status']}")

    doc_id = payload.doc_id

    # 从已存储的 chunks 重建原始文本
    stored_chunks = get_chunks_by_doc(doc_id)
    if not stored_chunks:
        raise HTTPException(status_code=404, detail="该文档没有已分段的 chunks")

    raw_text = "\n\n".join(c.get("content", "") for c in stored_chunks)

    config = SegmentConfig()
    store = EmbeddingStore()
    judge = EmbeddingRelevance(threshold=0.45)

    # 三种策略分段
    smart_result = segment_text(raw_text, doc_id=doc_id, config=config)
    smart_chunks = smart_result["chunks"]

    heading_objs = heading_based_segment(
        raw_text, doc_id=f"{doc_id}_heading",
        min_chars=config.min_chars, target_chars=config.target_chars,
        max_chars=config.max_chars,
    )
    heading_chunks = [
        {"chunk_id": c.chunk_id, "content": c.content, "title_path": c.title_path,
         "chunk_type": c.chunk_type, "char_count": c.char_count,
         "source_refs": c.source_refs, "quality_flags": c.quality_flags}
        for c in heading_objs
    ]

    fixed_objs = fixed_length_segment(raw_text, doc_id=f"{doc_id}_fixed")
    fixed_chunks = [
        {"chunk_id": c.chunk_id, "content": c.content, "title_path": c.title_path,
         "chunk_type": c.chunk_type, "char_count": c.char_count,
         "source_refs": c.source_refs, "quality_flags": c.quality_flags}
        for c in fixed_objs
    ]

    all_strategies = [
        ("smart", smart_chunks),
        ("heading", heading_chunks),
        ("fixed", fixed_chunks),
    ]

    # 评测查询 — 基于文档内容生成
    first_content = stored_chunks[0].get("content", "") if stored_chunks else ""
    test_queries = [
        "本文档的主要内容是什么？",
        "文档中提到了哪些关键数据或指标？",
        "文档的核心结论或要点是什么？",
    ]

    strategy_results: list[dict] = []
    for strategy_name, chunks in all_strategies:
        store.add_chunks(f"{doc_id}_{strategy_name}", chunks)

        metrics_accum: dict[str, list[float]] = {
            "recall@1": [], "recall@3": [], "recall@5": [],
            "precision@5": [], "ndcg@5": [], "mrr": [],
        }

        for query in test_queries:
            ref_text = chunks[0]["content"][:500] if chunks else query
            judge.set_reference(ref_text, [])
            hits = store.search(f"{doc_id}_{strategy_name}", query, top_k=payload.top_k)
            m = compute_ir_metrics(hits, judge, all_chunks=chunks)
            for key in metrics_accum:
                metrics_accum[key].append(m.get(key, 0.0))

        avg_chunk_size = sum(c.get("char_count", 0) for c in chunks) / max(1, len(chunks))
        strategy_results.append({
            "strategy": strategy_name,
            "chunk_count": len(chunks),
            "avg_chunk_size": round(avg_chunk_size, 1),
            "recall_at_1": round(_avg(metrics_accum["recall@1"]), 4),
            "recall_at_3": round(_avg(metrics_accum["recall@3"]), 4),
            "recall_at_5": round(_avg(metrics_accum["recall@5"]), 4),
            "precision_at_5": round(_avg(metrics_accum["precision@5"]), 4),
            "ndcg_at_5": round(_avg(metrics_accum["ndcg@5"]), 4),
            "mrr": round(_avg(metrics_accum["mrr"]), 4),
        })

    return EvaluateResponse(
        doc_id=doc_id,
        top_k=payload.top_k,
        strategies=strategy_results,
    )


def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"
