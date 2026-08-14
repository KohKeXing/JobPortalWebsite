"""Supabase-backed CRUD for job applications."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from supabase_client import get_supabase_client


VALID_STATUSES = ["Pending", "Interview", "Offer", "Rejected"]


def _is_valid_uuid(value: Any) -> bool:
    """Check a string looks like a UUID before querying a UUID column.

    Without this, an ID like "does-not-exist-123" reaches Postgres and
    raises a raw type error (22P02) instead of a clean "not found" --
    Flask turns that into an unhandled 500 rather than the intended 404.
    """
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


APPLICATION_COLUMNS = (
    "id,job_id,job_title_snapshot,company_snapshot,application_date,status,"
    "details,resume_id,cover_letter_text,cover_letter_file,"
    "cover_letter_original_name,owner_key"
)


def _api_application(row: dict[str, Any]) -> dict[str, Any]:
    """Map snake_case database fields to the current camelCase API."""
    return {
        "id": row.get("id"),
        "jobId": row.get("job_id"),
        "job": row.get("job_title_snapshot"),
        "company": row.get("company_snapshot"),
        "date": row.get("application_date"),
        "status": row.get("status"),
        "details": row.get("details") or "",
        "resumeId": row.get("resume_id"),
        "coverLetterText": row.get("cover_letter_text"),
        "coverLetterFile": row.get("cover_letter_file"),
        "coverLetterOriginalName": row.get("cover_letter_original_name"),
        "ownerKey": row.get("owner_key"),
    }


class ApplicationTracking:
    """Shared Supabase application storage for seeker and employer apps."""

    def __init__(self, client: Any | None = None):
        self._provided_client = client

    @property
    def client(self) -> Any:
        return self._provided_client or get_supabase_client()

    def get_applications(self) -> list[dict[str, Any]]:
        response = (
            self.client.table("applications")
            .select(APPLICATION_COLUMNS)
            .order("application_date", desc=True)
            .execute()
        )
        return [_api_application(row) for row in (response.data or [])]

    def get_applications_for_owner(
        self,
        owner_key: str,
    ) -> list[dict[str, Any]]:
        """Return only applications created by one signed-in job seeker."""
        if not owner_key:
            return []
        response = (
            self.client.table("applications")
            .select(APPLICATION_COLUMNS)
            .eq("owner_key", owner_key)
            .order("application_date", desc=True)
            .execute()
        )
        return [_api_application(row) for row in (response.data or [])]

    def get_application(self, app_id: str) -> dict[str, Any] | None:
        if not _is_valid_uuid(app_id):
            return None
        response = (
            self.client.table("applications")
            .select(APPLICATION_COLUMNS)
            .eq("id", app_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _api_application(rows[0]) if rows else None

    def add_application(
        self,
        job_id: str,
        job_title: str,
        company: str,
        date: str | None = None,
        status: str = "Pending",
        details: str = "",
        resume_id: str | None = None,
        cover_letter_text: str | None = None,
        cover_letter_file: str | None = None,
        cover_letter_original_name: str | None = None,
        owner_key: str | None = None,
    ) -> dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Status must be one of: {', '.join(VALID_STATUSES)}"
            )
        if date is None:
            date = datetime.now(timezone.utc).date().isoformat()

        row = {
            "id": str(uuid.uuid4()),
            "job_id": job_id,
            "job_title_snapshot": job_title,
            "company_snapshot": company,
            "application_date": date,
            "status": status,
            "details": details,
            "resume_id": resume_id,
            "cover_letter_text": cover_letter_text,
            "cover_letter_file": cover_letter_file,
            "cover_letter_original_name": cover_letter_original_name,
            "owner_key": owner_key,
        }
        response = self.client.table("applications").insert(row).execute()
        return _api_application(response.data[0])

    def update_status(
        self,
        app_id: str,
        new_status: str,
        new_details: str | None = None,
    ) -> bool:
        if new_status not in VALID_STATUSES:
            raise ValueError(
                f"Status must be one of: {', '.join(VALID_STATUSES)}"
            )
        if not _is_valid_uuid(app_id):
            return False

        changes: dict[str, Any] = {"status": new_status}
        if new_details is not None:
            changes["details"] = new_details

        response = (
            self.client.table("applications")
            .update(changes)
            .eq("id", app_id)
            .execute()
        )
        return bool(response.data)

    def claim_legacy_application(self, app_id: str, owner_key: str) -> bool:
        """Attach a pre-owner-key application to its verified seeker.

        The caller must first verify ownership (for example by matching the
        submitted resume email/name to the signed-in profile).  The database
        update itself is guarded so an already-owned application can never be
        reassigned.
        """
        if not _is_valid_uuid(app_id) or not owner_key:
            return False
        response = (
            self.client.table("applications")
            .update({"owner_key": owner_key})
            .eq("id", app_id)
            .is_("owner_key", "null")
            .execute()
        )
        return bool(response.data)

    def delete_application(self, app_id: str) -> bool:
        if self.get_application(app_id) is None:
            return False
        self.client.table("applications").delete().eq("id", app_id).execute()
        return True

    def get_owner_key_for_cover_letter(self, cover_letter_file: str) -> str | None:
        """Return the owner_key of the application this cover letter belongs
        to, or None if no application references it (or it predates the
        owner_key migration)."""
        response = (
            self.client.table("applications")
            .select("owner_key")
            .eq("cover_letter_file", cover_letter_file)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0].get("owner_key") if rows else None

    def cover_letter_belongs_to_application(self, cover_letter_file: str) -> bool:
        """True if some application actually references this file (used by
        the employer app, which has no owner session of its own)."""
        response = (
            self.client.table("applications")
            .select("id")
            .eq("cover_letter_file", cover_letter_file)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def resume_belongs_to_application(self, resume_id: str) -> bool:
        """True if some application actually references this resume (used
        by the employer app to confirm a resume was really submitted, not
        just guessed)."""
        response = (
            self.client.table("applications")
            .select("id")
            .eq("resume_id", resume_id)
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def get_applications_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Return every application submitted against a specific job."""
        response = (
            self.client.table("applications")
            .select(APPLICATION_COLUMNS)
            .eq("job_id", job_id)
            .execute()
        )
        return [_api_application(row) for row in (response.data or [])]

    def delete_applications_for_job(self, job_id: str) -> list[dict[str, Any]]:
        """Delete every application tied to a job (used for cascade delete).

        Returns the applications that were removed so the caller can clean up
        any associated files (e.g. cover letters) stored outside the table.
        """
        applications = self.get_applications_for_job(job_id)
        if applications:
            self.client.table("applications").delete().eq("job_id", job_id).execute()
        return applications