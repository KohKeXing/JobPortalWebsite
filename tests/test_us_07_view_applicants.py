"""
US-07: View Applicants for a Job Posting

As an employer, I want to view the list of applicants who applied for my
job postings so that I can review potential candidates.
"""
from conftest import post_job, create_valid_application


def test_view_all_applicants_across_postings(employer_client, seeker_client):
    """
    Given I have posted a job and it has received applicants
    When I open the Applicants section of the employer console
    Then I should see the application listed
    """
    job = post_job(employer_client, title='Frontend Developer', company='PixelWorks').get_json()
    application = create_valid_application(seeker_client, job)

    res = employer_client.get('/api/applications')
    apps = res.get_json()

    assert any(a['id'] == application['id'] for a in apps)


def test_filter_applicants_by_job_posting(employer_client, seeker_client):
    """
    Given I have posted multiple jobs, each with applicants
    When I filter applicants by a specific job
    Then only applicants for that specific job should be displayed
    """
    job_a = post_job(employer_client, title='Job A', company='MultiCo').get_json()
    job_b = post_job(employer_client, title='Job B', company='MultiCo').get_json()
    create_valid_application(seeker_client, job_a)
    create_valid_application(seeker_client, job_b)

    all_apps = employer_client.get('/api/applications').get_json()
    filtered = [a for a in all_apps if a['jobId'] == job_a['id']]

    assert len(filtered) == 1
    assert filtered[0]['jobId'] == job_a['id']


def test_a_job_posting_with_no_applicants_shows_an_empty_result(employer_client):
    """
    Given I have posted a job with no applicants
    When I filter applicants by that job
    Then no applicants should be displayed for that job
    """
    empty_job = post_job(employer_client, title='Untouched Posting', company='QuietCo').get_json()

    all_apps = employer_client.get('/api/applications').get_json()
    filtered = [a for a in all_apps if a['jobId'] == empty_job['id']]

    assert len(filtered) == 0