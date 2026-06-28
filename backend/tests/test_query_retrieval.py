from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.api.routes import query_retrieved_chunks
from backend.app.models.schemas import QueryRequest
from backend.app.services.rag_store.chroma_store import _build_retrieval_document
from backend.app.services.rag_store.service import retrieve_chunks


class QueryContractTest(unittest.TestCase):
    @patch("backend.app.api.routes.retrieve_chunks")
    def test_query_route_accepts_question_only(self, mock_retrieve: unittest.mock.Mock) -> None:
        mock_retrieve.return_value = {
            "question": "什么是 RAG",
            "top_k": 3,
            "chunks": [],
        }

        payload = QueryRequest(question="什么是 RAG", top_k=3)
        response = query_retrieved_chunks(payload)

        self.assertEqual(response.question, "什么是 RAG")
        self.assertEqual(response.top_k, 3)
        self.assertEqual(response.chunks, [])
        mock_retrieve.assert_called_once_with(question="什么是 RAG", top_k=3)

    def test_query_request_rejects_empty_question(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest(question="", top_k=3)


class RetrievalRerankTest(unittest.TestCase):
    @patch("backend.app.services.rag_store.service.get_chunks_by_ids")
    @patch("backend.app.services.rag_store.service.query_chunks")
    def test_retrieve_chunks_reranks_by_semantic_and_lexical(
        self,
        mock_query_chunks: unittest.mock.Mock,
        mock_get_chunks_by_ids: unittest.mock.Mock,
    ) -> None:
        mock_query_chunks.return_value = [
            {"chunk_id": "chunk_a", "distance": 0.1},
            {"chunk_id": "chunk_b", "distance": 0.43},
        ]
        mock_get_chunks_by_ids.return_value = {
            "chunk_a": {
                "chunk_id": "chunk_a",
                "doc_id": "doc_1",
                "title_path": ["概述"],
                "label": ["normal", "背景"],
                "entity_tags": [],
                "summary": "",
                "content": "与问题无关的内容",
                "quality_flags": [],
            },
            "chunk_b": {
                "chunk_id": "chunk_b",
                "doc_id": "doc_1",
                "title_path": ["检索策略"],
                "label": ["normal", "BM25", "检索"],
                "entity_tags": ["BM25"],
                "summary": "BM25 检索在关键词匹配中效果稳定",
                "content": "BM25 检索适用于关键词密集型问题",
                "quality_flags": [],
            },
        }

        result = retrieve_chunks(question="BM25 检索", top_k=1)

        self.assertEqual(result["question"], "BM25 检索")
        self.assertEqual(result["top_k"], 1)
        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["chunks"][0]["chunk_id"], "chunk_b")

    def test_build_retrieval_document_includes_structured_fields(self) -> None:
        chunk = {
            "title_path": ["第一章", "检索方案"],
            "label": ["normal", "检索", "BM25"],
            "entity_tags": ["BM25", "RAG"],
            "summary": "关键词检索摘要",
            "content": "正文内容",
        }

        retrieval_doc = _build_retrieval_document(chunk)

        self.assertIn("标题路径: 第一章 / 检索方案", retrieval_doc)
        self.assertIn("标签: normal, 检索, BM25", retrieval_doc)
        self.assertIn("实体: BM25, RAG", retrieval_doc)
        self.assertIn("摘要: 关键词检索摘要", retrieval_doc)
        self.assertIn("正文: 正文内容", retrieval_doc)


if __name__ == "__main__":
    unittest.main()
