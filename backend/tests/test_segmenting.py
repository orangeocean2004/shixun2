from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.services.document_loader import load_document
from backend.app.services.retrieval import InMemoryVectorStore
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


if __name__ == "__main__":
    unittest.main()
