"""
US-05: Track Application Status

As a job seeker, I want to track my job application status so that I can
know the progress of my applications.
"""
from conftest import post_job, create_valid_application


def test_view_all_my_submitted_applications(employer_client, seeker_client):
    """
    Given I have submitted applications to 3 different jobs
    When I fetch my applications
    Then I should see all 3 applications listed with a status
    """
    for title in ['Job One', 'Job Two', 'Job Three']:
        job = post_job(employer_client, title=title).get_json()
        create_valid_application(seeker_client, job)

    res = seeker_client.get('/api/applications')
    apps = res.get_json()

    assert len(apps) >= 3
    for app in apps:
        assert 'status' in app


def test_new_applications_start_as_pending(employer_client, seeker_client):
    """
    Given I have just applied to a job
    When I check that application
    Then its status should be "Pending"
    """
    job = post_job(employer_client, title='Fresh Application Job').get_json()
    application = create_valid_application(seeker_client, job)

    res = seeker_client.get('/api/applications')
    fetched = next(a for a in res.get_json() if a['id'] == application['id'])

    assert fetched['status'] == 'Pending'


def test_status_updates_made_by_an_employer_are_visible_to_me(employer_client, seeker_client):
    """
    Given I have an application currently "Pending"
    And the employer updates that application to "Interview"
    When I fetch my applications again
    Then that application should now show status "Interview"
    """
    job = post_job(employer_client, title='Status Tracking Job').get_json()
    application = create_valid_application(seeker_client, job)
    assert application['status'] == 'Pending'

    update_res = employer_client.put(f"/api/applications/{application['id']}", json={'status': 'Interview'})
    assert update_res.status_code == 200

    res = seeker_client.get('/api/applications')
    fetched = next(a for a in res.get_json() if a['id'] == application['id'])
    assert fetched['status'] == 'Interview'


def test_updating_a_nonexistent_application_is_rejected(employer_client):
    """
    Given no application exists with a made-up ID
    When the employer attempts to update that application's status
    Then the system should respond that the application was not found
    """
    res = employer_client.put('/api/applications/does-not-exist-123', json={'status': 'Interview'})

    assert res.status_code == 404
    assert 'not found' in res.get_json()['error'].lower()


def test_updating_status_without_providing_a_status_value_is_rejected(employer_client, seeker_client):
    """
    Given I have just applied to a job
    When the employer attempts to update the status with no status value
    Then the system should reject the request
    """
    job = post_job(employer_client, title='No Status Value Job').get_json()
    application = create_valid_application(seeker_client, job)

    res = employer_client.put(f"/api/applications/{application['id']}", json={})

    assert res.status_code == 400


def test_updating_status_to_an_invalid_value_is_rejected(employer_client, seeker_client):
    """
    Given I have just applied to a job
    When the employer attempts to set the status to "banana"
    Then the system should reject the request
    And the application's status should remain unchanged

    [BUG FOUND & FIXED] The API previously accepted ANY string as a status
    with no validation. Now validated against Pending/Interview/Offer/Rejected.
    """
    job = post_job(employer_client, title='Invalid Status Job').get_json()
    application = create_valid_application(seeker_client, job)

    res = employer_client.put(f"/api/applications/{application['id']}", json={'status': 'banana'})
    assert res.status_code == 400

    check_res = seeker_client.get('/api/applications')
    fetched = next(a for a in check_res.get_json() if a['id'] == application['id'])
    assert fetched['status'] == 'Pending'


def test_employer_can_delete_a_rejected_application(employer_client, seeker_client):
    """
    Given I have an application that the employer has set to "Rejected"
    When the employer deletes that application
    Then the application should be removed from the system
    """
    job = post_job(employer_client, title='Soon Rejected Job').get_json()
    application = create_valid_application(seeker_client, job)
    employer_client.put(f"/api/applications/{application['id']}", json={'status': 'Rejected'})

    res = employer_client.delete(f"/api/applications/{application['id']}")

    assert res.status_code == 200
    remaining = seeker_client.get('/api/applications').get_json()
    assert not any(a['id'] == application['id'] for a in remaining)


def test_employer_cannot_delete_an_application_that_is_not_rejected(employer_client, seeker_client):
    """
    Given I have just applied to a job (status still "Pending")
    When the employer attempts to delete that application
    Then the system should refuse to delete it
    And the application should still exist
    """
    job = post_job(employer_client, title='Still Pending Job').get_json()
    application = create_valid_application(seeker_client, job)

    res = employer_client.delete(f"/api/applications/{application['id']}")

    assert res.status_code == 400
    remaining = seeker_client.get('/api/applications').get_json()
    assert any(a['id'] == application['id'] for a in remaining)