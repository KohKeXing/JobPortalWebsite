import json
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
APPLICATIONS_FILE = DATA_DIR / "applications.json"

# Seed data shown the first time the app runs, so the dashboard/employer
# console aren't empty before any real applications exist.
DEFAULT_APPLICATIONS = [
    {
        "id": str(uuid.uuid4()),
        "jobId": "job-1",
        "job": "Python Developer",
        "company": "ABC Technology",
        "date": "2026-07-01",
        "status": "Interview",
        "details": "Technical interview scheduled",
        "resumeId": None,
        "coverLetterText": None,
        "coverLetterFile": None,
        "coverLetterOriginalName": None,
    },
    {
        "id": str(uuid.uuid4()),
        "jobId": "job-3",
        "job": "Software Engineer",
        "company": "XYZ Software",
        "date": "2026-06-25",
        "status": "Pending",
        "details": "Waiting for employer response",
        "resumeId": None,
        "coverLetterText": None,
        "coverLetterFile": None,
        "coverLetterOriginalName": None,
    },
    {
        "id": str(uuid.uuid4()),
        "jobId": "job-4",
        "job": "Data Analyst",
        "company": "Data Solution Sdn Bhd",
        "date": "2026-06-20",
        "status": "Rejected",
        "details": "Application unsuccessful",
        "resumeId": None,
        "coverLetterText": None,
        "coverLetterFile": None,
        "coverLetterOriginalName": None,
    },
]


class ApplicationTracking:
    """Real Python persistence for job applications: plain JSON file I/O on disk.

    This used to be in-memory only, which meant applications submitted through
    seeker_main.py were invisible to employer_main.py — they're separate Flask
    processes, so an in-memory list in one never reaches the other. Writing to
    a shared JSON file on disk (like JobStorage and ResumeStorage already do)
    fixes that: both apps read/write the same file, so a real application a
    seeker submits actually shows up for the employer to review.
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not APPLICATIONS_FILE.exists():
            self._write(DEFAULT_APPLICATIONS)

    def _read(self):
        try:
            return json.loads(APPLICATIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, applications):
        APPLICATIONS_FILE.write_text(json.dumps(applications, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_applications(self):
        return self._read()

    def get_application(self, app_id):
        for app in self._read():
            if app["id"] == app_id:
                return app
        return None

    def add_application(self, job_id, job_title, company, date=None, status="Pending", details="",
                         resume_id=None, cover_letter_text=None, cover_letter_file=None,
                         cover_letter_original_name=None):
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        new_app = {
            "id": str(uuid.uuid4()),
            "jobId": job_id,
            "job": job_title,
            "company": company,
            "date": date,
            "status": status,
            "details": details,
            "resumeId": resume_id,
            "coverLetterText": cover_letter_text,
            "coverLetterFile": cover_letter_file,
            "coverLetterOriginalName": cover_letter_original_name,
        }
        applications = self._read()
        applications.append(new_app)
        self._write(applications)
        return new_app

    def update_status(self, app_id, new_status, new_details=None):
        applications = self._read()
        for app in applications:
            if app["id"] == app_id:
                app["status"] = new_status
                if new_details is not None:
                    app["details"] = new_details
                self._write(applications)
                return True
        return False

    def delete_application(self, app_id):
        applications = self._read()
        remaining = [a for a in applications if a["id"] != app_id]
        if len(remaining) == len(applications):
            return False
        self._write(remaining)
        return True