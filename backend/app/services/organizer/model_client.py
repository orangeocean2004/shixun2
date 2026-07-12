"""LLM client for content organization (tagging, summarisation, entity extraction).

Provides a thin wrapper around langchain-openai ChatOpenAI. Supports OpenAI,
Ollama, and any OpenAI-compatible endpoint.

No rule-based fallback — LLM is the only path for tag and summary generation.
"""

from __future__ import annotations

from typing import Any

from backend.app.main import logger


class LLMClient:
    """Thin wrapper around langchain-openai ChatOpenAI.

    Returns ``""`` when no API key is configured so callers can detect
    unavailability and respond accordingly.
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
            from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
        except ImportError:
            return ""

        try:
            llm = ChatOpenAI(
                model=self.model,
                api_key=self.api_key,
                base_url=self.base_url,
                temperature=temperature,
                max_tokens=max_tokens,
                request_timeout=30,
            )
            messages: list[tuple[str, str]] = []
            if system_prompt:
                messages.append(("system", system_prompt))
            messages.append(("user", prompt))
            response = llm.invoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"[LLMClient] generate failed: {e}")
            return ""
