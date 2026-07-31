"""Supabase-backed CRUD for job bookmarks."""

from __future__ import annotations

from typing import Any

from supabase_client import get_supabase_client


BOOKMARK_COLUMNS = "id,job_id,created_at"


class BookmarkStorage:
    """Store bookmarks for a temporary Sprint 2 owner or a future user."""

    def __init__(self, client: Any | None = None):
        self._provided_client = client

    @property
    def client(self) -> Any:
        return self._provided_client or get_supabase_client()

    def get_job_ids(self, owner_key: str) -> list[str]:
        response = (
            self.client.table("bookmarks")
            .select(BOOKMARK_COLUMNS)
            .eq("owner_key", owner_key)
            .order("created_at", desc=True)
            .execute()
        )
        return [
            row["job_id"]
            for row in (response.data or [])
            if row.get("job_id")
        ]

    def has_bookmark(self, owner_key: str, job_id: str) -> bool:
        response = (
            self.client.table("bookmarks")
            .select("id")
            .eq("owner_key", owner_key)
            .eq("job_id", job_id)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def add_bookmark(self, owner_key: str, job_id: str) -> bool:
        """Add a bookmark and return False when it already exists."""
        if self.has_bookmark(owner_key, job_id):
            return False

        response = (
            self.client.table("bookmarks")
            .insert({"owner_key": owner_key, "job_id": job_id})
            .execute()
        )
        return bool(response.data)

    def delete_bookmark(self, owner_key: str, job_id: str) -> bool:
        """Delete a bookmark and return False when it was not present."""
        if not self.has_bookmark(owner_key, job_id):
            return False

        self.client.table("bookmarks").delete().eq(
            "owner_key", owner_key
        ).eq("job_id", job_id).execute()
        return True