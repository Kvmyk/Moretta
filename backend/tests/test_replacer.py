"""
Moretta — PII replacer tests.

The replacer is the point where plaintext becomes tokens. A miss leaks data; a
mis-placed replacement corrupts the document.
"""

from anonymizer.replacer import PiiReplacer


def _pii(text, type_, start, end, score=0.9):
    return {"text": text, "type": type_, "start": start, "end": end, "score": score}


class TestAnonymize:
    def test_replaces_at_exact_offsets(self):
        text = "Jan Kowalski ma PESEL 44051401359."
        items = [
            _pii("Jan Kowalski", "PERSON", 0, 12),
            _pii("44051401359", "PESEL", 22, 33),
        ]

        masked, token_map = PiiReplacer().anonymize(text, items)

        assert "Jan Kowalski" not in masked
        assert "44051401359" not in masked
        assert set(token_map.values()) == {"Jan Kowalski", "44051401359"}

    def test_same_value_reuses_one_token(self):
        text = "Jan Kowalski i znowu Jan Kowalski"
        items = [
            _pii("Jan Kowalski", "PERSON", 0, 12),
            _pii("Jan Kowalski", "PERSON", 21, 33),
        ]

        masked, token_map = PiiReplacer().anonymize(text, items)

        assert len(token_map) == 1
        token = next(iter(token_map))
        assert masked.count(token) == 2

    def test_overlapping_detections_do_not_corrupt(self):
        """
        Two stages can flag overlapping spans (e.g. IBAN and the PESEL-shaped
        digits inside it). Only one may be applied.
        """
        text = "Konto PL61109010140000071219812874 klienta"
        items = [
            _pii("PL61109010140000071219812874", "IBAN_CODE", 6, 34, score=0.95),
            _pii("10914000007", "PESEL", 12, 23, score=0.85),
        ]

        masked, token_map = PiiReplacer().anonymize(text, items)

        assert len(token_map) == 1
        assert "IBAN" in next(iter(token_map))
        assert "PL61109010140000071219812874" not in masked

    def test_stale_offsets_pick_nearest_occurrence(self):
        """
        When offsets no longer line up, the value nearest the recorded position
        is replaced - not simply the first one in the document.
        """
        text = "Kowalski pracuje. Potem znowu Kowalski kończy."
        # Offsets point at the second occurrence but are shifted by two chars.
        items = [_pii("Kowalski", "PERSON", 32, 40)]

        masked, token_map = PiiReplacer().anonymize(text, items)

        token = next(iter(token_map))
        assert masked.startswith("Kowalski pracuje")  # first one untouched
        assert token in masked
        assert masked.count("Kowalski") == 1

    def test_value_absent_from_text_is_dropped(self):
        """A mapping must never advertise a token that is not in the text."""
        text = "Dokument bez danych osobowych."
        items = [_pii("Anna Nowak", "PERSON", 5, 15)]

        masked, token_map = PiiReplacer().anonymize(text, items)

        assert masked == text
        assert token_map == {}

    def test_empty_input(self):
        masked, token_map = PiiReplacer().anonymize("tekst", [])
        assert masked == "tekst"
        assert token_map == {}

    def test_round_trip_with_reinjektor(self):
        from reinjektor.reinjektor import Reinjektor

        text = "Umowa dla Jan Kowalski, PESEL 44051401359."
        items = [
            _pii("Jan Kowalski", "PERSON", 10, 22),
            _pii("44051401359", "PESEL", 30, 41),
        ]

        masked, token_map = PiiReplacer().anonymize(text, items)
        restored, unresolved = Reinjektor().reinject(masked, token_map)

        assert restored == text
        assert unresolved == []
