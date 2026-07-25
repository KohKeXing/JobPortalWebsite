"""Supabase-backed CRUD for job applications."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from supabase_client import get_supabase_client


VALID_STATUSES = ["Pending", "Interview", "Offer", "Rejected"]

APPLICATION_COLUMNS = (
    "id,job_id,job_title_snapshot,company_snapshot,application_date,status,"
    "details,resume_id,cover_letter_text,cover_letter_file,"
    "cover_letter_original_name"
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

    def get_application(self, app_id: str) -> dict[str, Any] | None:
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

    def delete_application(self, app_id: str) -> bool:
        if self.get_application(app_id) is None:
            return False
        self.client.table("applications").delete().eq("id", app_id).execute()
        return True