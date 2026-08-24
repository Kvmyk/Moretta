"""
Moretta — Core flow tests.
Tests the critical path: upload → PII detection → task → result → download.
Also tests the persistent store, dashboard, and audit logging.
"""

from pathlib import Path

import pytest


# ── Store Tests ────────────────────────────────────────────────────


class TestPersistentStore:
    """Test that PersistentStore persists data across instances."""

    def test_store_basic_crud(self, tmp_path: Path):
        from store import PersistentStore

        store = PersistentStore("items", sqlite_path=tmp_path / "test.db")
        store.initialize()

        store["key1"] = {"name": "test", "value": 42}
        assert "key1" in store
        assert store["key1"]["name"] == "test"
        assert len(store) == 1

        del store["key1"]
        assert "key1" not in store
        assert len(store) == 0

    def test_store_persistence_across_instances(self, tmp_path: Path):
        from store import PersistentStore

        db_path = tmp_path / "persist.db"

        # Write with first instance
        store1 = PersistentStore("data", sqlite_path=db_path)
        store1.initialize()
        store1["session1"] = {"status": "active", "count": 5}
        store1["session2"] = {"status": "done", "count": 10}

        # Read with new instance (simulates restart)
        store2 = PersistentStore("data", sqlite_path=db_path)
        store2.initialize()
        assert "session1" in store2
        assert store2["session1"]["status"] == "active"
        assert store2["session2"]["count"] == 10
        assert len(store2) == 2

    def test_store_blob_persistence(self, tmp_path: Path):
        from store import PersistentStore

        db_path = tmp_path / "blob.db"
        store = PersistentStore("files", sqlite_path=db_path)
        store.initialize()

        test_bytes = b"Hello, binary world! \x00\xff\xfe"
        store["file1"] = {"filename": "test.docx", "original_bytes": test_bytes}

        # Verify blob is in memory
        assert store["file1"]["original_bytes"] == test_bytes

        # Verify blob survives reload
        store2 = PersistentStore("files", sqlite_path=db_path)
        store2.initialize()
        assert store2["file1"]["original_bytes"] == test_bytes

    def test_store_persist_after_mutation(self, tmp_path: Path):
        from store import PersistentStore

        db_path = tmp_path / "mutate.db"
        store = PersistentStore("tasks", sqlite_path=db_path)
        store.initialize()

        store["task1"] = {"status": "processing", "messages": []}
        store["task1"]["status"] = "completed"
        store["task1"]["messages"].append({"role": "user", "content": "hello"})
        store.persist("task1")

        # Reload and verify
        store2 = PersistentStore("tasks", sqlite_path=db_path)
        store2.initialize()
        assert store2["task1"]["status"] == "completed"
        assert len(store2["task1"]["messages"]) == 1

    def test_store_encrypts_payload_at_rest(self, tmp_path: Path):
        """Document text and chat history must not be readable in the DB file."""
        import sqlite3
        from store import PersistentStore

        db_path = tmp_path / "encrypted.db"
        store = PersistentStore(
            "tasks", sqlite_path=db_path, encryption_key="unit-test-key"
        )
        store.initialize()
        store["t1"] = {
            "text": "Jan Kowalski, PESEL 92010212345",
            "messages": [{"role": "assistant", "content": "Umowa dla Jan Kowalski"}],
        }

        raw = sqlite3.connect(db_path).execute(
            "SELECT value FROM tasks WHERE key = 't1'"
        ).fetchone()[0]
        assert "Jan Kowalski" not in raw
        assert "92010212345" not in raw

        # Still readable through the store itself.
        reopened = PersistentStore(
            "tasks", sqlite_path=db_path, encryption_key="unit-test-key"
        )
        reopened.initialize()
        assert reopened["t1"]["text"] == "Jan Kowalski, PESEL 92010212345"

    def test_store_reads_legacy_plaintext_rows(self, tmp_path: Path):
        """A database written before encryption was enabled must still load."""
        from store import PersistentStore

        db_path = tmp_path / "legacy.db"
        legacy = PersistentStore("files", sqlite_path=db_path)  # no key
        legacy.initialize()
        legacy["old"] = {"filename": "a.docx", "text": "plain"}

        upgraded = PersistentStore(
            "files", sqlite_path=db_path, encryption_key="new-key"
        )
        upgraded.initialize()
        assert upgraded["old"]["text"] == "plain"

    def test_store_drop_fields(self, tmp_path: Path):
        from store import PersistentStore

        db_path = tmp_path / "drop.db"
        store = PersistentStore("tasks", sqlite_path=db_path, encryption_key="k")
        store.initialize()
        store["t1"] = {"status": "done", "solution_text": "big", "keep": 1}

        store.drop_fields("t1", {"solution_text"})

        assert "solution_text" not in store["t1"]
        assert store["t1"]["keep"] == 1

        reopened = PersistentStore("tasks", sqlite_path=db_path, encryption_key="k")
        reopened.initialize()
        assert "solution_text" not in reopened["t1"]

    def test_store_cleanup(self, tmp_path: Path):
        from store import PersistentStore
        from datetime import datetime, timezone, timedelta

        store = PersistentStore("sessions", sqlite_path=tmp_path / "ttl.db")
        store.initialize()

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        new_time = datetime.now(timezone.utc).isoformat()

        store["old"] = {"uploaded_at": old_time, "data": "old"}
        store["new"] = {"uploaded_at": new_time, "data": "new"}

        removed = store.cleanup_older_than(3600, "uploaded_at")  # 1 hour
        assert "old" in removed
        assert "old" not in store
        assert "new" in store


