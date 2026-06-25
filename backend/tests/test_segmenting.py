from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.services.document_loader import load_document
from backend.app.services.retrieval import InMemoryVectorStore
from backend.app.services.evaluation import EmbeddingRelevance, compute_ir_metrics
from backend.app.services.segmenting import SegmentConfig, segment_blocks, segment_text


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
        self.assertLessEqual(statistics["chunk_count"], 4)

    def test_docx_sample_keeps_source_refs_complete(self) -> None:
        blocks = load_document(PROJECT_ROOT / "assets" / "开题报告_课题11_面向RAG的智能分段与内容组织智能体.docx")
        result = segment_blocks(blocks, doc_id="open_report")

        statistics = result["statistics"]
        self.assertEqual(statistics["oversized_count"], 0)
        self.assertEqual(statistics["source_ref_complete_rate"], 1.0)
        self.assertLessEqual(statistics["chunk_count"], 20)

    def test_recursive_split_handles_long_plain_text(self) -> None:
        text = "第一章\n\n" + ("这是一个很长的连续文本片段" * 40) + "\n\n" + ("第二段内容" * 40)
        config = SegmentConfig(min_chars=80, target_chars=140, max_chars=180, overlap_sentences=1)

        result = segment_text(text, doc_id="recursive", config=config)
        statistics = result["statistics"]

        self.assertGreaterEqual(statistics["chunk_count"], 2)
        self.assertEqual(statistics["oversized_count"], 0)
        for chunk in result["chunks"]:
            self.assertLessEqual(chunk["char_count"], config.max_chars)

    def test_local_retrieval_returns_related_chunk(self) -> None:
        chunks = [
            {
                "chunk_id": "doc_chunk_0001",
                "content": "本课题需要实现结构感知分段、原文回链和检索评估。",
                "title_path": ["课题目标"],
                "chunk_type": "normal",
                "char_count": 25,
                "source_refs": [{"page": 1}],
                "quality_flags": [],
            },
            {
                "chunk_id": "doc_chunk_0002",
                "content": "前端页面负责上传文档并展示分段结果。",
                "title_path": ["系统界面"],
                "chunk_type": "normal",
                "char_count": 18,
                "source_refs": [{"page": 2}],
                "quality_flags": [],
            },
        ]
        store = InMemoryVectorStore()
        store.upsert("doc", chunks)

        hits = store.search("doc", "原文回链怎么做", top_k=1)

        self.assertEqual(hits[0].chunk_id, "doc_chunk_0001")

    def test_merged_short_sections_keep_first_title_path(self) -> None:
        text = "\n".join(
            [
                "一、背景",
                "背景内容。" * 60,
                "二、目标",
                "目标内容。" * 18,
                "三、能力",
                "能力内容。" * 18,
            ]
        )
        config = SegmentConfig(
            min_chars=300,
            target_chars=900,
            max_chars=1200,
            heading_flush_min_chars=300,
            enable_semantic_boundary=False,
        )

        result = segment_text(text, doc_id="titles", config=config)
        merged = next(chunk for chunk in result["chunks"] if "二、目标" in chunk["content"])

        self.assertEqual(merged["title_path"], ["二、目标"])
        self.assertIn("二、目标", merged["section_titles"])
        self.assertIn("三、能力", merged["section_titles"])
        self.assertIn("包含小节", merged["retrieval_text"])

    def test_metric_chunk_builds_retrieval_text(self) -> None:
        text = "\n".join(
            [
                "一、验收标准",
                "不破句率 100%；表格/公式/代码整体成块率 ≥ 95%；目标长度区间命中率 ≥ 90%。",
            ]
        )

        result = segment_text(text, doc_id="metrics")
        chunk = result["chunks"][0]

        self.assertEqual(chunk["chunk_type"], "metric")
        self.assertIn("contains_metric", chunk["quality_flags"])
        self.assertIn("关键指标", chunk["retrieval_text"])
        self.assertIn("不破句率", chunk["retrieval_text"])

    def test_metrics_recall_uses_all_relevant_chunks(self) -> None:
        chunks = [
            {"content": "不破句率 100%", "score": 0.9},
            {"content": "目标长度区间命中率 90%", "score": 0.8},
        ]
        judge = EmbeddingRelevance()
        judge.set_reference("不破句率 目标长度区间命中率", ["不破句率", "目标长度区间命中率"])

        metrics = compute_ir_metrics([chunks[0]], judge, all_chunks=chunks)

        self.assertEqual(metrics["recall@1"], 0.5)
        self.assertEqual(metrics["precision@1"], 1.0)


    def test_rule_based_tagger_extracts_keywords(self) -> None:
        from backend.app.services.model_client import RuleBasedTagger

        tagger = RuleBasedTagger(max_tags=5)
        text = "智能分段系统需要支持标题边界检测、语义完整性保护和长度约束控制。"
        tags = tagger.extract_tags(text)

        self.assertGreater(len(tags), 0, "Should extract at least one tag")
        self.assertLessEqual(len(tags), 5)

    def test_rule_based_tagger_extracts_entities(self) -> None:
        from backend.app.services.model_client import RuleBasedTagger

        tagger = RuleBasedTagger()
        text = "不破句率要求达到100%，Recall@5提升≥10%，nDCG不低于0.67。"
        entities = tagger.extract_entities(text)

        values = [e["value"] for e in entities]
        self.assertTrue(any("100%" in v for v in values), f"Should find percentage, got {values}")

    def test_organizer_fallback_mode_works_without_llm(self) -> None:
        from backend.app.services.organizer import ContentOrganizer

        organizer = ContentOrganizer()  # No LLM client → rule-based path
        result = organizer.organize_chunk(
            "知识图谱是Google在2012年提出的技术，用于增强搜索引擎的语义理解能力。",
        )

        self.assertIsNotNone(result)
        self.assertGreater(len(result.tags), 0)

    def test_summary_faithfulness_evaluator(self) -> None:
        from backend.app.services.evaluator import SummaryFaithfulnessEvaluator

        evaluator = SummaryFaithfulnessEvaluator()
        content = "不破句率要求达到100%，目标长度区间命中率不低于90%，表格公式代码整体成块率大于等于95%。"
        good_summary = "不破句率100%，长度命中率90%，特殊块保护率95%。"

        result = evaluator.evaluate(good_summary, content)
        self.assertGreaterEqual(result["faithfulness"], 0)
        self.assertLessEqual(result["faithfulness"], 1.0)
        self.assertIn("is_faithful", result)

    def test_e2e_segment_with_organizer(self) -> None:
        from backend.app.services.organizer import ContentOrganizer

        organizer = ContentOrganizer()
        config = SegmentConfig(
            min_chars=300, target_chars=900, max_chars=1200, overlap_sentences=2,
        )
        text = (PROJECT_ROOT / "assets" / "title.md").read_text(encoding="utf-8")
        result = segment_text(text, doc_id="e2e", config=config, organizer=organizer)

        for chunk in result["chunks"]:
            self.assertIn("tags", chunk)
            self.assertIn("summary", chunk)
            self.assertIn("entity_labels", chunk)
            self.assertIsInstance(chunk["tags"], list)
            self.assertIsInstance(chunk["summary"], str)

        self.assertIn("document_summary", result)


if __name__ == "__main__":
    unittest.main()
