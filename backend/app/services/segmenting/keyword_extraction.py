from __future__ import annotations

import re
from collections import Counter
from typing import Protocol

import jieba
import jieba.analyse


DEFAULT_KEYWORD_STRATEGY = "jieba_tfidf"

DEFAULT_STOPWORDS = {
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

INVALID_TOKEN_PATTERN = re.compile(r"^[\W_]+$")


class KeywordExtractionStrategy(Protocol):
    name: str

    def extract(self, text: str, top_k: int, stopwords: set[str] | None = None) -> list[str]:
        pass


class JiebaTFIDFKeywordStrategy:
    name = "jieba_tfidf"

    def extract(self, text: str, top_k: int, stopwords: set[str] | None = None) -> list[str]:
        if top_k <= 0:
            return []

        content = (text or "").strip()
        if not content:
            return []

        normalized_stopwords = _normalize_stopwords(stopwords)
        candidates = jieba.analyse.extract_tags(content, topK=max(top_k * 3, top_k), withWeight=True)

        weighted_terms: list[tuple[str, float]] = []
        for term, weight in candidates:
            token = term.strip()
            if not _is_valid_token(token, normalized_stopwords):
                continue
            weighted_terms.append((token, float(weight)))

        weighted_terms.sort(key=lambda item: (-item[1], item[0]))
        ordered = _dedupe_keep_order([term for term, _ in weighted_terms])
        return ordered[:top_k]


class JiebaFrequencyKeywordStrategy:
    name = "jieba_freq"

    def extract(self, text: str, top_k: int, stopwords: set[str] | None = None) -> list[str]:
        if top_k <= 0:
            return []

        content = (text or "").strip()
        if not content:
            return []

        normalized_stopwords = _normalize_stopwords(stopwords)
        tokens = [token.strip() for token in jieba.cut(content, HMM=False)]
        filtered = [token for token in tokens if _is_valid_token(token, normalized_stopwords)]

        ranked = sorted(Counter(filtered).items(), key=lambda item: (-item[1], item[0]))
        return [token for token, _ in ranked[:top_k]]


_STRATEGY_FACTORIES: dict[str, type[KeywordExtractionStrategy]] = {
    JiebaTFIDFKeywordStrategy.name: JiebaTFIDFKeywordStrategy,
    JiebaFrequencyKeywordStrategy.name: JiebaFrequencyKeywordStrategy,
}


def get_keyword_strategy(name: str | None = None) -> KeywordExtractionStrategy:
    strategy_name = (name or DEFAULT_KEYWORD_STRATEGY).strip().lower()
    factory = _STRATEGY_FACTORIES.get(strategy_name)
    if factory is None:
        choices = ", ".join(list_keyword_strategies())
        raise ValueError(f"Unsupported keyword_strategy: {strategy_name}. Available: {choices}")
    return factory()


def list_keyword_strategies() -> tuple[str, ...]:
    return tuple(sorted(_STRATEGY_FACTORIES.keys()))


def _normalize_stopwords(stopwords: set[str] | None) -> set[str]:
    merged = set(DEFAULT_STOPWORDS)
    if stopwords:
        merged.update(stopwords)
    return {word.lower() for word in merged if word.strip()}


def _is_valid_token(token: str, normalized_stopwords: set[str]) -> bool:
    lowered = token.lower()
    if lowered in normalized_stopwords:
        return False
    if len(token) < 2:
        return False
    if INVALID_TOKEN_PATTERN.match(token):
        return False
    return True


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
