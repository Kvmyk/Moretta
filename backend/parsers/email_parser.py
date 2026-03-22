"""
Moretta — Email file parser.
Extracts text content from EML and MSG email files.
"""

from __future__ import annotations

import email
import email.policy
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("moretta.parsers.email")


def parse_email(file_path: Path) -> dict[str, Any]:
    """
    Extract text from an email file (.eml or .msg).
    """
    ext = file_path.suffix.lower()

    if ext == ".msg":
        text = _parse_msg(file_path)
    elif ext == ".eml":
        text = _parse_eml(file_path)
    else:
        raise ValueError(f"Unsupported email format: {ext}")
    
    return {
        "text": text,
        "preview_data": {
            "type": "email",
            "text": text
        }
    }


def _parse_eml(file_path: Path) -> str:
    """Parse a standard .eml file using Python's email module."""
    with open(file_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    parts: list[str] = []

    # Headers
    subject = msg.get("Subject", "")
    sender = msg.get("From", "")
    to = msg.get("To", "")
    date = msg.get("Date", "")
    cc = msg.get("Cc", "")

    if subject:
        parts.append(f"Temat: {subject}")
    if sender:
        parts.append(f"Od: {sender}")
    if to:
        parts.append(f"Do: {to}")
    if cc:
        parts.append(f"DW: {cc}")
    if date:
        parts.append(f"Data: {date}")

    parts.append("")  # Separator

    # Body
    body = _extract_body(msg)
    if body:
        parts.append(body)

    full_text = "\n".join(parts)
    logger.info(f"Parsed EML: {file_path.name} — {len(full_text)} chars")
    return full_text


def _parse_msg(file_path: Path) -> str:
    """Parse a Microsoft Outlook .msg file using extract-msg."""
    try:
        import extract_msg

        msg = extract_msg.Message(str(file_path))
        parts: list[str] = []

        if msg.subject:
            parts.append(f"Temat: {msg.subject}")
        if msg.sender:
            parts.append(f"Od: {msg.sender}")
        if msg.to:
            parts.append(f"Do: {msg.to}")
        if msg.cc:
            parts.append(f"DW: {msg.cc}")
        if msg.date:
            parts.append(f"Data: {msg.date}")

        parts.append("")

        if msg.body:
            parts.append(msg.body)

        msg.close()

        full_text = "\n".join(parts)
        logger.info(f"Parsed MSG: {file_path.name} — {len(full_text)} chars")
        return full_text

    except ImportError:
        raise RuntimeError("extract-msg is required for .msg file parsing")


def _extract_body(msg: email.message.Message) -> str:
    """Extract the text body from an email message."""
    if msg.is_multipart():
        text_parts: list[str] = []
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text_parts.append(payload.decode(charset, errors="replace"))
                    except (LookupError, UnicodeDecodeError):
                        text_parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(text_parts)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                return payload.decode("utf-8", errors="replace")
    return ""
