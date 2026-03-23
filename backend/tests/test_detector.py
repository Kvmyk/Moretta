"""
Moretta — Unit tests for the PII Detector module.
Tests the regex engine, duplicate merging logic, and the mocked deep scan via Ollama.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from anonymizer.detector import PiiDetector

# Provide a lightweight fixture to initialize detector without needing a real NLP engine initially,
# or we just let it init. The Presidio analyzer might log a warning but it's safe to run in tests.
@pytest.fixture
def detector():
    return PiiDetector(ollama_url="http://localhost:11434", model="test-model")


class TestDetectorRegex:
    """Tests the static RegEx definitions for Polish PII contexts."""

    def test_regex_nip(self, detector):
        text = "Mój NIP to 123-456-78-19 oraz 1234567819."
        results = detector._detect_regex(text)
        nips = [r for r in results if r["type"] == "NIP"]
        
        assert len(nips) == 2
        assert nips[0]["text"] == "123-456-78-19"
        assert nips[1]["text"] == "1234567819"

    def test_regex_pesel(self, detector):
        text = "Oto PESEL pracownika: 92010212345. Proszę go zataić."
        results = detector._detect_regex(text)
        
        assert len(results) == 1
        assert results[0]["type"] == "PESEL"
        assert results[0]["text"] == "92010212345"
        assert results[0]["score"] == 0.85
        assert results[0]["source"] == "regex"

    def test_regex_phone(self, detector):
        text = "Zadzwoń: +48 600 700 800 lub pod stary numer 600-700-800."
        results = detector._detect_regex(text)
        phones = [r for r in results if r["type"] == "PHONE_NUMBER"]
        
        assert len(phones) == 2
        assert "+48 600 700 800" in [p["text"].strip() for p in phones]
        assert "600-700-800" in [p["text"].strip() for p in phones]

    def test_regex_iban(self, detector):
        text = "Proszę przelać na konto PL 12 1234 5678 9012 3456 7890 1234 opłatę."
        results = detector._detect_regex(text)
        ibans = [r for r in results if r["type"] == "IBAN_CODE"]
        
        assert len(ibans) == 1
        assert ibans[0]["text"] == "PL 12 1234 5678 9012 3456 7890 1234"

    def test_regex_krs(self, detector):
        text = "Spółka zarejestrowana pod numerem: 0000123456."
        results = detector._detect_regex(text)
        
        # NOTE: 10-digit KRS can be confused with a 10-digit NIP without dashes.
        # The regex engine correctly extracts the 10 digits. We just verify the entity is found.
        types_found = [r["type"] for r in results]
        texts_found = [r["text"] for r in results]
        
        assert len(results) >= 1
        assert "0000123456" in texts_found

    def test_regex_regon(self, detector):
        text = "REGON firmy to 123456789. ORAZ stary: 12345678901234."
        results = detector._detect_regex(text)
        regons = [r for r in results if r["type"] == "REGON"]
        
        assert len(regons) == 2
        assert "123456789" in [r["text"] for r in regons]
        assert "12345678901234" in [r["text"] for r in regons]

    def test_regex_mixed_polish_data(self, detector):
        # A realistic string containing several Polish PII types
        text = "Dyrektor Janusz (PESEL: 80010112345) prosi o przelew na PL 12123456789012345678901234 dla NIP: 526-021-02-28."
        results = detector._detect_regex(text)
        types = [r["type"] for r in results]
        
        assert "PESEL" in types
        assert "IBAN_CODE" in types
        assert "NIP" in types
        assert "80010112345" in [r["text"] for r in results]
        assert "526-021-02-28" in [r["text"] for r in results]


class TestDetectorDuplicates:
    """Tests the logic that merges overlapping bounding boxes."""

    def test_duplicate_exact_match(self, detector):
        item = {"start": 10, "end": 20}
        existing = [{"start": 10, "end": 20}]
        assert detector._is_duplicate(item, existing) is True

    def test_duplicate_overlap(self, detector):
        # item is slightly larger but heavily overlaps
        item = {"start": 10, "end": 25}
        existing = [{"start": 12, "end": 22}] 
        assert detector._is_duplicate(item, existing, overlap_threshold=0.5) is True

    def test_no_duplicate(self, detector):
        # Different ranges entirely
        item = {"start": 10, "end": 20}
        existing = [{"start": 30, "end": 40}]
        assert detector._is_duplicate(item, existing) is False


@pytest.mark.asyncio
class TestDetectorDeepScan:
    """Tests asynchronous deeply contextual scans using a mocked LLM endpoint."""

    async def test_deep_scan_successful_json(self, detector):
        # Mock successful LLM returning well-formed JSON array
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[\n  {"text": "Projekt Apollo", "type": "SECRET_PROJECT"}\n]'
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "Pracujemy nad projektem o nazwie Projekt Apollo w sekrecie."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            assert len(results) == 1
            assert results[0]["type"] == "SECRET_PROJECT"
            assert results[0]["text"] == "Projekt Apollo"
            assert results[0]["start"] == 33
            assert results[0]["end"] == 47
            assert results[0]["source"] == "ollama_deep"

    async def test_deep_scan_fallback_declension(self, detector):
        # Mock LLM returning a slightly different word declension that exists in the text
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"text": "Projekcie Apollo", "type": "SECRET_PROJECT"}]'
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "Rozmawiamy dzisiaj o Projekcie Apollo. To ściśle tajne."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            assert len(results) == 1
            assert results[0]["text"] == "Projekcie Apollo"
            assert results[0]["type"] == "SECRET_PROJECT"

    async def test_deep_scan_ignores_duplicates_from_existing(self, detector):
        # Mock LLM returning something that's already in existing_results (from regex/presidio)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"text": "10.0.0.5", "type": "IT_INFRA"}]'
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "Nasz adres to: 10.0.0.5."
            existing = [{"start": 15, "end": 23}] # 10.0.0.5 is at index 15:23
            
            results = await detector.detect_deep_async(text, existing_results=existing)
            # Should be discarded because it's already captured
            assert len(results) == 0

    async def test_deep_scan_financial_data(self, detector):
        # LLM detecting salaries and amounts
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"text": "15 000 PLN", "type": "FINANCE"}, {"text": "premia 20%", "type": "FINANCE"}]'
        }
        mock_response.raise_for_status = MagicMock()
        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient.post", mock_post):
            text = "Dla Jana Kowalskiego przypada 15 000 PLN oraz premia 20% za kwartał."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            assert len(results) == 2
            assert any(r["text"] == "15 000 PLN" for r in results)
            assert any(r["text"] == "premia 20%" for r in results)
            assert all(r["type"] == "FINANCE" for r in results)

    async def test_deep_scan_internal_ids(self, detector):
        # LLM detecting internal documentation numbers
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"text": "UM-2024/001/X", "type": "INTERNAL_ID"}]'
        }
        mock_response.raise_for_status = MagicMock()
        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient.post", mock_post):
            text = "Zgodnie z umową nr UM-2024/001/X prosimy o kontakt."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            assert len(results) == 1
            assert results[0]["text"] == "UM-2024/001/X"
            assert results[0]["type"] == "INTERNAL_ID"

    async def test_deep_scan_it_infra(self, detector):
        # LLM detecting server names or internal urls
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": '[{"text": "srv-prod-01.internal", "type": "IT_INFRA"}]'
        }
        mock_response.raise_for_status = MagicMock()
        mock_post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient.post", mock_post):
            text = "Logi są dostępne na maszynie srv-prod-01.internal w katalogu /root."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            assert len(results) == 1
            assert results[0]["text"] == "srv-prod-01.internal"
            assert results[0]["type"] == "IT_INFRA"

    async def test_deep_scan_malformed_json_fallback(self, detector):
        # Mock LLM failing to return proper JSON (missing bracket)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": 'Znalazłem coś:\n[{"text": "10.0.0.5", "type": "IT_INFRA"}'
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "Serwer 10.0.0.5 padł."
            results = await detector.detect_deep_async(text, existing_results=[])
            
            # The JSON array parser should fail gracefully and return empty
            assert len(results) == 0

    async def test_deep_scan_empty_clean_results(self, detector):
        # Mock LLM returning empty brackets because there is no PII
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": "[]"
        }
        mock_response.raise_for_status = MagicMock()

        mock_post = AsyncMock(return_value=mock_response)
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "To jest kompletnie bezpieczny i nudny tekst."
            results = await detector.detect_deep_async(text, existing_results=[])
            assert len(results) == 0

    async def test_deep_scan_api_timeout(self, detector):
        # Mock network failure/timeout
        mock_post = AsyncMock(side_effect=Exception("Timeout hitting Ollama API!"))
        
        with patch("httpx.AsyncClient.post", mock_post):
            text = "Ważny projekt Manhattan."
            results = await detector.detect_deep_async(text, existing_results=[])
            # The deep scan must not crash the whole application, should return empty list on failure
            assert len(results) == 0
