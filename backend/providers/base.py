"""
PrivateProxy — AI Provider base class and factory.
Abstract interface for external AI providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger("privateproxy.providers")


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    @abstractmethod
    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """
        Send anonymized text to the AI provider with full conversation history.

        Args:
            text: The anonymized text (contains tokens, not real PII).
            messages: List of chat messages, e.g. [{"role": "user", "content": "..."}]

        Returns:
            The AI's response text (still containing tokens).
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...


def get_provider(
    provider_id: str,
    settings: "Settings",
    model: str | None = None,
) -> Optional[AIProvider]:
    """
    Factory function to create an AI provider instance.

    Args:
        provider_id: Provider identifier ('claude', 'openai', 'gemini').
        settings: Application settings with API keys.
        model: Optional specific model ID. Falls back to registry default.

    Returns:
        An AIProvider instance, or None if the provider is not configured.
    """
    from providers.models_registry import get_default_model

    if provider_id == "claude":
        if not settings.anthropic_api_key:
            logger.error("Claude provider requested but ANTHROPIC_API_KEY not set")
            return None
        from providers.claude_provider import ClaudeProvider
        return ClaudeProvider(
            api_key=settings.anthropic_api_key,
            model=model or get_default_model("claude"),
        )

    elif provider_id == "openai":
        if not settings.openai_api_key:
            logger.error("OpenAI provider requested but OPENAI_API_KEY not set")
            return None
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=model or get_default_model("openai"),
        )

    elif provider_id == "gemini":
        if not settings.google_ai_api_key:
            logger.error("Gemini provider requested but GOOGLE_AI_API_KEY not set")
            return None
        from providers.gemini_provider import GeminiProvider
        return GeminiProvider(
            api_key=settings.google_ai_api_key,
            model=model or get_default_model("gemini"),
        )

    else:
        logger.error(f"Unknown provider: {provider_id}")
        return None

