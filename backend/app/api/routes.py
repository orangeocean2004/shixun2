from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Query, UploadFile
from torch.distributed._shard.sharded_tensor import logger

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

router = APIRouter()


def _generate_qa_fallback(chunks: list[dict], max_pairs: int = 10) -> list[dict]:
    """Generate simple QA pairs from chunk content without LLM.

    Extracts first key sentence from each chunk as the answer and creates a
    question from the title path. Used when no LLM API key is configured.
    """
    import re as _re

    qa_pairs = []
    sentence_pat = _re.compile(r"[^。！？.!?\n]+[。！？.!?]")

    for chunk in chunks[:max(max_pairs, 1) + 2]:
        content = (chunk.get("content") or "").strip()
        if not content:
            continue

        title_path = chunk.get("title_path") or []
        title = " > ".join(title_path) if title_path else ""

        # Extract first meaningful sentence as answer
        sentences = sentence_pat.findall(content)
        answer = ""
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean) >= 10:
                answer = s_clean
                break
        if not answer:
            answer = content[:200].strip()

        terms = _extract_fallback_question_terms(answer or content)
        topic = "、".join(terms[:4])

        # Build a retrievable question. Generic questions such as
        # "这段内容的关键信息是什么" do not contain enough lexical signal for
        # automatic retrieval evaluation.
        if title and topic:
            question = f"{title}部分关于{topic}的核心内容是什么？"
        elif topic:
            question = f"文档中关于{topic}的内容是什么？"
        elif title:
            question = f"{title}部分的核心内容是什么？"
        else:
            question = f"这段内容的关键信息是什么？"

        qa_pairs.append({
            "question": question,
            "answer": answer,
            "chunk_id": chunk.get("chunk_id", ""),
        })

        if len(qa_pairs) >= max(max_pairs, 1):
            break

    return qa_pairs



def _extract_fallback_question_terms(text: str) -> list[str]:
    import re as _re

    stopwords = {
        "本文", "文档", "内容", "部分", "核心", "主要", "进行", "通过",
        "以及", "可以", "需要", "实现", "支持", "相关", "一个", "一种",
        "如何", "什么", "其中", "使用", "用于", "要求",
    }
    terms: list[str] = []

    for term in (
        "RAG", "智能分段", "内容组织", "语义感知", "结构感知",
        "检索评测", "Recall", "nDCG", "MRR", "FastAPI", "Vue",
    ):
        if term.lower() in (text or "").lower() and term not in terms:
            terms.append(term)

    try:
        import jieba
        candidates = jieba.lcut(text or "")
    except Exception:
        candidates = _re.findall(r"[A-Za-z][A-Za-z0-9_@.+-]{1,}|[\u4e00-\u9fff]{2,6}", text or "")

    for raw in candidates:
        term = raw.strip(" ，。！？；：、()（）[]【】《》\"'")
        if not term or term in stopwords:
            continue
        if _re.fullmatch(r"[\u4e00-\u9fff]", term):
            continue
        if len(term) >= 2 and term not in terms:
            terms.append(term)
        if len(terms) >= 6:
            break
    return terms


def _prepare_qa_pairs_for_storage(qa_pairs: list[dict], source: str) -> list[dict]:
    prepared: list[dict] = []
    for pair in qa_pairs:
        item = dict(pair)
        item["chunk_id"] = item.get("chunk_id") or item.get("source_chunk_id") or ""
        item["source"] = source
        prepared.append(item)
    return prepared


def _ensure_fallback_qa_pairs(doc_id: str, chunks: list[dict]) -> list[dict]:
    from backend.app.services.rag_store.sqlite_store import get_qa_pairs_by_doc, upsert_qa_pairs

    stored_pairs = get_qa_pairs_by_doc(doc_id)
    if stored_pairs:
        if any(pair.get("source") != "fallback" for pair in stored_pairs):
            return stored_pairs
        if any("关于" in (pair.get("question") or "") for pair in stored_pairs):
            return stored_pairs

    qa_pairs = _prepare_qa_pairs_for_storage(_generate_qa_fallback(chunks), "fallback")
    if qa_pairs:
        upsert_qa_pairs(doc_id, qa_pairs, replace=bool(stored_pairs))
    return qa_pairs


