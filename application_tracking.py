import uuid
from datetime import datetime

class ApplicationTracking:
    def __init__(self):
        # 为每条硬编码申请添加 jobId，与 JOBS_DATABASE 中的 id 对应
        self.applications = [
            {
                "id": str(uuid.uuid4()),
                "jobId": "job-1",          # Python Developer → job-1 (Senior React Engineer, 但作为示例)
                "job": "Python Developer",
                "company": "ABC Technology",
                "date": "2026-07-01",
                "status": "Interview",
                "details": "Technical interview scheduled"
            },
            {
                "id": str(uuid.uuid4()),
                "jobId": "job-3",          # Software Engineer → job-3 (Growth Marketing Manager)
                "job": "Software Engineer",
                "company": "XYZ Software",
                "date": "2026-06-25",
                "status": "Pending",
                "details": "Waiting for employer response"
            },
            {
                "id": str(uuid.uuid4()),
                "jobId": "job-4",          # Data Analyst → job-4 (Healthcare Data Analyst)
                "job": "Data Analyst",
                "company": "Data Solution Sdn Bhd",
                "date": "2026-06-20",
                "status": "Rejected",
                "details": "Application unsuccessful"
            }
        ]

    def get_applications(self):
        return self.applications

    def get_application(self, app_id):
        for app in self.applications:
            if app["id"] == app_id:
                return app
        return None

    def add_application(self, job_id, job_title, company, date=None, status="Pending", details=""):
        if date is None:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        new_app = {
            "id": str(uuid.uuid4()),
            "jobId": job_id,
            "job": job_title,
            "company": company,
            "date": date,
            "status": status,
            "details": details
        }
        self.applications.append(new_app)
        return new_app

    def update_status(self, app_id, new_status, new_details=None):
        app = self.get_application(app_id)
        if app:
            app["status"] = new_status
            if new_details is not None:
                app["details"] = new_details
            return True
        return False
