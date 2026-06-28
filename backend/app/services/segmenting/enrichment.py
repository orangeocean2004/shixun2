from __future__ import annotations

import re
from collections import Counter
from typing import Any


TOKEN_PATTERN = re.compile(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9_\-]{2,}")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?；;])")
DATE_PATTERN = re.compile(r"\b\d{4}[-/.年]\d{1,2}([-/月.]\d{1,2}日?)?\b")
VERSION_PATTERN = re.compile(r"\bv?\d+(?:\.\d+){1,3}\b", re.IGNORECASE)

STOPWORDS = {
    "以及",
    "为了",
    "通过",
    "可以",
    "进行",
    "实现",
    "这个",
    "我们",
    "你们",
    "他们",
    "然后",
    "相关",
    "其中",
    "一个",
    "一种",
    "about",
    "with",
    "from",
    "that",
    "this",
    "have",
    "will",
    "using",
}

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


def build_label(title_path: list[str], chunk_type: str, content: str) -> str:
    for title in reversed(title_path):
        if title and title.strip():
            return title.strip()

    keywords = _top_keywords(content, top_k=1)
    if keywords:
        return f"{chunk_type}-{keywords[0]}"
    return chunk_type


def build_summary(content: str, max_chars: int = 120) -> str:
    cleaned = _normalize(content)
    if not cleaned:
        return ""

    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(cleaned) if s.strip()]
    if not sentences:
        return cleaned[:max_chars]

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
            selected.append(sentence[: max_chars - current_len])
            break

    summary = "".join(selected).strip()
    return summary[:max_chars]


def extract_entity_tags(content: str, max_tags: int = 10) -> list[str]:
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


def _top_keywords(content: str, top_k: int = 3) -> list[str]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(content)]
    filtered = [token for token in tokens if token not in STOPWORDS and len(token) >= 2]
    ranked = Counter(filtered).most_common(top_k)
    return [token for token, _ in ranked]


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
