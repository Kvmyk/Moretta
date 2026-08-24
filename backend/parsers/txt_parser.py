"""
Moretta — Plain text file parser.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("moretta.parsers.txt")


def parse_txt(file_path: Path) -> dict[str, Any]:
    """Read a plain text file, tolerating unknown encodings."""
    raw = file_path.read_bytes()
    for encoding in ("utf-8", "cp1250", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")

    logger.info("Parsed TXT: %s — %s chars", file_path.name, len(text))
    return {
        "text": text,
        "preview_data": {
            "type": "document",
            "text": text,
        },
    }
