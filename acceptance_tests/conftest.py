"""Deterministic fixtures for the JobPortal acceptance-test suite.

The Flask route handlers are real. External Supabase, Auth, Storage, and email
operations are replaced with small in-memory fakes so the acceptance suite can
run repeatedly without creating accounts, sending emails, or changing live
project data.
"""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import employer_main  # noqa: E402
import seeker_main  # noqa: E402


SEEKER_USER_ID = "11111111-1111-4111-8111-111111111111"
EMPLOYER_USER_ID = "22222222-2222-4222-8222-222222222222"
SEEKER_EMAIL = "seeker.acceptance@example.com"
EMPLOYER_EMAIL = "employer.acceptance@example.com"
VALID_PASSWORD = "StrongPass1!"


class AccountDirectory:
    def __init__(self, emails: set[str] | None = None):
        self.emails = {email.lower() for email in (emails or set())}

    def exists(self, email: str) -> bool:
        return str(email or "").strip().lower() in self.emails


class FakeSeekerAuthService:
    def __init__(self):
        self.registration_error = None
        self.login_error = None
        self.profile = {
            "id": SEEKER_USER_ID,
            "full_name": "Koh Ke Xing",
            "headline": "Software Tester",
            "phone": "+60 123456789",
            "bio": "Quality assurance specialist with automation experience.",
            "skills": ["Python", "Selenium"],
            "avatar": None,
            "role": "job_seeker",
        }

    def register_user(self, email: str, password: str, full_name: str):
        if self.registration_error:
            return None, self.registration_error
        return {
            "id": SEEKER_USER_ID,
            "email": email,
            "full_name": full_name,
            "role": "job_seeker",
        }, None

    def login_user(self, email: str, password: str):
        if self.login_error:
            return None, self.login_error
        return {
            "id": SEEKER_USER_ID,
            "email": email,
            "full_name": self.profile["full_name"],
            "role": "job_seeker",
            "access_token": "seeker-access-token",
            "refresh_token": "seeker-refresh-token",
        }, None

    def get_profile(self, user_id: str):
        if user_id != SEEKER_USER_ID:
            return None
        return copy.deepcopy(self.profile)

    def update_profile(self, user_id: str, updates: dict[str, Any]):
        if user_id != SEEKER_USER_ID:
            return None
        self.profile.update(copy.deepcopy(updates))
        return copy.deepcopy(self.profile)


class FakeAuthClient:
    """Subset of supabase.auth used by both Flask applications."""

    def __init__(self, user_id: str, email: str):
        self.auth = self
        self.user_id = user_id
        self.email = email
        self.login_error: Exception | None = None
        self.reset_requests: list[dict[str, Any]] = []
        self.sessions: list[tuple[str, str]] = []
        self.password_updates: list[str] = []
        self.signed_out = False

    def sign_up(self, payload: dict[str, Any]):
        options = payload.get("options") or {}
        metadata = options.get("data") or {}
        user = SimpleNamespace(
            id=self.user_id,
            email=payload.get("email"),
            user_metadata=metadata,
        )
        return SimpleNamespace(user=user, session=SimpleNamespace(access_token="signup"))

    def sign_in_with_password(self, payload: dict[str, Any]):
        if self.login_error:
            raise self.login_error
        user = SimpleNamespace(id=self.user_id, email=payload.get("email"))
        auth_session = SimpleNamespace(
            access_token="employer-access-token",
            refresh_token="employer-refresh-token",
        )
        return SimpleNamespace(user=user, session=auth_session)

    def reset_password_for_email(self, email: str, options: dict[str, Any]):
        self.reset_requests.append({"email": email, "options": options})
        return SimpleNamespace()

    def set_session(self, access_token: str, refresh_token: str):
        self.sessions.append((access_token, refresh_token))
        return SimpleNamespace()

    def update_user(self, payload: dict[str, Any]):
        self.password_updates.append(payload.get("password"))
        return SimpleNamespace(user=SimpleNamespace(id=self.user_id))

    def sign_out(self):
        self.signed_out = True


