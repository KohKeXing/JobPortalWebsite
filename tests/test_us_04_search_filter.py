"""
US-04: Search and Filter Job Listings

As a job seeker, I want to search and filter job listings so that I can
find suitable jobs efficiently.

IMPORTANT: search and filtering itself (keyword matching, job type
checkboxes, salary slider) runs entirely in client-side JavaScript in
seeker.html -- there is no server-side /api/jobs?keyword=... endpoint.
This cannot be tested through the Flask backend the way the other stories
can; a true automated test of this story requires browser automation
(e.g. Selenium/Playwright) driving the actual page.

What CAN be verified at the backend level is the data contract the filter
UI depends on: that every job returned by the API actually has the fields
(title, type, salary, location) the filter logic reads. That is what this
test checks -- it is a precondition check, not a test of the filtering
behavior itself.
"""
from conftest import post_job


def test_job_listings_include_the_fields_required_for_clientside_filtering(employer_client, seeker_client):
    """
    Given jobs have been posted with different types and salaries
    When I fetch the job listings
    Then each job should include a title, type, salary, and location field
    """
    post_job(employer_client, title='Remote Developer', location='KL, Malaysia (Remote)',
              salary='RM 5000-7000', type='Remote')
    post_job(employer_client, title='Onsite Analyst', location='Penang, Malaysia',
              salary='RM 4000-6000', type='Full-time')

    res = seeker_client.get('/api/jobs')
    jobs = res.get_json()

    assert len(jobs) >= 2
    for job in jobs:
        assert job.get('title')
        assert job.get('type')
        assert job.get('salary')
        assert job.get('location')