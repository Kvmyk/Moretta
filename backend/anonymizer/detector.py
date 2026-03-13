"""
PrivateProxy — PII Detection pipeline.
Stage 1: Microsoft Presidio (deterministic, rule-based)
Stage 2: Local LLM via Ollama (contextual, business-specific)
"""

from __future__ import annotations

import json
import logging
from typing import Any
import re
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

# ── Custom Regex Patterns for Polish Data ──────────────────────────

POLISH_REGEX_RULES = [
    {
        "type": "NIP",
        # Obiekty typu 123-456-78-19, 1234567819, 123-45-67-819
        "pattern": r"\b[0-9]{3}-?[0-9]{2}-?[0-9]{2}-?[0-9]{3}\b|\b[0-9]{3}-?[0-9]{3}-?[0-9]{2}-?[0-9]{2}\b",
    },
    {
        "type": "REGON",
        # 9 or 14 digits
        "pattern": r"\b[0-9]{9}\b|\b[0-9]{14}\b",
    },
    {
        "type": "PHONE_NUMBER",
        # Polish numbers with optional +48/0048 and spaces/dashes
        "pattern": r"(?:\+48|0048)?\s*(?:[1-9][0-9]{2}[\s\-]?[0-9]{3}[\s\-]?[0-9]{3}|[1-9][0-9][\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2})\b",
    },
    {
        "type": "KRS",
        "pattern": r"\b0000[0-9]{6}\b",
    },
    {
        "type": "PESEL",
        "pattern": r"\b[0-9]{11}\b",
    },
    {
        "type": "IBAN_CODE",
        # Standard Polish IBAN is 26 digits, sometimes prefixed with PL
        "pattern": r"\b(?:PL)?[\s]*[0-9]{2}[\s]*[0-9]{4}[\s]*[0-9]{4}[\s]*[0-9]{4}[\s]*[0-9]{4}[\s]*[0-9]{4}[\s]*[0-9]{4}\b",
    }
]

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

        # Stage 2: Custom Regex (replaces unreliable Ollama)
        regex_results = self._detect_regex(text)
        # Deduplicate against Presidio results
        for item in regex_results:
            if not self._is_duplicate(item, results):
                results.append(item)
        logger.info(f"Custom Regex detected {len(regex_results)} additional PII entities")

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

    def _detect_regex(self, text: str) -> list[dict[str, Any]]:
        """Stage 2: Deterministic Regex-based detection for Polish business formats."""
        results = []

        for rule in POLISH_REGEX_RULES:
            pattern = re.compile(rule["pattern"], re.IGNORECASE)
            for match in pattern.finditer(text):
                results.append({
                    "text": match.group(),
                    "type": rule["type"],
                    "start": match.start(),
                    "end": match.end(),
                    "score": 0.85,
                    "source": "regex",
                })

        # Optymalizacja: usuwamy te regexy, które nachodzą na siebie (np. regex PESEL wewnątrz regex IBAN)
        filtered_results = []
        for item in sorted(results, key=lambda x: x["end"] - x["start"], reverse=True): # Najpierw najdłuższe (IBAN > PESEL)
            if not self._is_duplicate(item, filtered_results, overlap_threshold=0.1):
                filtered_results.append(item)

        return filtered_results

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

    async def detect_deep_async(self, text: str, existing_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stage 2: Asynchronous Deep Scan via local LLM (Ollama)."""
        # Truncate very long texts to fit model context
        MAX_CHARS = 8000
        fragment = text[:MAX_CHARS] if len(text) > MAX_CHARS else text

        prompt = (
            "Przeanalizuj poniższy tekst biznesowy pod kątem wycieków danych (Data Leak Prevention). "
            "Zwróć w formacie JSON listę poufnych informacji, takich jak nazwy tajnych projektów, "
            "kwoty finansowe powiązane z osobami, wewnętrzne ID, czy stanowiska zarządu ukryte w tekście. "
            "UWAGA: Pomiń standardowe rzeczy jak PESEL czy NIP, szukaj tylko nieoczywistych, dających się powiązać z osobą danych.\n\n"
            "Format wyjściowy (zawsze jako poprawna tablica JSON, NIC WIECEJ):\n"
            '[{"text": "znaleziony fragment", "type": "OTHER_PII", "start": N, "end": N}]\n\n'
            "Jeśli nie znajdziesz żadnych poufnych danych, zwróć dokładnie: []\n\n"
            f"Tekst:\n{fragment}"
        )

        try:
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

            start_idx = raw_response.find("[")
            end_idx = raw_response.rfind("]")
            if start_idx != -1 and end_idx != -1:
                json_str = raw_response[start_idx:end_idx + 1]
                items = json.loads(json_str)
            else:
                items = []
                
            new_results = []
            for item in items:
                if isinstance(item, dict) and "text" in item and "type" in item:
                    # Treat start/end loosely since LLM might hallucinate indexes, fallback to string matching
                    text_found = item["text"]
                    if text_found in text:
                        start_real = text.find(text_found)
                        end_real = start_real + len(text_found)
                        
                        pii_entry = {
                            "text": text_found,
                            "type": item.get("type", "OTHER_PII"),
                            "start": start_real,
                            "end": end_real,
                            "score": 0.6,
                            "source": "ollama_deep",
                        }
                        if not self._is_duplicate(pii_entry, existing_results):
                            new_results.append(pii_entry)
            
            logger.info(f"Ollama deep scan detected {len(new_results)} additional PII entities")
            return new_results

        except Exception as exc:
            logger.warning(f"Ollama deep scan failed: {exc}")
            return []
