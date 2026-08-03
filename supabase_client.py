"""Supabase clients used by the Flask application.

The admin client is used only on the server for trusted database operations.
The auth client is created fresh for each register/login operation so one
user's Supabase session is never shared with another Flask request.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent


def _load_settings() -> tuple[str, str, str]:
    load_dotenv(BASE_DIR / ".env", override=False)

    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    admin_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # ← This should be here
        or os.getenv("SUPABASE_SECRET_KEY")     # ← Fallback for backwards compatibility
        or ""
    ).strip()
    anon_key = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or ""
    ).strip()

    if not url:
        raise RuntimeError("SUPABASE_URL is missing from .env.")

    if not admin_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) is missing "
            "from .env. Do not place the anon key in this variable."
        )

    if not anon_key:
        raise RuntimeError(
            "SUPABASE_ANON_KEY (or SUPABASE_PUBLISHABLE_KEY) is missing "
            "from .env."
        )

    return url, admin_key, anon_key


def _jwt_role(key: str) -> str | None:
    """Read the role claim from legacy JWT keys when possible."""
    if key.startswith("sb_"):
        # New Supabase secret/publishable keys don't contain JWT claims.
        return None

    try:
        parts = key.split(".")
        if len(parts) != 3:
            return None

        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()

        return json.loads(decoded).get("role")

    except Exception:
        return None


def _create_client(url: str, key: str) -> Any:
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError(
            "Supabase packages are missing. "
            "Run:\n"
            "python -m pip install supabase python-dotenv"
        ) from exc

    return create_client(url, key)


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Any:
    """
    Cached server-side client.

    This client is used only by the Flask backend for database operations.
    """

    url, admin_key, _ = _load_settings()

    role = _jwt_role(admin_key)

    if role in {"anon", "authenticated"}:
        raise RuntimeError(
            "The value in SUPABASE_SERVICE_ROLE_KEY is not an admin key.\n"
            "Copy the Service Role (legacy) or Secret key "
            "from Project Settings → API."
        )

    return _create_client(url, admin_key)


def create_supabase_auth_client() -> Any:
    """
    Fresh client used only for login/register.

    A new client is created for every request so users do not share
    authentication sessions.
    """

    url, _, anon_key = _load_settings()

    return _create_client(url, anon_key)


# Backwards compatibility
# Existing modules (job.py, resume_builder.py, bookmark.py, etc.)
# already import get_supabase_client().
def get_supabase_client() -> Any:
    return get_supabase_admin_client()