def _generate_qa_for_chunks(chunks: list[dict]) -> list[dict]:
    """Use LLM to generate QA pairs from chunks for evaluation.

    Returns list of {'question': str, 'answer': str} dicts.
    """
    try:
        from backend.app.services.organizer.model_client import LLMClient
        from backend.app.core.model_settings import get_model_settings

        settings = get_model_settings()
        llm = LLMClient(
            api_key=settings["OPENAI_API_KEY"],
            base_url=settings["OPENAI_BASE_URL"],
            model=settings["LLM_MODEL"],
        )
        if not llm.is_available:
            return _generate_qa_fallback(chunks)

        qa_pairs = []
        system_prompt = (
            "你是问答对生成器。根据文档片段生成1-2个问答对。"
            "严格输出 JSON 数组：[{\"question\":\"...\",\"answer\":\"...\"}]"
        )

        for chunk in chunks[:5]:  # Limit to first 5 chunks for speed
            content = (chunk.get("content") or "")[:1000].strip()
            if not content:
                continue
            title = " > ".join(chunk.get("title_path") or []) or ""
            prompt = f"标题：{title}\n\n内容：{content}" if title else content

            raw = llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=200,
            )
            if not raw:
                continue

            # Parse JSON from LLM output
            import json as _json
            import re as _re
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw.rsplit("\n", 1)[0]
            try:
                pairs = _json.loads(raw)
            except _json.JSONDecodeError:
                m = _re.search(r"\[.*\]", raw, re.DOTALL)
                if not m:
                    continue
                try:
                    pairs = _json.loads(m.group())
                except _json.JSONDecodeError:
                    continue
            if not isinstance(pairs, list):
                continue

            chunk_id = chunk.get("chunk_id") or ""
            for pair in pairs:
                q = (pair.get("question") or "").strip()
                a = (pair.get("answer") or "").strip()
                if q and a:
                    qa_pairs.append({"question": q, "answer": a, "chunk_id": chunk_id})

            if len(qa_pairs) >= 8:  # Target ~8 QA pairs for quick eval
                break

        return qa_pairs[:10]
    except Exception:
        import logging
        logging.getLogger(__name__).warning("QA generation failed", exc_info=True)
        return []


# In-memory cache for background evaluation results
_eval_cache: dict[str, dict] = {}


def _enrich_chunks_with_llm(chunks: list[dict]) -> None:
    """Enrich chunks with LLM-generated tags and summaries (batched, synchronous)."""
    from backend.app.core.model_settings import get_model_settings
    from backend.app.services.organizer.model_client import LLMClient
    from backend.app.services.organizer.organizer import ContentOrganizer

    settings = get_model_settings()
    llm = LLMClient(
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
        model=settings["LLM_MODEL"],
    )
    if not llm.is_available:
        return

    organizer = ContentOrganizer(llm_client=llm)
    results, _doc_summary = organizer.organize_batch_fast(chunks)

    for chunk, result in zip(chunks, results):
        if result.tags:
            chunk["label"] = result.tags
        if result.summary:
            chunk["summary"] = result.summary


def _background_qa_evaluate(doc_id: str, chunks: list[dict]) -> None:
    """Run QA generation + evaluation in background. Persist QA pairs to SQLite.

    Uses fallback QA generation (no LLM) for speed and reliability.
    LLM-based QA is available via the /api/synthesize-qa endpoint (QA 合成 tab).
    """
    try:
        print(f"[Eval] Starting for doc_id={doc_id}, chunks={len(chunks)}")
        qa_pairs = _ensure_fallback_qa_pairs(doc_id, chunks)
        print(f"[Eval] Using {len(qa_pairs)} QA pairs")
        if not qa_pairs:
            print(f"[Eval] No QA pairs, aborting")
            return

        # ── Evaluate FIRST (fast, no DB dependency) ──
        raw_text = "\n\n".join(c.get("content", "") for c in chunks)
        from backend.app.services.evaluation.evaluator import evaluate_with_qa_pairs
        print(f"[Eval] Running evaluation...")
        evaluation_raw = evaluate_with_qa_pairs(raw_text, qa_pairs)
        print(f"[Eval] Done: {evaluation_raw is not None}, keys={list(evaluation_raw.keys()) if evaluation_raw else 'NONE'}")
        if evaluation_raw:
            _eval_cache[doc_id] = evaluation_raw
            print(f"[Eval] CACHED for {doc_id}")
        else:
            print(f"[Eval] evaluate_with_qa_pairs returned None!")

    except Exception:
        import traceback
        print(f"[Eval] CRASHED:")
        traceback.print_exc()


