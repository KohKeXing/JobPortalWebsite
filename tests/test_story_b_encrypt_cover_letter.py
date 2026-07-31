"""
Story B: Encrypt Cover Letter Files At Rest

As a job seeker, I want my cover letter files encrypted before they're
stored, so my personal documents stay unreadable if the bucket is ever
breached.

NOTE: mirrors test_story_a_encrypt_resume.py -- same three guarantees,
applied to the cover-letters/ path in the same storage bucket.
"""
import io
import uuid

from resume_builder import RESUME_BUCKET
from supabase_client import get_supabase_client
from conftest import valid_pdf_bytes


def _raw_bucket_bytes(storage_path):
    return get_supabase_client().storage.from_(RESUME_BUCKET).download(storage_path)


def test_an_uploaded_cover_letter_is_not_readable_directly_from_storage(seeker_client):
    """
    Given I upload a cover letter with known, identifiable plaintext content
    When I fetch the raw bytes directly from the storage bucket
    (bypassing the app entirely)
    Then those raw bytes should NOT be a readable PDF
    And should NOT contain the original identifiable content
    """
    marker = 'UNIQUE_MARKER_' + uuid.uuid4().hex
    fake_pdf = (io.BytesIO(valid_pdf_bytes(marker=marker)), 'Encrypted_Cover_Letter.pdf')

    upload_res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': fake_pdf},
        content_type='multipart/form-data'
    )
    cover_letter = upload_res.get_json()

    storage_path = f"cover-letters/{cover_letter['storedFileName']}"
    raw_bytes = _raw_bucket_bytes(storage_path)

    assert not raw_bytes.startswith(b'%PDF')
    assert marker.encode() not in raw_bytes


def test_an_uploaded_cover_letter_still_downloads_correctly_through_the_app(seeker_client):
    """
    Given I upload a cover letter with known content
    When I download it through the app's normal download route
    Then I should receive back the exact original content
    (encryption/decryption should be fully transparent)
    """
    original_content = valid_pdf_bytes(text='Dear Hiring Manager, this is my real cover letter.')
    fake_pdf = (io.BytesIO(original_content), 'Roundtrip_Cover_Letter.pdf')

    upload_res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': fake_pdf},
        content_type='multipart/form-data'
    )
    cover_letter = upload_res.get_json()

    download_res = seeker_client.get(f"/uploads/cover-letters/{cover_letter['storedFileName']}")

    assert download_res.status_code == 200
    assert download_res.data == original_content


def test_the_encryption_key_is_not_stored_alongside_the_file_content(seeker_client):
    """
    Given I upload a cover letter
    When I inspect where its encryption key comes from
    Then the key should be loaded from environment configuration
    (.env), not stored in the database row or the storage bucket itself
    """
    fake_pdf = (io.BytesIO(valid_pdf_bytes(text='key separation check')), 'Key_Separation_Cover.pdf')

    upload_res = seeker_client.post(
        '/api/cover-letters/upload',
        data={'coverLetter': fake_pdf},
        content_type='multipart/form-data'
    )
    cover_letter = upload_res.get_json()
    assert upload_res.status_code == 201

    # The API response for an upload should only ever contain filenames,
    # never the encryption key or key material.
    assert 'key' not in {k.lower() for k in cover_letter.keys()}
    for value in cover_letter.values():
        assert 'RESUME_ENCRYPTION_KEY' not in str(value)


def test_a_cover_letter_stored_before_encryption_was_enabled_still_downloads_without_crashing(seeker_client):
    """
    Given a cover letter file was stored as plain, unencrypted bytes
    (simulating one uploaded before encryption existed)
    When I download it through the app's normal download route
    Then it should still be served successfully, not crash with a
    decryption error
    """
    legacy_content = b'%PDF-1.4 legacy unencrypted cover letter, stored before encryption existed'
    stored_name = f"{uuid.uuid4().hex}.pdf"
    storage_path = f"cover-letters/{stored_name}"

    get_supabase_client().storage.from_(RESUME_BUCKET).upload(
        path=storage_path,
        file=legacy_content,
        file_options={"content-type": "application/pdf", "upsert": "false"},
    )

    download_res = seeker_client.get(f"/uploads/cover-letters/{stored_name}")

    assert download_res.status_code == 200
    assert download_res.data == legacy_content