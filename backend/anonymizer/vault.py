"""
Moretta - Encrypted PII vault.
Stores session token maps in PostgreSQL or SQLite with app-level encryption.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from db import connect, normalize_backend
from storage_crypto import InvalidToken, build_fernet, decrypt_text, encrypt_text

logger = logging.getLogger("moretta.vault")


class Vault:
    """Encrypted vault for PII token mappings."""

    def __init__(
        self,
        *,
        database_backend: str,
        database_url: str | None = None,
        sqlite_path: Path | None = None,
        encryption_key: str = "",
    ) -> None:
        self._database_backend = normalize_backend(database_backend)
        self._database_url = database_url
        self._sqlite_path = sqlite_path
        self._fernet = build_fernet(encryption_key)

    def _connect(self):
        return connect(
            database_backend=self._database_backend,
            database_url=self._database_url,
            sqlite_path=self._sqlite_path,
        )

    def initialize(self) -> None:
        """Create the vault table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pii_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_map TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )
        logger.info("Vault initialized using %s", self._database_backend)

    def store_session(self, session_id: str, token_map: dict[str, str]) -> None:
        """Store a token mapping for a session."""
        token_payload = json.dumps(token_map, ensure_ascii=False)
        if self._fernet:
            token_payload = encrypt_text(token_payload, self._fernet)

        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            if self._database_backend == "postgres":
                conn.execute(
                    """
                    INSERT INTO pii_sessions (session_id, token_map, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE
                    SET token_map = EXCLUDED.token_map,
                        created_at = EXCLUDED.created_at
                    """,
                    (session_id, token_payload, created_at),
                )
            else:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pii_sessions (session_id, token_map, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (session_id, token_payload, created_at),
                )
        logger.info("Stored %s tokens for session %s...", len(token_map), session_id[:8])

    def get_session(self, session_id: str) -> dict[str, str]:
        """Retrieve the token mapping for a session."""
        placeholder = "%s" if self._database_backend == "postgres" else "?"
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT token_map FROM pii_sessions WHERE session_id = {placeholder}",
                (session_id,),
            ).fetchone()

        if row is None:
            logger.warning("Session %s... not found in vault", session_id[:8])
            return {}

        token_payload = row[0]
        if self._fernet:
            try:
                token_payload = decrypt_text(token_payload, self._fernet)
            except (InvalidToken, ValueError) as exc:
                logger.error("Failed to decrypt vault session %s...: %s", session_id[:8], exc)
                return {}
        return json.loads(token_payload)

    def delete_session(self, session_id: str) -> None:
        """Delete a session's token mapping."""
        placeholder = "%s" if self._database_backend == "postgres" else "?"
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM pii_sessions WHERE session_id = {placeholder}",
                (session_id,),
            )
        logger.info("Deleted session %s... from vault", session_id[:8])

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of deleted sessions."""
        now = datetime.now(timezone.utc).isoformat()
        placeholder = "%s" if self._database_backend == "postgres" else "?"
        with self._connect() as conn:
            cursor = conn.execute(
                f"DELETE FROM pii_sessions WHERE expires_at IS NOT NULL AND expires_at < {placeholder}",
                (now,),
            )
        count = cursor.rowcount
        if count > 0:
            logger.info("Cleaned up %s expired vault sessions", count)
        return count
