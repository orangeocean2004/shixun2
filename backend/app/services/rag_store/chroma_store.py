from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.core.config import CHROMA_COLLECTION_NAME, CHROMA_PERSIST_DIR

_client = None
_collection = None


def initialize_chroma() -> None:
    global _client, _collection
    try:
        from chromadb import PersistentClient
    except ImportError as exc:
        raise RuntimeError("chromadb 未安装，请先安装依赖后再启动服务") from exc

    Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
    if _client is None:
        _client = PersistentClient(path=str(CHROMA_PERSIST_DIR))
    _collection = _client.get_or_create_collection(name=CHROMA_COLLECTION_NAME)


def _get_collection():
    if _collection is None:
        initialize_chroma()
    return _collection


def delete_document_vectors(doc_id: str) -> None:
    collection = _get_collection()
    collection.delete(where={"doc_id": doc_id})


def upsert_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> None:
    if not chunks:
        return

    collection = _get_collection()
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for ordinal, chunk in enumerate(chunks, start=1):
        source_refs = chunk.get("source_refs", [])
        pages = [ref.get("page") for ref in source_refs if isinstance(ref.get("page"), int)]
        title_path = chunk.get("title_path", [])

        ids.append(chunk["chunk_id"])
        documents.append(chunk.get("content", ""))
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


def query_chunks(doc_id: str, question: str, top_k: int) -> list[dict[str, Any]]:
    collection = _get_collection()
    result = collection.query(
        query_texts=[question],
        n_results=top_k,
        where={"doc_id": doc_id},
        include=["distances", "metadatas", "documents"],
    )

    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    items: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        distance = distances[index] if index < len(distances) else None
        items.append({"chunk_id": chunk_id, "distance": distance})
    return items