class MemoryQuery:
    def __init__(self, admin: "MemoryAdmin", table_name: str):
        self.admin = admin
        self.table_name = table_name
        self.action = "select"
        self.payload: Any = None
        self.filters: list[tuple[str, str, Any]] = []
        self.conflict_fields: list[str] = []
        self.limit_value: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column: str, value: Any):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]):
        self.filters.append(("in", column, {str(value) for value in values}))
        return self

    def is_(self, column: str, value: Any):
        self.filters.append(("is", column, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def insert(self, payload: Any):
        self.action = "insert"
        self.payload = payload
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None):
        self.action = "upsert"
        self.payload = payload
        self.conflict_fields = [
            field.strip() for field in str(on_conflict or "").split(",")
            if field.strip()
        ]
        return self

    def update(self, payload: dict[str, Any]):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for operator, column, expected in self.filters:
            actual = row.get(column)
            if operator == "eq" and str(actual) != str(expected):
                return False
            if operator == "in" and str(actual) not in expected:
                return False
            if operator == "is":
                if str(expected).lower() == "null" and actual is not None:
                    return False
                if str(expected).lower() != "null" and actual != expected:
                    return False
        return True

    def _normalise_rows(self, payload: Any) -> list[dict[str, Any]]:
        rows = payload if isinstance(payload, list) else [payload]
        return [copy.deepcopy(row) for row in rows]

    def _add_generated_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        existing_count = len(self.admin.tables.setdefault(self.table_name, []))
        if self.table_name == "employers":
            row.setdefault("id", f"employer-row-{existing_count + 1}")
            row.setdefault("employer_id", f"EMP{existing_count + 1:03d}")
        elif self.table_name == "employer_interviews":
            row.setdefault("id", f"INT{existing_count + 1:03d}")
        elif self.table_name.endswith("notifications"):
            row.setdefault("id", f"NOTE{existing_count + 1:03d}")
        return row

    def execute(self):
        table = self.admin.tables.setdefault(self.table_name, [])

        if self.action == "select":
            result = [copy.deepcopy(row) for row in table if self._matches(row)]
            if self.limit_value is not None:
                result = result[:self.limit_value]
            return SimpleNamespace(data=result)

        if self.action == "insert":
            inserted = []
            for row in self._normalise_rows(self.payload):
                row = self._add_generated_fields(row)
                table.append(row)
                inserted.append(copy.deepcopy(row))
            return SimpleNamespace(data=inserted)

        if self.action == "upsert":
            saved = []
            for incoming in self._normalise_rows(self.payload):
                match = None
                if self.conflict_fields:
                    match = next((
                        row for row in table
                        if all(str(row.get(field)) == str(incoming.get(field))
                               for field in self.conflict_fields)
                    ), None)
                if match is None:
                    incoming = self._add_generated_fields(incoming)
                    table.append(incoming)
                    match = incoming
                else:
                    match.update(incoming)
                saved.append(copy.deepcopy(match))
            return SimpleNamespace(data=saved)

        if self.action == "update":
            updated = []
            for row in table:
                if self._matches(row):
                    row.update(copy.deepcopy(self.payload))
                    updated.append(copy.deepcopy(row))
            return SimpleNamespace(data=updated)

        if self.action == "delete":
            deleted = [copy.deepcopy(row) for row in table if self._matches(row)]
            self.admin.tables[self.table_name] = [
                row for row in table if not self._matches(row)
            ]
            return SimpleNamespace(data=deleted)

        raise AssertionError(f"Unsupported in-memory action: {self.action}")


class MemoryAdmin:
    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "profiles": [],
            "employers": [],
            "employer_job_controls": [],
            "employer_interviews": [],
            "employer_notifications": [],
            "job_seeker_notifications": [],
        }

    def table(self, table_name: str):
        return MemoryQuery(self, table_name)


