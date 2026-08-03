from io import BytesIO
from flask import Flask, jsonify, render_template, request, send_file

# Import the shared application tracking module
from application_tracking import ApplicationTracking, VALID_STATUSES

# Import the shared Supabase Database + private Storage helpers.
from resume_builder import (
    ResumeStorage,
    delete_cover_letter_file,
    download_cover_letter_file,
)

# Import the shared Supabase job storage.
from job import JobStorage

REQUIRED_JOB_FIELDS = ["title", "company", "location", "salary", "type", "description"]

# Import encryption for decryption
from file_encryption import decrypt_bytes

# ---------------------------------------------------------
# Instantiate storage
# ---------------------------------------------------------
job_store = JobStorage()
app_tracker = ApplicationTracking()
resume_store = ResumeStorage()  # shared with seeker_main.py — read-only use here

# ---------------------------------------------------------
# Simple employer authorization (temporary)
# In production, use a database table for employers
# ---------------------------------------------------------
# Simple employer API keys - in production, store these in a database
EMPLOYER_KEYS = {
    "pixelcraft": "emp_key_12345",
    "synthetix": "emp_key_67890",
    "cloudnet": "emp_key_11111",
    "test_employer": "test_key_99999",
}

def verify_employer(employer_id: str, api_key: str) -> bool:
    """Verify if employer has valid credentials."""
    if not employer_id or not api_key:
        return False
    return EMPLOYER_KEYS.get(employer_id) == api_key

def verify_employer_for_file(employer_id: str, file_owner_key: str) -> bool:
    """
    Verify employer can access a file.
    In a real system, you'd check if the employer owns the job
    that the file is associated with.
    """
    # For now, if employer is verified, they can access
    # In production, add job ownership check
    return True

