"""Content organisation service — tagging, summarisation, entity labelling.

``ContentOrganizer`` is the main entry-point.  It tries LLM-based generation
when an ``LLMClient`` is provided, falling back to ``RuleBasedTagger``
otherwise (or if the LLM call fails).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.services.model_client import LLMClient, RuleBasedTagger


# ── Prompt templates (kept short for low-latency LLM calls) ─

_TAG_SYSTEM = (
    "你是内容标注专家。请为文档片段生成2-5个简洁的主题/关键词标签。"
    "每个标签一行，以\"- \"开头。标签应为名词短语（≤8字），"
    "避免过于泛化的词（如\"内容\"、\"文档\"）。"
)

_SUMMARY_SYSTEM = (
    "你是内容摘要专家。请为文档片段写一句话摘要（≤80字）。"
    "只描述原文已有信息，不添加原文没有的内容。保持客观中立。"
)

_ENTITY_SYSTEM = (
    "你是实体识别专家。从文本中提取实体。"
    "类型：指标名称、百分比、日期、机构、版本号。"
    "每行格式：\"类型: 值\"。无实体则输出\"无\"。"
)


# ── Data structures ───────────────────────────────────────


@dataclass
class OrganizeResult:
    """Per-chunk organisation output."""

    tags: list[str] = field(default_factory=list)
    summary: str = ""
    entity_labels: list[dict[str, str]] = field(default_factory=list)


# ── Content organiser ─────────────────────────────────────


class ContentOrganizer:
    """Orchestrate tagging + summarisation + entity extraction.

    Parameters
    ----------
    llm_client:
        Optional ``LLMClient``.  When provided *and* available the organiser
        uses LLM prompts; otherwise it falls back to ``RuleBasedTagger``.
    """

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm = llm_client
        self._rule = RuleBasedTagger(max_tags=5)

    # ── single-chunk API ──────────────────────────────────

    def organize_chunk(
        self,
        content: str,
        document_context: str = "",
    ) -> OrganizeResult:
        """Tag + summarise + extract entities for a single chunk."""
        if self._llm and self._llm.is_available:
            result = self._llm_organize(content, document_context)
            if result.tags or result.summary:
                return result

        return self._rule_organize(content, document_context)

    # ── batch API ─────────────────────────────────────────

    def organize_batch(
        self,
        chunks: list[dict],
        doc_id: str = "",
    ) -> tuple[list[OrganizeResult], str]:
        """Process all chunks in one pass and also produce a document summary.

        Returns
        -------
        (per_chunk_results, document_summary)
        """
        # Build document-level corpus for IDF computation.
        corpus = "\n\n".join(
            chunk.get("content", "") for chunk in chunks
        )

        per_chunk: list[OrganizeResult] = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if not content.strip():
                per_chunk.append(OrganizeResult())
                continue
            per_chunk.append(self.organize_chunk(content, corpus))

        doc_summary = self._build_document_summary(per_chunk)
        return per_chunk, doc_summary

    # ── LLM path ──────────────────────────────────────────

    def _llm_organize(
        self, content: str, context: str
    ) -> OrganizeResult:
        """Try LLM-based tagging / summarisation / entity extraction."""
        assert self._llm is not None

        # Trim content if it is very long to keep prompts small.
        snippet = content if len(content) <= 2000 else content[:2000]

        tags = self._parse_tag_response(
            self._llm.generate(
                f"文档上下文：{context[:500]}\n\n片段内容：\n{snippet}",
                system_prompt=_TAG_SYSTEM,
                temperature=0.2,
                max_tokens=128,
            )
        )

        summary = self._llm.generate(
            f"片段内容：\n{snippet}",
            system_prompt=_SUMMARY_SYSTEM,
            temperature=0.2,
            max_tokens=128,
        ).strip()

        entities = self._parse_entity_response(
            self._llm.generate(
                f"{snippet}",
                system_prompt=_ENTITY_SYSTEM,
                temperature=0.1,
                max_tokens=128,
            )
        )

        return OrganizeResult(tags=tags, summary=summary, entity_labels=entities)

    # ── Rule-based path ───────────────────────────────────

    def _rule_organize(
        self, content: str, document_context: str
    ) -> OrganizeResult:
        return OrganizeResult(
            tags=self._rule.extract_tags(content, document_context),
            summary=self._rule.generate_summary(content, max_length=120),
            entity_labels=self._rule.extract_entities(content),
        )

    # ── Document summary ──────────────────────────────────

    def _build_document_summary(
        self, results: list[OrganizeResult], max_length: int = 300
    ) -> str:
        """Aggregate per-chunk summaries into a document-level summary."""
        summaries = [r.summary for r in results if r.summary]
        if not summaries:
            return ""

        if self._llm and self._llm.is_available:
            prompt = (
                "请将以下片段摘要合并为一段文档级摘要（≤200字），"
                "按原文顺序概括核心内容：\n\n"
                + "\n".join(f"- {s}" for s in summaries)
            )
            doc_summary = self._llm.generate(
                prompt,
                system_prompt="你是文档摘要专家。请生成一段连贯的文档摘要。",
                temperature=0.3,
                max_tokens=256,
            ).strip()
            if doc_summary:
                return doc_summary

        raw = "；".join(summaries)
        return raw[:max_length]

    # ── Response parsers ──────────────────────────────────

    @staticmethod
    def _parse_tag_response(response: str) -> list[str]:
        """Parse ``- 标签1\\n- 标签2`` into a flat list."""
        tags: list[str] = []
        for line in (response or "").splitlines():
            line = line.strip()
            if line.startswith("-"):
                tag = line.lstrip("- ").strip()
                if tag and len(tag) <= 20:
                    tags.append(tag)
            elif line and not line.startswith("#"):
                # Some models output comma-separated tags.
                for part in line.split(","):
                    part = part.strip().lstrip("0123456789.、) ").strip()
                    if part and len(part) <= 20:
                        tags.append(part)
        return tags[:5]

    @staticmethod
    def _parse_entity_response(response: str) -> list[dict[str, str]]:
        """Parse ``类型: 值`` lines into typed entity dicts."""
        entities: list[dict[str, str]] = []
        for line in (response or "").splitlines():
            line = line.strip()
            if ":" in line or "：" in line:
                line = line.replace("：", ":")
                parts = line.split(":", 1)
                if len(parts) == 2:
                    etype = parts[0].strip()
                    value = parts[1].strip()
                    if etype and value and value != "无":
                        entities.append({"type": etype, "value": value})
        return entities
