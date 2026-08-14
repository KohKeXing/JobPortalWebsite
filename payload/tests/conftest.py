"""Shared fixtures for the job portal acceptance tests."""

import io
import os
import zipfile

import pytest
from reportlab.pdfgen import canvas

import seeker_main
import employer_main
from job import JobStorage
from application_tracking import ApplicationTracking
from resume_builder import ResumeStorage

job_store = JobStorage()
app_tracker = ApplicationTracking()
resume_store = ResumeStorage()

TEST_SEEKER_USER_ID = os.environ.get(
    "TEST_SEEKER_USER_ID",
    "11111111-1111-4111-8111-111111111111",
)
TEST_EMPLOYER_ID = os.environ.get("TEST_EMPLOYER_ID", "EMP007")

_resolved_employer = None


def _get_test_employer():
    """Return the real employer record used by integration tests.

    The recruitment tables reference ``auth.users(id)``. A made-up UUID in
    the Flask session therefore authenticates the request but correctly fails
    when the lifecycle row is inserted. Resolve the configured public
    employer ID to its genuine Auth user ID instead.
    """
    global _resolved_employer
    if _resolved_employer is None:
        _resolved_employer = employer_main.get_employer_from_db(
            TEST_EMPLOYER_ID
        )

    if not _resolved_employer:
        pytest.fail(
            "No employer record was found for TEST_EMPLOYER_ID="
            f"{TEST_EMPLOYER_ID!r}. Set TEST_EMPLOYER_ID in .env to an "
            "existing employer such as EMP007."
        )
    if not _resolved_employer.get("user_id"):
        pytest.fail(
            f"Employer {TEST_EMPLOYER_ID!r} is not linked to a Supabase "
            "Auth user. Register/login that employer once before testing."
        )
    return _resolved_employer


def authenticate_seeker_client(client):
    """Attach the signed-in seeker session expected by protected routes."""
    with client.session_transaction() as flask_session:
        flask_session["user_id"] = TEST_SEEKER_USER_ID
        flask_session["email"] = "acceptance.seeker@example.com"
        flask_session["full_name"] = "Acceptance Job Seeker"
        # Use the application's canonical value instead of duplicating the
        # role string here.  This keeps the acceptance session identical to a
        # real successful login even if AuthService changes the stored label.
        flask_session["role"] = seeker_main.JOB_SEEKER_ROLE
    return client


def authenticate_employer_client(client):
    """Attach a session backed by a genuine employers/auth.users row."""
    employer = _get_test_employer()
    with client.session_transaction() as flask_session:
        flask_session["auth_user_id"] = str(employer["user_id"])
        flask_session["employer_id"] = str(employer["employer_id"])
        flask_session["company_name"] = employer.get("company_name") or "Employer"
        flask_session["company_email"] = employer.get("company_email") or ""
        flask_session["role"] = "employer"
    return client


def valid_pdf_bytes(text='Sample Resume Content', marker=None):
    """
    Build a REAL, structurally valid single-page PDF (not just bytes that
    start with "%PDF"). resume_builder.py's upload validation actually
    parses the PDF with pypdf and requires a readable page structure --
    a fake string like b'%PDF-1.4 some text' fails that check with
    "The uploaded PDF is corrupted or invalid." This generates a genuine
    PDF using reportlab (already a project dependency) so upload tests
    exercise the real validation path successfully.

    If `marker` is given, it's embedded in the PDF's Subject metadata --
    useful for tests that need to prove a specific, identifiable piece of
    content made it into (or was scrubbed from) the stored file.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, text)
    if marker:
        c.setSubject(marker)
    c.save()
    return buf.getvalue()


def valid_docx_bytes(text="Sample Resume Content"):
    """Build the minimum valid OOXML package required for a DOCX upload."""
    buf = io.BytesIO()
    escaped_text = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        archive.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>"""
            + escaped_text
            + """</w:t></w:r></w:p><w:sectPr/></w:body>
</w:document>""",
        )
    return buf.getvalue()


@pytest.fixture(autouse=True)
def reset_storage():
    """Snapshot existing rows before each test, then delete anything new
    the test created, so runs stay isolated without touching real data."""
    existing_job_ids = {j["id"] for j in job_store.get_jobs()}
    existing_app_ids = {a["id"] for a in app_tracker.get_applications()}
    existing_resume_ids = {r["id"] for r in resume_store.get_resumes()}

    yield

    # Order matters: applications reference jobs/resumes, so clean those
    # up first to avoid foreign-key errors.
    for a in app_tracker.get_applications():
        if a["id"] not in existing_app_ids:
            app_tracker.delete_application(a["id"])
    for r in resume_store.get_resumes():
        if r["id"] not in existing_resume_ids:
            resume_store.delete_resume(r["id"])
    for j in job_store.get_jobs():
        if j["id"] not in existing_job_ids:
            job_store.delete_job(j["id"])


@pytest.fixture
def seeker_client():
    app = seeker_main.create_app()
    app.testing = True
    client = app.test_client()
    return authenticate_seeker_client(client)


@pytest.fixture
def employer_client():
    app = employer_main.create_app()
    app.testing = True
    client = app.test_client()
    return authenticate_employer_client(client)


def create_valid_application(seeker_client, job):
    """
    Shared test helper: creates a fully valid application (with a real
    uploaded resume and a written cover letter) for a given job. Used by
    tests that need an existing application already in the system.
    """
    resume_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': (io.BytesIO(valid_pdf_bytes()), 'setup_resume.pdf')},
        content_type='multipart/form-data'
    )
    resume = resume_res.get_json()['resume']

    app_res = seeker_client.post('/api/applications', json={
        'jobId': job['id'],
        'job': job['title'],
        'company': job['company'],
        'details': f"Resume: {resume['name']} • Cover Letter: written",
        'resumeId': resume['id'],
        'coverLetterText': 'Dear Hiring Manager, I am applying for this role.',
    })
    assert app_res.status_code == 201, app_res.get_json()
    return app_res.get_json()['application']


def create_test_resume(seeker_client, filename='setup_resume.pdf'):
    """Shared helper: uploads a resume and returns its API record."""
    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': (io.BytesIO(valid_pdf_bytes()), filename)},
        content_type='multipart/form-data'
    )
    return res.get_json()['resume']


def upload_cover_letter(seeker_client, filename='setup_cover.pdf'):
    """Shared helper: uploads a cover letter and returns its API record."""
    res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': (io.BytesIO(valid_pdf_bytes()), filename)},
        content_type='multipart/form-data'
    )
    return res.get_json()


def post_job(employer_client, **overrides):
    """Shared helper: posts a job with sensible defaults, overridable per test.

    NOTE: job.py's validate_job_data() is strict -- title/location are
    letters+spaces(+commas) only, and salary must be digits only (no "RM",
    no dashes). Defaults here are chosen to satisfy that validation; tests
    that override title/location/salary need to stay within those rules
    too, or they're testing the validation bug, not the story.
    """
    payload = {
        'title': 'QA Engineer', 'company': 'TestCo', 'location': 'Kuala Lumpur',
        'salary': '5000', 'type': 'Full-time', 'description': 'Test everything.',
    }
    payload.update(overrides)
    res = employer_client.post('/api/jobs', json=payload)
    return res