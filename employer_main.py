from io import BytesIO
from flask import Flask, jsonify, render_template, request, send_file, session, redirect, url_for, make_response
import uuid
import re
import bcrypt

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
from supabase_client import get_supabase_admin_client, create_supabase_auth_client

# ---------------------------------------------------------
# Instantiate storage
# ---------------------------------------------------------
job_store = JobStorage()
app_tracker = ApplicationTracking()
resume_store = ResumeStorage()

# ---------------------------------------------------------
# Employer authorization
# ---------------------------------------------------------

def get_employer_from_db(employer_id: str):
    """Fetch employer from database by employer_id - WITHOUT api_key"""
    try:
        admin = get_supabase_admin_client()
        response = admin.table("employers").select("id,user_id,employer_id,company_name,created_at,updated_at").eq("employer_id", employer_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching employer: {e}")
        return None

def verify_employer(employer_id: str, api_key: str) -> bool:
    """Verify if employer has valid credentials."""
    if not employer_id or not api_key:
        return False
    
    # Check session first
    if session.get('employer_id') == employer_id and session.get('employer_api_key') == api_key:
        return True
    
    # Check database - compare hashed password
    try:
        admin = get_supabase_admin_client()
        response = admin.table("employers").select("api_key").eq("employer_id", employer_id).execute()
        if response.data:
            stored_hash = response.data[0].get('api_key')
            if stored_hash and bcrypt.checkpw(api_key.encode('utf-8'), stored_hash.encode('utf-8')):
                return True
    except Exception as e:
        print(f"Error verifying employer: {e}")
    
    return False

def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "employer-console-secure-token"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # =============================================================
    # EMPLOYER AUTHENTICATION PAGES
    # =============================================================
    @app.route("/")
    def index():
        return redirect(url_for('employer_login'))

    @app.route("/employer/login")
    def employer_login():
        return render_template("employer_login.html")

    @app.route("/employer/register")
    def employer_register_page():
        return render_template("employer_register.html")

    @app.route("/employer/dashboard")
    def employer_dashboard():
        if not session.get('employer_id') and not session.get('employer_token'):
            return redirect(url_for('employer_login'))
        return render_template("employer.html")

    # =============================================================
    # FORGOT PASSWORD - SHARED WITH SEEKER
    # =============================================================
    @app.route("/forgot-password")
    def forgot_password_page():
        """Render forgot password page - shared with seeker"""
        return render_template("forgot_password.html")

    @app.route("/reset-password")
    def reset_password_page():
        """Render reset password page - shared with seeker"""
        session.clear()
        resp = make_response(render_template("reset_password.html"))
        resp.set_cookie('session', '', expires=0)
        resp.set_cookie('supabase-auth-token', '', expires=0)
        resp.set_cookie('sb-refresh-token', '', expires=0)
        resp.set_cookie('sb-access-token', '', expires=0)
        return resp

    # =============================================================
    # EMPLOYER AUTHENTICATION API
    # =============================================================
    @app.route("/api/employer/register", methods=["POST"])
    def employer_register():
        data = request.get_json() or {}
        company_name = data.get("company_name", "").strip()
        employer_id = data.get("employer_id", "").strip().lower()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not company_name:
            return jsonify({"error": "Company name is required"}), 400
        if not employer_id:
            return jsonify({"error": "Employer ID is required"}), 400
        if not re.match(r"^[a-z]+$", employer_id):
            return jsonify({"error": "Employer ID can only contain lowercase letters (a-z)"}), 400
        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required"}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must contain at least 6 characters"}), 400

        # Check if employer_id already exists
        existing = get_employer_from_db(employer_id)
        if existing:
            return jsonify({"error": "Employer ID already exists"}), 409

        try:
            admin = get_supabase_admin_client()
            auth_client = create_supabase_auth_client()
            
            # Create auth user (password stored securely in auth.users)
            response = auth_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": company_name,
                        "role": "employer",
                        "employer_id": employer_id
                    }
                }
            })

            if not response.user:
                return jsonify({"error": "Failed to create account"}), 400

            # Hash the password before storing as api_key
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            # Insert into employers table with hashed password
            admin.table("employers").insert({
                "user_id": response.user.id,
                "company_name": company_name,
                "employer_id": employer_id,
                "api_key": hashed_password
            }).execute()

            return jsonify({
                "success": True,
                "message": "Registration successful! You can now login.",
                "employer_id": employer_id
            }), 201

        except Exception as e:
            print(f"EMPLOYER REGISTER ERROR: {repr(e)}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/employer/verify", methods=["POST"])
    def verify_employer_endpoint():
        data = request.get_json() or {}
        employer_id = data.get("employer_id")
        api_key = data.get("api_key")
        
        if not employer_id or not api_key:
            return jsonify({"error": "Employer ID and API key required"}), 400
        
        if verify_employer(employer_id, api_key):
            session['employer_id'] = employer_id
            session['employer_api_key'] = api_key
            session['role'] = 'employer'
            session['employer_token'] = str(uuid.uuid4())
            
            return jsonify({
                "success": True,
                "message": "Verified",
                "token": session['employer_token'],
                "employer_id": employer_id
            }), 200
        return jsonify({"error": "Invalid credentials"}), 401

    @app.route("/api/auth/forgot-password", methods=["POST"])
    def forgot_password():
        """Send password reset email - shared with seeker"""
        data = request.get_json() or {}
        email = str(data.get("email", "")).strip().lower()
        
        if not email:
            return jsonify({"error": "Email is required"}), 400
        
        try:
            from supabase_client import create_supabase_auth_client
            auth_client = create_supabase_auth_client()
            auth_client.auth.reset_password_for_email(email)
            
            print(f"✅ Reset email sent to {email}")
            return jsonify({
                "success": True,
                "message": "Password reset email sent! Please check your inbox."
            }), 200
            
        except Exception as e:
            print(f"PASSWORD RESET ERROR: {repr(e)}")
            return jsonify({
                "success": True,
                "message": "If this email is registered, you will receive a reset link shortly."
            }), 200

    @app.route("/api/auth/update-password", methods=["POST"])
    def update_password():
        """Update password after reset - shared with seeker"""
        data = request.get_json() or {}
        new_password = data.get("password", "")
        access_token = data.get("access_token")
        
        if len(new_password) < 6:
            return jsonify({
                "error": "Password must contain at least 6 characters."
            }), 400
        
        try:
            from supabase_client import create_supabase_auth_client
            supabase = create_supabase_auth_client()
            
            if access_token:
                supabase.auth.set_session(access_token, None)
            else:
                return jsonify({
                    "error": "Invalid reset token. Please request a new password reset."
                }), 400
            
            supabase.auth.update_user({
                "password": new_password
            })
            
            supabase.auth.sign_out()
            
            return jsonify({
                "success": True,
                "message": "Password updated successfully! Please login with your new password."
            }), 200
        except Exception as e:
            print("PASSWORD UPDATE ERROR:", repr(e))
            return jsonify({
                "error": "Failed to update password. Please try again or request a new reset link."
            }), 500

    @app.route("/api/employer/logout", methods=["POST"])
    def employer_logout():
        session.pop('employer_id', None)
        session.pop('employer_api_key', None)
        session.pop('role', None)
        session.pop('employer_token', None)
        return jsonify({"success": True, "redirect": "/employer/login"}), 200

    @app.route("/api/employer/check-session", methods=["GET"])
    def check_employer_session():
        return jsonify({
            "logged_in": bool(session.get('employer_id') and session.get('employer_token')),
            "employer_id": session.get('employer_id')
        })

    # =============================================================
    # EMPLOYER AUTHENTICATION HELPER
    # =============================================================
    def employer_required(view_function):
        from functools import wraps
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            if session.get('employer_id') and session.get('employer_token'):
                return view_function(*args, **kwargs)
            
            employer_id = request.headers.get("X-Employer-ID")
            api_key = request.headers.get("X-API-Key")
            
            if employer_id and api_key:
                if verify_employer(employer_id, api_key):
                    return view_function(*args, **kwargs)
            
            if request.path.startswith("/api/"):
                return jsonify({"error": "Employer authentication required"}), 401
            return redirect(url_for('employer_login'))
        
        return decorated_function

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
    @employer_required
    def create_job():
        data = request.get_json() or {}
        missing = [f for f in REQUIRED_JOB_FIELDS if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
        new_job = job_store.create_job(data)
        return jsonify(new_job), 201

    @app.route("/api/jobs/<job_id>", methods=["PUT"])
    @employer_required
    def update_job(job_id):
        data = request.get_json() or {}
        job = job_store.update_job(job_id, data)
        if job:
            return jsonify(job)
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs/<job_id>", methods=["DELETE"])
    @employer_required
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
    @employer_required
    def get_applications():
        return jsonify(app_tracker.get_applications())

    @app.route("/api/applications/<app_id>", methods=["PUT"])
    @employer_required
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
    @employer_required
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
    # VIEWING CANDIDATE SUBMISSIONS
    # =============================================================
    @app.route("/api/resumes/<resume_id>", methods=["GET"])
    @employer_required
    def get_candidate_resume(resume_id):
        resume = resume_store.get_resume(resume_id)
        if resume:
            return jsonify(resume)
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    @employer_required
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
    @employer_required
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