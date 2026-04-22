"""
Moretta - Persistent session store.
Supports PostgreSQL for runtime storage and SQLite for local fallback/tests.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from db import connect, normalize_backend
from storage_crypto import InvalidToken, build_fernet, decrypt_bytes, encrypt_bytes

logger = logging.getLogger("moretta.store")


class PersistentStore:
    """
    Dict-like store backed by PostgreSQL or SQLite.
    Keeps an in-memory cache for fast reads and persists every write.
    """

    BLOB_FIELDS = {"original_bytes"}

    def __init__(
        self,
        table: str,
        *,
        database_backend: str,
        database_url: str | None = None,
        sqlite_path: Path | None = None,
        encryption_key: str = "",
    ) -> None:
        self._table = table
        self._database_backend = normalize_backend(database_backend)
        self._database_url = database_url
        self._sqlite_path = sqlite_path
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._fernet = build_fernet(encryption_key)

    def _connect(self):
        return connect(
            database_backend=self._database_backend,
            database_url=self._database_url,
            sqlite_path=self._sqlite_path,
        )

    def initialize(self) -> None:
        """Create table if needed and load existing data into memory."""
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT,
                    blob_data TEXT NOT NULL DEFAULT '{{}}'
                )
                """
            )
        self._load_from_db()
        logger.info(
            "Store '%s' loaded: %s entries using %s",
            self._table,
            len(self._cache),
            self._database_backend,
        )

    def _load_from_db(self) -> None:
        """Load all entries from the database into the in-memory cache."""
        self._cache = {}
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT key, value, blob_data FROM {self._table}"
            ).fetchall()

        for key, value_json, blob_json in rows:
            try:
                data = json.loads(value_json)
                for field, encoded_blob in json.loads(blob_json or "{}").items():
                    blob_data = base64.b64decode(encoded_blob.encode("ascii"))
                    try:
                        data[field] = decrypt_bytes(blob_data, self._fernet)
                    except InvalidToken as exc:
                        logger.error("Failed to decrypt blob '%s.%s': %s", key, field, exc)
                self._cache[key] = data
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Skipping corrupt entry '%s' in '%s': %s", key, self._table, exc)

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self._cache[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = value
            self._persist(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            placeholder = "%s" if self._database_backend == "postgres" else "?"
            with self._connect() as conn:
                conn.execute(f"DELETE FROM {self._table} WHERE key = {placeholder}", (key,))

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def items(self) -> Iterator[tuple[str, dict[str, Any]]]:
        return iter(self._cache.items())

    def __len__(self) -> int:
        return len(self._cache)

    def _persist(self, key: str, value: dict[str, Any]) -> None:
        """Write the current value to the configured database backend."""
        data = dict(value)
        created_at = data.get("uploaded_at") or data.get("created_at") or ""

        blobs: dict[str, str] = {}
        for field in self.BLOB_FIELDS:
            blob_data = data.pop(field, None)
            if isinstance(blob_data, (bytes, bytearray)):
                encrypted_blob = encrypt_bytes(bytes(blob_data), self._fernet)
                blobs[field] = base64.b64encode(encrypted_blob).decode("ascii")

        serialized = json.dumps(data, default=str, ensure_ascii=False)
        blob_serialized = json.dumps(blobs)

        with self._connect() as conn:
            if self._database_backend == "postgres":
                conn.execute(
                    f"""
                    INSERT INTO {self._table} (key, value, created_at, blob_data)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value,
                        created_at = EXCLUDED.created_at,
                        blob_data = EXCLUDED.blob_data
                    """,
                    (key, serialized, created_at, blob_serialized),
                )
            else:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {self._table} (key, value, created_at, blob_data)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, serialized, created_at, blob_serialized),
                )

    def update_field(self, key: str, field: str, value: Any) -> None:
        """Update a single field without rewriting the in-memory object manually."""
        if key not in self._cache:
            raise KeyError(key)
        with self._lock:
            self._cache[key][field] = value
            self._persist(key, self._cache[key])

    def persist(self, key: str) -> None:
        """Explicitly flush in-memory mutations for a key to the database."""
        if key in self._cache:
            with self._lock:
                self._persist(key, self._cache[key])

    def cleanup_older_than(self, seconds: int, timestamp_field: str = "uploaded_at") -> list[str]:
        """Remove entries older than `seconds`. Returns list of removed keys."""
        now = datetime.now(timezone.utc)
        expired = []
        for key, data in list(self._cache.items()):
            ts = data.get(timestamp_field)
            if not ts:
                continue
            try:
                age = (now - datetime.fromisoformat(ts)).total_seconds()
            except (ValueError, TypeError):
                continue
            if age > seconds:
                expired.append(key)

        for key in expired:
            del self[key]

        return expired
