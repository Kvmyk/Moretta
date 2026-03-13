"""
PrivateProxy — Rebuilders.
Reconstruct files (DOCX, XLSX) from AI-processed text.
"""

import io
from openpyxl import Workbook
from docx import Document

def rebuild_xlsx(text: str) -> bytes:
    """
    Reconstruct an XLSX file from AI text output.
    Uses the format produced by xlsx_parser.py:
    [Arkusz: SheetName]
    col1 | col2 | col3
    """
    wb = Workbook()
    
    # Remove default sheet
    if wb.active:
        wb.remove(wb.active)

    current_sheet = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("[Arkusz:") and line.endswith("]"):
            sheet_name = line[8:-1].strip()
            # Max sheet name length is 31
            sheet_name = sheet_name[:31] if sheet_name else "Sheet1"
            try:
                current_sheet = wb.create_sheet(title=sheet_name)
            except ValueError:
                # Fallback if invalid name
                current_sheet = wb.create_sheet(title=f"Sheet_{len(wb.sheetnames)}")
            continue

        # If no sheet was found first, create default
        if current_sheet is None:
            current_sheet = wb.create_sheet(title="Wynik")

        # Split by separator (typically " | " from parser)
        # Try finding ' | ' first, then fallback to just '|'
        if " | " in line:
            cells = line.split(" | ")
        else:
            cells = line.split("|")
            
        cells = [c.strip() for c in cells]
        current_sheet.append(cells)

    if not wb.sheetnames:
        wb.create_sheet("Empty")

    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()

def rebuild_docx(text: str) -> bytes:
    """
    Reconstruct a basic DOCX file from AI text output.
    """
    doc = Document()
    
    for line in text.splitlines():
        line = line.strip()
        if line:
            doc.add_paragraph(line)

    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()
