"""
PrivateProxy — XLSX file parser.
Extracts text content from Microsoft Excel spreadsheets.
"""

from __future__ import annotations

import logging
from pathlib import Path

from openpyxl import load_workbook

logger = logging.getLogger("privateproxy.parsers.xlsx")


def parse_xlsx(file_path: Path) -> str:
    """
    Extract all text from an XLSX file.

    Processes all sheets and extracts cell values as structured text.

    Args:
        file_path: Path to the .xlsx file.

    Returns:
        Full text content of the spreadsheet.
    """
    wb = load_workbook(str(file_path), read_only=True, data_only=True)
    parts: list[str] = []

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        parts.append(f"[Arkusz: {sheet_name}]")

        for row in sheet.iter_rows(values_only=True):
            row_texts = []
            for cell_value in row:
                if cell_value is not None:
                    text = str(cell_value).strip()
                    if text:
                        row_texts.append(text)
            if row_texts:
                parts.append(" | ".join(row_texts))

    wb.close()

    full_text = "\n".join(parts)
    logger.info(
        f"Parsed XLSX: {file_path.name} — {len(wb.sheetnames)} sheets, {len(full_text)} chars"
    )
    return full_text
