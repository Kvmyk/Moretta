"""
Database connection helpers for SQLite backend.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(sqlite_path: Path) -> sqlite3.Connection:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(sqlite_path), timeout=30.0)
    # WAL lets readers run concurrently with a writer, which removes most of the
    # lock contention seen when several uploads are processed at the same time.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
