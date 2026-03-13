"""
PrivateProxy — Google Gemini AI Provider.
"""

from __future__ import annotations

import logging

import google.generativeai as genai

from providers.base import AIProvider

logger = logging.getLogger("privateproxy.providers.gemini")


class GeminiProvider(AIProvider):
    """Google Gemini API integration."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(model)

    @property
    def name(self) -> str:
        return "Gemini 2.5 Flash (Google)"

    async def process(self, text: str, instruction: str) -> str:
        """Send anonymized text to Gemini for processing."""
        logger.info(f"Sending request to Gemini ({self._model_name})")

        prompt = (
            f"Instrukcja: {instruction}\n\n"
            f"Poniżej znajduje się tekst dokumentu do przetworzenia. "
            f"Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to "
            f"zamaskowane dane poufne — zachowaj je bez zmian w odpowiedzi.\n\n"
            f"Tekst:\n{text}"
        )

        response = await self._model.generate_content_async(prompt)
        response_text = response.text or ""

        logger.info(f"Gemini response received: {len(response_text)} chars")
        return response_text