def _background_longbench_finalize(
    doc_id: str,
    file_name: str,
    file_size: int,
    file_sha256: str,
    all_chunks: list[dict],
    sample_doc_ids: list[str],
    seg_result: dict,
    payload: bytes,
) -> None:
    """Background: ChromaDB storage + LongBench evaluation for JSONL uploads.

    Segmentation already ran synchronously; this handles the slow parts
    (ChromaDB vector upsert, three-strategy evaluation) without blocking
    the HTTP response.
    """
    import logging
    logger = logging.getLogger(__name__)

    # ── 1. Store document record ──
    try:
        from backend.app.services.rag_store.sqlite_store import (
            upsert_document_processing,
            mark_document_ready,
        )
        upsert_document_processing(
            doc_id=doc_id,
            file_name=file_name,
            file_sha256=file_sha256,
            file_size=file_size,
            block_count=0,
        )
    except Exception:
        logger.warning("LongBench background: document record failed", exc_info=True)
        return

    # ── 2. ChromaDB vector storage ──
    try:
        from backend.app.services.rag_store.sqlite_store import replace_chunks
        from backend.app.services.rag_store.chroma_store import (
            delete_document_vectors,
            upsert_chunks,
        )

        replace_chunks(doc_id, all_chunks)
        for did in sample_doc_ids:
            try:
                delete_document_vectors(did)
            except Exception:
                pass
        upsert_chunks(doc_id, all_chunks)
    except Exception:
        logger.warning("LongBench background: ChromaDB failed", exc_info=True)

    # ── 3. Mark document ready ──
    try:
        from backend.app.services.rag_store.sqlite_store import mark_document_ready as _mark_ready
        _mark_ready(
            doc_id=doc_id,
            chunk_count=len(all_chunks),
            strategy=seg_result.get("strategy", {}),
            statistics=seg_result.get("statistics", {}),
            preprocess={},
        )
    except Exception:
        logger.warning("LongBench background: mark ready failed", exc_info=True)

    # ── 4. Generate QA pairs + persist to SQLite ──
    try:
        from backend.app.services.rag_store.sqlite_store import get_qa_pairs_by_doc, upsert_qa_pairs
        qa_pairs = get_qa_pairs_by_doc(doc_id)
        if not qa_pairs:
            qa_pairs = _prepare_qa_pairs_for_storage(_generate_qa_for_chunks(all_chunks), "llm")
            if not qa_pairs:
                qa_pairs = _prepare_qa_pairs_for_storage(_generate_qa_fallback(all_chunks), "fallback")
            if qa_pairs:
                upsert_qa_pairs(doc_id, qa_pairs, replace=False)
    except Exception:
        logger.warning("LongBench background: QA pairs failed", exc_info=True)

    # ── 5. Run LongBench evaluation ──
    try:
        from backend.app.services.evaluation.evaluator import evaluate_longbench
        evaluation_raw = evaluate_longbench(payload, max_samples=30)
        if evaluation_raw:
            _eval_cache[doc_id] = evaluation_raw
    except Exception:
        logger.warning("LongBench background: evaluation failed", exc_info=True)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/settings/model", response_model=ModelSettingsResponse)
def get_model_settings_api() -> ModelSettingsResponse:
    try:
        return ModelSettingsResponse(**get_model_settings())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"获取模型设置失败：{exc}") from exc


@router.put("/api/settings/model", response_model=ModelSettingsResponse)
def update_model_settings_api(payload: ModelSettingsPayload) -> ModelSettingsResponse:
    try:
        saved = update_model_settings(payload.model_dump(exclude_unset=True, exclude_none=True))
        return ModelSettingsResponse(**saved)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存模型设置失败：{exc}") from exc


