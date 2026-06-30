"""LLM client abstraction with rule-based fallback for content organization.

Provides two tiers:
- RuleBasedTagger: Statistical keyword/entity extraction + extractive
  summarisation. Works offline with jieba + TF-IDF. No API key required.
- LLMClient: langchain-openai wrapper. Supports OpenAI, Ollama, and any
  OpenAI-compatible endpoint. Gracefully degrades to empty responses when
  no API key is configured so callers always have a fallback path.
"""
from __future__ import annotations


import re
from collections import Counter
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from backend.app.services.segmenting.splitter import split_sentences

# ── Regex patterns (reuse where possible from existing code) ────

_TOKENS = re.compile(r"[一-鿿]+|[A-Za-z0-9_]+|[^\s]")

_ENTITY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("percentage", re.compile(r"\d+(?:\.\d+)?%")),
    ("threshold", re.compile(r"[≥≤>=<]+\s*\d+(?:\.\d+)?%?")),
    ("metric", re.compile(
        r"(?:Recall|Precision|nDCG|MRR|F1|ROUGE|BLEU|Accuracy)(?:@\d+)?",
        re.IGNORECASE,
    )),
    ("date", re.compile(r"\d{4}\s*[年/-]\s*\d{1,2}\s*[月/-]\s*\d{1,2}\s*日?")),
    ("version", re.compile(r"[Vv]\d+(?:\.\d+)+")),
    ("org_suffix", re.compile(
        r"[一-鿿]{2,16}(?:大学|学院|研究所|实验室|公司|部门|中心|委员会|课题组|团队|平台|系统|框架|模型)"
    )),
]

# ── Stopwords ──────────────────────────────────────────────

_STOP_WORDS: set[str] = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "所", "为", "所以", "因为", "但是", "然而", "虽然", "如果", "可以",
    "这个", "那个", "这些", "那些", "什么", "怎么", "如何", "为什么",
    "进行", "使用", "通过", "以及", "或者", "其中", "其他", "之后",
    "一种", "用于", "基于", "针对", "关于",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "this", "that", "these", "those", "it", "its", "and", "but", "or",
    "not", "no", "such", "each", "all", "both", "few", "more", "most",
}


