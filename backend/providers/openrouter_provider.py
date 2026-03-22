"""
Moretta — OpenRouter AI Provider.
OpenRouter aggregates 200+ models from multiple providers (Anthropic, OpenAI, Google, Meta, Mistral, etc.)
via a single OpenAI-compatible API endpoint.
https://openrouter.ai/docs
"""

from __future__ import annotations

import logging

import openai

from providers.base import AIProvider

logger = logging.getLogger("moretta.providers.openrouter")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(AIProvider):
    """OpenRouter multi-model API integration (OpenAI-compatible)."""

    def __init__(self, api_key: str, model: str = "anthropic/claude-sonnet-4") -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://moretta.local",
                "X-Title": "Moretta",
            },
        )
        self._model = model

    @property
    def name(self) -> str:
        return f"OpenRouter ({self._model})"

    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """Send anonymized text and chat history to OpenRouter."""
        logger.info(f"Sending request to OpenRouter ({self._model})")

        formatted_messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś asystentem przetwarzającym dokumenty. Twoim zadaniem jest modyfikacja tekstu według instrukcji.\n\n"
                    "ZASADY KOMUNIKACJI:\n"
                    "1. Jeśli wykonujesz modyfikację dokumentu, zwróć jego PEŁNĄ treść zamkniętą w tagach <ROZWIAZANIE> i </ROZWIAZANIE>. Nie dodawaj wstępów ani komentarzy poza tymi tagami.\n"
                    "2. Jeśli instrukcja jest niejasna, brakuje danych lub chcesz coś doprecyzować, napisz normalną wiadomość BEZ używania tagów <ROZWIAZANIE>.\n"
                    "3. Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to zamaskowane dane poufne — zachowaj je bez zmian wewnątrz tagów <ROZWIAZANIE>.\n\n"
                    f"Tekst bazowego dokumentu:\n{text}"
                ),
            }
        ]
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        response = await self._client.chat.completions.create(
            model=self._model,
            max_completion_tokens=4096,
            messages=formatted_messages,
        )

        response_text = response.choices[0].message.content or ""
        logger.info(f"OpenRouter response received: {len(response_text)} chars")
        return response_text