class MemoryJobStore:
    def __init__(self, jobs: list[dict[str, Any]] | None = None):
        self.jobs = {str(job["id"]): copy.deepcopy(job) for job in (jobs or [])}

    def get_jobs(self, employer_id: str | None = None):
        rows = list(self.jobs.values())
        if employer_id:
            rows = [
                row for row in rows
                if str(row.get("employerId") or row.get("employer_id") or "")
                == str(employer_id)
            ]
        return copy.deepcopy(rows)

    def get_job(self, job_id: str, employer_id: str | None = None):
        row = self.jobs.get(str(job_id))
        if not row:
            return None
        owner = row.get("employerId") or row.get("employer_id")
        if employer_id and str(owner) != str(employer_id):
            return None
        return copy.deepcopy(row)

    def create_job(self, data: dict[str, Any], employer_id: str):
        job_id = f"JOB{len(self.jobs) + 1:03d}"
        row = {"id": job_id, **copy.deepcopy(data), "employerId": employer_id}
        self.jobs[job_id] = row
        return copy.deepcopy(row)

    def update_job(self, job_id: str, data: dict[str, Any], employer_id: str):
        if self.get_job(job_id, employer_id) is None:
            return None
        self.jobs[str(job_id)].update(copy.deepcopy(data))
        return copy.deepcopy(self.jobs[str(job_id)])

    def delete_job(self, job_id: str, employer_id: str | None = None):
        if self.get_job(job_id, employer_id) is None:
            return False
        del self.jobs[str(job_id)]
        return True


class MemoryApplicationTracker:
    def __init__(self, applications: list[dict[str, Any]] | None = None):
        self.applications = {
            str(application["id"]): copy.deepcopy(application)
            for application in (applications or [])
        }

    def get_application(self, application_id: str):
        application = self.applications.get(str(application_id))
        return copy.deepcopy(application) if application else None

    def get_applications(self):
        return copy.deepcopy(list(self.applications.values()))

    def get_applications_for_owner(self, owner_key: str):
        return [
            copy.deepcopy(item) for item in self.applications.values()
            if str(item.get("ownerKey") or item.get("owner_key") or "")
            == str(owner_key)
        ]

    def update_status(self, application_id: str, status: str, details=None):
        application = self.applications.get(str(application_id))
        if not application:
            return False
        application["status"] = status
        if details is not None:
            application["details"] = details
        return True

    def delete_applications_for_job(self, job_id: str):
        removed = [
            copy.deepcopy(item) for item in self.applications.values()
            if str(item.get("jobId")) == str(job_id)
        ]
        for item in removed:
            self.applications.pop(str(item["id"]), None)
        return removed


def login_seeker(client):
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = SEEKER_USER_ID
        flask_session["email"] = SEEKER_EMAIL
        flask_session["full_name"] = "Koh Ke Xing"
        flask_session["role"] = "job_seeker"


def login_employer(client):
    with client.session_transaction() as flask_session:
        flask_session["auth_user_id"] = EMPLOYER_USER_ID
        flask_session["employer_id"] = "EMP001"
        flask_session["company_name"] = "Acceptance Technologies"
        flask_session["company_email"] = EMPLOYER_EMAIL
        flask_session["role"] = "employer"


@dataclass
class AcceptanceContext:
    client: Any
    accounts: AccountDirectory
    auth_client: FakeAuthClient
    admin: MemoryAdmin | None = None
    auth_service: FakeSeekerAuthService | None = None


@pytest.fixture
def seeker_context(monkeypatch):
    monkeypatch.delenv("PASSWORD_RESET_REDIRECT_URL", raising=False)
    accounts = AccountDirectory({SEEKER_EMAIL})
    auth_client = FakeAuthClient(SEEKER_USER_ID, SEEKER_EMAIL)
    auth_service = FakeSeekerAuthService()

    monkeypatch.setattr(seeker_main, "auth_account_exists", accounts.exists)
    monkeypatch.setattr(seeker_main, "create_supabase_auth_client", lambda: auth_client)
    monkeypatch.setattr(seeker_main, "auth_service", auth_service)

    app = seeker_main.create_app()
    app.config.update(TESTING=True, SECRET_KEY="acceptance-seeker-secret")
    return AcceptanceContext(
        client=app.test_client(),
        accounts=accounts,
        auth_client=auth_client,
        auth_service=auth_service,
    )


