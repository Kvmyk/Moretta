"""
Moretta — Reinjektor.
Replaces UUID tokens in AI responses with original PII values from the vault.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("moretta.reinjektor")

# Pattern to match tokens like [OSOBA_a3f2], [KWOTA_b8c1], etc.
TOKEN_PATTERN = re.compile(r"\[[A-ZĄĆĘŁŃÓŚŹŻ_]+_[a-f0-9]{4}\]")


class Reinjektor:
    """Reinjects original PII data into AI-processed text by replacing tokens."""

    def reinject(
        self,
        ai_response: str,
        token_map: dict[str, str],
    ) -> tuple[str, list[str]]:
        """
        Replace all tokens in the AI response with original PII values.

        Args:
            ai_response: Text returned by the external AI (contains tokens).
            token_map: Mapping of token → original PII value.

        Returns:
            (reinjected_text, unresolved_tokens) where unresolved_tokens
            lists any tokens found in text but missing from the map.
        """
        if not token_map:
            return ai_response, []

        result = ai_response
        used_tokens: set[str] = set()
        unresolved: list[str] = []

        # Replace known tokens
        for token, original_value in token_map.items():
            if token in result:
                result = result.replace(token, original_value)
                used_tokens.add(token)

        # Check for any remaining tokens that weren't in our map
        remaining_tokens = TOKEN_PATTERN.findall(result)
        for token in remaining_tokens:
            if token not in used_tokens and token not in token_map:
                unresolved.append(token)
                logger.warning(f"Unresolved token in AI response: {token}")

        # Log statistics
        total_tokens = len(token_map)
        resolved_count = len(used_tokens)
        missing_count = total_tokens - resolved_count

        if missing_count > 0:
            # Tokens in map but not found in AI response (AI may have dropped them)
            missing = [t for t in token_map if t not in used_tokens]
            logger.warning(
                f"Reinjektion: {resolved_count}/{total_tokens} tokens resolved. "
                f"Missing from response: {missing}"
            )
        else:
            logger.info(f"Reinjektion: all {total_tokens} tokens resolved successfully")

        return result, unresolved
