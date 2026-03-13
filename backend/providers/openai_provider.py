"""
PrivateProxy — OpenAI GPT Provider.
"""

from __future__ import annotations

import logging

import openai

from providers.base import AIProvider

logger = logging.getLogger("privateproxy.providers.openai")


class OpenAIProvider(AIProvider):
    """OpenAI GPT API integration."""

    def __init__(self, api_key: str, model: str = "gpt-4.1") -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return "GPT-4.1 (OpenAI)"

    async def process(self, text: str, instruction: str) -> str:
        """Send anonymized text to GPT for processing."""
        logger.info(f"Sending request to OpenAI ({self._model})")

        response = await self._client.chat.completions.create(
            model=self._model,
            max_completion_tokens=4096,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Jesteś asystentem przetwarzającym dokumenty. "
                        "Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to "
                        "zamaskowane dane poufne — zachowaj je bez zmian w odpowiedzi."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Instrukcja: {instruction}\n\nTekst:\n{text}",
                },
            ],
        )

        response_text = response.choices[0].message.content or ""
        logger.info(f"OpenAI response received: {len(response_text)} chars")
        return response_text