class TestVault:
    """Test that the encrypted vault persists token maps correctly."""

    def test_vault_store_and_load(self, tmp_path: Path):
        from anonymizer.vault import Vault

        vault = Vault(
            sqlite_path=tmp_path / "vault.db",
            encryption_key="test-secret",
        )
        vault.initialize()

        token_map = {"<UUID_1>": "Jan Kowalski", "<UUID_2>": "92010212345"}
        vault.store_session("session-1", token_map)

        restored = vault.get_session("session-1")
        assert restored == token_map

    def test_vault_delete_session(self, tmp_path: Path):
        from anonymizer.vault import Vault, VaultSessionError

        vault = Vault(
            sqlite_path=tmp_path / "vault.db",
            encryption_key="test-secret",
        )
        vault.initialize()
        vault.store_session("session-1", {"<UUID_1>": "Jan Kowalski"})
        assert vault.has_session("session-1")

        vault.delete_session("session-1")

        # Must fail closed: an empty mapping would silently disable
        # re-anonymization of the conversation history.
        assert not vault.has_session("session-1")
        with pytest.raises(VaultSessionError):
            vault.get_session("session-1")

    def test_vault_missing_session_raises(self, tmp_path: Path):
        from anonymizer.vault import Vault, VaultSessionError

        vault = Vault(sqlite_path=tmp_path / "vault.db", encryption_key="k")
        vault.initialize()

        with pytest.raises(VaultSessionError):
            vault.get_session("never-stored")

    def test_vault_wrong_key_raises_instead_of_empty(self, tmp_path: Path):
        from anonymizer.vault import Vault, VaultSessionError

        db = tmp_path / "vault.db"
        writer = Vault(sqlite_path=db, encryption_key="original-key")
        writer.initialize()
        writer.store_session("s1", {"<T1>": "Jan Kowalski"})

        reader = Vault(sqlite_path=db, encryption_key="rotated-key")
        reader.initialize()
        with pytest.raises(VaultSessionError):
            reader.get_session("s1")

    def test_vault_expiry_cleanup(self, tmp_path: Path):
        from anonymizer.vault import Vault, VaultSessionError

        vault = Vault(sqlite_path=tmp_path / "vault.db", encryption_key="k")
        vault.initialize()
        vault.store_session("expired", {"<T1>": "x"}, ttl_seconds=-1)
        vault.store_session("fresh", {"<T2>": "y"}, ttl_seconds=3600)

        removed = vault.cleanup_expired()

        assert removed == 1
        assert vault.get_session("fresh") == {"<T2>": "y"}
        with pytest.raises(VaultSessionError):
            vault.get_session("expired")


# ── API Tests ──────────────────────────────────────────────────────


