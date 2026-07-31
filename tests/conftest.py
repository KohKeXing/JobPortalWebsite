"""
Shared fixtures for the plain pytest acceptance tests.

These talk to the REAL Flask apps (seeker_main.py and employer_main.py)
through their test clients -- no mocking of the storage layer, so a
passing test means the actual backend code (including real Supabase
Database + Storage calls) works, not just that a mock was set up
correctly.

NOTE: storage is now Supabase (Postgres + Storage bucket), not a local
data/ folder. Instead of wiping a directory, each test's reset_storage
fixture snapshots what already exists before the test runs, and deletes
only the rows/files that test itself created -- so the shared Supabase
project doesn't accumulate test junk between runs, and tests don't step
on each other's or your real data.
"""
import io

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
    return app.test_client()


@pytest.fixture
def employer_client():
    app = employer_main.create_app()
    app.testing = True
    return app.test_client()


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