"""Lazy, server-side Supabase client shared by the Flask storage classes."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def get_supabase_client() -> Any:
    """Create one server-side client without exposing the secret to browsers."""
    load_dotenv(BASE_DIR / ".env")

    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY"
    )

    if not url:
        raise RuntimeError("SUPABASE_URL is missing from the root .env file.")
    if not secret_key:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY is missing from the root .env file. "
            "Do not use the anon key for server-side CRUD."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Supabase packages are missing. Run: "
            "python -m pip install supabase python-dotenv"
        ) from exc

    return create_client(url, secret_key)