@router.post("/api/segment/upload", response_model=SegmentUploadResponse)
async def upload_and_segment(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
    min_chars: int = Form(DEFAULT_MIN_CHARS),
    target_chars: int = Form(DEFAULT_TARGET_CHARS),
    max_chars: int = Form(DEFAULT_MAX_CHARS),
    overlap_sentences: int = Form(DEFAULT_OVERLAP_SENTENCES),
) -> SegmentUploadResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"[ROUTE] 暂不支持的文件类型：{suffix or '无后缀'}")

    if min_chars <= 0 or target_chars <= 0 or max_chars <= 0 or overlap_sentences < 0:
        raise HTTPException(status_code=400, detail="分段参数必须为正数，且 overlap_sentences 不能小于 0")
    if not (min_chars <= target_chars <= max_chars):
        raise HTTPException(status_code=400, detail="分段参数需满足 min_chars <= target_chars <= max_chars")

    try:
        payload = await file.read()
        result_doc_id = doc_id.strip() if doc_id and doc_id.strip() else safe_doc_id(Path(filename).stem)

        # ── Detect LongBench JSONL ──────────────────────────
        from backend.app.services.evaluation.evaluator import (
            evaluate_longbench,
            evaluate_with_qa_pairs,
            is_longbench_jsonl,
        )

        is_longbench = suffix == ".jsonl" and is_longbench_jsonl(payload)

        if is_longbench:
            # LongBench mode: segment ALL samples synchronously (for full
            # frontend display), defer ChromaDB + evaluation to background.
            import json as _json
            from backend.app.services.segmenting import segment_text
            import hashlib as _hashlib

            samples_raw = payload.decode("utf-8").strip().split("\n")
            all_samples: list[dict] = []
            for line in samples_raw:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    if obj.get("context") and obj.get("input") and obj.get("answers"):
                        all_samples.append(obj)
                except _json.JSONDecodeError:
                    continue

            if not all_samples:
                raise HTTPException(status_code=400, detail="LongBench JSONL 中没有有效的样本")

            first_context = all_samples[0].get("context", "") if all_samples else ""

            # ── Segment ALL samples synchronously ──────────────
            seg_result = segment_text(
                first_context,
                doc_id=result_doc_id,
                config=None,
            )
            all_chunks: list[dict] = list(seg_result["chunks"])
            sample_doc_ids = [result_doc_id]
            total_chars = sum(int(c.get("char_count", 0)) for c in seg_result["chunks"])
            total_segmented = 1

            for i, sample in enumerate(all_samples):
                if i == 0:
                    continue
                sample_ctx = sample.get("context", "")
                if not sample_ctx.strip():
                    continue
                sid = f"{result_doc_id}_{i}"
                sample_doc_ids.append(sid)
                try:
                    sr = segment_text(sample_ctx, doc_id=sid, config=None)
                    all_chunks.extend(sr["chunks"])
                    total_chars += sum(int(c.get("char_count", 0)) for c in sr["chunks"])
                    total_segmented += 1
                except Exception as exc:
                    raise HTTPException(status_code=500, detail=f"LongBench 样本分段失败（doc_id={sid}）: {exc}") from exc

            # ── Aggregate statistics across all samples ────────
            agg_statistics = dict(seg_result.get("statistics", {}))
            agg_statistics["total_chunks"] = len(all_chunks)
            agg_statistics["total_chars"] = total_chars
            agg_statistics["avg_chunk_size"] = round(total_chars / len(all_chunks), 1) if all_chunks else 0
            agg_statistics["samples_segmented"] = total_segmented
            agg_statistics["total_samples"] = len(all_samples)

            result = {
                "doc_id": result_doc_id,
                "file_name": filename,
                "file_size": len(payload),
                "block_count": 0,
                "chunks": all_chunks,  # return ALL chunks for frontend display
                "statistics": agg_statistics,
                "strategy": seg_result["strategy"],
            }

            # ── Defer ChromaDB + evaluation to background ─────
            _file_sha256 = _hashlib.sha256(payload).hexdigest()
            evaluation_raw = None
            background_tasks.add_task(
                _background_longbench_finalize,
                doc_id=result_doc_id,
                file_name=filename,
                file_size=len(payload),
                file_sha256=_file_sha256,
                all_chunks=all_chunks,
                sample_doc_ids=sample_doc_ids,
                seg_result=seg_result,
                payload=payload,
            )
        else:
            # Regular mode: normal ingestion
            print(f"[Upload] Regular file upload: {filename}")
            result = ingest_document(
                file_name=filename,
                payload=payload,
                doc_id=result_doc_id,
                min_chars=min_chars,
                target_chars=target_chars,
                max_chars=max_chars,
                overlap_sentences=overlap_sentences,
            )

            # ── Run evaluation using persisted QA pairs; create fallback QA only when absent ──
            evaluation_raw = None
            try:
                qa_pairs = _ensure_fallback_qa_pairs(result_doc_id, result["chunks"])
                print(f"[EvalSync] Using {len(qa_pairs)} QA pairs for {result_doc_id}")
                if qa_pairs:
                    raw_text = "\n\n".join(c.get("content", "") for c in result["chunks"])
                    from backend.app.services.evaluation.evaluator import evaluate_with_qa_pairs
                    evaluation_raw = evaluate_with_qa_pairs(raw_text, qa_pairs)
                    print(f"[EvalSync] Evaluation done: {list(evaluation_raw.keys()) if evaluation_raw else 'NONE'}")
            except Exception as e:
                import traceback
                print(f"[EvalSync] FAILED: {e}")
                traceback.print_exc()

            # 富化已在 ingest_document 内部同步完成

        # ── Convert evaluation to Pydantic ──────────────────
        evaluation = None
        if evaluation_raw:
            try:
                from backend.app.models.schemas import EvalQuestionHit, EvalResult, EvalStrategyResult
                evaluation = EvalResult(
                    mode=evaluation_raw.get("mode", ""),
                    processed=evaluation_raw.get("processed", 0),
                    strategies=[
                        EvalStrategyResult(**s)
                        for s in evaluation_raw.get("strategies", [])
                    ],
                    question_results=[
                        EvalQuestionHit(**qr)
                        for qr in evaluation_raw.get("question_results", [])
                    ],
                    total_gain=evaluation_raw.get("total_gain", 0.0),
                    structure_gain=evaluation_raw.get("structure_gain", 0.0),
                    semantic_gain=evaluation_raw.get("semantic_gain", 0.0),
                )
            except Exception:
                import traceback
                print(f"[EvalSync] Pydantic conversion FAILED:")
                traceback.print_exc()

        print(f"[EvalSync] Final evaluation={evaluation is not None}")
        return SegmentUploadResponse(
            doc_id=result["doc_id"],
            file_name=result["file_name"],
            file_size=result["file_size"],
            block_count=result["block_count"],
            total_chars=result.get("total_chars", 0),
            chunks=result["chunks"],
            statistics=result["statistics"],
            strategy=result["strategy"],
            evaluation=evaluation,
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


def _find_best_qa_match(question: str, qa_pairs: list[dict], threshold: float = 0.70) -> dict | None:
    """Use embedding similarity to find the best-matching QA pair for a question.

    Returns the matched QA pair dict with an extra 'similarity' key, or None if
    no pair exceeds *threshold*.
    """
    if not qa_pairs:
        return None

    try:
        from backend.app.services.retrieval.embedding import embedding_similarity
    except ImportError:
        return None

    best_pair: dict | None = None
    best_similarity = 0.0

    for pair in qa_pairs:
        stored_q = pair.get("question", "").strip()
        if not stored_q:
            continue
        sim = embedding_similarity(question, stored_q)
        if sim is not None and sim > best_similarity:
            best_similarity = sim
            best_pair = pair

    if best_pair and best_similarity >= threshold:
        result = dict(best_pair)
        result["similarity"] = round(best_similarity, 4)
        return result
    return None


def _check_answer_coverage(chunks: list[dict], answer: str) -> bool:
    """Return True if *answer* appears (normalized) inside the retrieved chunks."""
    if not answer or not answer.strip():
        return False

    # Normalize: keep only alphanumeric + CJK characters
    def _norm(text: str) -> str:
        result: list[str] = []
        for ch in text:
            if ch.isalnum() or ("一" <= ch <= "鿿"):
                result.append(ch)
        return "".join(result).lower()

    norm_answer = _norm(answer)
    if len(norm_answer) < 2:
        return False

    combined = "\n".join(c.get("content", "") for c in chunks)
    return norm_answer in _norm(combined)


@router.post("/api/query", response_model=QueryResponse)
def query_retrieved_chunks(payload: QueryRequest) -> QueryResponse:
    try:
        from backend.app.models.schemas import QAMatch

        top_k = payload.top_k if payload.top_k > 0 else DEFAULT_RETRIEVE_TOP_K

        # ── Step 1: Try to match against stored QA pairs ──
        matched_qa: QAMatch | None = None
        if payload.doc_id:
            try:
                from backend.app.services.rag_store.sqlite_store import get_qa_pairs_by_doc

                stored_pairs = get_qa_pairs_by_doc(payload.doc_id)
                match = _find_best_qa_match(payload.question, stored_pairs)
                if match:
                    matched_qa = QAMatch(
                        question=match["question"],
                        answer=match["answer"],
                        chunk_id=match.get("chunk_id", ""),
                        similarity=match.get("similarity", 0.0),
                    )
            except ImportError as exc:
                raise HTTPException(status_code=500, detail=f"加载 QA 存储模块失败：{exc}") from exc

        # ── Step 2: Retrieve chunks (always needed for context) ──
        retrieve_kwargs = {"question": payload.question, "top_k": top_k}
        if payload.doc_id:
            retrieve_kwargs["doc_id"] = payload.doc_id
        result = retrieve_chunks(**retrieve_kwargs)
        result_chunks: list[dict] = result.get("chunks", [])

        # ── Step 3: Determine answer ──
        answer = ""
        answer_covered: bool | None = None

        if matched_qa:
            # Use the stored QA answer directly — it was generated from the source chunk
            answer = matched_qa.answer
            answer_covered = _check_answer_coverage(result_chunks, matched_qa.answer)
        else:
            # No QA match — fall back to LLM generation from retrieved chunks
            try:
                from backend.app.services.organizer.model_client import LLMClient

                settings = get_model_settings()
                llm = LLMClient(
                    api_key=settings["OPENAI_API_KEY"],
                    base_url=settings["OPENAI_BASE_URL"],
                    model=settings["LLM_MODEL"],
                )
                if llm.is_available and result_chunks:
                    context_parts: list[str] = []
                    for c in result_chunks:
                        title = " > ".join(c.get("title_path", [])) or "无标题"
                        context_parts.append(f"[{title}]\n{c.get('content', '')[:800]}")
                    context = "\n\n---\n\n".join(context_parts)

                    answer = llm.generate(
                        "根据以下文档片段回答问题。如果片段中没有足够信息，请如实说明。\n\n"
                        f"文档片段：\n{context}\n\n"
                        f"问题：{payload.question}\n\n"
                        f"回答：",
                        system_prompt="你是基于文档的问答助手。只根据提供的文档片段回答，不添加外部知识。",
                        temperature=0.3,
                        max_tokens=512,
                    ).strip()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"LLM 生成答案失败：{exc}") from exc

        return QueryResponse(
            question=payload.question,
            top_k=top_k or DEFAULT_RETRIEVE_TOP_K,
            answer=answer,
            chunks=result_chunks,
            matched_qa=matched_qa,
            answer_covered=answer_covered,
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
    doc_id = (payload.get("doc_id") or "").strip()
    save_mode = payload.get("save_mode") or "replace"
    if save_mode not in ["replace", "append"]:
        raise HTTPException(status_code=400, detail="save_mode 只能是 replace 或 append")
    if not chunks:
        raise HTTPException(status_code=400, detail="chunks 不能为空")

    try:
        qa_count = int(payload.get("qa_count") or 10)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="qa_count 必须是整数")
    if qa_count <= 0:
        raise HTTPException(status_code=400, detail="qa_count 必须大于 0")
    if qa_count > 100:
        raise HTTPException(status_code=400, detail="qa_count 不能超过 100")

    settings = get_model_settings()
    llm = LLMClient(
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
        model=settings["LLM_MODEL"],
    )
    if not llm.is_available:
        raise HTTPException(status_code=400, detail="请先在设置页配置 OPENAI_API_KEY")

    evaluator_name = settings.get("QA_QUALITY_EVALUATOR")
    evaluator = get_qa_quality_evaluator(evaluator_name, llm)

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
                "source": "llm",
                "source_chunk_id": chunk.get("chunk_id", ""),
                "title_path": chunk.get("title_path", []),
                "answerable": quality.answerable,
                "answerable_score": quality.answerable_score,
                "faithful": quality.faithful,
                "faithful_score": quality.faithful_score,
                "quality_score": quality.quality_score,
            })
            if len(qa_pairs) >= qa_count:
                break

        if len(qa_pairs) >= qa_count:
            break


    if not qa_pairs:
        qa_pairs = _prepare_qa_pairs_for_storage(_generate_qa_fallback(chunks, max_pairs=qa_count), "fallback")

    saved = 0
    evaluation_raw = None
    prepared_pairs = _prepare_qa_pairs_for_storage(
        qa_pairs,
        "llm" if any((pair.get("source") == "llm") for pair in qa_pairs) else "fallback",
    )
    eval_pairs = prepared_pairs

    if doc_id and prepared_pairs:
        from backend.app.services.rag_store.sqlite_store import get_qa_pairs_by_doc, upsert_qa_pairs

        try:
            saved = upsert_qa_pairs(
                doc_id,
                prepared_pairs,
                replace=(save_mode == "replace"),
            )
            stored_pairs = get_qa_pairs_by_doc(doc_id)
            if stored_pairs:
                eval_pairs = stored_pairs
        except Exception:
            import logging
            logging.getLogger(__name__).warning("QA pair persistence failed; evaluating in-memory pairs", exc_info=True)

    if eval_pairs:
        try:
            from backend.app.services.evaluation.evaluator import evaluate_with_qa_pairs

            raw_text = "\n\n".join(chunk.get("content", "") for chunk in chunks)
            evaluation_raw = evaluate_with_qa_pairs(raw_text, eval_pairs)
            if doc_id and evaluation_raw:
                _eval_cache[doc_id] = evaluation_raw
        except Exception:
            import logging
            logging.getLogger(__name__).warning("QA synthesis evaluation refresh failed", exc_info=True)
    return {
        "qa_pairs": qa_pairs,
        "total": len(qa_pairs),
        "saved": saved,
        "save_mode": save_mode if doc_id else "",
        "evaluation": evaluation_raw,
    }


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
        default_config={
            "min_chars": config.min_chars,
            "target_chars": config.target_chars,
            "max_chars": config.max_chars,
            "overlap_sentences": config.overlap_sentences,
            "enable_semantic_boundary": config.enable_semantic_boundary,
            "semantic_boundary_threshold": config.semantic_boundary_threshold,
        },
    )


