"""Acceptance tests for interviews and employer job lifecycle states."""

from datetime import datetime, timedelta, timezone

import pytest


MALAYSIA_TIMEZONE = timezone(timedelta(hours=8))


def future_interview_time():
    return (datetime.now(MALAYSIA_TIMEZONE) + timedelta(days=2)).isoformat()


@pytest.mark.acceptance
class TestInterviewScheduling:
    def test_interview_cannot_be_scheduled_while_application_is_pending(
        self,
        workflow_context,
    ):
        response = workflow_context.employer_client.post(
            "/api/applications/APP001/interview",
            json={
                "interviewAt": future_interview_time(),
                "interviewType": "online",
                "locationOrLink": "https://meet.example.com/interview",
                "notes": "Prepare testing portfolio.",
            },
        )

        assert response.status_code == 409
        assert "change the applicant status" in response.get_json()["error"].lower()

    def test_employer_can_schedule_interview_after_status_changes_to_interview(
        self,
        workflow_context,
    ):
        status_response = workflow_context.employer_client.put(
            "/api/applications/APP001",
            json={"status": "Interview"},
        )
        assert status_response.status_code == 200

        response = workflow_context.employer_client.post(
            "/api/applications/APP001/interview",
            json={
                "interviewAt": future_interview_time(),
                "interviewType": "online",
                "locationOrLink": "https://meet.example.com/interview",
                "notes": "Prepare testing portfolio.",
            },
        )

        assert response.status_code == 200
        interview = response.get_json()["interview"]
        assert interview["status"] == "scheduled"
        assert interview["interviewType"] == "online"
        assert interview["locationOrLink"].startswith("https://")

    def test_interview_date_must_be_in_the_future(self, workflow_context):
        workflow_context.applications.update_status("APP001", "Interview")
        past_time = (datetime.now(MALAYSIA_TIMEZONE) - timedelta(hours=1)).isoformat()

        response = workflow_context.employer_client.post(
            "/api/applications/APP001/interview",
            json={
                "interviewAt": past_time,
                "interviewType": "online",
                "locationOrLink": "https://meet.example.com/interview",
            },
        )

        assert response.status_code == 400
        assert "future" in response.get_json()["error"].lower()

    def test_job_seeker_application_displays_scheduled_interview(self, workflow_context):
        workflow_context.applications.update_status("APP001", "Interview")
        schedule_response = workflow_context.employer_client.post(
            "/api/applications/APP001/interview",
            json={
                "interviewAt": future_interview_time(),
                "interviewType": "physical",
                "locationOrLink": "Penang Main Office",
                "notes": "Bring identification.",
            },
        )
        assert schedule_response.status_code == 200

        applications_response = workflow_context.seeker_client.get("/api/applications")
        assert applications_response.status_code == 200
        application = next(
            item for item in applications_response.get_json()
            if item["id"] == "APP001"
        )
        assert application["interview"]["status"] == "scheduled"
        assert application["interview"]["locationOrLink"] == "Penang Main Office"


@pytest.mark.acceptance
class TestJobPostingLifecycle:
    @pytest.mark.parametrize("status", ["draft", "published", "closed", "archived"])
    def test_employer_can_change_job_posting_status(self, workflow_context, status):
        response = workflow_context.employer_client.patch(
            "/api/jobs/JOB001/lifecycle",
            json={"status": status},
        )

        assert response.status_code == 200
        assert response.get_json()["job"]["lifecycleStatus"] == status

    def test_invalid_job_posting_status_is_rejected(self, workflow_context):
        response = workflow_context.employer_client.patch(
            "/api/jobs/JOB001/lifecycle",
            json={"status": "deleted"},
        )

        assert response.status_code == 400
        assert "draft" in response.get_json()["error"].lower()

    @pytest.mark.parametrize(
        ("status", "visible_to_job_seeker"),
        [
            ("published", True),
            ("draft", False),
            ("closed", False),
            ("archived", False),
        ],
    )
    def test_job_seeker_visibility_follows_lifecycle_status(
        self,
        workflow_context,
        status,
        visible_to_job_seeker,
    ):
        update_response = workflow_context.employer_client.patch(
            "/api/jobs/JOB001/lifecycle",
            json={"status": status},
        )
        assert update_response.status_code == 200

        public_jobs = workflow_context.seeker_client.get("/api/jobs").get_json()
        is_visible = any(job["id"] == "JOB001" for job in public_jobs)
        assert is_visible is visible_to_job_seeker