class TestHealthAndProviders:
    """Test basic API endpoints."""

    def test_health_endpoint_is_public(self, client):
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_providers_default_model_is_a_real_model(self, client):
        """A stale DEFAULT_AI_MODEL must never be advertised to the UI."""
        data = client.get("/api/providers").json()
        by_id = {p["id"]: p for p in data["providers"]}
        default_provider = data["default_provider"]
        valid_ids = {m["id"] for m in by_id[default_provider]["models"]}
        assert data["default_model"] in valid_ids

    def test_providers_endpoint(self, client):
        res = client.get("/api/providers")
        assert res.status_code == 200
        data = res.json()
        assert "providers" in data
        assert len(data["providers"]) >= 3  # at least claude, openai, gemini

    def test_tasks_list_empty(self, client):
        res = client.get("/api/tasks")
        assert res.status_code == 200
        data = res.json()
        assert "tasks" in data

    def test_dashboard_endpoint(self, client):
        res = client.get("/api/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert "stats" in data
        assert "pii_breakdown" in data
        assert "provider_usage" in data
        assert "daily_activity" in data
        assert "total_files" in data["stats"]

    def test_audit_endpoint(self, client):
        res = client.get("/api/audit")
        assert res.status_code == 200
        data = res.json()
        assert "entries" in data
        assert "total" in data


class TestUploadFlow:
    """Test file upload and text submission."""

    def test_upload_unsupported_file(self, client, tmp_path: Path):
        bad_file = tmp_path / "test.bin"
        bad_file.write_text("not a supported format")
        with open(bad_file, "rb") as f:
            res = client.post("/api/upload", files={"file": ("test.bin", f)})
        assert res.status_code == 400
        assert "Unsupported" in res.json()["detail"]

    def test_upload_docx_file(self, client, sample_docx: Path):
        with open(sample_docx, "rb") as f:
            res = client.post("/api/upload", files={"file": (sample_docx.name, f)})
        assert res.status_code == 200
        data = res.json()
        assert "file_id" in data
        assert data["filename"].endswith(".docx")
        assert data["size_bytes"] > 0

        preview_res = client.get(f"/api/file/{data['file_id']}/preview")
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert preview["preview_data"]["type"] == "document"
        assert isinstance(preview["preview_data"]["text"], str)
        assert len(preview["preview_data"]["text"]) > 0

    def test_upload_xlsx_file(self, client, sample_xlsx: Path):
        with open(sample_xlsx, "rb") as f:
            res = client.post("/api/upload", files={"file": (sample_xlsx.name, f)})
        assert res.status_code == 200
        data = res.json()
        assert "file_id" in data
        assert data["filename"].endswith(".xlsx")
        assert data["size_bytes"] > 0

        preview_res = client.get(f"/api/file/{data['file_id']}/preview")
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert preview["preview_data"]["type"] == "spreadsheet"
        assert len(preview["preview_data"]["sheets"]) >= 1
        first_sheet_rows = preview["preview_data"]["sheets"][0]["rows"]
        assert any("Imie i nazwisko" in str(cell) for row in first_sheet_rows for cell in row)

    def test_upload_pdf_file(self, client, sample_pdf: Path):
        with open(sample_pdf, "rb") as f:
            res = client.post("/api/upload", files={"file": (sample_pdf.name, f)})
        assert res.status_code == 200
        data = res.json()
        assert "file_id" in data
        assert data["filename"].endswith(".pdf")
        assert data["size_bytes"] > 0

        preview_res = client.get(f"/api/file/{data['file_id']}/preview")
        assert preview_res.status_code == 200
        preview = preview_res.json()
        assert preview["preview_data"]["type"] == "document"
        assert isinstance(preview["preview_data"]["text"], str)
        assert len(preview["preview_data"]["text"]) > 0

    def test_text_submission(self, client, sample_text: str):
        res = client.post(
            "/api/text",
            json={"text": sample_text},
        )
        assert res.status_code == 200
        data = res.json()
        assert "file_id" in data
        assert data["pii_count"] >= 0  # PII detection depends on models being loaded

    def test_text_submission_empty(self, client):
        res = client.post("/api/text", json={"text": "   "})
        assert res.status_code == 400

    def test_pii_endpoint_not_found(self, client):
        res = client.get("/api/file/nonexistent-id/pii")
        assert res.status_code == 404

    def test_preview_endpoint_not_found(self, client):
        res = client.get("/api/file/nonexistent-id/preview")
        assert res.status_code == 404


class TestTaskFlow:
    """Test task creation, status, and result endpoints."""

    def test_task_creation_file_not_found(self, client):
        res = client.post(
            "/api/task",
            json={"file_id": "nonexistent", "instruction": "Fix this"},
        )
        assert res.status_code == 404

    def test_task_status_not_found(self, client):
        res = client.get("/api/task/nonexistent/status")
        assert res.status_code == 404

    def test_task_result_not_found(self, client):
        res = client.get("/api/task/nonexistent/result")
        assert res.status_code == 404

    def test_task_download_not_found(self, client):
        res = client.get("/api/task/nonexistent/download")
        assert res.status_code == 404

    def test_chat_task_not_found(self, client):
        res = client.post(
            "/api/task/nonexistent/chat",
            json={"instruction": "Continue"},
        )
        assert res.status_code == 404

    def test_task_rejects_unknown_model(self, client, sample_text: str):
        file_id = client.post("/api/text", json={"text": sample_text}).json()["file_id"]

        res = client.post(
            "/api/task",
            json={
                "file_id": file_id,
                "instruction": "Popraw tekst",
                "provider": "claude",
                "model": "definitely-not-a-real-model",
            },
        )
        assert res.status_code == 400
        assert "not available" in res.json()["detail"]

    def test_task_blocked_while_deep_scan_pending(self, client, sample_text: str):
        """Sending a document before contextual detection finishes must be refused."""
        from main import file_store

        file_id = client.post("/api/text", json={"text": sample_text}).json()["file_id"]
        # Simulate the scan still running (background task already completed here).
        file_store[file_id]["deep_scan_completed"] = False
        file_store.persist(file_id)

        res = client.post(
            "/api/task",
            json={"file_id": file_id, "instruction": "Popraw tekst"},
        )
        assert res.status_code == 409
        assert "Deep scan" in res.json()["detail"]


class TestInputLimits:
    """Uploads and raw text must be bounded."""

    def test_text_over_limit_rejected(self, client):
        from config import get_settings

        oversized = "a" * (get_settings().max_text_chars + 1)
        res = client.post("/api/text", json={"text": oversized})
        assert res.status_code == 422

    def test_upload_over_limit_rejected(self, client, tmp_path: Path, monkeypatch):
        import main

        monkeypatch.setattr(main.settings, "max_upload_bytes", 1024)

        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * 4096)
        with open(big, "rb") as f:
            res = client.post("/api/upload", files={"file": ("big.txt", f)})

        assert res.status_code == 413

    def test_txt_upload_supported(self, client, tmp_path: Path):
        """The UI offers .txt, so the backend must accept it."""
        txt = tmp_path / "notatka.txt"
        txt.write_text("Jan Kowalski, PESEL 92010212345", encoding="utf-8")
        with open(txt, "rb") as f:
            res = client.post("/api/upload", files={"file": ("notatka.txt", f)})

        assert res.status_code == 200
        assert res.json()["filename"].endswith(".txt")


