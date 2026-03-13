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

    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """Send anonymized text and chat history to Gemini."""
        logger.info(f"Sending request to Gemini ({self._model_name})")

        history = []
        history.append({
            "role": "user",
            "parts": [
                f"Jesteś asystentem przetwarzającym dokumenty. Twoim zadaniem jest modyfikacja tekstu według instrukcji.\n\n"
                f"ZASADY KOMUNIKACJI:\n"
                f"1. Jeśli wykonujesz modyfikację dokumentu, zwróć jego PEŁNĄ treść zamkniętą w tagach <ROZWIAZANIE> i </ROZWIAZANIE>. Nie dodawaj wstępów ani komentarzy poza tymi tagami.\n"
                f"2. Jeśli instrukcja jest niejasna, brakuje danych lub chcesz coś doprecyzować, napisz normalną wiadomość BEZ używania tagów <ROZWIAZANIE>.\n"
                f"3. Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to zamaskowane dane poufne — zachowaj je bez zmian wewnątrz tagów <ROZWIAZANIE>.\n\n"
                f"Tekst dokumentu do przetworzenia:\n{text}"
            ]
        })
        history.append({
            "role": "model",
            "parts": ["Zrozumiałem. Czekam na instrukcje."]
        })
        
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({
                "role": role,
                "parts": [msg["content"]]
            })
            
        chat = self._model.start_chat(history=history)
        
        last_msg = messages[-1]["content"]
        response = await chat.send_message_async(last_msg)
        
        response_text = response.text or ""

        logger.info(f"Gemini response received: {len(response_text)} chars")
        return response_text
