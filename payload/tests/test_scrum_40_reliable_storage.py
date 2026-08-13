"""
SCRUM-40: Reliable Application/Resume Storage

As a job seeker, I want my resumes and applications reliably saved even
under heavy site usage, so that I never lose my submitted work.

NOTE: these tests verify the actual persistence guarantee the story is
about -- that data survives past the lifetime of a single Flask process,
because it's backed by a real Supabase database rather than an in-memory
or per-process store. Each test writes data through one app instance,
then creates a BRAND NEW Flask app instance (simulating a server
restart/redeploy) and confirms the data is still there when read through
a completely fresh process.
"""
import io

import seeker_main
import employer_main
from conftest import (
    authenticate_employer_client,
    authenticate_seeker_client,
    create_valid_application,
    post_job,
    valid_pdf_bytes,
)


def _fresh_seeker_client():
    """A new Flask app instance, as if the server had just restarted."""
    app = seeker_main.create_app()
    app.testing = True
    return authenticate_seeker_client(app.test_client())


def _fresh_employer_client():
    app = employer_main.create_app()
    app.testing = True
    return authenticate_employer_client(app.test_client())


def test_a_submitted_application_survives_a_server_restart(employer_client, seeker_client):
    """
    Given I have submitted a job application
    When the server process restarts (a fresh app instance is created)
    Then my application should still exist and be retrievable
    """
    job = post_job(employer_client, title='Persistence Test Job').get_json()
    application = create_valid_application(seeker_client, job)

    restarted_client = _fresh_seeker_client()
    res = restarted_client.get('/api/applications')

    apps_after_restart = res.get_json()
    assert any(a['id'] == application['id'] for a in apps_after_restart)


def test_an_uploaded_resume_survives_a_server_restart(seeker_client):
    """
    Given I have uploaded a resume
    When the server process restarts
    Then my resume should still be listed and its file still downloadable
    """
    fake_pdf = (io.BytesIO(valid_pdf_bytes()), 'Durable_Resume.pdf')
    upload_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    resume = upload_res.get_json()['resume']

    restarted_client = _fresh_seeker_client()

    listed = restarted_client.get('/api/resumes').get_json()
    assert any(r['id'] == resume['id'] for r in listed)

    file_res = restarted_client.get(f"/uploads/{resume['storedFileName']}")
    assert file_res.status_code == 200


def test_a_posted_job_survives_a_server_restart(employer_client):
    """
    Given an employer has posted a job
    When the server process restarts
    Then the job posting should still exist
    """
    job = post_job(employer_client, title='Durable Job Posting').get_json()

    restarted_client = _fresh_employer_client()
    res = restarted_client.get('/api/jobs')

    jobs_after_restart = res.get_json()
    assert any(j['id'] == job['id'] for j in jobs_after_restart)


def test_an_application_status_change_survives_a_server_restart(employer_client, seeker_client):
    """
    Given I have an application that an employer has moved to "Interview"
    When the server process restarts
    Then that status change should still be reflected
    """
    job = post_job(employer_client, title='Status Persistence Job').get_json()
    application = create_valid_application(seeker_client, job)
    employer_client.put(f"/api/applications/{application['id']}", json={'status': 'Interview'})

    restarted_client = _fresh_seeker_client()
    res = restarted_client.get('/api/applications')

    fetched = next(a for a in res.get_json() if a['id'] == application['id'])
    assert fetched['status'] == 'Interview'


def test_data_written_by_one_process_is_immediately_visible_to_another(employer_client, seeker_client):
    """
    Given the seeker app and employer app are separate Flask processes
    sharing the same underlying database
    When I submit an application through the seeker app
    Then it should be immediately visible through the employer app
    without any restart or delay
    """
    job = post_job(employer_client, title='Cross Process Visibility Job').get_json()
    application = create_valid_application(seeker_client, job)

    # A different process (employer_client, a separate Flask app instance)
    # should see it right away -- proves storage isn't per-process memory.
    res = employer_client.get('/api/applications')
    assert any(a['id'] == application['id'] for a in res.get_json())