@pytest.fixture
def employer_context(monkeypatch):
    monkeypatch.delenv("EMPLOYER_PASSWORD_RESET_REDIRECT_URL", raising=False)
    monkeypatch.delenv("EMPLOYER_EMAIL_CONFIRMATION_REDIRECT_URL", raising=False)
    accounts = AccountDirectory({EMPLOYER_EMAIL})
    auth_client = FakeAuthClient(EMPLOYER_USER_ID, EMPLOYER_EMAIL)
    admin = MemoryAdmin()
    employer = {
        "id": "employer-row-1",
        "user_id": EMPLOYER_USER_ID,
        "employer_id": "EMP001",
        "company_name": "Acceptance Technologies",
        "company_email": EMPLOYER_EMAIL,
        "logo_url": "",
        "logo_path": "",
        "company_background": "We build reliable hiring software.",
        "industry": "Technology",
        "company_size": "11-50 employees",
        "location": "Penang, Malaysia",
        "website": "https://example.com",
        "founded_year": 2020,
        "benefits": "Training and flexible working arrangements.",
        "gallery": [{
            "url": "https://cdn.example.com/company-gallery.png",
            "path": "private/company-gallery.png",
        }],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    admin.tables["employers"].append(employer)

    def employer_by_user_id(user_id: str):
        row = next((
            item for item in admin.tables["employers"]
            if str(item.get("user_id")) == str(user_id)
        ), None)
        return copy.deepcopy(row) if row else None

    def employer_by_public_id(employer_id: str):
        row = next((
            item for item in admin.tables["employers"]
            if str(item.get("employer_id")).upper() == str(employer_id).upper()
        ), None)
        return copy.deepcopy(row) if row else None

    monkeypatch.setattr(employer_main, "auth_account_exists", accounts.exists)
    monkeypatch.setattr(employer_main, "create_supabase_auth_client", lambda: auth_client)
    monkeypatch.setattr(employer_main, "get_supabase_admin_client", lambda: admin)
    monkeypatch.setattr(employer_main, "get_employer_by_user_id", employer_by_user_id)
    monkeypatch.setattr(employer_main, "get_employer_from_db", employer_by_public_id)

    app = employer_main.create_app()
    app.config.update(TESTING=True, SECRET_KEY="acceptance-employer-secret")
    return AcceptanceContext(
        client=app.test_client(),
        accounts=accounts,
        auth_client=auth_client,
        admin=admin,
    )


@dataclass
class WorkflowContext:
    employer_client: Any
    seeker_client: Any
    admin: MemoryAdmin
    jobs: MemoryJobStore
    applications: MemoryApplicationTracker


@pytest.fixture
def workflow_context(employer_context, monkeypatch):
    admin = employer_context.admin
    jobs = MemoryJobStore([{
        "id": "JOB001",
        "title": "Software Test Engineer",
        "company": "Acceptance Technologies",
        "location": "Penang",
        "salary": "5000",
        "type": "Full-time",
        "description": "Test web applications and APIs.",
        "employerId": EMPLOYER_USER_ID,
    }])
    applications = MemoryApplicationTracker([{
        "id": "APP001",
        "jobId": "JOB001",
        "job": "Software Test Engineer",
        "company": "Acceptance Technologies",
        "date": "2026-08-14",
        "status": "Pending",
        "details": "Resume and cover letter submitted.",
        "ownerKey": SEEKER_USER_ID,
        "candidateName": "Koh Ke Xing",
    }])

    monkeypatch.setattr(employer_main, "job_store", jobs)
    monkeypatch.setattr(employer_main, "app_tracker", applications)
    monkeypatch.setattr(employer_main, "_create_notification", lambda *_a, **_k: None)
    monkeypatch.setattr(
        employer_main,
        "_enrich_applications",
        lambda items, _user_id: [
            {**copy.deepcopy(item), "candidateName": item.get("candidateName") or "Koh Ke Xing"}
            for item in items
        ],
    )
    login_employer(employer_context.client)

    monkeypatch.setattr(seeker_main, "job_store", jobs)
    monkeypatch.setattr(seeker_main, "app_tracker", applications)
    monkeypatch.setattr(seeker_main, "get_supabase_admin_client", lambda: admin)
    seeker_app = seeker_main.create_app()
    seeker_app.config.update(TESTING=True, SECRET_KEY="acceptance-workflow-secret")
    seeker_client = seeker_app.test_client()
    login_seeker(seeker_client)

    return WorkflowContext(
        employer_client=employer_context.client,
        seeker_client=seeker_client,
        admin=admin,
        jobs=jobs,
        applications=applications,
    )
