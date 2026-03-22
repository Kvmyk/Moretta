"""
Moretta — PII Replacer.
Generates UUID-based tokens and substitutes PII in text.
"""

from __future__ import annotations

import uuid
from typing import Any

# ── Type → Token Prefix mapping ───────────────────────────────────

_TYPE_PREFIX = {
    "PERSON": "OSOBA",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "TELEFON",
    "IBAN_CODE": "IBAN",
    "PESEL": "PESEL",
    "NIP": "NIP",
    "NRP": "PESEL",
    "LOCATION": "ADRES",
    "DATE_TIME": "DATA",
    "CREDIT_CARD": "KARTA",
    "CRYPTO": "CRYPTO",
    "IP_ADDRESS": "IP",
    "SALARY": "KWOTA",
    "FINANCIAL": "KWOTA",
    "PROJECT_ID": "PROJEKT",
    "CLIENT_NAME": "KLIENT",
    "CONTRACT_NUMBER": "UMOWA",
    "INTERNAL_ID": "ID_WEWN",
}


class PiiReplacer:
    """Replaces PII in text with UUID-based tokens."""

    def anonymize(
        self,
        text: str,
        pii_items: list[dict[str, Any]],
    ) -> tuple[str, dict[str, str]]:
        """
        Replace all PII occurrences in text with tokens.

        Returns:
            (anonymized_text, token_map) where token_map is {token: original_value}
        """
        if not pii_items:
            return text, {}

        token_map: dict[str, str] = {}
        # Keep a cache so the same PII text gets the same token
        text_to_token: dict[str, str] = {}

        # Sort PII by position (end → start) so replacements don't shift indices
        sorted_items = sorted(pii_items, key=lambda x: x.get("start", 0), reverse=True)

        anonymized = text
        for item in sorted_items:
            original_text = item.get("text", "")
            pii_type = item.get("type", "UNKNOWN")
            start = item.get("start", 0)
            end = item.get("end", 0)

            if not original_text:
                continue

            # Reuse token for identical text
            cache_key = f"{pii_type}:{original_text}"
            if cache_key in text_to_token:
                token = text_to_token[cache_key]
            else:
                token = self._generate_token(pii_type)
                text_to_token[cache_key] = token
                token_map[token] = original_text

            # Replace at exact position if possible, fallback to first occurrence
            if start >= 0 and end > start and end <= len(anonymized):
                if anonymized[start:end] == original_text:
                    anonymized = anonymized[:start] + token + anonymized[end:]
                    continue

            # Fallback: replace first occurrence
            anonymized = anonymized.replace(original_text, token, 1)

        return anonymized, token_map

    @staticmethod
    def _generate_token(pii_type: str) -> str:
        """Generate a UUID-based token like [OSOBA_a3f2]."""
        prefix = _TYPE_PREFIX.get(pii_type, pii_type.upper())
        short_uuid = uuid.uuid4().hex[:4]
        return f"[{prefix}_{short_uuid}]"
