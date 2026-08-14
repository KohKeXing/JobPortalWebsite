"""Whole-site page, navigation, session, and route smoke tests.

These tests complement the feature acceptance suite by rendering every
user-facing Flask page in both applications. They deliberately fail on missing
templates, broken redirects, unexpected server errors, or removed routes.
"""

import os
from urllib.parse import urlparse

import pytest

import employer_main
import seeker_main
from conftest import (
    _get_test_employer,
    authenticate_employer_client,
)


SEEKER_PAGE_ROUTES = {
    "/login",
    "/register",
    "/forgot-password",
    "/reset-password",
    "/",
    "/dashboard",
    "/view-company/<employer_id>",
    "/resumes",
}

EMPLOYER_PAGE_ROUTES = {
    "/",
    "/employer/login",
    "/employer/register",
    "/employer/dashboard",
    "/companies/<employer_id>",
    "/forgot-password",
    "/reset-password",
    "/employer/company-profile",
}


def _client(app_factory, authenticated=None):
    app = app_factory()
    app.testing = True
    client = app.test_client()
    return authenticated(client) if authenticated else client


def _authenticate_seeker_client(client):
    """Create the same Flask session as a successful seeker login.

    Keep this page-test helper local so an older conftest.py elsewhere in the
    project cannot silently supply a stale role value.
    """
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = os.environ.get(
            "TEST_SEEKER_USER_ID",
            "11111111-1111-4111-8111-111111111111",
        )
        flask_session["email"] = "acceptance.seeker@example.com"
        flask_session["full_name"] = "Acceptance Job Seeker"
        flask_session["role"] = seeker_main.JOB_SEEKER_ROLE
    return client


def _assert_html_response(response, expected_status=200):
    assert response.status_code == expected_status, response.get_data(as_text=True)
    assert response.content_type.startswith("text/html")
    body = response.get_data(as_text=True)
    assert body.strip(), "The page returned an empty HTML response."
    assert "Internal Server Error" not in body
    return body


def _assert_redirect(response, expected_path):
    assert response.status_code in {301, 302, 303, 307, 308}
    location = response.headers.get("Location")
    assert location, "Redirect response did not include a Location header."
    assert urlparse(location).path == expected_path


def _public_employer_id():
    return str(_get_test_employer()["employer_id"])


def test_seeker_user_facing_route_inventory_is_complete():
    app = seeker_main.create_app()
    actual = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if "GET" in rule.methods
        and not rule.rule.startswith(("/api/", "/uploads/", "/static/"))
        and rule.rule != "/logout-direct"
    }
    assert SEEKER_PAGE_ROUTES <= actual


def test_employer_user_facing_route_inventory_is_complete():
    app = employer_main.create_app()
    actual = {
        rule.rule
        for rule in app.url_map.iter_rules()
        if "GET" in rule.methods
        and not rule.rule.startswith(("/api/", "/uploads/", "/static/"))
    }
    assert EMPLOYER_PAGE_ROUTES <= actual


@pytest.mark.parametrize(
    "path",
    ["/login", "/register", "/forgot-password", "/reset-password"],
    ids=["login", "register", "forgot-password", "reset-password"],
)
def test_seeker_public_auth_pages_render(path):
    response = _client(seeker_main.create_app).get(path)
    _assert_html_response(response)


@pytest.mark.parametrize(
    "path",
    [
        "/employer/login",
        "/employer/register",
        "/forgot-password",
        "/reset-password",
    ],
    ids=["login", "register", "forgot-password", "reset-password"],
)
def test_employer_public_auth_pages_render(path):
    response = _client(employer_main.create_app).get(path)
    _assert_html_response(response)


@pytest.mark.parametrize(
    ("path", "redirect_path"),
    [
        ("/", "/login"),
        ("/dashboard", "/login"),
        ("/resumes", "/login"),
    ],
    ids=["explore-positions", "dashboard", "resumes"],
)
def test_seeker_private_pages_redirect_guests(path, redirect_path):
    response = _client(seeker_main.create_app).get(path)
    _assert_redirect(response, redirect_path)


