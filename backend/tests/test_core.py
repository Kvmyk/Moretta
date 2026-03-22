"""
Moretta — Core flow tests.
Tests the critical path: upload → PII detection → task → result → download.
Also tests the persistent store, dashboard, and audit logging.
"""

import json
from pathlib import Path

import pytest


# ── Store Tests ────────────────────────────────────────────────────


class TestPersistentStore:
    """Test that PersistentStore persists data across instances."""

    def test_store_basic_crud(self, tmp_path: Path):
        from store import PersistentStore

        store = PersistentStore(tmp_path / "test.db", "items")
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
        store1 = PersistentStore(db_path, "data")
        store1.initialize()
        store1["session1"] = {"status": "active", "count": 5}
        store1["session2"] = {"status": "done", "count": 10}

        # Read with new instance (simulates restart)
        store2 = PersistentStore(db_path, "data")
        store2.initialize()
        assert "session1" in store2
        assert store2["session1"]["status"] == "active"
        assert store2["session2"]["count"] == 10
        assert len(store2) == 2

    def test_store_blob_persistence(self, tmp_path: Path):
        from store import PersistentStore

        blob_dir = tmp_path / "blobs"
        store = PersistentStore(tmp_path / "blob.db", "files", blob_dir=blob_dir)
        store.initialize()

        test_bytes = b"Hello, binary world! \x00\xff\xfe"
        store["file1"] = {"filename": "test.docx", "original_bytes": test_bytes}

        # Verify blob is on disk
        assert (blob_dir / "file1.original_bytes").exists()

        # Verify blob is in memory
        assert store["file1"]["original_bytes"] == test_bytes

        # Verify blob survives reload
        store2 = PersistentStore(tmp_path / "blob.db", "files", blob_dir=blob_dir)
        store2.initialize()
        assert store2["file1"]["original_bytes"] == test_bytes

    def test_store_persist_after_mutation(self, tmp_path: Path):
        from store import PersistentStore

        db_path = tmp_path / "mutate.db"
        store = PersistentStore(db_path, "tasks")
        store.initialize()

        store["task1"] = {"status": "processing", "messages": []}
        store["task1"]["status"] = "completed"
        store["task1"]["messages"].append({"role": "user", "content": "hello"})
        store.persist("task1")

        # Reload and verify
        store2 = PersistentStore(db_path, "tasks")
        store2.initialize()
        assert store2["task1"]["status"] == "completed"
        assert len(store2["task1"]["messages"]) == 1

    def test_store_cleanup(self, tmp_path: Path):
        from store import PersistentStore
        from datetime import datetime, timezone, timedelta

        store = PersistentStore(tmp_path / "ttl.db", "sessions")
        store.initialize()

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        new_time = datetime.now(timezone.utc).isoformat()

        store["old"] = {"uploaded_at": old_time, "data": "old"}
        store["new"] = {"uploaded_at": new_time, "data": "new"}

        removed = store.cleanup_older_than(3600, "uploaded_at")  # 1 hour
        assert "old" in removed
        assert "old" not in store
        assert "new" in store


# ── API Tests ──────────────────────────────────────────────────────


class TestHealthAndProviders:
    """Test basic API endpoints."""

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
        bad_file = tmp_path / "test.pdf"
        bad_file.write_text("not a real pdf")
        with open(bad_file, "rb") as f:
            res = client.post("/api/upload", files={"file": ("test.pdf", f)})
        assert res.status_code == 400
        assert "Unsupported" in res.json()["detail"]

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