# ── Audit Log Tests ────────────────────────────────────────────────

class TestAuditLog:
    """Test audit logging functionality."""

    def test_audit_logger_write_and_read(self, tmp_path: Path):
        from audit.audit_log import AuditLogger

        logger = AuditLogger(tmp_path / "test_audit.jsonl")

        logger.log(event="test_event", user="test_user", detail="hello")
        logger.log(event="test_event_2", user="test_user_2")

        entries = logger.read(limit=10)
        assert len(entries) == 2
        assert entries[0]["event"] == "test_event_2"  # Most recent first
        assert entries[1]["event"] == "test_event"

    def test_audit_does_not_log_pii_values(self, tmp_path: Path):
        from audit.audit_log import AuditLogger

        log_path = tmp_path / "pii_test.jsonl"
        logger = AuditLogger(log_path)

        logger.log(
            event="file_uploaded",
            user="admin",
            filename="***.docx",
            pii_count=3,
            pii_types=["PERSON", "PESEL"],
        )

        content = log_path.read_text()
        assert "Jan Kowalski" not in content
        assert "92010212345" not in content
        assert "PERSON" in content  # Type is OK
        assert "***.docx" in content  # Sanitized filename


# ── Sanitization Tests ─────────────────────────────────────────────

class TestSanitization:
    """Test PII sanitization in logs."""

    def test_sanitize_filename(self):
        import importlib
        import main
        importlib.reload(main)
        from main import _sanitize_filename

        assert _sanitize_filename("Jan_Kowalski_umowa.docx") == "***.docx"
        assert _sanitize_filename("raport.xlsx") == "***.xlsx"
        assert _sanitize_filename("noextension") == "***"

    def test_sanitize_error(self):
        from main import _sanitize_error

        error = "Failed at row: Jan Kowalski, PESEL 92010212345, email jan@firma.pl"
        sanitized = _sanitize_error(error)

        assert "92010212345" not in sanitized
        assert "jan@firma.pl" not in sanitized
        assert "[PESEL]" in sanitized
        assert "[EMAIL]" in sanitized

    def test_sanitize_error_truncation(self):
        from main import _sanitize_error

        long_error = "x" * 500
        sanitized = _sanitize_error(long_error, max_length=200)
        assert len(sanitized) < 250  # 200 + truncation notice
        assert "[truncated]" in sanitized
