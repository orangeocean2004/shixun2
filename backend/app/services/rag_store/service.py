from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from backend.app.core.config import (
    DEFAULT_RETRIEVE_CANDIDATE_MULTIPLIER,
    DEFAULT_RETRIEVE_MIN_CANDIDATES,
    RETRIEVE_LEXICAL_WEIGHT,
    RETRIEVE_QUALITY_PENALTY,
    RETRIEVE_SEMANTIC_WEIGHT,
)
from backend.app.services.document_loader import DocumentLoaderError, load_document
from backend.app.services.preprocessing import preprocess_document_blocks
from backend.app.services.segmenting import SegmentConfig, segment_blocks

from .chroma_store import delete_document_vectors, initialize_chroma, query_chunks, upsert_chunks
from .sqlite_store import (
    get_chunks_by_doc,
    get_chunks_by_ids,
    get_document,
    initialize_sqlite,
    mark_document_failed,
    mark_document_ready,
    replace_chunks,
    upsert_document_processing,
)


class RAGStoreError(Exception):
    pass


class RAGValidationError(RAGStoreError):
    pass


class RAGDocumentBusyError(RAGStoreError):
    pass


class RAGDocumentNotFoundError(RAGStoreError):
    pass


class RAGDocumentNotReadyError(RAGStoreError):
    pass


def initialize_rag_store() -> None:
    initialize_sqlite()
    initialize_chroma()


def ingest_document(
    file_name: str,
    payload: bytes,
    doc_id: str,
    min_chars: int,
    target_chars: int,
    max_chars: int,
    overlap_sentences: int,
    keyword_strategy: str,
) -> dict[str, Any]:
    if not doc_id.strip():
        raise RAGValidationError("doc_id 不能为空")

    file_sha256 = hashlib.sha256(payload).hexdigest()
    existing_doc = get_document(doc_id)
    if existing_doc and existing_doc["status"] == "processing":
        raise RAGDocumentBusyError("该 doc_id 正在处理中，请稍后重试")

    if existing_doc and existing_doc["status"] == "ready" and existing_doc["file_sha256"] == file_sha256:
        cached_chunks = get_chunks_by_doc(doc_id)
        return {
            "doc_id": doc_id,
            "file_name": existing_doc["file_name"],
            "file_size": existing_doc["file_size"],
            "block_count": existing_doc["block_count"],
            "chunks": cached_chunks,
            "statistics": existing_doc["statistics"],
            "strategy": existing_doc["strategy"],
        }

    suffix = Path(file_name).suffix.lower() or ".txt"
    temp_path: str | None = None
    stored_doc = False

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(payload)
            temp_path = temp_file.name

        blocks = load_document(temp_path)
        block_count = len(blocks)
        upsert_document_processing(
            doc_id=doc_id,
            file_name=file_name,
            file_sha256=file_sha256,
            file_size=len(payload),
            block_count=block_count,
        )
        stored_doc = True

        cleaned_blocks, preprocess_report = preprocess_document_blocks(blocks)
        config = SegmentConfig(
            min_chars=min_chars,
            target_chars=target_chars,
            max_chars=max_chars,
            overlap_sentences=overlap_sentences,
            keyword_strategy=keyword_strategy,
        )
        result = segment_blocks(cleaned_blocks, doc_id=doc_id, config=config)

        replace_chunks(doc_id, result["chunks"])
        delete_document_vectors(doc_id)
        upsert_chunks(doc_id, result["chunks"])

        mark_document_ready(
            doc_id=doc_id,
            chunk_count=len(result["chunks"]),
            strategy=result["strategy"],
            statistics=result["statistics"],
            preprocess=preprocess_report.to_dict(),
        )

        return {
            "doc_id": result["doc_id"],
            "file_name": file_name,
            "file_size": len(payload),
            "block_count": block_count,
            "chunks": result["chunks"],
            "statistics": result["statistics"],
            "strategy": result["strategy"],
        }
    except DocumentLoaderError:
        if stored_doc:
            mark_document_failed(doc_id, "文档解析失败")
        raise
    except Exception as exc:
        if stored_doc:
            mark_document_failed(doc_id, str(exc))
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


TOKEN_PATTERN = re.compile(r"[一-鿿A-Za-z0-9_]+")


def retrieve_chunks(question: str, top_k: int) -> dict[str, Any]:
    normalized_question = (question or "").strip()
    if not normalized_question:
        raise RAGValidationError("question 不能为空")
    if top_k <= 0:
        raise RAGValidationError("top_k 必须大于 0")

    candidate_k = max(top_k * DEFAULT_RETRIEVE_CANDIDATE_MULTIPLIER, DEFAULT_RETRIEVE_MIN_CANDIDATES)
    hits = query_chunks(question=normalized_question, top_k=candidate_k)
    chunk_ids = [hit["chunk_id"] for hit in hits]
    chunk_map = get_chunks_by_ids(chunk_ids)

    ranked: list[dict[str, Any]] = []
    for hit in hits:
        chunk = chunk_map.get(hit["chunk_id"])
        if not chunk:
            continue

        semantic_score = distance_to_score(hit.get("distance")) or 0.0
        lexical_score = lexical_overlap_score(normalized_question, chunk)
        quality_penalty = chunk_quality_penalty(chunk)
        final_score = (
            RETRIEVE_SEMANTIC_WEIGHT * semantic_score
            + RETRIEVE_LEXICAL_WEIGHT * lexical_score
            - quality_penalty
        )

        enriched_chunk = dict(chunk)
        enriched_chunk["score"] = round(final_score, 6)
        enriched_chunk["semantic_score"] = round(semantic_score, 6)
        enriched_chunk["lexical_score"] = round(lexical_score, 6)
        ranked.append(enriched_chunk)

    ranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)

    return {
        "question": normalized_question,
        "top_k": top_k,
        "chunks": ranked[:top_k],
    }

def lexical_overlap_score(question: str, chunk: dict[str, Any]) -> float:
    query_tokens = tokenize(question)
    if not query_tokens:
        return 0.0

    retrieval_text = "\n".join(
        [
            " / ".join(chunk.get("title_path", [])),
            " ".join(chunk.get("label", [])),
            " ".join(chunk.get("entity_tags", [])),
            chunk.get("summary", ""),
            chunk.get("content", ""),
        ]
    )
    chunk_tokens = tokenize(retrieval_text)
    if not chunk_tokens:
        return 0.0

    overlap = query_tokens & chunk_tokens
    return len(overlap) / len(query_tokens)


def chunk_quality_penalty(chunk: dict[str, Any]) -> float:
    flags = set(chunk.get("quality_flags", []))
    penalty = 0.0
    if "undersized" in flags:
        penalty += RETRIEVE_QUALITY_PENALTY
    if "oversized" in flags:
        penalty += RETRIEVE_QUALITY_PENALTY
    return penalty


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text or "") if token.strip()}


def list_all_chunks(doc_id: str) -> dict[str, Any]:
    document = get_document(doc_id)
    if not document:
        raise RAGDocumentNotFoundError("未找到对应 doc_id")

    chunks = get_chunks_by_doc(doc_id)
    return {
        "doc_id": doc_id,
        "total": len(chunks),
        "chunks": chunks,
    }


def distance_to_score(distance: float | None) -> float | None:
    if distance is None:
        return None
    normalized = max(float(distance), 0.0)
    return round(1 / (1 + normalized), 6)
