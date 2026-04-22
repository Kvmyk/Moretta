"""
Shared encryption helpers for storage backends.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def build_fernet(encryption_key: str) -> Fernet | None:
    if not encryption_key:
        return None

    key32 = base64.urlsafe_b64encode(hashlib.sha256(encryption_key.encode("utf-8")).digest())
    return Fernet(key32)


def encrypt_bytes(data: bytes, fernet: Fernet | None) -> bytes:
    if not fernet:
        return data
    return fernet.encrypt(data)


def decrypt_bytes(data: bytes, fernet: Fernet | None) -> bytes:
    if not fernet:
        return data
    return fernet.decrypt(data)


def encrypt_text(text: str, fernet: Fernet | None) -> str:
    payload = text.encode("utf-8")
    encrypted = encrypt_bytes(payload, fernet)
    return base64.urlsafe_b64encode(encrypted).decode("ascii")


def decrypt_text(text: str, fernet: Fernet | None) -> str:
    payload = base64.urlsafe_b64decode(text.encode("ascii"))
    decrypted = decrypt_bytes(payload, fernet)
    return decrypted.decode("utf-8")


__all__ = [
    "InvalidToken",
    "build_fernet",
    "decrypt_bytes",
    "decrypt_text",
    "encrypt_bytes",
    "encrypt_text",
]