class RuleBasedTagger:
    """Statistical keyword / entity tagger and extractive summariser.

    Uses jieba for Chinese word segmentation + sklearn TfidfVectorizer
    for keyword importance scoring.  No GPU or API key needed.
    """

    def __init__(self, max_tags: int = 5) -> None:
        self.max_tags = max_tags
        self._jieba_loaded = False

    # ── public API ──────────────────────────────────────────

    def extract_tags(self, text: str, document_corpus: str = "") -> list[str]:
        """Return up to *max_tags* salient keyword / topic labels."""
        if not text.strip():
            return []

        tokens = self._tokenise(text)
        if not tokens:
            return []

        scored = self._score_tokens(tokens, document_corpus)
        return self._select_top(scored)

    def extract_entities(self, text: str) -> list[dict[str, str]]:
        """Regex-based entity extraction (percentages, metrics, dates, …)."""
        results: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for entity_type, pattern in _ENTITY_PATTERNS:
            for match in pattern.finditer(text or ""):
                value = match.group(0).strip()
                key = (entity_type, value)
                if key not in seen:
                    seen.add(key)
                    results.append({"type": entity_type, "value": value})

        return results

    def generate_summary(self, text: str, max_length: int = 120) -> str:
        """Extractive summary via Lead-1 + TF-IDF sentence scoring."""
        sentences = split_sentences(text)
        if not sentences:
            return text[:max_length].strip()

        if len(sentences) <= 2:
            raw = "".join(sentences).strip()
            return raw[:max_length]

        lead = sentences[0]
        remaining = sentences[1:]

        tokens = self._tokenise(text)
        tf = Counter(tokens)
        total = max(sum(tf.values()), 1)

        def sentence_score(sent: str) -> float:
            sent_tokens = self._tokenise(sent)
            return sum(tf.get(token, 0) / total for token in sent_tokens)

        scored = sorted(remaining, key=sentence_score, reverse=True)

        original_order: dict[str, int] = {
            sent: idx for idx, sent in enumerate(sentences)
        }
        picked = [lead]
        budget = max_length - len(lead)

        for sent in scored:
            if sent == lead:
                continue
            if budget <= 0:
                break
            if len(sent) <= budget + 20:
                picked.append(sent)
                budget -= len(sent)

        picked.sort(key=lambda sent: original_order.get(sent, 99))
        raw = "".join(picked).strip()
        return raw[:max_length]

    # ── internals ───────────────────────────────────────────

    def _tokenise(self, text: str) -> list[str]:
        """Tokenise with jieba (if available) or fallback regex."""
        if not self._jieba_loaded:
            try:
                import jieba  # type: ignore[import-untyped]
                jieba.setLogLevel(20)
                self._jieba_loaded = True
            except ImportError:
                self._jieba_loaded = False

        if self._jieba_loaded:
            import jieba  # type: ignore[import-untyped]
            words: list[str] = []
            for word in jieba.cut(text or ""):
                word = word.strip()
                if len(word) >= 2 and word not in _STOP_WORDS:
                    words.append(word)
            return words

        raw = _TOKENS.findall(text or "")
        return [
            token for token in raw
            if len(token) >= 2 and token.lower() not in _STOP_WORDS
        ]

    def _score_tokens(
        self, tokens: list[str], document_corpus: str
    ) -> list[tuple[str, float]]:
        """TF-IDF scoring with optional document-level IDF."""
        tf = Counter(tokens)
        total = max(sum(tf.values()), 1)

        if document_corpus.strip():
            vectorizer = TfidfVectorizer(
                tokenizer=lambda t: self._tokenise(t),
                lowercase=False,
                max_features=500,
            )
            try:
                vectorizer.fit([document_corpus])
                idf = dict(zip(vectorizer.get_feature_names_out(), vectorizer.idf_))
            except ValueError:
                idf = {}
        else:
            idf = {}

        scored: list[tuple[str, float]] = []
        for token, count in tf.items():
            tf_norm = count / total
            idf_val = idf.get(token, 1.0)
            scored.append((token, tf_norm * idf_val))

        return scored

    def _select_top(self, scored: list[tuple[str, float]]) -> list[str]:
        """Pick top-N tokens, preferring meaningful bigrams."""
        scored.sort(key=lambda item: item[1], reverse=True)
        tokens = [item[0] for item in scored]

        # Bigram candidates
        bigram_tf: dict[str, float] = {}
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}{tokens[i+1]}"
            if len(bigram) <= 12:
                score = scored[i][1] + scored[i + 1][1]
                if bigram not in bigram_tf or score > bigram_tf[bigram]:
                    bigram_tf[bigram] = score
        bigrams = sorted(bigram_tf.items(), key=lambda item: item[1], reverse=True)

        picked: list[str] = []
        seen: set[str] = set()
        for phrase, _score in bigrams:
            if len(picked) >= self.max_tags:
                break
            if phrase not in seen:
                picked.append(phrase)
                seen.add(phrase)

        for token, _score in scored:
            if len(picked) >= self.max_tags:
                break
            if token not in seen:
                picked.append(token)
                seen.add(token)

        return picked


# ── LLM client ────────────────────────────────────────────


class LLMClient:
    """Thin wrapper around langchain-openai ChatOpenAI.

    Gracefully degrades: every method returns ``""`` when no API key is
    configured, so callers always have a fallback path.
    """

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> str:
        """One-shot completion. Returns ``""`` on any failure."""
        if not self.api_key:
            return ""

        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            return ""

        try:
            llm = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            messages: list[tuple[str, str]] = []
            if system_prompt:
                messages.append(("system", system_prompt))
            messages.append(("user", prompt))
            response = llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            print(f"LLM error error: {e}")
            return ""
