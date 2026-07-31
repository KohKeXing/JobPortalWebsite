"""Encrypt/decrypt file bytes before they touch Supabase Storage.

Used by resume_builder.py so that resumes and cover letters are stored
encrypted at rest — even a leaked bucket URL or a storage-provider breach
does not expose readable file content without the key below.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _get_fernet():
    """Build the Fernet cipher once, from a key that lives only in .env."""
    load_dotenv(BASE_DIR / ".env")

    key = os.getenv("RESUME_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "RESUME_ENCRYPTION_KEY is missing from the root .env file. "
            "Generate one with: python -c \"from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())\" and add it to "
            ".env. Never commit this key or reuse it across environments."
        )

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "The cryptography package is missing. Run: "
            "python -m pip install cryptography"
        ) from exc

    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise RuntimeError(
            "RESUME_ENCRYPTION_KEY is not a valid Fernet key. Generate a "
            "new one with Fernet.generate_key()."
        ) from exc


def encrypt_bytes(content: bytes) -> bytes:
    """Encrypt raw file bytes before uploading to Supabase Storage."""
    return _get_fernet().encrypt(content)


def decrypt_bytes(content: bytes) -> bytes:
    """Decrypt bytes downloaded from Supabase Storage back to the original file.

    Raises RuntimeError if the ciphertext is invalid or was encrypted with a
    different key (e.g. key rotated without re-encrypting old files) — this
    is intentional: it is safer to fail loudly than to silently hand back
    garbage bytes as a "resume".
    """
    from cryptography.fernet import InvalidToken

    try:
        return _get_fernet().decrypt(content)
    except InvalidToken as exc:
        raise RuntimeError(
            "Could not decrypt this file — it may have been stored before "
            "encryption was enabled, or with a different key."
        ) from exc