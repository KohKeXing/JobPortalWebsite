"""Supabase-backed CRUD for job postings."""

from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from supabase_client import get_supabase_client


LOGO_COLOR_ROTATION = [
    "bg-blue-600 text-white",
    "bg-pink-600 text-white",
    "bg-emerald-600 text-white",
    "bg-orange-600 text-white",
    "bg-purple-600 text-white",
    "bg-teal-600 text-white",
    "bg-rose-600 text-white",
    "bg-cyan-600 text-white",
]

REQUIRED_JOB_FIELDS = [
    "title",
    "company",
    "location",
    "salary",
    "type",
    "description",
]

JOB_COLUMNS = (
    "id,title,company,location,salary,type,description,tags,featured,"
    "category,posted,logo_color,icon,employer_id"
)


def _api_job(row: dict[str, Any]) -> dict[str, Any]:
    """Return only fields used by the existing Flask/JavaScript API."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "salary": row.get("salary"),
        "type": row.get("type"),
        "description": row.get("description"),
        "tags": row.get("tags") or [],
        "featured": bool(row.get("featured", False)),
        "category": row.get("category"),
        "posted": row.get("posted"),
        "logo_color": row.get("logo_color"),
        "icon": row.get("icon"),
    }

def validate_job_data(data):
    alpha_pattern = re.compile(r"^[A-Za-z ]+$")
    location_pattern = re.compile(r"^[A-Za-z, ]+$")
    # Allow letters, spaces, commas, and ampersands in categories and tags.
    category_tag_pattern = re.compile(r"^[A-Za-z&, ]+$")
    salary_pattern = re.compile(r"^\d+$")

    title = str(data.get("title", "")).strip()
    location = str(data.get("location", "")).strip()
    category = str(data.get("category", "")).strip()
    salary = str(data.get("salary", "")).strip()
    tags = data.get("tags") or []

    if not alpha_pattern.fullmatch(title):
        raise ValueError(
            "Job title can only contain letters and spaces."
        )

    if not location_pattern.fullmatch(location):
        raise ValueError(
        "Location can only contain letters, spaces, and commas."
    )

    if category and not category_tag_pattern.fullmatch(category):
        raise ValueError(
            "Category can only contain letters, spaces, commas, and &."
        )

    if not salary_pattern.fullmatch(salary):
        raise ValueError(
            "Salary can only contain numbers."
        )

    for tag in tags:
        if not category_tag_pattern.fullmatch(str(tag).strip()):
            raise ValueError(
                "Tags can only contain letters, spaces, commas, and &."
            )
        
class JobStorage:
    """Shared Supabase persistence used by seeker and employer Flask apps."""

    def __init__(self, client: Any | None = None):
        self._provided_client = client

    @property
    def client(self) -> Any:
        return self._provided_client or get_supabase_client()

    def get_jobs(self, employer_id: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table("jobs").select(JOB_COLUMNS)
        if employer_id:
            query = query.eq("employer_id", employer_id)
        response = query.order("posted", desc=True).execute()
        return [_api_job(row) for row in (response.data or [])]

    def get_job(
        self,
        job_id: str,
        employer_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = self.client.table("jobs").select(JOB_COLUMNS).eq("id", job_id)
        if employer_id:
            query = query.eq("employer_id", employer_id)
        response = query.limit(1).execute()
        rows = response.data or []
        return _api_job(rows[0]) if rows else None

    def create_job(
        self,
        data: dict[str, Any],
        employer_id: str | None = None,
    ) -> dict[str, Any]:
        if not employer_id:
            raise ValueError("An authenticated employer account is required.")

        missing = [field for field in REQUIRED_JOB_FIELDS if not data.get(field)]
        if missing:
            raise ValueError(
                f"Missing required field(s): {', '.join(missing)}"
            )

        validate_job_data(data)

        job_count = len(self.get_jobs())
        company = data["company"].strip()
        row = {
            "id": "job-" + uuid.uuid4().hex[:10],
            "title": data["title"].strip(),
            "company": company,
            "location": data["location"].strip(),
            "salary": data["salary"].strip(),
            "type": data["type"].strip(),
            "description": data["description"].strip(),
            "tags": data.get("tags") or [],
            "featured": bool(data.get("featured", False)),
            "category": (data.get("category") or "").strip(),
            "posted": datetime.now(timezone.utc).date().isoformat(),
            "logo_color": LOGO_COLOR_ROTATION[
                job_count % len(LOGO_COLOR_ROTATION)
            ],
            "icon": company[:2].upper() if company else "JP",
            "employer_id": employer_id,
        }
        response = self.client.table("jobs").insert(row).execute()
        rows = response.data or []
        if not rows:
            created_job = self.get_job(row["id"], employer_id)
            if created_job:
                return created_job
            raise RuntimeError("Supabase did not return the created job row.")
        return _api_job(rows[0])

    def update_job(
        self,
        job_id: str,
        data: dict[str, Any],
        employer_id: str | None = None,
    ) -> dict[str, Any] | None:
        if self.get_job(job_id, employer_id) is None:
            return None

        changes: dict[str, Any] = {}
        for field in REQUIRED_JOB_FIELDS + ["category"]:
            if field in data:
                value = data[field]
                changes[field] = value.strip() if isinstance(value, str) else value

        if "tags" in data:
            changes["tags"] = data["tags"] or []
        if "featured" in data:
            changes["featured"] = bool(data["featured"])
        if data.get("company"):
            changes["icon"] = data["company"].strip()[:2].upper()

        if not changes:
            return self.get_job(job_id, employer_id)

        validate_job_data(changes)

        query = self.client.table("jobs").update(changes).eq("id", job_id)
        if employer_id:
            query = query.eq("employer_id", employer_id)
        response = query.execute()
        rows = response.data or []
        return _api_job(rows[0]) if rows else self.get_job(job_id, employer_id)

    def delete_job(
        self,
        job_id: str,
        employer_id: str | None = None,
    ) -> bool:
        if self.get_job(job_id, employer_id) is None:
            return False
        query = self.client.table("jobs").delete().eq("id", job_id)
        if employer_id:
            query = query.eq("employer_id", employer_id)
        query.execute()
        return True
