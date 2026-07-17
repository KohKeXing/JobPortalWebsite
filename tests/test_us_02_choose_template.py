"""
US-02: Choose Resume Template Style

As a job seeker, I want to choose from different visual resume templates
so that my resume's look matches industry expectations.

NOTE: switching templates and seeing an immediate live preview update
happens entirely in client-side JavaScript. What's tested here is the
backend contract these UI actions depend on: that a chosen template is
actually saved and retrievable, and that changing it persists correctly.
"""
import pytest

RESUME_DATA = {
    "personalInfo": {"name": "Test Candidate", "email": "test@example.com"},
    "skills": ["Python", "Flask"]
}


def test_create_a_resume_with_a_chosen_template(seeker_client):
    """
    Given I am building a resume
    When I save it with the "Elegant" template selected
    Then the resume should be saved with layout "Elegant"
    """
    res = seeker_client.post('/api/resumes/builder', json={
        'name': 'My_Resume', 'layout': 'Elegant', 'data': RESUME_DATA
    })

    assert res.status_code == 201
    assert res.get_json()['resume']['layout'] == 'Elegant'


@pytest.mark.parametrize('template', ['Modern', 'Tech', 'Elegant', 'Minimalist'])
def test_save_a_resume_using_each_supported_template(seeker_client, template):
    """
    Given I am building a resume
    When I save it with the "{template}" template selected
    Then the resume should be saved with layout "{template}"
    """
    res = seeker_client.post('/api/resumes/builder', json={
        'name': 'My_Resume', 'layout': template, 'data': RESUME_DATA
    })

    assert res.status_code == 201
    assert res.get_json()['resume']['layout'] == template


def test_template_defaults_to_modern_when_none_is_specified(seeker_client):
    """
    Given I am building a resume
    When I save it without explicitly selecting a template
    Then the resume should default to layout "modern"
    """
    res = seeker_client.post('/api/resumes/builder', json={
        'name': 'My_Resume', 'data': RESUME_DATA
    })

    assert res.status_code == 201
    assert res.get_json()['resume']['layout'] == 'modern'


def test_template_choice_persists_after_being_changed(seeker_client):
    """
    Given I have a saved resume using the "Modern" template
    When I update that resume to use the "Tech" template
    Then the resume should now be saved with layout "Tech"
    And the resume's other data should be unchanged
    """
    create_res = seeker_client.post('/api/resumes/builder', json={
        'name': 'My_Resume', 'layout': 'Modern', 'data': RESUME_DATA
    })
    resume_id = create_res.get_json()['resume']['id']

    update_res = seeker_client.put(f'/api/resumes/{resume_id}', json={'layout': 'Tech'})

    assert update_res.status_code == 200
    updated = update_res.get_json()['resume']
    assert updated['layout'] == 'Tech'
    assert updated['data']['personalInfo']['name'] == 'Test Candidate'


def test_updating_the_template_of_a_resume_that_does_not_exist_returns_not_found(seeker_client):
    """
    Given no resume exists with a given ID
    When I attempt to change its template
    Then the system should respond that the resume was not found
    """
    res = seeker_client.put('/api/resumes/does-not-exist-123', json={'layout': 'Tech'})

    assert res.status_code == 404
    assert 'not found' in res.get_json()['error'].lower()