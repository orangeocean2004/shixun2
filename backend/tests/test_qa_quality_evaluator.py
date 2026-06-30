from __future__ import annotations

import unittest

from backend.app.services.qa_quality.evaluator import (
    DEFAULT_QA_QUALITY_EVALUATOR,
    LexicalOverlapQualityEvaluator,
    get_qa_quality_evaluator,
    list_qa_quality_evaluators,
)


class QAQualityEvaluatorTest(unittest.TestCase):
    def test_registry_contains_default(self) -> None:
        evaluators = set(list_qa_quality_evaluators())
        self.assertIn(DEFAULT_QA_QUALITY_EVALUATOR, evaluators)

    def test_unknown_evaluator_falls_back_to_default(self) -> None:
        evaluator = get_qa_quality_evaluator("unknown_evaluator")
        self.assertIsInstance(evaluator, LexicalOverlapQualityEvaluator)

    def test_default_evaluator_scoring(self) -> None:
        evaluator = get_qa_quality_evaluator(DEFAULT_QA_QUALITY_EVALUATOR)

        result = evaluator.evaluate(
            question="what is this",
            answer="alpha beta gamma",
            content="alpha beta delta",
        )

        self.assertTrue(result.answerable)
        self.assertEqual(result.answerable_score, 0.667)
        self.assertTrue(result.faithful)
        self.assertEqual(result.faithful_score, 0.5)
        self.assertEqual(result.quality_score, 0.583)

    def test_empty_answer_returns_zero_scores(self) -> None:
        evaluator = get_qa_quality_evaluator(DEFAULT_QA_QUALITY_EVALUATOR)

        result = evaluator.evaluate(
            question="what is this",
            answer="",
            content="alpha beta delta",
        )

        self.assertFalse(result.answerable)
        self.assertEqual(result.answerable_score, 0.0)
        self.assertFalse(result.faithful)
        self.assertEqual(result.faithful_score, 0.0)
        self.assertEqual(result.quality_score, 0.0)


if __name__ == "__main__":
    unittest.main()