# ── /organize ────────────────────────────────────────────


@router.post("/api/organize", response_model=OrganizeResponse)
def organize_chunks(payload: OrganizeRequest) -> OrganizeResponse:
    """对已有 chunks 独立执行内容组织（标签、摘要、实体）。"""
    from backend.app.services.organizer.model_client import LLMClient
    from backend.app.services.organizer.organizer import ContentOrganizer

    if not payload.chunks:
        raise HTTPException(status_code=400, detail="chunks 不能为空")

    settings = get_model_settings()
    llm = LLMClient(
        model=settings["LLM_MODEL"],
        api_key=settings["OPENAI_API_KEY"],
        base_url=settings["OPENAI_BASE_URL"],
    )
    organizer = ContentOrganizer(llm_client=llm)
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


@router.post("/api/evaluate", response_model=EvaluateResponse)
def evaluate_document(payload: EvaluateRequest) -> EvaluateResponse:
    """对已上传的文档运行三策略对比评测，返回检索指标。"""
    from backend.app.services.rag_store.sqlite_store import get_chunks_by_doc, get_document
    from backend.app.services.evaluation.evaluator import evaluate_with_qa_pairs

    doc = get_document(payload.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{payload.doc_id}")
    if doc["status"] != "ready":
        raise HTTPException(status_code=409, detail=f"文档未就绪，当前状态：{doc['status']}")

    doc_id = payload.doc_id
    stored_chunks = get_chunks_by_doc(doc_id)
    if not stored_chunks:
        raise HTTPException(status_code=404, detail="该文档没有已分段的 chunks")

    raw_text = "\n\n".join(c.get("content", "") for c in stored_chunks)
    stored_qa_pairs = _ensure_fallback_qa_pairs(doc_id, stored_chunks)
    if not stored_qa_pairs:
        raise HTTPException(status_code=400, detail="该文档没有可用的 QA 评测样本")

    evaluation_raw = evaluate_with_qa_pairs(raw_text, stored_qa_pairs)
    if evaluation_raw.get("error"):
        raise HTTPException(status_code=500, detail=evaluation_raw["error"])

    strategy_results = []
    for item in evaluation_raw.get("strategies", []):
        strategy_results.append({
            "strategy": item.get("strategy", ""),
            "chunk_count": item.get("chunk_count", 0),
            "avg_chunk_size": item.get("avg_chunk_size", 0.0),
            "recall_at_1": round(item.get("recall_at_1", 0.0), 4),
            "recall_at_3": round(item.get("recall_at_3", 0.0), 4),
            "recall_at_5": round(item.get("recall_at_5", 0.0), 4),
            "precision_at_5": round(item.get("precision_at_5", 0.0), 4),
            "ndcg_at_5": round(item.get("ndcg_at_5", 0.0), 4),
            "mrr": round(item.get("mrr", 0.0), 4),
        })

    return EvaluateResponse(
        doc_id=doc_id,
        top_k=payload.top_k,
        strategies=strategy_results,
    )

def safe_doc_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value.strip())
    return safe.strip("_") or "doc"


