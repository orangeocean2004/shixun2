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


class LLMQualityEvaluator:
    """LLM-as-judge for QA answerability and faithfulness.

    Uses the configured LLM to judge whether a question can be answered
    from the given content and whether the answer is faithful (no hallucination).
    """

    name = "llm_judge_v1"

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client

    def evaluate(self, question: str, answer: str, content: str) -> QAQualityResult:
        if not self._llm or not self._llm.is_available:
            return QAQualityResult(
                answerable=False, answerable_score=0.0,
                faithful=False, faithful_score=0.0, quality_score=0.0,
            )

        snippet = content if len(content) <= 2000 else content[:2000]

        # ── Answerability ──
        answerable_prompt = (
            f"原文片段：\n{snippet}\n\n"
            f"问题：{question}\n\n"
            f"请判断：仅根据原文片段的信息，能否完整回答这个问题？\n"
            f"只回答 YES 或 NO，不要解释。"
        )
        answerable_raw = self._llm.generate(
            answerable_prompt,
            system_prompt="你是问答质量评估专家。严格根据原文判断问题的可答性。",
            temperature=0.1,
            max_tokens=16,
        ).strip().upper()
        answerable = "YES" in answerable_raw

        # ── Faithfulness ──
        faithful_prompt = (
            f"原文片段：\n{snippet}\n\n"
            f"问题：{question}\n"
            f"答案：{answer}\n\n"
            f"请判断：答案中的所有信息是否都能在原文片段中找到依据？\n"
            f"答案有没有添加原文没有的事实、数字或判断？\n"
            f"如果没有臆造内容，回答 FAITHFUL；如果有臆造，回答 HALLUCINATION。\n"
            f"只回答 FAITHFUL 或 HALLUCINATION，不要解释。"
        )
        faithful_raw = self._llm.generate(
            faithful_prompt,
            system_prompt="你是问答质量评估专家。严格检查答案是否忠实于原文，不添加原文没有的信息。",
            temperature=0.1,
            max_tokens=16,
        ).strip().upper()
        faithful = "FAITHFUL" in faithful_raw

        answerable_score = 1.0 if answerable else 0.0
        faithful_score = 1.0 if faithful else 0.0
        quality_score = (answerable_score + faithful_score) / 2

        return QAQualityResult(
            answerable=answerable,
            answerable_score=answerable_score,
            faithful=faithful,
            faithful_score=faithful_score,
            quality_score=quality_score,
        )


_EVALUATOR_FACTORIES: dict[str, type[QAQualityEvaluator]] = {
    LexicalOverlapQualityEvaluator.name: LexicalOverlapQualityEvaluator,
    LLMQualityEvaluator.name: LLMQualityEvaluator,
}


def get_qa_quality_evaluator(
    name: str | None = None,
    llm_client = None,
) -> QAQualityEvaluator:
    evaluator_name = (name or DEFAULT_QA_QUALITY_EVALUATOR).strip().lower() or DEFAULT_QA_QUALITY_EVALUATOR
    factory = _EVALUATOR_FACTORIES.get(evaluator_name)
    if factory is None:
        factory = _EVALUATOR_FACTORIES[DEFAULT_QA_QUALITY_EVALUATOR]
    if evaluator_name == LLMQualityEvaluator.name and llm_client is not None:
        return LLMQualityEvaluator(llm_client=llm_client)
    return factory()


def list_qa_quality_evaluators() -> tuple[str, ...]:
    return tuple(sorted(_EVALUATOR_FACTORIES.keys()))


def _extract_ngrams(text: str, n: int) -> list[str]:
    words = _TOKEN_PATTERN.findall(text)
    if len(words) < n:
        return [" ".join(words)] if words else []
    return [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
