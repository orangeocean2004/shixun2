from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

DEFAULT_QA_QUALITY_EVALUATOR = "lexical_overlap_v1"

_TOKEN_PATTERN = re.compile(r"[一-鿿\w]+")


@dataclass
class QAQualityResult:
    answerable: bool
    answerable_score: float
    faithful: bool
    faithful_score: float
    quality_score: float


class QAQualityEvaluator(Protocol):
    name: str

    def evaluate(self, question: str, answer: str, content: str) -> QAQualityResult:
        pass


class LexicalOverlapQualityEvaluator:
    name = DEFAULT_QA_QUALITY_EVALUATOR

    def evaluate(self, question: str, answer: str, content: str) -> QAQualityResult:
        del question
        normalized_answer = (answer or "").strip().lower()
        normalized_content = (content or "").strip().lower()

        if not normalized_answer or not normalized_content:
            return QAQualityResult(
                answerable=False,
                answerable_score=0.0,
                faithful=False,
                faithful_score=0.0,
                quality_score=0.0,
            )

        answer_words = set(_TOKEN_PATTERN.findall(normalized_answer))
        content_words = set(_TOKEN_PATTERN.findall(normalized_content))
        overlap = answer_words & content_words
        answerable_score = len(overlap) / max(len(answer_words), 1)

        answer_ngrams = _extract_ngrams(normalized_answer, 2)
        if answer_ngrams:
            faithful_score = sum(1 for ngram in answer_ngrams if ngram in normalized_content) / len(answer_ngrams)
        else:
            faithful_score = answerable_score

        quality_score = (answerable_score + faithful_score) / 2
        return QAQualityResult(
            answerable=answerable_score >= 0.3,
            answerable_score=round(answerable_score, 3),
            faithful=faithful_score >= 0.5,
            faithful_score=round(faithful_score, 3),
            quality_score=round(quality_score, 3),
        )


_EVALUATOR_FACTORIES: dict[str, type[QAQualityEvaluator]] = {
    LexicalOverlapQualityEvaluator.name: LexicalOverlapQualityEvaluator,
}


def get_qa_quality_evaluator(name: str | None = None) -> QAQualityEvaluator:
    evaluator_name = (name or DEFAULT_QA_QUALITY_EVALUATOR).strip().lower() or DEFAULT_QA_QUALITY_EVALUATOR
    factory = _EVALUATOR_FACTORIES.get(evaluator_name)
    if factory is None:
        factory = _EVALUATOR_FACTORIES[DEFAULT_QA_QUALITY_EVALUATOR]
    return factory()


def list_qa_quality_evaluators() -> tuple[str, ...]:
    return tuple(sorted(_EVALUATOR_FACTORIES.keys()))


def _extract_ngrams(text: str, n: int) -> list[str]:
    words = _TOKEN_PATTERN.findall(text)
    if len(words) < n:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
