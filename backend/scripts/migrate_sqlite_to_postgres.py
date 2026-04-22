"""
One-time migration utility from legacy SQLite files to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py \
        --store-db ../data/store.db \
        --vault-db ../data/vault.db \
        --database-url postgresql://moretta:moretta@localhost:5432/moretta \
        --encryption-key your-secret
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage_crypto import build_fernet, decrypt_bytes, decrypt_text


def _load_legacy_store(conn: sqlite3.Connection, table: str, blob_dir: Path, fernet):
    rows = conn.execute(f"SELECT key, value, created_at FROM {table}").fetchall()
    for key, value_json, created_at in rows:
        payload = json.loads(value_json)
        blobs: dict[str, str] = {}
        blob_path = blob_dir / f"{key}.original_bytes"
        if blob_path.exists():
            blob_data = blob_path.read_bytes()
            if fernet:
                blob_data = decrypt_bytes(blob_data, fernet)
            blobs["original_bytes"] = base64.b64encode(blob_data).decode("ascii")
        yield key, json.dumps(payload, ensure_ascii=False), created_at or "", json.dumps(blobs)


def _load_legacy_vault(conn: sqlite3.Connection, fernet):
    rows = conn.execute(
        "SELECT session_id, token_map, created_at, expires_at FROM pii_sessions"
    ).fetchall()
    for session_id, token_map, created_at, expires_at in rows:
        if fernet:
            try:
                token_map = decrypt_text(token_map, fernet)
            except Exception:
                pass
        yield session_id, token_map, created_at, expires_at


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy SQLite storage into PostgreSQL.")
    parser.add_argument("--store-db", type=Path, required=True, help="Path to legacy store.db")
    parser.add_argument("--vault-db", type=Path, required=True, help="Path to legacy vault.db")
    parser.add_argument("--blob-dir", type=Path, help="Path to legacy blob directory")
    parser.add_argument("--database-url", required=True, help="Target PostgreSQL DSN")
    parser.add_argument("--encryption-key", default="", help="Vault/blob encryption key if used")
    args = parser.parse_args()

    blob_dir = args.blob_dir or args.store_db.parent / "blobs"
    fernet = build_fernet(args.encryption_key)

    with psycopg.connect(args.database_url) as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS files (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT,
                    blob_data TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at TEXT,
                    blob_data TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pii_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_map TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )

            with sqlite3.connect(args.store_db) as store_conn:
                for table_name in ("files", "tasks"):
                    for key, value_json, created_at, blob_json in _load_legacy_store(
                        store_conn, table_name, blob_dir, fernet
                    ):
                        cur.execute(
                            f"""
                            INSERT INTO {table_name} (key, value, created_at, blob_data)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (key) DO UPDATE
                            SET value = EXCLUDED.value,
                                created_at = EXCLUDED.created_at,
                                blob_data = EXCLUDED.blob_data
                            """,
                            (key, value_json, created_at, blob_json),
                        )

            with sqlite3.connect(args.vault_db) as vault_conn:
                for session_id, token_map, created_at, expires_at in _load_legacy_vault(vault_conn, fernet):
                    cur.execute(
                        """
                        INSERT INTO pii_sessions (session_id, token_map, created_at, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (session_id) DO UPDATE
                        SET token_map = EXCLUDED.token_map,
                            created_at = EXCLUDED.created_at,
                            expires_at = EXCLUDED.expires_at
                        """,
                        (session_id, token_map, created_at, expires_at),
                    )

        pg_conn.commit()

    print("Migration finished successfully.")


if __name__ == "__main__":
    main()
