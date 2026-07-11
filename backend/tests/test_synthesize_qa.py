from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.app.api.routes import synthesize_qa
from backend.app.services.qa_quality import QAQualityResult


class _FakeEvaluator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def evaluate(self, question: str, answer: str, content: str) -> QAQualityResult:
        self.calls.append((question, answer, content))
        return QAQualityResult(
            answerable=True,
            answerable_score=0.91,
            faithful=True,
            faithful_score=0.86,
            quality_score=0.885,
        )


class _FakeLLM:
    is_available = True

    def generate(self, *args, **kwargs) -> str:
        del args, kwargs
        return '[{"question":"Q1","answer":"A1"}]'


class SynthesizeQATest(unittest.TestCase):
    @patch("backend.app.services.organizer.model_client.LLMClient", return_value=_FakeLLM())
    @patch("backend.app.api.routes.get_model_settings")
    @patch("backend.app.api.routes.get_qa_quality_evaluator")
    def test_synthesize_qa_uses_pluggable_evaluator(
        self,
        mock_get_evaluator: unittest.mock.Mock,
        mock_get_settings: unittest.mock.Mock,
        mock_llm_client: unittest.mock.Mock,
    ) -> None:
        fake_evaluator = _FakeEvaluator()
        mock_get_evaluator.return_value = fake_evaluator
        mock_get_settings.return_value = {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "LLM_MODEL": "deepseek-chat",
            "QA_QUALITY_EVALUATOR": "lexical_overlap_v1",
        }

        response = synthesize_qa(
            {
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "title_path": ["chapter"],
                        "content": "Some content",
                    }
                ]
            }
        )

        self.assertEqual(response["total"], 1)
        pair = response["qa_pairs"][0]
        self.assertEqual(pair["question"], "Q1")
        self.assertEqual(pair["answer"], "A1")
        self.assertEqual(pair["answerable"], True)
        self.assertEqual(pair["answerable_score"], 0.91)
        self.assertEqual(pair["faithful"], True)
        self.assertEqual(pair["faithful_score"], 0.86)
        self.assertEqual(pair["quality_score"], 0.885)

        mock_get_evaluator.assert_called_once_with("lexical_overlap_v1")
        mock_llm_client.assert_called_once()
        self.assertEqual(len(fake_evaluator.calls), 1)


    @patch("backend.app.services.rag_store.sqlite_store.get_qa_pairs_by_doc", return_value=[])
    @patch("backend.app.services.rag_store.sqlite_store.upsert_qa_pairs", return_value=1)
    @patch("backend.app.services.organizer.model_client.LLMClient", return_value=_FakeLLM())
    @patch("backend.app.api.routes.get_model_settings")
    @patch("backend.app.api.routes.get_qa_quality_evaluator")
    def test_synthesize_qa_saves_llm_pairs_when_doc_id_is_provided(
        self,
        mock_get_evaluator: unittest.mock.Mock,
        mock_get_settings: unittest.mock.Mock,
        mock_llm_client: unittest.mock.Mock,
        mock_upsert: unittest.mock.Mock,
        mock_get_qa_pairs: unittest.mock.Mock,
    ) -> None:
        mock_get_evaluator.return_value = _FakeEvaluator()
        mock_get_settings.return_value = {
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "LLM_MODEL": "deepseek-chat",
            "QA_QUALITY_EVALUATOR": "lexical_overlap_v1",
        }

        response = synthesize_qa(
            {
                "doc_id": "doc_1",
                "save_mode": "append",
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "title_path": ["chapter"],
                        "content": "Some content",
                    }
                ],
            }
        )

        self.assertEqual(response["saved"], 1)
        self.assertEqual(response["save_mode"], "append")
        saved_doc_id, saved_pairs = mock_upsert.call_args.args
        self.assertEqual(saved_doc_id, "doc_1")
        self.assertEqual(saved_pairs[0]["source"], "llm")
        self.assertEqual(saved_pairs[0]["chunk_id"], "chunk_1")
        self.assertEqual(mock_upsert.call_args.kwargs["replace"], False)



if __name__ == "__main__":
    unittest.main()
