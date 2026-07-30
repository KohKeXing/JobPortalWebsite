from io import BytesIO

from flask import Flask, jsonify, render_template, request, send_file

# Import the shared application tracking module (same one seeker_main.py uses)
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


# ---------------------------------------------------------
# Instantiate storage
# ---------------------------------------------------------
job_store = JobStorage()
app_tracker = ApplicationTracking()
resume_store = ResumeStorage()  # shared with seeker_main.py — read-only use here


def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "employer-console-secure-token"

    @app.route("/")
    def index():
        return render_template("employer.html")

    # =============================================================
    # JOB POSTING CRUD (the employer's core function)
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
            # Cascade: remove every application tied to this job first (and
            # their cover letter files), so the FK constraint on
            # applications.job_id doesn't block the job delete below.
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
    # APPLICANT REVIEW (read applications, update their status)
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
    # VIEWING CANDIDATE SUBMISSIONS (read-only access to the
    # resume/cover-letter storage that seeker_main.py writes to)
    # =============================================================
    @app.route("/api/resumes/<resume_id>", methods=["GET"])
    def get_candidate_resume(resume_id):
        resume = resume_store.get_resume(resume_id)
        if resume:
            return jsonify(resume)
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    def serve_resume_file(filename):
        stored_file = resume_store.download_uploaded_resume(filename)
        if stored_file is None:
            return jsonify({"error": "Resume file not found"}), 404
        return send_file(
            BytesIO(stored_file["content"]),
            mimetype=stored_file["content_type"],
            download_name=stored_file["file_name"],
            as_attachment=False,
        )

    @app.route("/uploads/cover-letters/<filename>")
    def serve_cover_letter_file(filename):
        stored_file = download_cover_letter_file(filename)
        if stored_file is None:
            return jsonify({"error": "Cover letter not found"}), 404
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