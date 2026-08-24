"""
Moretta — PII Replacer.
Generates UUID-based tokens and substitutes PII in text.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("moretta.replacer")

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
    "SECRET_PROJECT": "PROJEKT_TAJNY",
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

        # Detections come from several stages (Presidio, regex, deep scan) and can
        # overlap. Replacing an overlapping span would corrupt a token that was
        # already written, so keep the first (highest-scoring) of each overlap and
        # discard the rest.
        candidates = [
            item
            for item in pii_items
            if item.get("text") and item.get("end", 0) > item.get("start", -1) >= 0
        ]
        candidates.sort(
            key=lambda x: (-float(x.get("score", 0)), -(x["end"] - x["start"]))
        )

        accepted: list[dict[str, Any]] = []
        claimed: list[tuple[int, int]] = []
        for item in candidates:
            start, end = item["start"], item["end"]
            if any(start < c_end and end > c_start for c_start, c_end in claimed):
                continue
            accepted.append(item)
            claimed.append((start, end))

        # Replace right to left so earlier offsets stay valid.
        accepted.sort(key=lambda x: x["start"], reverse=True)

        anonymized = text
        for item in accepted:
            original_text = item["text"]
            pii_type = item.get("type", "UNKNOWN")
            start, end = item["start"], item["end"]

            # Reuse token for identical text
            cache_key = f"{pii_type}:{original_text}"
            if cache_key in text_to_token:
                token = text_to_token[cache_key]
            else:
                token = self._generate_token(pii_type)
                text_to_token[cache_key] = token
                token_map[token] = original_text

            if end <= len(anonymized) and anonymized[start:end] == original_text:
                anonymized = anonymized[:start] + token + anonymized[end:]
                continue

            # Offsets disagree with the text (stale detection). Fall back to the
            # occurrence closest to the recorded position rather than the first
            # one in the document, which is often an entirely different match.
            replace_at = self._closest_occurrence(anonymized, original_text, start)
            if replace_at is None:
                logger.warning(
                    "Could not place %s token; value not found in text", pii_type
                )
                # Drop the unused token so the vault never advertises a mapping
                # that does not appear in the anonymized text.
                if token_map.get(token) == original_text and token not in anonymized:
                    token_map.pop(token, None)
                    text_to_token.pop(cache_key, None)
                continue

            anonymized = (
                anonymized[:replace_at]
                + token
                + anonymized[replace_at + len(original_text):]
            )

        return anonymized, token_map

    @staticmethod
    def _closest_occurrence(text: str, needle: str, expected_start: int) -> int | None:
        """Return the occurrence of `needle` nearest to `expected_start`."""
        positions = []
        index = text.find(needle)
        while index != -1:
            positions.append(index)
            index = text.find(needle, index + 1)

        if not positions:
            return None
        return min(positions, key=lambda pos: abs(pos - expected_start))

    @staticmethod
    def _generate_token(pii_type: str) -> str:
        """Generate a UUID-based token like [OSOBA_a3f2]."""
        prefix = _TYPE_PREFIX.get(pii_type, pii_type.upper())
        short_uuid = uuid.uuid4().hex[:4]
        return f"[{prefix}_{short_uuid}]"
