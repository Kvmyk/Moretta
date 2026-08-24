"""
Moretta - Encrypted PII vault.
Stores session token maps in SQLite with app-level encryption.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect
from storage_crypto import InvalidToken, build_fernet, decrypt_text, encrypt_text

logger = logging.getLogger("moretta.vault")


class VaultSessionError(Exception):
    """
    Raised when a token map cannot be retrieved.

    Callers must treat this as fail-closed: without the mapping we cannot
    re-anonymize a conversation, and sending it onward would leak plaintext PII
    to an external provider.
    """


class Vault:
    """Encrypted vault for PII token mappings."""

    def __init__(
        self,
        *,
        sqlite_path: Path | None = None,
        encryption_key: str = "",
    ) -> None:
        self._sqlite_path = sqlite_path
        self._fernet = build_fernet(encryption_key)

    def _connect(self):
        if not self._sqlite_path:
            raise ValueError("sqlite_path is required")
        return connect(self._sqlite_path)

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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pii_sessions_expires_at "
                "ON pii_sessions (expires_at)"
            )
        logger.info("Vault initialized (encryption %s)", "on" if self._fernet else "OFF")

    def store_session(
        self,
        session_id: str,
        token_map: dict[str, str],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store a token mapping for a session."""
        token_payload = json.dumps(token_map, ensure_ascii=False)
        if self._fernet:
            token_payload = encrypt_text(token_payload, self._fernet)

        now = datetime.now(timezone.utc)
        expires_at = (
            (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pii_sessions
                    (session_id, token_map, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, token_payload, now.isoformat(), expires_at),
            )
        logger.info("Stored %s tokens for session %s...", len(token_map), session_id[:8])

    def has_session(self, session_id: str) -> bool:
        """Check whether a mapping row exists, without decrypting it."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM pii_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row is not None

    def get_session(self, session_id: str) -> dict[str, str]:
        """
        Retrieve the token mapping for a session.

        Raises:
            VaultSessionError: if the session is missing or cannot be decrypted.
                Never returns an empty mapping as a stand-in for failure - an
                empty map would silently disable re-anonymization.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT token_map FROM pii_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            logger.warning("Session %s... not found in vault", session_id[:8])
            raise VaultSessionError("PII mapping for this session is no longer available")

        token_payload = row[0]
        if self._fernet:
            try:
                token_payload = decrypt_text(token_payload, self._fernet)
            except (InvalidToken, ValueError) as exc:
                logger.error(
                    "Failed to decrypt vault session %s...: %s", session_id[:8], exc
                )
                raise VaultSessionError(
                    "PII mapping for this session could not be decrypted"
                ) from exc

        try:
            return json.loads(token_payload)
        except json.JSONDecodeError as exc:
            logger.error("Corrupt token map for session %s...", session_id[:8])
            raise VaultSessionError("PII mapping for this session is corrupt") from exc

    def delete_session(self, session_id: str) -> None:
        """Delete a session's token mapping."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM pii_sessions WHERE session_id = ?",
                (session_id,),
            )
        logger.info("Deleted session %s... from vault", session_id[:8])

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of deleted sessions."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM pii_sessions WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            count = cursor.rowcount
        if count > 0:
            logger.info("Cleaned up %s expired vault sessions", count)
        return count
