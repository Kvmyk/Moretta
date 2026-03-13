"""
PrivateProxy — PII Detection pipeline.
Stage 1: Microsoft Presidio (deterministic, rule-based)
Stage 2: Local LLM via Ollama (contextual, business-specific)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

logger = logging.getLogger("privateproxy.detector")

# ── Polish PII type names ──────────────────────────────────────────

PII_TYPE_REMAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL_ADDRESS",
    "PHONE_NUMBER": "PHONE_NUMBER",
    "IBAN_CODE": "IBAN_CODE",
    "NRP": "PESEL",
    "LOCATION": "LOCATION",
    "DATE_TIME": "DATE_TIME",
    "CREDIT_CARD": "CREDIT_CARD",
    "CRYPTO": "CRYPTO",
    "IP_ADDRESS": "IP_ADDRESS",
}


class PiiDetector:
    """Two-stage PII detection: Presidio + Ollama LLM."""

    def __init__(self, ollama_url: str, model: str) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model

        # Initialize Presidio with Polish NLP
        try:
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "pl", "model_name": "pl_core_news_sm"}],
            }
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
            self._analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                supported_languages=["pl", "en"],
            )
            logger.info("Presidio analyzer initialized with Polish NLP")
        except Exception as exc:
            logger.warning(f"Failed to initialize Presidio with Polish NLP: {exc}. Falling back to English.")
            self._analyzer = AnalyzerEngine()

    async def detect(self, text: str) -> list[dict[str, Any]]:
        """Run both detection stages and merge results."""
        results: list[dict[str, Any]] = []

        # Stage 1: Presidio
        presidio_results = self._detect_presidio(text)
        results.extend(presidio_results)
        logger.info(f"Presidio detected {len(presidio_results)} PII entities")

        # Stage 2: Ollama LLM
        try:
            ollama_results = await self._detect_ollama(text)
            # Deduplicate against Presidio results
            for item in ollama_results:
                if not self._is_duplicate(item, results):
                    results.append(item)
            logger.info(f"Ollama detected {len(ollama_results)} additional PII entities")
        except Exception as exc:
            logger.warning(f"Ollama detection failed (continuing with Presidio only): {exc}")

        return results

    def _detect_presidio(self, text: str) -> list[dict[str, Any]]:
        """Stage 1: Deterministic PII detection via Presidio."""
        results = []

        # Try Polish first, then English
        for lang in ["pl", "en"]:
            try:
                analyzer_results: list[RecognizerResult] = self._analyzer.analyze(
                    text=text,
                    language=lang,
                    entities=list(PII_TYPE_REMAP.keys()),
                    score_threshold=0.4,
                )
                for r in analyzer_results:
                    pii_type = PII_TYPE_REMAP.get(r.entity_type, r.entity_type)
                    results.append({
                        "text": text[r.start:r.end],
                        "type": pii_type,
                        "start": r.start,
                        "end": r.end,
                        "score": r.score,
                        "source": "presidio",
                    })
                if results:
                    break  # Got results from this language
            except Exception as exc:
                logger.debug(f"Presidio analysis for '{lang}' failed: {exc}")

        return results

    async def _detect_ollama(self, text: str) -> list[dict[str, Any]]:
        """Stage 2: Contextual PII detection via local LLM (Ollama)."""
        # Truncate very long texts to fit model context
        MAX_CHARS = 8000
        fragment = text[:MAX_CHARS] if len(text) > MAX_CHARS else text

        prompt = (
            "Przeanalizuj poniższy tekst. Zwróć w formacie JSON listę dodatkowych "
            "danych poufnych, których mogło nie wykryć standardowe narzędzie. "
            "Szczególną uwagę zwróć na: imiona i nazwiska (jako typ: PERSON) oraz "
            "pełne adresy zamieszkania/pobytu (jako typ: LOCATION). "
            "Szukaj też innych danych: kody projektów, wewnętrzne ID, nazwy klientów, kwoty finansowe. "
            "Format: "
            '[{"text": "...", "type": "...", "start": N, "end": N}]\n\n'
            "Jeśli nie znajdziesz żadnych dodatkowych danych poufnych, zwróć: []\n\n"
            f"Tekst: {fragment}"
        )

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
            )
            response.raise_for_status()

        data = response.json()
        raw_response = data.get("response", "").strip()

        # Parse JSON from LLM response
        try:
            # Try to extract JSON array from response
            start_idx = raw_response.find("[")
            end_idx = raw_response.rfind("]")
            if start_idx != -1 and end_idx != -1:
                json_str = raw_response[start_idx:end_idx + 1]
                items = json.loads(json_str)
            else:
                items = []
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse Ollama JSON response: {raw_response[:200]}")
            items = []

        results = []
        for item in items:
            if isinstance(item, dict) and "text" in item and "type" in item:
                results.append({
                    "text": item["text"],
                    "type": item.get("type", "UNKNOWN"),
                    "start": item.get("start", 0),
                    "end": item.get("end", 0),
                    "score": 0.7,
                    "source": "ollama",
                })

        return results

    @staticmethod
    def _is_duplicate(
        item: dict[str, Any],
        existing: list[dict[str, Any]],
        overlap_threshold: float = 0.5,
    ) -> bool:
        """Check if a detected PII overlaps significantly with existing detections."""
        for ex in existing:
            overlap_start = max(item.get("start", 0), ex.get("start", 0))
            overlap_end = min(item.get("end", 0), ex.get("end", 0))
            if overlap_end > overlap_start:
                overlap_len = overlap_end - overlap_start
                item_len = item.get("end", 0) - item.get("start", 0)
                if item_len > 0 and overlap_len / item_len >= overlap_threshold:
                    return True
        return False
