"""
Database connection helpers for PostgreSQL and SQLite backends.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - depends on optional runtime dependency
    psycopg = None


def normalize_backend(database_backend: str) -> str:
    backend = (database_backend or "postgres").strip().lower()
    if backend not in {"postgres", "sqlite"}:
        raise ValueError(f"Unsupported database backend: {database_backend}")
    return backend


def connect(
    *,
    database_backend: str,
    database_url: str | None = None,
    sqlite_path: Path | None = None,
):
    backend = normalize_backend(database_backend)

    if backend == "postgres":
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL backend requires the 'psycopg' package. "
                "Install backend requirements or switch DATABASE_BACKEND=sqlite."
            )
        if not database_url:
            raise ValueError("DATABASE_URL is required for the PostgreSQL backend")
        return psycopg.connect(database_url)

    if sqlite_path is None:
        raise ValueError("sqlite_path is required for the SQLite backend")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(sqlite_path))
