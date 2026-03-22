"""
Moretta — Persistent session store.
Drop-in replacement for in-memory dicts, backed by SQLite + disk files.
Data survives process restarts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import hashlib
import base64
from pathlib import Path
from typing import Any, Iterator

from cryptography.fernet import Fernet

logger = logging.getLogger("moretta.store")


class PersistentStore:
    """
    Dict-like store backed by SQLite for metadata and disk for binary blobs.
    Keeps an in-memory cache for fast reads, syncs writes to disk.

    Usage:
        store = PersistentStore(db_path, "files", blob_dir=Path("/app/data/blobs"))
        store.initialize()
        store["abc-123"] = {"filename": "doc.docx", "original_bytes": b"...", ...}
        data = store["abc-123"]
    """

    BLOB_FIELDS = {"original_bytes"}  # Fields stored as files, not JSON

    def __init__(self, db_path: Path, table: str, blob_dir: Path | None = None, encryption_key: str = "") -> None:
        self._db_path = db_path
        self._table = table
        self._blob_dir = blob_dir
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        
        self._fernet = None
        if encryption_key:
            # Derive a 32-urlsafe-base64 key required by Fernet using SHA-256
            key32 = base64.urlsafe_b64encode(hashlib.sha256(encryption_key.encode()).digest())
            self._fernet = Fernet(key32)

    def initialize(self) -> None:
        """Create table if needed and load existing data into memory."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        if self._blob_dir:
            self._blob_dir.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

        self._load_from_db()
        logger.info(f"Store '{self._table}' loaded: {len(self._cache)} entries from {self._db_path}")

    def _load_from_db(self) -> None:
        """Load all entries from SQLite into the in-memory cache."""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(f"SELECT key, value FROM {self._table}").fetchall()

        for key, value_json in rows:
            try:
                data = json.loads(value_json)
                # Restore blob data from disk
                if self._blob_dir:
                    for field in self.BLOB_FIELDS:
                        blob_path = self._blob_dir / f"{key}.{field}"
                        if blob_path.exists():
                            blob_data = blob_path.read_bytes()
                            if self._fernet:
                                try:
                                    blob_data = self._fernet.decrypt(blob_data)
                                except Exception as exc:
                                    logger.error(f"Failed to decrypt blob {blob_path}: {exc}")
                                    continue
                            data[field] = blob_data
                self._cache[key] = data
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning(f"Skipping corrupt entry '{key}' in '{self._table}': {exc}")

    # ── Dict-like interface ────────────────────────────────────────

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self._cache[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = value
            self._persist(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(f"DELETE FROM {self._table} WHERE key = ?", (key,))
            # Remove blob files
            if self._blob_dir:
                for field in self.BLOB_FIELDS:
                    blob_path = self._blob_dir / f"{key}.{field}"
                    blob_path.unlink(missing_ok=True)

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def items(self) -> Iterator[tuple[str, dict[str, Any]]]:
        return iter(self._cache.items())

    def __len__(self) -> int:
        return len(self._cache)

    # ── Persistence ────────────────────────────────────────────────

    def _persist(self, key: str, value: dict[str, Any]) -> None:
        """Write metadata to SQLite and blobs to disk."""
        data = dict(value)  # shallow copy
        created_at = data.get("uploaded_at") or data.get("created_at") or ""

        # Extract blob fields and save to disk
        if self._blob_dir:
            for field in self.BLOB_FIELDS:
                blob_data = data.pop(field, None)
                if blob_data and isinstance(blob_data, (bytes, bytearray)):
                    blob_path = self._blob_dir / f"{key}.{field}"
                    if self._fernet:
                        blob_data = self._fernet.encrypt(bytes(blob_data))
                    blob_path.write_bytes(blob_data)

        serialized = json.dumps(data, default=str, ensure_ascii=False)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {self._table} (key, value, created_at) VALUES (?, ?, ?)",
                (key, serialized, created_at),
            )

    def update_field(self, key: str, field: str, value: Any) -> None:
        """Update a single field without rewriting the entire entry."""
        if key not in self._cache:
            raise KeyError(key)
        with self._lock:
            self._cache[key][field] = value
            self._persist(key, self._cache[key])

    def persist(self, key: str) -> None:
        """Explicitly flush in-memory mutations for a key to disk.

        Call this after directly mutating nested values, e.g.:
            store[key]["status"] = "completed"
            store.persist(key)
        """
        if key in self._cache:
            with self._lock:
                self._persist(key, self._cache[key])

    def cleanup_older_than(self, seconds: int, timestamp_field: str = "uploaded_at") -> list[str]:
        """Remove entries older than `seconds`. Returns list of removed keys."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        expired = []
        for key, data in list(self._cache.items()):
            ts = data.get(timestamp_field)
            if ts:
                try:
                    age = (now - datetime.fromisoformat(ts)).total_seconds()
                    if age > seconds:
                        expired.append(key)
                except (ValueError, TypeError):
                    pass

        for key in expired:
            del self[key]

        return expired