@pytest.mark.parametrize(
    ("path", "redirect_path"),
    [
        ("/", "/employer/login"),
        ("/employer/dashboard", "/employer/login"),
        ("/employer/company-profile", "/employer/login"),
    ],
    ids=["root", "dashboard", "company-profile-editor"],
)
def test_employer_private_pages_redirect_guests(path, redirect_path):
    response = _client(employer_main.create_app).get(path)
    _assert_redirect(response, redirect_path)


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/resumes"],
    ids=["dashboard", "resumes"],
)
def test_authenticated_seeker_pages_render(path):
    client = _client(seeker_main.create_app, _authenticate_seeker_client)
    response = client.get(path)
    _assert_html_response(response)


def test_authenticated_employer_dashboard_renders():
    client = _client(employer_main.create_app, authenticate_employer_client)
    response = client.get("/employer/dashboard")
    _assert_html_response(response)


def test_authenticated_employer_company_editor_redirects_to_own_page():
    client = _client(employer_main.create_app, authenticate_employer_client)
    response = client.get("/employer/company-profile")
    _assert_redirect(response, f"/companies/{_public_employer_id()}")

    final_response = client.get(response.headers["Location"])
    _assert_html_response(final_response)


def test_employer_public_company_page_renders_without_login():
    client = _client(employer_main.create_app)
    response = client.get(f"/companies/{_public_employer_id()}")
    _assert_html_response(response)


def test_seeker_view_company_page_renders_without_login():
    client = _client(seeker_main.create_app)
    response = client.get(f"/view-company/{_public_employer_id()}")
    _assert_html_response(response)


@pytest.mark.parametrize(
    ("app_factory", "path"),
    [
        (seeker_main.create_app, "/view-company/EMP999999"),
        (employer_main.create_app, "/companies/EMP999999"),
    ],
    ids=["seeker-company-view", "employer-company-view"],
)
def test_unknown_company_pages_return_not_found(app_factory, path):
    response = _client(app_factory).get(path)
    _assert_html_response(response, expected_status=404)



def test_seeker_reset_password_page_clears_existing_session():
    client = _client(seeker_main.create_app, _authenticate_seeker_client)
    _assert_html_response(client.get("/reset-password"))
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_employer_reset_password_page_clears_existing_session():
    client = _client(employer_main.create_app, authenticate_employer_client)
    _assert_html_response(client.get("/reset-password"))
    response = client.get("/api/employer/check-session")
    assert response.status_code == 200
    assert response.get_json()["logged_in"] is False


@pytest.mark.parametrize(
    "path",
    ["/api/health", "/api/jobs", "/api/jobs/recommendations"],
    ids=["health", "published-jobs", "job-recommendations"],
)
def test_seeker_public_read_apis_do_not_fail(path):
    response = _client(seeker_main.create_app).get(path)
    assert response.status_code == 200, response.get_json()
    assert response.is_json


def test_public_company_profile_api_returns_company_information():
    response = _client(employer_main.create_app).get(
        f"/api/companies/{_public_employer_id()}"
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    assert payload["employer_id"] == _public_employer_id()
    assert payload.get("company_name")


@pytest.mark.parametrize(
    "path",
    ["/api/profile", "/api/applications", "/api/bookmarks"],
    ids=["profile", "applications", "bookmarks"],
)
def test_seeker_protected_read_apis_reject_guests(path):
    response = _client(seeker_main.create_app).get(path)
    assert response.status_code == 401
    assert response.is_json


@pytest.mark.parametrize(
    "path",
    [
        "/api/employer/profile",
        "/api/jobs",
        "/api/applications",
        "/api/employer/notifications",
    ],
    ids=["profile", "jobs", "applications", "notifications"],
)
def test_employer_protected_read_apis_reject_guests(path):
    response = _client(employer_main.create_app).get(path)
    assert response.status_code == 401
    assert response.is_json


@pytest.mark.parametrize(
    ("app_factory", "path"),
    [
        (seeker_main.create_app, "/dashboard"),
        (seeker_main.create_app, "/view-company/EMP007"),
        (employer_main.create_app, "/employer/dashboard"),
        (employer_main.create_app, "/companies/EMP007"),
    ],
    ids=[
        "seeker-dashboard",
        "seeker-company-page",
        "employer-dashboard",
        "employer-company-page",
    ],
)
def test_read_only_pages_reject_post_requests(app_factory, path):
    response = _client(app_factory).post(path)
    assert response.status_code == 405


def test_unknown_paths_return_not_found_in_both_apps():
    for app_factory in (seeker_main.create_app, employer_main.create_app):
        response = _client(app_factory).get("/this-page-does-not-exist")
        assert response.status_code == 404