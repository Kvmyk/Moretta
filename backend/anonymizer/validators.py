"""
Moretta - checksum validators for Polish identifiers.

The regex stage matches on shape alone, so "any 11 digits" was flagged as a
PESEL and "any 9 digits" as a REGON. Every one of these identifiers carries a
check digit, so verifying it removes most false positives (invoice numbers,
order ids, amounts) without losing a single genuine match.
"""

from __future__ import annotations

PESEL_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
REGON9_WEIGHTS = (8, 9, 2, 3, 4, 5, 6, 7)
REGON14_WEIGHTS = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def is_valid_pesel(value: str) -> bool:
    """Validate a PESEL number, including its check digit and birth date."""
    digits = _digits(value)
    if len(digits) != 11:
        return False

    checksum = sum(int(d) * w for d, w in zip(digits[:10], PESEL_WEIGHTS))
    if (10 - checksum % 10) % 10 != int(digits[10]):
        return False

    # Month encodes the century; a valid PESEL always maps to a real month.
    month = int(digits[2:4]) % 20
    if not 1 <= month <= 12:
        return False
    day = int(digits[4:6])
    return 1 <= day <= 31


def is_valid_nip(value: str) -> bool:
    """Validate a NIP (Polish VAT) number's check digit."""
    digits = _digits(value)
    if len(digits) != 10 or len(set(digits)) == 1:
        return False

    checksum = sum(int(d) * w for d, w in zip(digits[:9], NIP_WEIGHTS)) % 11
    if checksum == 10:
        return False
    return checksum == int(digits[9])


def is_valid_regon(value: str) -> bool:
    """Validate a 9- or 14-digit REGON number's check digit."""
    digits = _digits(value)

    if len(digits) == 9:
        weights = REGON9_WEIGHTS
    elif len(digits) == 14:
        weights = REGON14_WEIGHTS
    else:
        return False

    checksum = sum(int(d) * w for d, w in zip(digits[:-1], weights)) % 11
    if checksum == 10:
        checksum = 0
    return checksum == int(digits[-1])


def is_valid_iban(value: str) -> bool:
    """Validate an IBAN using the ISO 7064 mod-97 check."""
    normalized = "".join(value.split()).upper()
    if not normalized:
        return False
    if normalized.isdigit():
        # Polish account numbers are often written without the country prefix.
        normalized = "PL" + normalized
    if len(normalized) < 15 or not normalized[:2].isalpha():
        return False

    rearranged = normalized[4:] + normalized[:4]
    converted = ""
    for char in rearranged:
        if char.isdigit():
            converted += char
        elif char.isalpha():
            converted += str(ord(char) - ord("A") + 10)
        else:
            return False

    try:
        return int(converted) % 97 == 1
    except ValueError:
        return False


# Maps a detected PII type to the validator that must accept it.
CHECKSUM_VALIDATORS = {
    "PESEL": is_valid_pesel,
    "NIP": is_valid_nip,
    "REGON": is_valid_regon,
    "IBAN_CODE": is_valid_iban,
}
