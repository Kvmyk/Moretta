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

    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """Send anonymized text and chat history to GPT."""
        logger.info(f"Sending request to OpenAI ({self._model})")

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
        logger.info(f"OpenAI response received: {len(response_text)} chars")
        return response_text
