"""
Story A: Encrypt Resume Files At Rest

As a job seeker, I want my uploaded/generated resume files encrypted
before they're stored, so that even if the storage bucket is
compromised, my resume content can't be read directly.

NOTE: these tests check both sides of the guarantee:
  1. What's actually sitting in Supabase Storage is NOT a readable
     PDF/DOCX (it's ciphertext) -- checked by downloading the RAW bytes
     directly from the bucket, bypassing the app entirely.
  2. Going through the app's normal download route still works and
     returns the original, correct content -- encryption is transparent
     to a legitimate request.
  3. A file that predates encryption (still plaintext in the bucket)
     doesn't crash the download route.
"""
import io
import uuid

import resume_builder
from resume_builder import RESUME_BUCKET
from supabase_client import get_supabase_client
from conftest import valid_pdf_bytes


def _raw_bucket_bytes(storage_path):
    """Fetch exactly what's stored in the bucket, with no decryption --
    used to verify content is actually encrypted at rest."""
    return get_supabase_client().storage.from_(RESUME_BUCKET).download(storage_path)


def test_an_uploaded_resume_is_not_readable_directly_from_storage(seeker_client):
    """
    Given I upload a resume with known, identifiable plaintext content
    When I fetch the raw bytes directly from the storage bucket
    (bypassing the app entirely)
    Then those raw bytes should NOT be a readable PDF
    And should NOT contain the original identifiable content
    """
    marker = 'UNIQUE_MARKER_' + uuid.uuid4().hex
    fake_pdf = (io.BytesIO(valid_pdf_bytes(marker=marker)), 'Encrypted_Resume.pdf')

    upload_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    resume = upload_res.get_json()['resume']

    storage_path = f"unassigned/{resume['storedFileName']}"
    raw_bytes = _raw_bucket_bytes(storage_path)

    assert not raw_bytes.startswith(b'%PDF')
    assert marker.encode() not in raw_bytes


def test_an_uploaded_resume_still_downloads_correctly_through_the_app(seeker_client):
    """
    Given I upload a resume with known content
    When I download it through the app's normal download route
    Then I should receive back the exact original content
    (encryption/decryption should be fully transparent)
    """
    original_content = valid_pdf_bytes(text='this is my real resume content')
    fake_pdf = (io.BytesIO(original_content), 'Roundtrip_Resume.pdf')

    upload_res = seeker_client.post(
        '/api/resumes/upload',
        data={'resume': fake_pdf},
        content_type='multipart/form-data'
    )
    resume = upload_res.get_json()['resume']

    download_res = seeker_client.get(f"/uploads/{resume['storedFileName']}")

    assert download_res.status_code == 200
    assert download_res.data == original_content


def test_a_builder_generated_resume_is_also_encrypted_at_rest(seeker_client):
    """
    Given I generate a resume using the built-in template builder
    (not a raw upload)
    When I fetch the raw bytes directly from the storage bucket
    Then those raw bytes should NOT be a readable PDF either
    """
    create_res = seeker_client.post('/api/resumes/builder', json={
        'name': 'Encrypted_Builder_Resume',
        'layout': 'modern',
        'data': {'personalInfo': {'name': 'Test Candidate'}},
        'outputFormat': 'pdf',
    })
    resume = create_res.get_json()['resume']

    storage_path = f"unassigned/{resume['storedFileName']}"
    raw_bytes = _raw_bucket_bytes(storage_path)

    assert not raw_bytes.startswith(b'%PDF')


def test_a_resume_stored_before_encryption_was_enabled_still_downloads_without_crashing(seeker_client):
    """
    Given a resume file was stored as plain, unencrypted bytes
    (simulating one uploaded before encryption existed)
    When I download it through the app's normal download route
    Then it should still be served successfully, not crash with a
    decryption error
    """
    legacy_content = b'%PDF-1.4 legacy unencrypted resume, stored before encryption existed'
    stored_name = f"{uuid.uuid4().hex}.pdf"
    storage_path = f"unassigned/{stored_name}"

    client = get_supabase_client()
    client.storage.from_(RESUME_BUCKET).upload(
        path=storage_path,
        file=legacy_content,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )
    row = {
        "id": "res-" + uuid.uuid4().hex[:12],
        "name": "Legacy Resume",
        "type": "upload",
        "file_name": "legacy_resume.pdf",
        "stored_file_name": stored_name,
        "file_format": "pdf",
        "storage_bucket": RESUME_BUCKET,
        "storage_path": storage_path,
        "last_modified": resume_builder._utc_timestamp(),
        "owner_key": None,
    }
    client.table("resumes").insert(row).execute()

    seeker_client_download = seeker_client.get(f"/uploads/{stored_name}")

    assert seeker_client_download.status_code == 200
    assert seeker_client_download.data == legacy_content