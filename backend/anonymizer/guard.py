"""
Moretta — AI Security Guard (Prompt DLP).
Uses a local LLM to verify if user instructions contain unauthorized PII.
"""

from __future__ import annotations

import httpx
import logging

logger = logging.getLogger("moretta.guard")


class SecurityGuard:
    """Verifies user instructions for data leaks before sending to external AI."""

    def __init__(self, ollama_url: str, model: str) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model

    async def check_instruction(self, instruction: str) -> bool:
        """
        Check if the instruction contains sensitive data.
        Returns True if safe, False if a leak is detected.
        """
        if not instruction.strip():
            return True

        prompt = (
            "Jesteś systemem DLP (Data Leak Prevention). Zbadaj instrukcję Użytkownika pod kątem wycieku DANYCH OSOBOWYCH. "
            "Szukasz tylko: Imię i Nazwisko, PESEL, numer konta, hasło, numer dowodu. "
            "Ogólne pojęcia takie jak 'umowa', 'faktura', 'B2B', 'UoP', 'projekt' SĄ W PEŁNI BEZPIECZNE (CZYSTE).\n\n"
            "ZASADY WYJŚCIA:\n"
            "1. Zwróć WYŁĄCZNIE słowo: CZYSTE (jeśli tekst zawiera tylko polecenia lub ogólne nazwy, np. 'popraw umowę B2B').\n"
            "2. Zwróć WYŁĄCZNIE słowo: ZAGROZENIE (jeśli tekst jawnie zawiera imię i nazwisko, pesel itp.).\n"
            "3. Nie dodawaj żadnych innych słów.\n\n"
            f"Instrukcja do weryfikacji:\n{instruction}\n\n"
            "Odpowiedź (CZYSTE/ZAGROZENIE):"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.0},
                    },
                )
                response.raise_for_status()

            data = response.json()
            raw_response = data.get("response", "").strip().upper()

            if "ZAGROZENIE" in raw_response and "CZYSTE" not in raw_response:
                logger.warning(f"Security Guard BLOCKED prompt ({len(instruction)} chars). LLM verdict: {raw_response}")
                return False
            
            # If it responds with CZYSTE or hallucinated something else, allow
            logger.info(f"Security Guard check PASSED ({len(instruction)} chars)")
            return True

        except Exception as exc:
            logger.critical(f"Security Guard check failed (BLOCKING request): {exc}")
            # Fail-closed: if the local LLM is down, we block the request for safety.
            return False
