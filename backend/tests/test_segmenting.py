from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.services.document_loader import load_document
from backend.app.services.segmenter import SegmentConfig, segment_blocks, segment_text
from backend.app.services.segmenting.parser import parse_plain_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SegmentingSmokeTest(unittest.TestCase):
    def test_plain_text_sample_is_chunked_compactly(self) -> None:
        text = (PROJECT_ROOT / "assets" / "title.md").read_text(encoding="utf-8")
        result = segment_text(text, doc_id="title")

        statistics = result["statistics"]
        self.assertEqual(statistics["oversized_count"], 0)
        self.assertEqual(statistics["undersized_count"], 0)
        self.assertEqual(statistics["source_ref_complete_rate"], 1.0)
        self.assertGreaterEqual(statistics["target_length_hit_rate"], 1.0)
        self.assertLessEqual(statistics["chunk_count"], 6)
        self.assertEqual(result["strategy"]["keyword_tokenizer"], "jieba")
        self.assertIn(result["strategy"]["keyword_strategy"], {"jieba_tfidf", "jieba_freq"})

        for chunk in result["chunks"]:
            self.assertIn("label", chunk)
            self.assertIsInstance(chunk["label"], list)
            self.assertTrue(chunk["label"])
            self.assertTrue(all(isinstance(label, str) for label in chunk["label"]))
            self.assertIn("summary", chunk)
            self.assertIn("entity_tags", chunk)
            self.assertIn("backlink", chunk)
            self.assertIn("section_titles", chunk)
            self.assertIn("retrieval_text", chunk)
            self.assertTrue(chunk["retrieval_text"])
            self.assertEqual(chunk["backlink"]["source_ref_count"], len(chunk["source_refs"]))
            self.assertEqual(
                set(chunk["backlink"]["source_ref_ids"]),
                {ref["block_id"] for ref in chunk["source_refs"]},
            )

    def test_docx_sample_keeps_source_refs_complete(self) -> None:
        blocks = load_document(PROJECT_ROOT / "assets" / "开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx")
        result = segment_blocks(blocks, doc_id="open_report")

        statistics = result["statistics"]
        self.assertEqual(statistics["oversized_count"], 0)
        self.assertEqual(statistics["source_ref_complete_rate"], 1.0)
        self.assertLessEqual(statistics["chunk_count"], 20)
        self.assertEqual(result["strategy"]["keyword_tokenizer"], "jieba")

        for chunk in result["chunks"]:
            self.assertIn("label", chunk)
            self.assertIsInstance(chunk["label"], list)
            self.assertTrue(chunk["label"])
            self.assertTrue(all(isinstance(label, str) for label in chunk["label"]))
            self.assertIn("summary", chunk)
            self.assertIn("entity_tags", chunk)
            self.assertIn("backlink", chunk)
            self.assertIn("section_titles", chunk)
            self.assertIn("retrieval_text", chunk)
            self.assertTrue(chunk["retrieval_text"])
            self.assertEqual(chunk["backlink"]["source_ref_count"], len(chunk["source_refs"]))
            self.assertEqual(
                set(chunk["backlink"]["source_ref_ids"]),
                {ref["block_id"] for ref in chunk["source_refs"]},
            )

    def test_keyword_strategy_can_be_switched(self) -> None:
        text = "分块策略和关键词算法都需要可插拔，以便后续替换底层实现。"
        result = segment_text(
            text,
            doc_id="switch_case",
            config=SegmentConfig(keyword_strategy="jieba_freq"),
        )

        self.assertEqual(result["strategy"]["keyword_strategy"], "jieba_freq")
        self.assertEqual(result["strategy"]["keyword_tokenizer"], "jieba")
        self.assertTrue(all(isinstance(chunk["label"], list) and chunk["label"] for chunk in result["chunks"]))

    def test_markdown_table_is_detected(self) -> None:
        text = """
# 标题

| 指标 | 数值 |
| --- | ---: |
| 准确率 | 92% |
""".strip()
        blocks = parse_plain_text(text)
        self.assertTrue(any(block.block_type == "table" for block in blocks))

    def test_pipe_text_not_misdetected_as_table(self) -> None:
        text = "A | B | C 只是普通描述，不是 markdown 表格"
        blocks = parse_plain_text(text)
        self.assertTrue(blocks)
        self.assertEqual(blocks[0].block_type, "paragraph")

    def test_markdown_image_is_detected(self) -> None:
        text = """
这里是说明。

![系统架构图](https://example.com/arch.png "arch")
""".strip()
        blocks = parse_plain_text(text)
        self.assertTrue(any(block.block_type == "image" for block in blocks))

    def test_html_image_is_detected(self) -> None:
        text = "<img src=\"https://example.com/arch.png\" alt=\"arch\"/>"
        blocks = parse_plain_text(text)
        self.assertTrue(any(block.block_type == "image" for block in blocks))

    def test_segmenting_adds_contains_image_flag(self) -> None:
        text = """
## 方案

![图示](https://example.com/pic.png)

系统支持图文混排。
""".strip()
        result = segment_text(text, doc_id="image_case")

        self.assertTrue(any("contains_image" in chunk["quality_flags"] for chunk in result["chunks"]))
        self.assertTrue(
            any(
                any(ref["block_type"] == "image" for ref in chunk["source_refs"])
                for chunk in result["chunks"]
            )
        )

    def test_merged_short_sections_keep_first_title_path(self) -> None:
        text = """
# 根标题

## 二、研究目标
短内容。

## 三、核心能力
这里继续补充说明，让短小节合并后仍然应当保留第一个标题路径。
""".strip()
        result = segment_text(
            text,
            doc_id="title_path_case",
            config=SegmentConfig(min_chars=80, target_chars=400, max_chars=800),
        )

        chunk = result["chunks"][0]
        self.assertIn("二、研究目标", chunk["content"])
        self.assertEqual(chunk["title_path"], ["根标题", "二、研究目标"])
        self.assertIn("二、研究目标", chunk["section_titles"])
        self.assertIn("三、核心能力", chunk["section_titles"])
        self.assertIn("包含小节", chunk["retrieval_text"])

    def test_metric_chunk_builds_retrieval_text(self) -> None:
        text = """
# 验收标准

不破句率: 100%
目标长度区间命中率 ≥ 90%
整体成块率 ≥ 95%
""".strip()
        result = segment_text(text, doc_id="metric_case")

        metric_chunks = [chunk for chunk in result["chunks"] if chunk["chunk_type"] == "metric"]
        self.assertTrue(metric_chunks)
        chunk = metric_chunks[0]
        self.assertIn("contains_metric", chunk["quality_flags"])
        self.assertIn("关键指标", chunk["retrieval_text"])
        self.assertIn("不破句率", chunk["retrieval_text"])


if __name__ == "__main__":
    unittest.main()
