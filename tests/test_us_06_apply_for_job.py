"""
US-06: Apply for Jobs with Resume and Cover Letter

As a job seeker, I want to apply for jobs using my resume and cover letter
so that I can submit applications easily.
"""
import io

from conftest import post_job


def _upload_resume(seeker_client, filename='my_resume.pdf'):
    fake_pdf = (io.BytesIO(b'%PDF-1.4 sample resume'), filename)
    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    return res.get_json()['resume']


def test_successfully_apply_with_a_written_cover_letter(employer_client, seeker_client):
    """
    Given I am viewing a job listing I have not applied to
    And I have at least one saved resume
    When I select a resume, write a cover letter, and submit the application
    Then the application should be submitted successfully
    And it should appear with status "Pending"
    """
    job = post_job(employer_client, title='Backend Engineer', company='Acme Corp').get_json()
    resume = _upload_resume(seeker_client)

    res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'resumeId': resume['id'],
        'coverLetterText': 'Dear Hiring Manager, I am excited to apply for this role.',
        'details': f"Resume: {resume['name']} • Cover Letter: written",
    })

    assert res.status_code == 201
    assert res.get_json()['application']['status'] == 'Pending'


def test_successfully_apply_with_an_uploaded_cover_letter_file(employer_client, seeker_client):
    """
    Given I am viewing a job listing I have not applied to
    And I have at least one saved resume
    When I select a resume, upload a cover letter file, and submit the application
    Then the application should be submitted successfully
    And the application should record the cover letter file name
    """
    job = post_job(employer_client, title='Backend Engineer', company='Acme Corp').get_json()
    resume = _upload_resume(seeker_client)

    fake_cover = (io.BytesIO(b'%PDF-1.4 cover letter content'), 'my_cover_letter.pdf')
    cover_res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': fake_cover},
        content_type='multipart/form-data'
    )
    cover_letter = cover_res.get_json()

    res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'resumeId': resume['id'],
        'coverLetterFile': cover_letter['storedFileName'],
        'coverLetterOriginalName': cover_letter['originalName'],
        'details': f"Resume: {resume['name']} • Cover Letter: {cover_letter['originalName']}",
    })

    assert res.status_code == 201
    application = res.get_json()['application']
    assert application['coverLetterFile'] == cover_letter['storedFileName']
    assert application['coverLetterOriginalName'] == cover_letter['originalName']


def test_prevent_duplicate_applications(employer_client, seeker_client):
    """
    Given I have already applied to a job
    When I attempt to apply to the same job again
    Then the system should prevent the duplicate submission

    [BUG FOUND & FIXED] Duplicate-prevention previously only existed in the
    browser's JavaScript -- the API itself would silently accept a second
    application. Now enforced server-side (409 Conflict).
    """
    job = post_job(employer_client, title='QA Engineer').get_json()
    resume1 = _upload_resume(seeker_client, 'resume1.pdf')

    first_res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'resumeId': resume1['id'], 'coverLetterText': 'First attempt.',
    })
    assert first_res.status_code == 201

    resume2 = _upload_resume(seeker_client, 'resume2.pdf')
    second_res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'resumeId': resume2['id'], 'coverLetterText': 'Second attempt.',
    })

    assert second_res.status_code == 409
    assert 'already applied' in second_res.get_json()['error'].lower()


def test_reject_application_submission_missing_a_job_id(seeker_client):
    """
    Given I am applying to a job
    When I submit an application with no job ID
    Then the system should reject the submission
    """
    res = seeker_client.post('/api/applications', json={
        'job': 'Some Job', 'company': 'Some Company', 'details': 'test'
    })

    assert res.status_code == 400


def test_reject_application_submission_missing_a_job_title(seeker_client):
    """
    Given I am applying to a job
    When I submit an application with no job title
    Then the system should reject the submission
    """
    res = seeker_client.post('/api/applications', json={
        'jobId': 'job-123', 'company': 'Some Company', 'details': 'test'
    })

    assert res.status_code == 400


def test_reject_application_submission_missing_a_company_name(seeker_client):
    """
    Given I am applying to a job
    When I submit an application with no company name
    Then the system should reject the submission
    """
    res = seeker_client.post('/api/applications', json={
        'jobId': 'job-123', 'job': 'Some Job', 'details': 'test'
    })

    assert res.status_code == 400


def test_reject_application_submission_with_no_resume_selected(employer_client, seeker_client):
    """
    Given I am viewing a job listing I have not applied to
    When I submit an application with no resume selected
    Then the system should reject the submission

    [BUG FOUND & FIXED] The API previously accepted an application with no
    resumeId at all, even though the story requires applying "using my
    resume." Now enforced server-side (400 if missing).
    """
    job = post_job(employer_client, title='No Resume Test').get_json()

    res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'coverLetterText': 'Dear Hiring Manager, ...',
    })

    assert res.status_code == 400


def test_reject_application_submission_with_no_cover_letter_at_all(employer_client, seeker_client):
    """
    Given I am viewing a job listing I have not applied to
    And I have at least one saved resume
    When I submit an application with a resume but no cover letter
    Then the system should reject the submission

    [BUG FOUND & FIXED] Same issue as the missing-resume case above, but
    for the cover letter -- neither written text nor an uploaded file was
    previously required. Now enforced server-side (400 if both are missing).
    """
    job = post_job(employer_client, title='No Cover Letter Test').get_json()
    resume = _upload_resume(seeker_client)

    res = seeker_client.post('/api/applications', json={
        'jobId': job['id'], 'job': job['title'], 'company': job['company'],
        'resumeId': resume['id'],
    })

    assert res.status_code == 400


def test_reject_an_invalid_cover_letter_file_type(seeker_client):
    """
    Given I am applying to a job
    When I attempt to upload a cover letter that is not a PDF or DOCX
    Then the cover letter upload should be rejected
    """
    fake_txt = (io.BytesIO(b'plain text, not a cover letter'), 'notes.txt')

    res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': fake_txt},
        content_type='multipart/form-data'
    )

    assert res.status_code == 400