"""Acceptance tests for the employer's public company background page."""

import pytest

import employer_main
from acceptance_tests.conftest import login_employer


VALID_COMPANY_BACKGROUND = {
    "company_background": (
        "Acceptance Technologies develops reliable recruitment software "
        "for employers and job seekers."
    ),
    "industry": "Technology",
    "company_size": "11-50 employees",
    "location": "Penang, Malaysia",
    "website": "https://example.com/careers",
    "founded_year": 2020,
    "benefits": "Training allowance, flexible work, and medical coverage.",
}


@pytest.mark.acceptance
class TestCompanyBackground:
    def test_company_background_requires_employer_authentication(self, employer_context):
        response = employer_context.client.put(
            "/api/employer/company-profile",
            json=VALID_COMPANY_BACKGROUND,
        )
        assert response.status_code == 401

    def test_employer_can_update_complete_company_background(self, employer_context):
        login_employer(employer_context.client)
        response = employer_context.client.put(
            "/api/employer/company-profile",
            json=VALID_COMPANY_BACKGROUND,
        )

        assert response.status_code == 200
        profile = response.get_json()["profile"]
        assert profile["industry"] == "Technology"
        assert profile["company_size"] == "11-50 employees"
        assert profile["founded_year"] == 2020
        assert profile["website"].startswith("https://")

    def test_company_website_requires_http_or_https(self, employer_context):
        login_employer(employer_context.client)
        payload = {**VALID_COMPANY_BACKGROUND, "website": "www.example.com"}
        response = employer_context.client.put(
            "/api/employer/company-profile",
            json=payload,
        )

        assert response.status_code == 400
        assert "http://" in response.get_json()["error"]

    def test_founded_year_cannot_be_in_the_future(self, employer_context):
        login_employer(employer_context.client)
        payload = {
            **VALID_COMPANY_BACKGROUND,
            "founded_year": employer_main.CURRENT_YEAR + 1,
        }
        response = employer_context.client.put(
            "/api/employer/company-profile",
            json=payload,
        )

        assert response.status_code == 400
        assert str(employer_main.CURRENT_YEAR) in response.get_json()["error"]

    def test_company_size_must_use_supported_employee_range(self, employer_context):
        login_employer(employer_context.client)
        payload = {**VALID_COMPANY_BACKGROUND, "company_size": "around fifty"}
        response = employer_context.client.put(
            "/api/employer/company-profile",
            json=payload,
        )

        assert response.status_code == 400
        assert "company size" in response.get_json()["error"].lower()

    def test_public_company_background_can_be_viewed_without_login(self, employer_context):
        response = employer_context.client.get("/api/companies/EMP001")

        assert response.status_code == 200
        profile = response.get_json()
        assert profile["company_name"] == "Acceptance Technologies"
        assert profile["company_background"]
        assert all("path" not in gallery_item for gallery_item in profile["gallery"])
