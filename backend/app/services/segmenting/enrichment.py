"""Chunk enrichment utilities.

- build_summary: extractive lead-N sentence summary (lightweight fallback).
- extract_entity_tags: regex-based entity extraction (dates, versions, orgs, etc.).
- build_backlink: construct source-reference backlinks for traceability.

Note: LLM-based tagging and summarisation are handled by
``ContentOrganizer`` in ``backend.app.services.organizer``.
"""

from __future__ import annotations

import re
from typing import Any


SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;])")
DATE_PATTERN = re.compile(r"\b\d{4}[-/.年]\d{1,2}([-/月.]\d{1,2}日?)?\b")
VERSION_PATTERN = re.compile(r"\bv?\d+(?:\.\d+){1,3}\b", re.IGNORECASE)

ORG_SUFFIXES = ("公司", "集团", "大学", "学院", "研究院", "委员会", "中心", "局", "厅", "部")
TECH_TERMS = {
    "RAG",
    "LLM",
    "NLP",
    "API",
    "SDK",
    "Python",
    "FastAPI",
    "LangChain",
    "OpenAI",
    "Transformer",
    "向量数据库",
    "知识库",
    "分块",
    "检索",
}


def build_summary(content: str, max_chars: int = 200) -> str:
    """Extractive lead-N summary — truncate to first few complete sentences."""
    cleaned = _normalize(content)
    if not cleaned:
        return ""

    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(cleaned) if s.strip()]
    if not sentences:
        return _soft_truncate(cleaned, max_chars)

    selected: list[str] = []
    current_len = 0
    for sentence in sentences:
        if current_len >= max_chars:
            break
        next_len = current_len + len(sentence)
        if next_len <= max_chars or not selected:
            selected.append(sentence)
            current_len = next_len
        else:
            break

    summary = "".join(selected).strip()
    return _soft_truncate(summary, max_chars)


def extract_entity_tags(content: str, max_tags: int = 10) -> list[str]:
    """Regex-based entity extraction: dates, versions, quoted terms, org names."""
    text = _normalize(content)
    if not text:
        return []

    entities: list[str] = []

    entities.extend(match.group(0) for match in DATE_PATTERN.finditer(text))
    entities.extend(match.group(0) for match in VERSION_PATTERN.finditer(text))
    entities.extend(_extract_quoted_terms(text))
    entities.extend(_extract_org_like_terms(text))

    for term in TECH_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE) or term in text:
            entities.append(term)

    deduped = _dedupe_keep_order([entity.strip() for entity in entities if entity.strip()])
    return deduped[:max_tags]


def build_backlink(doc_id: str, chunk_id: str, source_refs: list[dict[str, Any]]) -> dict[str, Any]:
    """Construct a source-reference backlink for traceability."""
    ref_ids = _dedupe_keep_order([
        str(ref.get("block_id"))
        for ref in source_refs
        if ref.get("block_id") is not None
    ])

    pages = [ref.get("page") for ref in source_refs if isinstance(ref.get("page"), int)]
    page_span = {
        "start": min(pages) if pages else None,
        "end": max(pages) if pages else None,
    }

    primary_ref = source_refs[0] if source_refs else None

    return {
        "kind": "source_refs_v1",
        "doc_id": doc_id,
        "chunk_id": chunk_id,
        "primary_ref": primary_ref,
        "source_ref_ids": ref_ids,
        "page_span": page_span,
        "source_ref_count": len(source_refs),
    }


# ── helpers ─────────────────────────────────────────────────


def _soft_truncate(text: str, max_chars: int) -> str:
    """Truncate to *max_chars*, back-tracking to the last sentence boundary."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    window = text[:max_chars]
    for ch in ("。", "！", "？", "；", ".", "!", "?", ";"):
        idx = window.rfind(ch)
        if idx > max_chars * 0.4:
            return text[:idx + 1]

    return text[:max_chars] + "…"


def _extract_quoted_terms(text: str) -> list[str]:
    terms: list[str] = []
    terms.extend(re.findall(r"《([^》]{2,30})》", text))
    terms.extend(re.findall(r"“([^”]{2,30})”", text))
    terms.extend(re.findall(r'"([^"\n]{2,30})"', text))
    return terms


def _extract_org_like_terms(text: str) -> list[str]:
    terms: list[str] = []
    for suffix in ORG_SUFFIXES:
        pattern = re.compile(rf"[一-鿿A-Za-z0-9]{{2,20}}{suffix}")
        terms.extend(pattern.findall(text))
    return terms


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result
