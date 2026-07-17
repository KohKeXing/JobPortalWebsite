"""
US-03: Calculate Job Match Percentage

As a job seeker, I want to see a calculated match percentage between my
profile and a specific job listing so that I can quickly judge how well
I fit that role.

NOTE: tests exercise the fallback scoring path (no GEMINI_API_KEY set),
which is deterministic in shape (always returns a valid 0-100 score plus
analysis text) even though the exact number varies. This keeps the test
reliable without depending on a live AI service or key being configured.
"""

RESUME_DATA = {
    "personalInfo": {"name": "Test Candidate", "title": "Software Engineer"},
    "skills": ["Python", "Flask", "SQL"],
    "experience": [{"role": "Backend Developer", "company": "Acme Corp"}]
}

JOB_LISTING = {
    "title": "Backend Engineer",
    "company": "TechCo",
    "requirements": ["Python", "Flask", "REST APIs"]
}


def test_receive_a_match_score_for_a_specific_job_listing(seeker_client):
    """
    Given I have resume data with my skills and experience
    And I am viewing a specific job listing with its requirements
    When I request a match analysis for that job
    Then I should receive a match score between 0 and 100
    And I should receive a written analysis of the match
    """
    res = seeker_client.post('/api/jobs/match', json={
        'resumeData': RESUME_DATA,
        'jobListing': JOB_LISTING
    })

    assert res.status_code == 200
    body = res.get_json()
    assert 0 <= body['matchScore'] <= 100
    assert isinstance(body['analysis'], str) and len(body['analysis']) > 0


def test_match_request_requires_both_resume_data_and_job_listing(seeker_client):
    """
    Given I have not provided resume data
    When I request a match analysis
    Then the system should reject the request
    And explain that resume data and job details are required
    """
    res = seeker_client.post('/api/jobs/match', json={
        'resumeData': None,
        'jobListing': {"title": "Some Job"}
    })

    assert res.status_code == 400
    error = res.get_json()['error']
    assert 'resume' in error.lower() and 'job' in error.lower()


def test_match_request_rejected_when_job_listing_is_missing(seeker_client):
    """
    Given I have resume data but no job listing
    When I request a match analysis
    Then the system should reject the request
    """
    res = seeker_client.post('/api/jobs/match', json={
        'resumeData': RESUME_DATA,
        'jobListing': None
    })

    assert res.status_code == 400


def test_match_still_returns_a_valid_score_for_a_resume_with_no_skills_listed(seeker_client):
    """
    Given I have resume data with an empty skills list
    And I am viewing a specific job listing with its requirements
    When I request a match analysis for that job
    Then I should still receive a valid match score between 0 and 100
    """
    empty_skills_resume = {
        "personalInfo": {"name": "Test Candidate"},
        "skills": [],
        "experience": []
    }

    res = seeker_client.post('/api/jobs/match', json={
        'resumeData': empty_skills_resume,
        'jobListing': JOB_LISTING
    })

    assert res.status_code == 200
    assert 0 <= res.get_json()['matchScore'] <= 100