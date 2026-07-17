"""
US-01: Upload Existing Resume

As a job seeker, I want to upload an existing resume file so that I can
reuse a resume I already have instead of building a new one.
"""
import io


def test_successfully_upload_a_valid_resume_file(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I upload a valid PDF file named "My_Resume.pdf"
    Then the file should be uploaded successfully
    And it should appear in "Your Resumes & Saved Materials" with its original filename
    """
    fake_pdf = (io.BytesIO(b'%PDF-1.4 sample resume content'), 'My_Resume.pdf')

    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )

    assert res.status_code == 201
    resumes = seeker_client.get('/api/resumes').get_json()
    assert any(r['fileName'] == 'My_Resume.pdf' for r in resumes)


def test_reject_an_invalid_file_type(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I attempt to upload a file that is not a PDF or DOCX
    Then the system should reject the upload
    And an error message should state that only PDF and DOCX files are supported
    """
    fake_txt = (io.BytesIO(b'just plain text, not a resume'), 'notes.txt')

    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_txt},
        content_type='multipart/form-data'
    )

    assert res.status_code == 400
    error = res.get_json()['error']
    assert 'PDF' in error and 'DOCX' in error


def test_accept_a_docx_file_as_well_as_pdf(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I upload a valid DOCX file named "My_Resume.docx"
    Then the file should be uploaded successfully
    """
    fake_docx = (io.BytesIO(b'PK\x03\x04 fake docx binary content'), 'My_Resume.docx')

    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_docx},
        content_type='multipart/form-data'
    )

    assert res.status_code == 201


def test_reject_a_file_with_no_extension(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I attempt to upload a file with no file extension
    Then the system should reject the upload
    """
    fake_file = (io.BytesIO(b'some content'), 'resume_no_extension')

    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_file},
        content_type='multipart/form-data'
    )

    assert res.status_code == 400


def test_accept_an_uppercase_file_extension(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I upload a valid PDF file named "MY_RESUME.PDF" (uppercase extension)
    Then the file should be uploaded successfully
    """
    fake_pdf = (io.BytesIO(b'%PDF-1.4 sample resume content'), 'MY_RESUME.PDF')

    res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )

    assert res.status_code == 201


def test_view_an_uploaded_resume(seeker_client):
    """
    Given I have previously uploaded a resume named "My_Resume.pdf"
    When I view that resume
    Then the actual resume file should be retrievable
    """
    fake_pdf = (io.BytesIO(b'%PDF-1.4 sample resume content'), 'My_Resume.pdf')
    upload_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    resume = upload_res.get_json()['resume']

    res = seeker_client.get(f"/uploads/{resume['storedFileName']}")

    assert res.status_code == 200
    assert b'%PDF' in res.data


def test_delete_an_uploaded_resume(seeker_client):
    """
    Given I have previously uploaded a resume named "My_Resume.pdf"
    When I delete that resume
    Then the resume should no longer appear in "Your Resumes & Saved Materials"
    And the underlying file should no longer be accessible
    """
    fake_pdf = (io.BytesIO(b'%PDF-1.4 sample resume content'), 'My_Resume.pdf')
    upload_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    resume = upload_res.get_json()['resume']

    delete_res = seeker_client.delete(f"/api/resumes/{resume['id']}")
    assert delete_res.status_code == 200

    resumes = seeker_client.get('/api/resumes').get_json()
    assert not any(r['id'] == resume['id'] for r in resumes)

    file_res = seeker_client.get(f"/uploads/{resume['storedFileName']}")
    assert file_res.status_code == 404


def test_reject_an_upload_request_with_no_file_attached(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I attempt to upload with no file attached at all
    Then the system should reject the upload
    """
    res = seeker_client.post(
        '/api/resumes/upload',
        data={},
        content_type='multipart/form-data'
    )

    assert res.status_code == 400


def test_deleting_a_resume_that_does_not_exist_returns_not_found(seeker_client):
    """
    Given I am a job seeker on the "My Resumes" page
    When I delete a resume with an ID that does not exist
    Then the system should respond that the resume was not found
    """
    res = seeker_client.delete('/api/resumes/does-not-exist-123')

    assert res.status_code == 404
    assert 'not found' in res.get_json()['error'].lower()