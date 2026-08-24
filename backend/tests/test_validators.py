"""
Moretta — checksum validator tests.

These guard the fix for the biggest source of false positives: shape-only
regexes that treated any 11 digits as a PESEL and any 9 digits as a REGON.
"""

import pytest

from anonymizer.validators import (
    is_valid_iban,
    is_valid_nip,
    is_valid_pesel,
    is_valid_regon,
)


class TestPesel:
    @pytest.mark.parametrize("value", ["44051401359", "02070803628", "92042199819"])
    def test_accepts_valid(self, value: str):
        assert is_valid_pesel(value)

    @pytest.mark.parametrize(
        "value",
        [
            "92010212345",  # bad check digit
            "12345678901",  # invoice-like sequence
            "00000000000",  # month/day out of range
            "4405140135",   # too short
            "abcdefghijk",
        ],
    )
    def test_rejects_invalid(self, value: str):
        assert not is_valid_pesel(value)


class TestNip:
    @pytest.mark.parametrize("value", ["1234563218", "123-456-32-18", "5252248481"])
    def test_accepts_valid(self, value: str):
        assert is_valid_nip(value)

    @pytest.mark.parametrize("value", ["1234567890", "1111111111", "12345"])
    def test_rejects_invalid(self, value: str):
        assert not is_valid_nip(value)


class TestRegon:
    @pytest.mark.parametrize("value", ["123456785", "12345678512347"])
    def test_accepts_valid(self, value: str):
        assert is_valid_regon(value)

    @pytest.mark.parametrize("value", ["123456789", "000000001", "1234"])
    def test_rejects_invalid(self, value: str):
        assert not is_valid_regon(value)


class TestIban:
    @pytest.mark.parametrize(
        "value",
        [
            "PL61109010140000071219812874",
            "PL 61 1090 1014 0000 0712 1981 2874",
            "61109010140000071219812874",
        ],
    )
    def test_accepts_valid(self, value: str):
        assert is_valid_iban(value)

    @pytest.mark.parametrize("value", ["PL61109010140000071219812875", "PL00", ""])
    def test_rejects_invalid(self, value: str):
        assert not is_valid_iban(value)
