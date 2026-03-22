"""
Moretta — Ollama Local AI Provider.
Uses the local Ollama instance (same one used for PII detection) as an AI processing provider.
Zero data leaves the local network.
"""

from __future__ import annotations

import logging

import httpx

from providers.base import AIProvider

logger = logging.getLogger("moretta.providers.ollama")


class OllamaProvider(AIProvider):
    """Local Ollama API integration for document processing."""

    def __init__(self, ollama_url: str, model: str = "llama3.3:8b") -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model

    @property
    def name(self) -> str:
        return f"Ollama Local ({self._model})"

    async def process(self, text: str, messages: list[dict[str, str]]) -> str:
        """Send anonymized text and chat history to local Ollama."""
        logger.info(f"Sending request to Ollama ({self._model})")

        system_prompt = (
            "Jesteś asystentem przetwarzającym dokumenty. Twoim zadaniem jest modyfikacja tekstu według instrukcji.\n\n"
            "ZASADY KOMUNIKACJI:\n"
            "1. Jeśli wykonujesz modyfikację dokumentu, zwróć jego PEŁNĄ treść zamkniętą w tagach <ROZWIAZANIE> i </ROZWIAZANIE>. Nie dodawaj wstępów ani komentarzy poza tymi tagami.\n"
            "2. Jeśli instrukcja jest niejasna, brakuje danych lub chcesz coś doprecyzować, napisz normalną wiadomość BEZ używania tagów <ROZWIAZANIE>.\n"
            "3. Tokeny w nawiasach kwadratowych (np. [OSOBA_a3f2]) to zamaskowane dane poufne — zachowaj je bez zmian wewnątrz tagów <ROZWIAZANIE>.\n\n"
            f"Tekst dokumentu do przetworzenia:\n{text}"
        )

        # Build conversation as a single prompt for Ollama /api/generate
        prompt_parts = [f"System: {system_prompt}\n"]
        for msg in messages:
            role = "Użytkownik" if msg["role"] == "user" else "Asystent"
            prompt_parts.append(f"{role}: {msg['content']}\n")
        prompt_parts.append("Asystent: ")

        full_prompt = "\n".join(prompt_parts)

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 4096},
                },
            )
            response.raise_for_status()

        data = response.json()
        response_text = data.get("response", "").strip()
        logger.info(f"Ollama response received: {len(response_text)} chars")
        return response_text
