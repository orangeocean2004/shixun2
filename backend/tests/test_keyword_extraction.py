from __future__ import annotations

import unittest

from backend.app.services.segmenting.enrichment import build_label
from backend.app.services.segmenting.keyword_extraction import (
    DEFAULT_KEYWORD_STRATEGY,
    get_keyword_strategy,
    list_keyword_strategies,
)


class _FakeKeywordStrategy:
    name = "fake"

    def extract(self, text: str, top_k: int, stopwords: set[str] | None = None) -> list[str]:
        return ["自定义词"][:top_k]


class KeywordExtractionTest(unittest.TestCase):
    def test_strategy_registry_contains_defaults(self) -> None:
        strategies = set(list_keyword_strategies())
        self.assertIn(DEFAULT_KEYWORD_STRATEGY, strategies)
        self.assertIn("jieba_freq", strategies)

    def test_unknown_strategy_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_keyword_strategy("unknown_strategy")

    def test_tfidf_strategy_is_deterministic(self) -> None:
        strategy = get_keyword_strategy("jieba_tfidf")
        text = "RAG系统通过向量数据库提升检索能力，分块策略影响召回与排序质量。"

        first = strategy.extract(text, top_k=5)
        second = strategy.extract(text, top_k=5)

        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 5)

    def test_freq_strategy_is_deterministic(self) -> None:
        strategy = get_keyword_strategy("jieba_freq")
        text = "分词策略与关键词策略可插拔，分词策略与关键词策略可插拔。"

        first = strategy.extract(text, top_k=5)
        second = strategy.extract(text, top_k=5)

        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 5)

    def test_build_label_uses_injected_strategy_when_no_title(self) -> None:
        label = build_label(
            title_path=[],
            chunk_type="paragraph",
            content="这是一个没有标题的片段",
            keyword_strategy=_FakeKeywordStrategy(),
        )
        self.assertEqual(label, ["自定义词"])

    def test_build_label_merges_title_and_content_keywords(self) -> None:
        label = build_label(
            title_path=["章节A"],
            chunk_type="paragraph",
            content="内容",
            keyword_strategy=_FakeKeywordStrategy(),
        )
        self.assertEqual(label, ["自定义词"])


if __name__ == "__main__":
    unittest.main()
