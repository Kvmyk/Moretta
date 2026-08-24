"""
Moretta - shared text masking helpers.

Both the anonymized preview and the outbound re-anonymization of chat history
need to swap original PII values back to tokens. Doing that with a loop of
`str.replace` per token is quadratic and misses anything that differs in case,
so both paths share the single-pass matcher below.
"""

from __future__ import annotations

import re

_POLISH_LETTER = r"[a-ząćęłńóśźż]"
# Polish declension usually appends an ending ("Kowalski" -> "Kowalskiego"), which
# a plain substring match already covers. It sometimes replaces the final letters
# instead ("Warszawa" -> "Warszawie"); the stem branch below catches those.
_STEM_TRIM = 1
_STEM_SUFFIX = _POLISH_LETTER + r"{1,4}"
_MIN_STEM_LENGTH = 6
_MAX_SUFFIX_STRIP = 4


def build_masking_pattern(
    originals: list[str],
    *,
    allow_inflection: bool = False,
) -> re.Pattern[str] | None:
    """
    Compile one alternation matching every original value.

    Literal branches come first and are ordered longest-first, so "Jan Kowalski"
    always wins over "Jan", and an appended declension ending is left outside the
    token (masking "Feniksem" as "[PROJEKT_x1]em", which reinjects cleanly).

    With `allow_inflection`, lower-priority stem branches are appended to also
    catch endings that replace the final letter.
    """
    unique = sorted({value for value in originals if value}, key=len, reverse=True)
    if not unique:
        return None

    branches = [re.escape(value) for value in unique]

    if allow_inflection:
        for value in unique:
            if len(value) >= _MIN_STEM_LENGTH:
                branches.append(re.escape(value[:-_STEM_TRIM]) + _STEM_SUFFIX)

    return re.compile("|".join(branches), re.IGNORECASE)


def mask_with_token_map(
    text: str,
    token_map: dict[str, str],
    *,
    allow_inflection: bool = False,
    pattern: re.Pattern[str] | None = None,
) -> str:
    """
    Replace every original PII value in `text` with its token.

    Args:
        text: Text that may contain plaintext PII.
        token_map: Mapping of token -> original value.
        allow_inflection: Also match Polish declension forms whose ending
            replaces the final letter. Use this on outbound paths, where a
            missed match means a plaintext leak.
        pattern: Pre-compiled pattern from `build_masking_pattern`, to avoid
            recompiling when masking many fragments with the same map.

    Returns:
        The text with all matched values replaced by their tokens.
    """
    if not text or not token_map:
        return text

    lookup = {original.lower(): token for token, original in token_map.items()}
    # Stem -> token, mirroring the stem branches in the compiled pattern.
    stems = {
        original.lower()[:-_STEM_TRIM]: token
        for token, original in token_map.items()
        if len(original) >= _MIN_STEM_LENGTH
    }

    if pattern is None:
        pattern = build_masking_pattern(
            list(token_map.values()), allow_inflection=allow_inflection
        )
    if pattern is None:
        return text

    def _replace(match: re.Match[str]) -> str:
        matched = match.group(0)
        token = lookup.get(matched.lower())
        if token is not None:
            return token

        # A stem branch matched an inflected form. Walk back to the root and
        # emit the bare token: "[OSOBA_a3f2]go" would reinject as "Kowalskigo",
        # so the declension ending is dropped instead.
        root = matched.lower()
        for cut in range(1, _MAX_SUFFIX_STRIP + 1):
            if cut >= len(root):
                break
            candidate = root[:-cut]
            token = lookup.get(candidate) or stems.get(candidate)
            if token is not None:
                return token

        return matched

    return pattern.sub(_replace, text)
