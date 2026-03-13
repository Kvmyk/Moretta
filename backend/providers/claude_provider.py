"""
PrivateProxy — Anthropic Claude AI Provider.
"""

from __future__ import annotations

import logging

import anthropic

from providers.base import AIProvider

logger = logging.getLogger("privateproxy.providers.claude")


class ClaudeProvider(AIProvider):
    """Anthropic Claude API integration."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4.6-20260217") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return "Claude (Anthropic)"

    async def process(self, text: str, instruction: str) -> str:
        """Send anonymized text to Claude for processing."""
        logger.info(f"Sending request to Claude ({self._model})")

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Instrukcja: {instruction}\n\n"
                        f"Poniżej znajduje się tekst dokumentu do przetworzenia. "
                        f"Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to "
                        f"zamaskowane dane — zachowaj je bez zmian w odpowiedzi.\n\n"
                        f"Tekst:\n{text}"
                    ),
                }
            ],
        )

        response_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                response_text += block.text

        logger.info(f"Claude response received: {len(response_text)} chars")
        return response_text