# ── Benchmark ──────────────────────────────────────────

from backend.app.models.schemas import (
    BenchmarkDatasetResult,
    BenchmarkResultsResponse,
    BenchmarkStrategyResult,
)

@router.get("/api/evaluate/cached")
def get_cached_evaluation(doc_id: str = Query(..., min_length=1)) -> dict | None:
    """Return cached background evaluation result for a document (if ready).

    Returns None with a status message when evaluation is still running.
    """
    cached = _eval_cache.get(doc_id.strip())
    print(f"[EvalCache] GET doc_id={doc_id.strip()}, found={cached is not None}, all_keys={list(_eval_cache.keys())}")
    if cached:
        return {"ready": True, "evaluation": cached}
    return {"ready": False, "evaluation": None}


_BENCHMARK_CACHE_FILE = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_results.json"


@router.get("/api/evaluate/benchmark/results", response_model=BenchmarkResultsResponse)
def get_benchmark_results() -> BenchmarkResultsResponse:
    """读取最近一次 LongBench 评测结果（来自 scripts/benchmark_results.json）。"""
    import json as _json
    import re

    if not _BENCHMARK_CACHE_FILE.exists():
        return BenchmarkResultsResponse(results=[], cached=False)

    try:
        raw = _BENCHMARK_CACHE_FILE.read_text(encoding="utf-8")
    except Exception:
        return BenchmarkResultsResponse(results=[], cached=False)

    # 提取 JSON 数组部分（前面可能有 jieba 等输出）
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return BenchmarkResultsResponse(results=[], cached=False)

    try:
        data = _json.loads(match.group())
    except _json.JSONDecodeError:
        return BenchmarkResultsResponse(results=[], cached=False)

    results: list[BenchmarkDatasetResult] = []
    for item in data:
        strategies = [
            BenchmarkStrategyResult(**s)
            for s in item.get("strategies", [])
        ]
        results.append(BenchmarkDatasetResult(
            dataset=item.get("dataset", ""),
            label=item.get("dataset", ""),
            samples=item.get("samples", 0),
            processed=item.get("processed", 0),
            strategies=strategies,
            structure_gain=item.get("structure_gain", 0.0),
            semantic_gain=item.get("semantic_gain", 0.0),
            total_gain=item.get("total_gain", 0.0),
        ))

    # 获取文件修改时间
    import os
    mtime = os.path.getmtime(str(_BENCHMARK_CACHE_FILE))
    from datetime import datetime
    last_run = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

    return BenchmarkResultsResponse(results=results, cached=True, last_run=last_run)

