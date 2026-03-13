"""
PrivateProxy — Encrypted PII Vault.
Stores session-based token ↔ original PII mappings in encrypted SQLite.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("privateproxy.vault")


class Vault:
    """Encrypted SQLite vault for PII token mappings."""

    def __init__(self, db_path: Path, encryption_key: str = "") -> None:
        self._db_path = db_path
        self._encryption_key = encryption_key

    def _connect(self) -> sqlite3.Connection:
        """Create a connection to the SQLite database."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))

        # Apply encryption if key is provided
        if self._encryption_key:
            try:
                conn.execute(f"PRAGMA key = '{self._encryption_key}'")
                logger.debug("Vault encryption enabled")
            except Exception as exc:
                logger.warning(f"SQLite encryption not available: {exc}. Running unencrypted.")

        return conn

    def initialize(self) -> None:
        """Create the vault table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pii_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_map TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
            """)
            conn.commit()
            logger.info(f"Vault initialized at {self._db_path}")
        finally:
            conn.close()

    def store_session(self, session_id: str, token_map: dict[str, str]) -> None:
        """Store a token mapping for a session."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO pii_sessions (session_id, token_map, created_at)
                VALUES (?, ?, ?)
                """,
                (
                    session_id,
                    json.dumps(token_map, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            logger.info(f"Stored {len(token_map)} tokens for session {session_id[:8]}...")
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict[str, str]:
        """Retrieve the token mapping for a session."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT token_map FROM pii_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row is None:
                logger.warning(f"Session {session_id[:8]}... not found in vault")
                return {}
            return json.loads(row[0])
        finally:
            conn.close()

    def delete_session(self, session_id: str) -> None:
        """Delete a session's token mapping (cleanup after task completion)."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM pii_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            logger.info(f"Deleted session {session_id[:8]}... from vault")
        finally:
            conn.close()

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of deleted sessions."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM pii_sessions WHERE expires_at IS NOT NULL AND expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"Cleaned up {count} expired vault sessions")
            return count
        finally:
            conn.close()
