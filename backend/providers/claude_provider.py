"""
Moretta — Anthropic Claude AI Provider.
"""

from __future__ import annotations

import logging

import anthropic

from providers.base import AIProvider

logger = logging.getLogger("moretta.providers.claude")


class ClaudeProvider(AIProvider):
    """Anthropic Claude API integration."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4.6-20260217") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def name(self) -> str:
        return "Claude (Anthropic)"

    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """Send anonymized text and chat history to Claude."""
        logger.info(f"Sending request to Claude ({self._model})")

        system_prompt = (
            f"Jesteś asystentem przetwarzającym dokumenty. Twoim zadaniem jest modyfikacja tekstu według instrukcji.\n\n"
            f"ZASADY KOMUNIKACJI:\n"
            f"1. Jeśli wykonujesz modyfikację dokumentu, zwróć jego PEŁNĄ treść zamkniętą w tagach <ROZWIAZANIE> i </ROZWIAZANIE>. Nie dodawaj wstępów ani komentarzy poza tymi tagami.\n"
            f"2. Jeśli instrukcja jest niejasna, brakuje danych lub chcesz coś doprecyzować, napisz normalną wiadomość BEZ używania tagów <ROZWIAZANIE>.\n"
            f"3. Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to zamaskowane dane poufne — zachowaj je bez zmian wewnątrz tagów <ROZWIAZANIE>.\n\n"
            f"Tekst dokumentu do przetworzenia:\n{text}"
        )
        
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system_prompt,
            messages=formatted_messages,
        )

        response_text = ""
        for block in message.content:
            if hasattr(block, "text"):
                response_text += block.text

        logger.info(f"Claude response received: {len(response_text)} chars")
        return response_text