def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "employer-console-secure-token"

    @app.route("/")
    def index():
        return render_template("employer.html")

    # =============================================================
    # EMPLOYER AUTHENTICATION
    # =============================================================
    @app.route("/api/employer/verify", methods=["POST"])
    def verify_employer_endpoint():
        """Simple employer verification endpoint."""
        data = request.get_json() or {}
        employer_id = data.get("employer_id")
        api_key = data.get("api_key")
        
        if not employer_id or not api_key:
            return jsonify({"error": "Employer ID and API key required"}), 400
        
        if verify_employer(employer_id, api_key):
            # Generate a session token (simple for now)
            import uuid
            session_token = str(uuid.uuid4())
            return jsonify({
                "success": True,
                "message": "Verified",
                "token": session_token,
                "employer_id": employer_id
            }), 200
        return jsonify({"error": "Invalid credentials"}), 401

    # =============================================================
    # JOB POSTING CRUD
    # =============================================================
    @app.route("/api/jobs", methods=["GET"])
    def get_jobs():
        return jsonify(job_store.get_jobs())

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id):
        job = job_store.get_job(job_id)
        if job:
            return jsonify(job)
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs", methods=["POST"])
    def create_job():
        data = request.get_json() or {}
        missing = [f for f in REQUIRED_JOB_FIELDS if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
        new_job = job_store.create_job(data)
        return jsonify(new_job), 201

    @app.route("/api/jobs/<job_id>", methods=["PUT"])
    def update_job(job_id):
        data = request.get_json() or {}
        job = job_store.update_job(job_id, data)
        if job:
            return jsonify(job)
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs/<job_id>", methods=["DELETE"])
    def delete_job(job_id):
        if job_store.get_job(job_id) is None:
            return jsonify({"error": "Job not found"}), 404

        try:
            removed_applications = app_tracker.delete_applications_for_job(job_id)
            for application in removed_applications:
                delete_cover_letter_file(application.get("coverLetterFile"))

            job_store.delete_job(job_id)
            return jsonify({
                "success": True,
                "deletedApplications": len(removed_applications),
            })
        except Exception:
            app.logger.exception("Job deletion failed")
            return jsonify({
                "error": "This job could not be deleted. Please try again."
            }), 500

    # =============================================================
    # APPLICANT REVIEW
    # =============================================================
    @app.route("/api/applications", methods=["GET"])
    def get_applications():
        return jsonify(app_tracker.get_applications())

    @app.route("/api/applications/<app_id>", methods=["PUT"])
    def update_application_status(app_id):
        data = request.get_json() or {}
        new_status = data.get("status")
        new_details = data.get("details")
        if not new_status:
            return jsonify({"error": "Status is required"}), 400
        if new_status not in VALID_STATUSES:
            return jsonify({"error": f"Status must be one of: {', '.join(VALID_STATUSES)}"}), 400

        success = app_tracker.update_status(app_id, new_status, new_details)
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Application not found"}), 404

    @app.route("/api/applications/<app_id>", methods=["DELETE"])
    def delete_application(app_id):
        application = app_tracker.get_application(app_id)
        if not application:
            return jsonify({"error": "Application not found"}), 404
        if application.get("status") != "Rejected":
            return jsonify({"error": "Only rejected applications can be deleted"}), 400

        success = app_tracker.delete_application(app_id)
        if success:
            delete_cover_letter_file(application.get("coverLetterFile"))
            return jsonify({"success": True}), 200
        return jsonify({"error": "Application not found"}), 404

    # =============================================================
    # VIEWING CANDIDATE SUBMISSIONS (with Authorization)
    # =============================================================
    @app.route("/api/resumes/<resume_id>", methods=["GET"])
    def get_candidate_resume(resume_id):
        # Check authorization - employer must provide credentials
        employer_id = request.headers.get("X-Employer-ID")
        api_key = request.headers.get("X-API-Key")
        
        if not employer_id or not api_key:
            return jsonify({"error": "Authorization required. Provide X-Employer-ID and X-API-Key headers."}), 401
        
        if not verify_employer(employer_id, api_key):
            return jsonify({"error": "Invalid employer credentials"}), 403
        
        resume = resume_store.get_resume(resume_id)
        if resume:
            return jsonify(resume)
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    def serve_resume_file(filename):
        """
        Serve a resume file - ONLY for authorized employers.
        The file is decrypted before being sent.
        """
        # Get employer credentials from request headers
        employer_id = request.headers.get("X-Employer-ID")
        api_key = request.headers.get("X-API-Key")
        
        if not employer_id or not api_key:
            return jsonify({"error": "Authorization required. Provide X-Employer-ID and X-API-Key headers."}), 401
        
        if not verify_employer(employer_id, api_key):
            return jsonify({"error": "Invalid employer credentials"}), 403
        
        # Download the file (which includes decryption)
        stored_file = resume_store.download_uploaded_resume(filename)
        if stored_file is None:
            return jsonify({"error": "Resume file not found"}), 404
        
        # The file is already decrypted by download_uploaded_resume
        return send_file(
            BytesIO(stored_file["content"]),
            mimetype=stored_file["content_type"],
            download_name=stored_file["file_name"],
            as_attachment=False,
        )

    @app.route("/uploads/cover-letters/<filename>")
    def serve_cover_letter_file(filename):
        """
        Serve a cover letter file - ONLY for authorized employers.
        The file is decrypted before being sent.
        """
        # Get employer credentials from request headers
        employer_id = request.headers.get("X-Employer-ID")
        api_key = request.headers.get("X-API-Key")
        
        if not employer_id or not api_key:
            return jsonify({"error": "Authorization required. Provide X-Employer-ID and X-API-Key headers."}), 401
        
        if not verify_employer(employer_id, api_key):
            return jsonify({"error": "Invalid employer credentials"}), 403
        
        # Download the file (which includes decryption)
        stored_file = download_cover_letter_file(filename)
        if stored_file is None:
            return jsonify({"error": "Cover letter not found"}), 404
        
        # The file is already decrypted by download_cover_letter_file
        return send_file(
            BytesIO(stored_file["content"]),
            mimetype=stored_file["content_type"],
            download_name=stored_file["file_name"],
            as_attachment=False,
        )

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)