"""
Moretta - PDF file parser.
Extracts text content from PDF documents.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger("moretta.parsers.pdf")


def parse_pdf(file_path: Path) -> dict[str, object]:
    """
    Extract text from a PDF file.
    """
    reader = PdfReader(str(file_path))
    parts: list[str] = []

    for page in reader.pages:
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            parts.append(text)

    full_text = "\n\n".join(parts)
    logger.info(
        "Parsed PDF: %s - %s pages, %s chars",
        file_path.name,
        len(reader.pages),
        len(full_text),
    )
    return {
        "text": full_text,
        "preview_data": {
            "type": "document",
            "text": full_text,
        },
    }
