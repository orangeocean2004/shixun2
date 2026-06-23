from __future__ import annotations

import unittest
from pathlib import Path

from backend.app.services.document_loader import load_document
from backend.app.services.segmenter import segment_blocks, segment_text


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


if __name__ == "__main__":
    unittest.main()
