"""
Moretta - Persistent session store.
Backed by SQLite with app-level encryption for every persisted payload.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from db import connect
from storage_crypto import (
    InvalidToken,
    build_fernet,
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    encrypt_text,
)

logger = logging.getLogger("moretta.store")


class PersistentStore:
    """
    Dict-like store backed by SQLite.
    Keeps an in-memory cache for fast reads and persists every write.

    Records hold plaintext document text, chat history and reinjected AI output,
    so the whole serialized payload is encrypted at rest whenever an encryption
    key is configured - not just the binary blobs.
    """

    BLOB_FIELDS = {"original_bytes"}

    def __init__(
        self,
        table: str,
        *,
        sqlite_path: Path | None = None,
        encryption_key: str = "",
    ) -> None:
        self._table = table
        self._sqlite_path = sqlite_path
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._fernet = build_fernet(encryption_key)
        # key -> {field: (source_bytes, encoded_ciphertext)}; lets us skip
        # re-encrypting a multi-megabyte blob on every unrelated field update.
        self._blob_cache: dict[str, dict[str, tuple[bytes, str]]] = {}

    def _connect(self):
        if not self._sqlite_path:
            raise ValueError("sqlite_path is required")
        return connect(self._sqlite_path)

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
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self._table}_created_at "
                f"ON {self._table} (created_at)"
            )
        self._load_from_db()
        logger.info(
            "Store '%s' loaded: %s entries (encryption %s)",
            self._table,
            len(self._cache),
            "on" if self._fernet else "OFF",
        )

    def _decode_value(self, value_json: str) -> dict[str, Any]:
        """
        Decode a persisted payload.

        Accepts both encrypted payloads and legacy plaintext JSON so databases
        written before encryption was enabled keep loading.
        """
        if value_json.lstrip().startswith("{"):
            return json.loads(value_json)
        if not self._fernet:
            raise ValueError("payload is encrypted but no encryption key is configured")
        return json.loads(decrypt_text(value_json, self._fernet))

    def _load_from_db(self) -> None:
        """Load all entries from the database into the in-memory cache."""
        self._cache = {}
        self._blob_cache = {}
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT key, value, blob_data FROM {self._table}"
            ).fetchall()

        for key, value_json, blob_json in rows:
            try:
                data = self._decode_value(value_json)
                for field, encoded_blob in json.loads(blob_json or "{}").items():
                    blob_data = base64.b64decode(encoded_blob.encode("ascii"))
                    try:
                        decrypted = decrypt_bytes(blob_data, self._fernet)
                    except InvalidToken as exc:
                        logger.error("Failed to decrypt blob '%s.%s': %s", key, field, exc)
                        continue
                    data[field] = decrypted
                    self._blob_cache.setdefault(key, {})[field] = (decrypted, encoded_blob)
                self._cache[key] = data
            except (json.JSONDecodeError, ValueError, TypeError, InvalidToken) as exc:
                logger.warning(
                    "Skipping unreadable entry '%s' in '%s': %s", key, self._table, exc
                )

    def __getitem__(self, key: str) -> dict[str, Any]:
        return self._cache[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = value
            self._persist(key, value)

    def __delitem__(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)
            self._blob_cache.pop(key, None)
            with self._connect() as conn:
                conn.execute(f"DELETE FROM {self._table} WHERE key = ?", (key,))

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def get(self, key: str, default: Any = None) -> Any:
        return self._cache.get(key, default)

    def items(self) -> Iterator[tuple[str, dict[str, Any]]]:
        return iter(list(self._cache.items()))

    def keys(self) -> list[str]:
        return list(self._cache.keys())

    def __len__(self) -> int:
        return len(self._cache)

    def _encode_blob(self, key: str, field: str, blob_data: bytes) -> str:
        """Encrypt a blob, reusing the previous ciphertext when bytes are unchanged."""
        cached = self._blob_cache.get(key, {}).get(field)
        if cached is not None and cached[0] is blob_data:
            return cached[1]
        encoded = base64.b64encode(encrypt_bytes(blob_data, self._fernet)).decode("ascii")
        self._blob_cache.setdefault(key, {})[field] = (blob_data, encoded)
        return encoded

    def _persist(self, key: str, value: dict[str, Any]) -> None:
        """Write the current value to the database."""
        data = dict(value)
        created_at = data.get("uploaded_at") or data.get("created_at") or ""

        blobs: dict[str, str] = {}
        for field in self.BLOB_FIELDS:
            blob_data = data.pop(field, None)
            if isinstance(blob_data, (bytes, bytearray)):
                blobs[field] = self._encode_blob(key, field, bytes(blob_data))

        serialized = json.dumps(data, default=str, ensure_ascii=False)
        if self._fernet:
            serialized = encrypt_text(serialized, self._fernet)
        blob_serialized = json.dumps(blobs)

        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT OR REPLACE INTO {self._table} (key, value, created_at, blob_data)
                VALUES (?, ?, ?, ?)
                """,
                (key, serialized, created_at, blob_serialized),
            )

    def update_field(self, key: str, field: str, value: Any) -> None:
        """Update a single field without rewriting the in-memory object manually."""
        with self._lock:
            if key not in self._cache:
                raise KeyError(key)
            self._cache[key][field] = value
            self._persist(key, self._cache[key])

    def persist(self, key: str) -> None:
        """Explicitly flush in-memory mutations for a key to the database."""
        with self._lock:
            if key in self._cache:
                self._persist(key, self._cache[key])

    def drop_fields(self, key: str, fields: set[str]) -> None:
        """Remove heavy fields from a record (memory + disk) and flush."""
        with self._lock:
            record = self._cache.get(key)
            if not record:
                return
            if not any(field in record for field in fields):
                return
            for field in fields:
                record.pop(field, None)
            self._blob_cache.pop(key, None)
            self._persist(key, record)

    def cleanup_older_than(
        self, seconds: int, timestamp_field: str = "uploaded_at"
    ) -> list[str]:
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
