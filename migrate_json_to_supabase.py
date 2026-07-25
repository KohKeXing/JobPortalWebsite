"""One-time, repeatable migration from local job-portal JSON to Supabase.

The script preserves the current public IDs:
  - jobs:        job-1, job-2, ...
  - resumes:     res-...
  - applications: UUID strings

It performs an upsert, so running it again updates matching records instead of
creating duplicates. It never deletes records already stored in Supabase.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

VALID_APPLICATION_STATUSES = {"Pending", "Interview", "Offer", "Rejected"}
VALID_RESUME_TYPES = {"upload", "builder"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate jobs, resumes, and applications JSON to Supabase."
    )
    parser.add_argument(
        "--jobs",
        type=Path,
        default=Path("data/jobs.json"),
        help="Path to jobs.json (default: data/jobs.json)",
    )
    parser.add_argument(
        "--resumes",
        type=Path,
        default=Path("data/resumes.json"),
        help="Path to resumes.json (default: data/resumes.json)",
    )
    parser.add_argument(
        "--applications",
        type=Path,
        default=Path("data/applications.json"),
        help="Path to applications.json (default: data/applications.json)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Rows sent per request (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and transform the JSON without connecting to Supabase.",
    )
    return parser.parse_args()


def load_json_array(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"{label} file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{label} contains invalid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(value, list):
        raise ValueError(f"{label} must contain a top-level JSON array.")
    if not all(isinstance(row, dict) for row in value):
        raise ValueError(f"Every item in {label} must be a JSON object.")
    return value


def required_text(row: dict[str, Any], key: str, label: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: '{key}' must be a non-empty string.")
    return value


def optional_text(row: dict[str, Any], key: str, label: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label}: '{key}' must be a string or null.")
    return value


def iso_date(value: str, label: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: expected an ISO date (YYYY-MM-DD).") from exc
    return value


def iso_timestamp(value: str, label: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label}: expected a valid ISO timestamp.") from exc
    return value


def transform_jobs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, row in enumerate(rows):
        label = f"jobs[{index}]"
        job_id = required_text(row, "id", label)
        if job_id in seen_ids:
            raise ValueError(f"{label}: duplicate job id '{job_id}'.")
        seen_ids.add(job_id)

        tags = row.get("tags", [])
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) for tag in tags
        ):
            raise ValueError(f"{label}: 'tags' must be an array of strings.")

        featured = row.get("featured", False)
        if not isinstance(featured, bool):
            raise ValueError(f"{label}: 'featured' must be true or false.")

        posted = optional_text(row, "posted", label)
        result.append(
            {
                "id": job_id,
                "title": required_text(row, "title", label),
                "company": required_text(row, "company", label),
                "location": optional_text(row, "location", label),
                "salary": optional_text(row, "salary", label),
                "type": optional_text(row, "type", label),
                "description": optional_text(row, "description", label),
                "tags": tags,
                "featured": featured,
                "category": optional_text(row, "category", label),
                "posted": iso_date(posted, f"{label}.posted") if posted else None,
                "logo_color": optional_text(row, "logo_color", label),
                "icon": optional_text(row, "icon", label),
            }
        )
    return result


def transform_resumes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, row in enumerate(rows):
        label = f"resumes[{index}]"
        resume_id = required_text(row, "id", label)
        if resume_id in seen_ids:
            raise ValueError(f"{label}: duplicate resume id '{resume_id}'.")
        seen_ids.add(resume_id)

        resume_type = required_text(row, "type", label)
        if resume_type not in VALID_RESUME_TYPES:
            raise ValueError(
                f"{label}: unsupported resume type '{resume_type}'."
            )

        last_modified = required_text(row, "lastModified", label)
        data = row.get("data")
        if data is not None and not isinstance(data, dict):
            raise ValueError(f"{label}: 'data' must be an object or null.")

        result.append(
            {
                "id": resume_id,
                "name": required_text(row, "name", label),
                "type": resume_type,
                "file_name": optional_text(row, "fileName", label),
                "stored_file_name": optional_text(
                    row, "storedFileName", label
                ),
                "file_format": optional_text(row, "fileFormat", label),
                "layout": optional_text(row, "layout", label),
                "data": data,
                "last_modified": iso_timestamp(
                    last_modified, f"{label}.lastModified"
                ),
            }
        )
    return result


def transform_applications(
    rows: list[dict[str, Any]],
    job_ids: set[str],
    resume_ids: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, row in enumerate(rows):
        label = f"applications[{index}]"
        application_id = required_text(row, "id", label)
        try:
            UUID(application_id)
        except ValueError as exc:
            raise ValueError(
                f"{label}: id '{application_id}' is not a valid UUID."
            ) from exc
        if application_id in seen_ids:
            raise ValueError(
                f"{label}: duplicate application id '{application_id}'."
            )
        seen_ids.add(application_id)

        job_id = required_text(row, "jobId", label)
        if job_id not in job_ids:
            raise ValueError(
                f"{label}: jobId '{job_id}' does not exist in jobs JSON."
            )

        resume_id = optional_text(row, "resumeId", label)
        if resume_id is not None and resume_id not in resume_ids:
            raise ValueError(
                f"{label}: resumeId '{resume_id}' does not exist in resumes JSON."
            )

        status = required_text(row, "status", label)
        if status not in VALID_APPLICATION_STATUSES:
            allowed = ", ".join(sorted(VALID_APPLICATION_STATUSES))
            raise ValueError(
                f"{label}: invalid status '{status}'. Allowed: {allowed}."
            )

        application_date = required_text(row, "date", label)
        result.append(
            {
                "id": application_id,
                "job_id": job_id,
                "resume_id": resume_id,
                # Keep the values recorded at application time. In the supplied
                # data, some snapshots differ from the current jobs table.
                "job_title_snapshot": required_text(row, "job", label),
                "company_snapshot": required_text(row, "company", label),
                "application_date": iso_date(
                    application_date, f"{label}.date"
                ),
                "status": status,
                "details": optional_text(row, "details", label),
                "cover_letter_text": optional_text(
                    row, "coverLetterText", label
                ),
                "cover_letter_file": optional_text(
                    row, "coverLetterFile", label
                ),
                "cover_letter_original_name": optional_text(
                    row, "coverLetterOriginalName", label
                ),
            }
        )
    return result


def chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def create_supabase_client() -> Any:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise ValueError(
            "Missing package. Run: python -m pip install supabase python-dotenv"
        ) from exc

    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY"
    )

    if not url:
        raise ValueError("SUPABASE_URL is missing from the environment or .env.")
    if not secret_key:
        raise ValueError(
            "SUPABASE_SECRET_KEY is missing from the environment or .env."
        )

    try:
        from supabase import create_client
    except ImportError as exc:
        raise ValueError(
            "Missing package. Run: python -m pip install supabase python-dotenv"
        ) from exc

    return create_client(url, secret_key)


def upsert_rows(
    client: Any,
    table: str,
    rows: list[dict[str, Any]],
    batch_size: int,
) -> None:
    for batch in chunks(rows, batch_size):
        client.table(table).upsert(batch, on_conflict="id").execute()
    print(f"Upserted {len(rows):>3} row(s) into {table}.")


def main() -> int:
    args = parse_args()
    if args.batch_size < 1:
        print("Migration failed: --batch-size must be at least 1.", file=sys.stderr)
        return 1

    try:
        jobs = transform_jobs(load_json_array(args.jobs, "jobs"))
        resumes = transform_resumes(load_json_array(args.resumes, "resumes"))
        applications = transform_applications(
            load_json_array(args.applications, "applications"),
            {row["id"] for row in jobs},
            {row["id"] for row in resumes},
        )

        print(
            "Validation passed: "
            f"{len(jobs)} jobs, {len(resumes)} resumes, "
            f"{len(applications)} applications."
        )

        if args.dry_run:
            print("Dry run complete. Nothing was sent to Supabase.")
            return 0

        client = create_supabase_client()
        # Dependency order is important because applications reference jobs
        # and may reference resumes.
        upsert_rows(client, "jobs", jobs, args.batch_size)
        upsert_rows(client, "resumes", resumes, args.batch_size)
        upsert_rows(client, "applications", applications, args.batch_size)
        print("Migration completed successfully.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Supabase/PostgREST errors reach this branch. Do not print keys or
        # environment values.
        print(
            f"Migration failed while communicating with Supabase: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())