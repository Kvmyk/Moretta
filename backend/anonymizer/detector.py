"""
Moretta — PII Detection pipeline.
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

logger = logging.getLogger("moretta.detector")

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
                matched_text = match.group()
                # Strip leading/trailing whitespace and adjust indices
                stripped_text = matched_text.strip()
                if not stripped_text:
                    continue
                    
                start_offset = matched_text.find(stripped_text)
                actual_start = match.start() + start_offset
                actual_end = actual_start + len(stripped_text)
                
                results.append({
                    "text": stripped_text,
                    "type": rule["type"],
                    "start": actual_start,
                    "end": actual_end,
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
                ex_len = ex.get("end", 0) - ex.get("start", 0)
                if item_len > 0 and ex_len > 0:
                    # Treat as duplicate if it significantly completely covers or is covered by another
                    if overlap_len / min(item_len, ex_len) >= overlap_threshold:
                        return True
        return False

    async def detect_deep_async(self, text: str, existing_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Stage 2: Asynchronous Deep Scan via local LLM (Ollama)."""
        # Truncate very long texts to fit model context
        MAX_CHARS = 4000
        fragment = text[:MAX_CHARS] if len(text) > MAX_CHARS else text

        prompt = (
            "Jesteś rygorystycznym, automatycznym systemem DLP (Data Leak Prevention). Zewnętrzny system przetwarza już standardowe dane jak PESEL, NIP, numery telefonów czy IBAN - zignoruj je.\n\n"
            "Twoim JEDYNYM zadaniem jest znalezienie i wyodrębnienie w tekście niestandardowych, ryzykownych danych biznesowych:\n"
            '1. "SECRET_PROJECT": Kryptonimy, nazwy tajnych projektów wewnętrznych i inicjatyw.\n'
            '2. "FINANCE": Kwoty finansowe (wynagrodzenia, premie, wyceny, kary) powiązane bezpośrednio z konkretnymi celami lub osobami.\n'
            '3. "INTERNAL_ID": Wewnętrzne identyfikatory, numery umów, numeracje faktur, zamówień.\n'
            '4. "IT_INFRA": Adresy IP, nazwy prywatnych serwerów, wewnętrzne adresy URL maszyn.\n'
            '5. "PERSON": Imiona i nazwiska, ale *tylko* jeśli występują w ryzykownym, niejawnym kontekście (np. listy zwolnień, tajne premie).\n\n'
            "ZASADY KRYTYCZNE (ZŁAMANIE ICH BĘDZIE SKUTKOWAĆ AWARIĄ SYSTEMU):\n"
            "- MUSISZ odpowiedzieć WYŁĄCZNIE i ZAWSZE jako surowa techniczna tablica JSON.\n"
            '- ZABRONIONE jest dodawanie JAKIEGOKOLWIEK tekstu poza JSON-em (żadnych słów typu "Oto wynik", "Zrozumiałem", żadnych uwag).\n'
            "- ZABRONIONE jest używanie znaczników markdown (np. ```json). Odpowiedź musi zaczynać się jawnie od znaku `[` i kończyć na `]`.\n"
            '- WYCIĄGAJ FRAGMENTY TEKSTU DOKŁADNIE TAK, JAK WYSTĘPUJĄ W ORYGINALE. Literalnie, bez poprawiania gramatyki, bez odmieniania, bez usuwania końcówek. Jeśli w oryginale jest "Projektu", wyciągnij "Projektu", a nie "Projekt".\n'
            '- Detekcja musi być najkrótsza z możliwych (samo słowo/klucz), bez słów wprowadzających.\n'
            '- Zwracane klucze w każdym obiekcie JSON to: "text" (dokładny fragment z tekstu), "type" (odpowiednia kategoria z listy powyżej).\n\n'
            "Przykładowa pożądana odpowiedź:\n"
            "[\n"
            '  {"text": "Projekt Apollo", "type": "SECRET_PROJECT"},\n'
            '  {"text": "10.0.0.5", "type": "IT_INFRA"},\n'
            '  {"text": "FV-2024/03/991", "type": "INTERNAL_ID"}\n'
            "]\n\n"
            "Jeśli w tekście nie ma ŻADNYCH z tych poufnych danych, Twoja cała odpowiedź musi składać się WYŁĄCZNIE Z DWÓCH ZNAKÓW:\n"
            "[]\n\n"
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
                    text_found = item["text"].strip()
                    if not text_found:
                        continue

                    # Try to find all occurrences of this text (case-insensitive)
                    pattern = re.compile(re.escape(text_found), re.IGNORECASE)
                    matches_found = list(pattern.finditer(text))
                    
                    if not matches_found and len(text_found) > 3:
                        # Fallback for Polish declension: if it's a longer string, try matching the prefix 
                        # or allow minor character differences at the end.
                        # We use a fuzzy regex that allows some characters after the word core.
                        core = text_found[:-1] if len(text_found) > 4 else text_found
                        fuzzy_pattern = re.compile(re.escape(core) + r"[a-ząęółńśćźż]{0,3}", re.IGNORECASE)
                        matches_found = list(fuzzy_pattern.finditer(text))

                    for match in matches_found:
                        pii_entry = {
                            "text": text[match.start():match.end()], # Extract ACTUAL literal text
                            "type": item.get("type", "OTHER_PII"),
                            "start": match.start(),
                            "end": match.end(),
                            "score": 0.6,
                            "source": "ollama_deep",
                        }
                        if not self._is_duplicate(pii_entry, existing_results) and not self._is_duplicate(pii_entry, new_results):
                            new_results.append(pii_entry)

            
            logger.info(f"Ollama deep scan finished. Detected {len(new_results)} new entities.")
            return new_results

        except Exception as exc:
            logger.exception("Ollama deep scan failed:")
            return []
