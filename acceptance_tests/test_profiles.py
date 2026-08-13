"""Acceptance tests for job seeker and employer profiles."""

import io

import pytest

import employer_main
from acceptance_tests.conftest import login_employer, login_seeker


VALID_SEEKER_PROFILE = {
    "full_name": "Koh Ke Xing",
    "headline": "Senior Software Tester",
    "phone_country": "+60",
    "phone": "0123456789",
    "bio": "Software tester experienced in API and browser automation.",
    "skills": ["Python", "Flask", "python"],
}


@pytest.mark.acceptance
class TestJobSeekerProfile:
    def test_profile_requires_authentication(self, seeker_context):
        response = seeker_context.client.get("/api/profile")
        assert response.status_code == 401

    def test_job_seeker_can_view_registered_profile(self, seeker_context):
        login_seeker(seeker_context.client)
        response = seeker_context.client.get("/api/profile")

        assert response.status_code == 200
        profile = response.get_json()
        assert profile["full_name"] == "Koh Ke Xing"
        assert profile["email"].endswith("@example.com")

    def test_job_seeker_can_update_valid_profile(self, seeker_context):
        login_seeker(seeker_context.client)
        response = seeker_context.client.put(
            "/api/profile",
            json=VALID_SEEKER_PROFILE,
        )

        assert response.status_code == 200
        profile = response.get_json()["profile"]
        assert profile["headline"] == "Senior Software Tester"
        assert profile["phone"] == "+60 123456789"
        assert profile["skills"] == ["Python", "Flask"]

    def test_job_seeker_profile_returns_field_validation_errors(self, seeker_context):
        login_seeker(seeker_context.client)
        response = seeker_context.client.put("/api/profile", json={
            "full_name": "Koh123",
            "headline": "<script>",
            "phone_country": "+60",
            "phone": "123",
            "bio": "Too short",
            "skills": [],
        })

        assert response.status_code == 400
        field_errors = response.get_json()["field_errors"]
        assert {"full_name", "headline", "phone", "bio", "skills"} <= set(field_errors)


@pytest.mark.acceptance
class TestEmployerProfile:
    def test_employer_profile_requires_authentication(self, employer_context):
        response = employer_context.client.get("/api/employer/profile")
        assert response.status_code == 401

    def test_employer_can_view_profile(self, employer_context):
        login_employer(employer_context.client)
        response = employer_context.client.get("/api/employer/profile")

        assert response.status_code == 200
        profile = response.get_json()
        assert profile["employer_id"] == "EMP001"
        assert profile["company_name"] == "Acceptance Technologies"
        assert profile["company_email"].endswith("@example.com")

    def test_registered_company_name_cannot_be_changed(self, employer_context):
        login_employer(employer_context.client)
        response = employer_context.client.put("/api/employer/profile", json={
            "company_name": "Changed Company Name",
        })

        assert response.status_code == 403
        assert "cannot be changed" in response.get_json()["error"].lower()

    def test_logo_upload_rejects_non_image_file(self, employer_context):
        login_employer(employer_context.client)
        response = employer_context.client.post(
            "/api/employer/profile/logo",
            data={"logo": (io.BytesIO(b"plain text"), "logo.txt")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 400
        assert "jpg" in response.get_json()["error"].lower()

    def test_employer_can_upload_company_logo(self, employer_context, monkeypatch):
        login_employer(employer_context.client)
        monkeypatch.setattr(
            employer_main,
            "_upload_company_image",
            lambda *_args: {
                "url": "https://cdn.example.com/company-logo.png",
                "path": "logos/company-logo.png",
            },
        )
        monkeypatch.setattr(employer_main, "_remove_company_image", lambda *_args: None)

        response = employer_context.client.post(
            "/api/employer/profile/logo",
            data={"logo": (io.BytesIO(b"valid-image-placeholder"), "logo.png")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 200
        assert response.get_json()["profile"]["logo_url"].endswith("company-logo.png")
