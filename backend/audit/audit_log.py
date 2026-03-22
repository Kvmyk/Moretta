"""
Moretta — Audit Logger.
Append-only JSONL log for compliance and security auditing.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("moretta.audit")


class AuditLogger:
    """Thread-safe append-only JSONL audit logger."""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self._lock = threading.Lock()

    def log(self, event: str, **kwargs: Any) -> None:
        """
        Append an audit event to the JSONL log.

        Args:
            event: Event type (e.g., 'file_uploaded', 'pii_detected', 'task_created').
            **kwargs: Additional event fields (session_id, filename, pii_count, etc.).

        Note:
            Never logs actual PII values — only types and counts.
            The 'data_left_boundary' field defaults to False.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "data_left_boundary": kwargs.pop("data_left_boundary", False),
            **kwargs,
        }

        # Safety check: if data_left_boundary is ever True, log critical warning
        if entry["data_left_boundary"]:
            logger.critical(
                f"SECURITY ALERT: data_left_boundary=true for event '{event}'. "
                f"Session: {kwargs.get('session_id', 'unknown')}"
            )

        line = json.dumps(entry, ensure_ascii=False, default=str)

        with self._lock:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        logger.debug(f"Audit: {event} — {kwargs.get('session_id', '')[:8]}")

    def read(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        Read audit log entries.

        Args:
            limit: Maximum number of entries to return.
            offset: Number of entries to skip from the end.

        Returns:
            List of audit entries, most recent first.
        """
        if not self._log_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Return most recent first
        entries.reverse()

        # Apply pagination
        return entries[offset:offset + limit]

    def count(self) -> int:
        """Return the total number of audit entries."""
        if not self._log_path.exists():
            return 0

        count = 0
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def export_csv(self) -> str:
        """Export audit log as CSV string."""
        entries = self.read(limit=10000, offset=0)
        if not entries:
            return ""

        # Collect all unique keys
        all_keys: list[str] = []
        key_set: set[str] = set()
        for entry in entries:
            for key in entry:
                if key not in key_set:
                    all_keys.append(key)
                    key_set.add(key)

        # Build CSV
        lines: list[str] = [",".join(all_keys)]
        for entry in entries:
            row = []
            for key in all_keys:
                value = entry.get(key, "")
                # Escape values for CSV
                str_val = str(value).replace('"', '""')
                if "," in str_val or '"' in str_val or "\n" in str_val:
                    str_val = f'"{str_val}"'
                row.append(str_val)
            lines.append(",".join(row))

        return "\n".join(lines)
