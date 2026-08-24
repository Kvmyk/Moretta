"""
Moretta — masking helper tests.

`mask_with_token_map` is on the outbound path: anything it fails to match is
plaintext PII handed to an external provider, so these cases matter.
"""

from text_utils import build_masking_pattern, mask_with_token_map


class TestMasking:
    def test_replaces_exact_values(self):
        token_map = {"[OSOBA_a1b2]": "Jan Kowalski", "[PESEL_c3d4]": "44051401359"}
        text = "Umowa dla Jan Kowalski, PESEL 44051401359."

        masked = mask_with_token_map(text, token_map)

        assert "Jan Kowalski" not in masked
        assert "44051401359" not in masked
        assert "[OSOBA_a1b2]" in masked
        assert "[PESEL_c3d4]" in masked

    def test_matching_is_case_insensitive(self):
        """A user retyping a name in lowercase must still be masked."""
        token_map = {"[OSOBA_a1b2]": "Jan Kowalski"}

        masked = mask_with_token_map("proszę poprawić dane jan kowalski", token_map)

        assert "jan kowalski" not in masked
        assert "[OSOBA_a1b2]" in masked

    def test_longest_value_wins(self):
        """"Jan Kowalski" must be replaced before the shorter "Jan"."""
        token_map = {"[OSOBA_full]": "Jan Kowalski", "[OSOBA_first]": "Jan"}

        masked = mask_with_token_map("Pan Jan Kowalski przyszedł", token_map)

        assert "[OSOBA_full]" in masked
        assert "Kowalski" not in masked

    def test_appended_ending_is_masked_losslessly(self):
        """
        "Feniksem" contains "Feniks", so the value is masked and the ending is
        left outside the token — reinjection restores the word exactly.
        """
        token_map = {"[PROJEKT_x1]": "Feniks"}

        masked = mask_with_token_map("Prace nad Feniksem trwają", token_map)

        assert masked == "Prace nad [PROJEKT_x1]em trwają"
        assert masked.replace("[PROJEKT_x1]", "Feniks") == "Prace nad Feniksem trwają"

    def test_stem_changing_inflection_needs_the_flag(self):
        """
        "Warszawa" -> "Warszawie" replaces the ending, so a substring match
        cannot find it. This is the case that would otherwise leak.
        """
        token_map = {"[ADRES_x1]": "Warszawa"}

        without = mask_with_token_map("Spotkanie w Warszawie", token_map)
        with_flag = mask_with_token_map(
            "Spotkanie w Warszawie", token_map, allow_inflection=True
        )

        assert "Warszawie" in without
        assert "Warszawie" not in with_flag
        assert "[ADRES_x1]" in with_flag

    def test_inflection_does_not_break_exact_matches(self):
        token_map = {"[ADRES_x1]": "Warszawa"}

        masked = mask_with_token_map(
            "Miasto Warszawa", token_map, allow_inflection=True
        )

        assert masked == "Miasto [ADRES_x1]"

    def test_empty_inputs_are_passthrough(self):
        assert mask_with_token_map("", {"[T]": "x"}) == ""
        assert mask_with_token_map("abc", {}) == "abc"

    def test_pattern_can_be_reused(self):
        token_map = {"[OSOBA_a1b2]": "Jan Kowalski"}
        pattern = build_masking_pattern(list(token_map.values()))

        first = mask_with_token_map("Jan Kowalski", token_map, pattern=pattern)
        second = mask_with_token_map("kontakt: Jan Kowalski", token_map, pattern=pattern)

        assert first == "[OSOBA_a1b2]"
        assert "[OSOBA_a1b2]" in second

    def test_build_pattern_returns_none_for_empty(self):
        assert build_masking_pattern([]) is None
        assert build_masking_pattern(["", ""]) is None

    def test_regex_metacharacters_are_escaped(self):
        """PII values are literals, not patterns."""
        token_map = {"[ID_a1]": "FV-2024/03/991 (v1.0)"}

        masked = mask_with_token_map("Faktura FV-2024/03/991 (v1.0) opłacona", token_map)

        assert "[ID_a1]" in masked
        assert "FV-2024" not in masked
