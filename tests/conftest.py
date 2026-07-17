"""
Shared fixtures for the plain pytest acceptance tests.

Each test gets a clean data/ folder so tests don't leak state into each
other or into your real server's data. These talk to the REAL Flask apps
(seeker_main.py and employer_main.py) through their test clients -- no
mocking of the storage layer, so a passing test means the actual backend
code works, not just that a mock was set up correctly.
"""
import shutil
import io
from pathlib import Path

import pytest

import seeker_main
import employer_main
import resume_builder

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def reset_storage():
    """Wipe data/ before every test so each one starts from a clean slate."""
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    resume_builder.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    resume_builder.COVER_LETTER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)


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
        data={'resume': (io.BytesIO(b'%PDF-1.4 sample resume'), 'setup_resume.pdf')},
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


def post_job(employer_client, **overrides):
    """Shared helper: posts a job with sensible defaults, overridable per test."""
    payload = {
        'title': 'QA Engineer', 'company': 'TestCo', 'location': 'KL, Malaysia',
        'salary': 'RM 5000-7000', 'type': 'Full-time', 'description': 'Test everything.',
    }
    payload.update(overrides)
    res = employer_client.post('/api/jobs', json=payload)
    return res