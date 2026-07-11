from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from backend.app.core.config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR

logger = logging.getLogger(__name__)

_client = None
_collection = None
_chroma_ready = False
_chroma_init_lock = threading.Lock()


def initialize_chroma() -> None:
    """在后台线程初始化 ChromaDB，不阻塞启动。

    ChromaDB 首次初始化会下载模型（可能很慢或超时），
    如果初始化失败，所有向量操作静默跳过，不影响分段功能。
    """
    global _client, _collection, _chroma_ready

    Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)

    def _do_init() -> None:
        global _client, _collection, _chroma_ready
        try:
            with _chroma_init_lock:
                if _chroma_ready:
                    return
                from chromadb import PersistentClient
                _client = PersistentClient(path=str(CHROMA_PERSIST_DIR))
                embedding_fn = _get_chromadb_embedding_function()
                if embedding_fn is None:
                    embedding_fn = _get_embedding_function()
                _collection = _client.get_or_create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    embedding_function=embedding_fn,
                )
                _chroma_ready = True
                logger.info("ChromaDB initialized successfully")
        except Exception:
            logger.warning("ChromaDB init failed, vector store unavailable")

    threading.Thread(target=_do_init, daemon=True, name="chroma-init").start()


_embedding_fn = None
_chromadb_embedding_fn = None
_chromadb_embedding_checked = False


def _get_chromadb_embedding_function():
    global _chromadb_embedding_fn, _chromadb_embedding_checked
    if _chromadb_embedding_checked:
        return _chromadb_embedding_fn

    _chromadb_embedding_checked = True
    try:
        from chromadb.utils import embedding_functions

        candidate = embedding_functions.DefaultEmbeddingFunction()
        candidate(["health check"])
        _chromadb_embedding_fn = candidate
    except Exception:
        _chromadb_embedding_fn = None

    return _chromadb_embedding_fn


def _get_embedding_function():
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn
    try:
        from chromadb.utils import embedding_functions
        _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2",
        )
    except ImportError:
        _embedding_fn = None
    return _embedding_fn


def _get_collection():
    if _collection is None:
        return None
    return _collection


def _ensure_collection():
    """获取已初始化的 collection，未就绪返回 None。"""
    if not _chroma_ready:
        return None
    return _collection


def delete_document_vectors(doc_id: str) -> None:
    collection = _ensure_collection()
    if collection is None:
        return
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        pass


def _build_retrieval_document(chunk: dict[str, Any]) -> str:
    retrieval_text = (chunk.get("retrieval_text", "") or "").strip()
    if retrieval_text:
        return retrieval_text

    title_path = chunk.get("title_path", [])
    section_titles = chunk.get("section_titles", [])
    label = chunk.get("label", [])
    entity_tags = chunk.get("entity_tags", [])
    summary = (chunk.get("summary", "") or "").strip()
    content = (chunk.get("content", "") or "").strip()

    title_text = " / ".join([item for item in title_path if isinstance(item, str) and item.strip()])
    section_text = " / ".join([item for item in section_titles if isinstance(item, str) and item.strip()])
    label_text = ", ".join([item for item in label if isinstance(item, str) and item.strip()])
    entity_text = ", ".join([item for item in entity_tags if isinstance(item, str) and item.strip()])

    sections = [
        f"标题路径: {title_text}" if title_text else "",
        f"包含小节: {section_text}" if section_text else "",
        f"标签: {label_text}" if label_text else "",
        f"实体: {entity_text}" if entity_text else "",
        f"摘要: {summary}" if summary else "",
        f"正文: {content}" if content else "",
    ]
    return "\n".join([section for section in sections if section])


def upsert_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> None:
    if not chunks:
        return

    collection = _ensure_collection()
    if collection is None:
        return
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for ordinal, chunk in enumerate(chunks, start=1):
        source_refs = chunk.get("source_refs", [])
        pages = [ref.get("page") for ref in source_refs if isinstance(ref.get("page"), int)]
        title_path = chunk.get("title_path", [])

        ids.append(chunk["chunk_id"])
        documents.append(_build_retrieval_document(chunk))
        metadatas.append(
            {
                "doc_id": doc_id,
                "chunk_id": chunk["chunk_id"],
                "ordinal": ordinal,
                "chunk_type": chunk.get("chunk_type", "normal"),
                "char_count": int(chunk.get("char_count", 0)),
                "source_ref_count": len(source_refs),
                "page_start": min(pages) if pages else -1,
                "page_end": max(pages) if pages else -1,
                "title_path": " / ".join(title_path),
                "quality_flags": ",".join(chunk.get("quality_flags", [])),
            }
        )

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def query_chunks(question: str, top_k: int, doc_id: str | None = None) -> list[dict[str, Any]]:
    collection = _ensure_collection()
    if collection is None:
        return []
    query_kwargs: dict[str, Any] = {
        "query_texts": [question],
        "n_results": top_k,
        "include": ["distances", "metadatas", "documents"],
    }
    if doc_id:
        query_kwargs["where"] = {"doc_id": doc_id}
    result = collection.query(**query_kwargs)

    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    items: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        distance = distances[index] if index < len(distances) else None
        items.append({"chunk_id": chunk_id, "distance": distance})
    return items
