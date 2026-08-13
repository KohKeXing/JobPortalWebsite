"""Acceptance tests for seeker and employer authentication journeys."""

import pytest

from acceptance_tests.conftest import EMPLOYER_EMAIL, SEEKER_EMAIL, VALID_PASSWORD


@pytest.mark.acceptance
class TestJobSeekerAuthentication:
    def test_signup_accepts_valid_job_seeker_details(self, seeker_context):
        response = seeker_context.client.post("/api/auth/register", json={
            "name": "Nur Aisyah",
            "email": "new.seeker@example.com",
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 201
        assert response.get_json()["success"] is True

    def test_signup_rejects_duplicate_email(self, seeker_context):
        response = seeker_context.client.post("/api/auth/register", json={
            "name": "Koh Ke Xing",
            "email": SEEKER_EMAIL,
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 409
        assert "already registered" in response.get_json()["error"].lower()

    def test_signup_rejects_weak_password(self, seeker_context):
        response = seeker_context.client.post("/api/auth/register", json={
            "name": "Nur Aisyah",
            "email": "new.seeker@example.com",
            "password": "weak",
        })

        assert response.status_code == 400
        assert response.get_json()["error"]

    def test_login_creates_job_seeker_session(self, seeker_context):
        response = seeker_context.client.post("/api/auth/login", json={
            "email": SEEKER_EMAIL,
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 200
        assert response.get_json()["redirect"] == "/dashboard"
        current_user = seeker_context.client.get("/api/auth/me")
        assert current_user.status_code == 200
        assert current_user.get_json()["user"]["email"] == SEEKER_EMAIL

    def test_login_rejects_incorrect_password(self, seeker_context):
        seeker_context.auth_service.login_error = "Invalid email or password."
        response = seeker_context.client.post("/api/auth/login", json={
            "email": SEEKER_EMAIL,
            "password": "WrongPass1!",
        })

        assert response.status_code == 401
        assert "incorrect password" in response.get_json()["error"].lower()

    def test_forgot_password_sends_reset_request_for_registered_email(self, seeker_context):
        response = seeker_context.client.post("/api/auth/forgot-password", json={
            "email": SEEKER_EMAIL,
        })

        assert response.status_code == 200
        assert seeker_context.auth_client.reset_requests[0]["email"] == SEEKER_EMAIL
        redirect_url = seeker_context.auth_client.reset_requests[0]["options"]["redirect_to"]
        assert redirect_url.endswith("/reset-password")

    def test_forgot_password_rejects_unknown_email(self, seeker_context):
        response = seeker_context.client.post("/api/auth/forgot-password", json={
            "email": "missing.seeker@example.com",
        })

        assert response.status_code == 404

    def test_reset_password_accepts_valid_recovery_tokens(self, seeker_context):
        response = seeker_context.client.post("/api/auth/update-password", json={
            "password": "NewStrong1!",
            "access_token": "valid-access-token",
            "refresh_token": "valid-refresh-token",
        })

        assert response.status_code == 200
        assert seeker_context.auth_client.sessions == [
            ("valid-access-token", "valid-refresh-token")
        ]
        assert seeker_context.auth_client.password_updates == ["NewStrong1!"]

    def test_reset_password_rejects_missing_recovery_tokens(self, seeker_context):
        response = seeker_context.client.post("/api/auth/update-password", json={
            "password": "NewStrong1!",
        })

        assert response.status_code == 400
        assert "reset link" in response.get_json()["error"].lower()


@pytest.mark.acceptance
class TestEmployerAuthentication:
    def test_signup_accepts_valid_employer_details(self, employer_context):
        response = employer_context.client.post("/api/employer/register", json={
            "company_name": "New Employer Company",
            "email": "new.employer@example.com",
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 201
        assert response.get_json()["success"] is True
        created = [
            row for row in employer_context.admin.tables["employers"]
            if row.get("company_email") == "new.employer@example.com"
        ]
        assert len(created) == 1
        assert str(created[0]["employer_id"]).startswith("EMP")

    def test_signup_rejects_duplicate_employer_email(self, employer_context):
        response = employer_context.client.post("/api/employer/register", json={
            "company_name": "Acceptance Technologies",
            "email": EMPLOYER_EMAIL,
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 409

    def test_login_creates_employer_session(self, employer_context):
        response = employer_context.client.post("/api/employer/verify", json={
            "email": EMPLOYER_EMAIL,
            "password": VALID_PASSWORD,
        })

        assert response.status_code == 200
        assert response.get_json()["employer_id"] == "EMP001"
        session_check = employer_context.client.get("/api/employer/check-session")
        assert session_check.get_json()["logged_in"] is True

    def test_login_rejects_invalid_employer_credentials(self, employer_context):
        employer_context.auth_client.login_error = Exception("invalid credentials")
        response = employer_context.client.post("/api/employer/verify", json={
            "email": EMPLOYER_EMAIL,
            "password": "WrongPass1!",
        })

        assert response.status_code == 401
        assert "invalid" in response.get_json()["error"].lower()

    def test_forgot_password_uses_employer_reset_page(self, employer_context):
        response = employer_context.client.post("/api/auth/forgot-password", json={
            "email": EMPLOYER_EMAIL,
        })

        assert response.status_code == 200
        request = employer_context.auth_client.reset_requests[0]
        assert request["email"] == EMPLOYER_EMAIL
        assert request["options"]["redirect_to"].endswith("/reset-password")

    def test_reset_password_updates_employer_password(self, employer_context):
        response = employer_context.client.post("/api/auth/update-password", json={
            "password": "EmployerNew1!",
            "access_token": "employer-access",
            "refresh_token": "employer-refresh",
        })

        assert response.status_code == 200
        assert employer_context.auth_client.password_updates == ["EmployerNew1!"]
