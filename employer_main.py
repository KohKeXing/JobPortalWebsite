from io import BytesIO
from flask import Flask, jsonify, render_template, request, send_file, session, redirect, url_for, make_response
import os
import secrets

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
from supabase_client import (
    ACCOUNT_NOT_FOUND_MESSAGE,
    EMAIL_RATE_LIMIT_MESSAGE,
    auth_account_exists,
    create_supabase_auth_client,
    get_supabase_admin_client,
    is_email_rate_limit_error,
    password_policy_error,
)

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
        response = admin.table("employers").select(
            "id,user_id,employer_id,company_name,company_email,created_at,updated_at"
        ).eq("employer_id", employer_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching employer: {e}")
        return None

def get_employer_by_user_id(user_id: str):
    """Fetch the employer profile linked to a Supabase Auth user."""
    if not user_id:
        return None

    try:
        admin = get_supabase_admin_client()
        response = (
            admin.table("employers")
            .select(
                "id,user_id,employer_id,company_name,company_email,created_at,updated_at"
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching employer by user_id: {e}")
        return None

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
        if not (
            session.get("auth_user_id")
            and session.get("employer_id")
            and session.get("role") == "employer"
        ):
            return redirect(url_for('employer_login'))

        company_name = str(session.get("company_name") or "Employer").strip()
        company_email = str(session.get("company_email") or "").strip()
        company_words = [word for word in company_name.split() if word]
        if len(company_words) >= 2:
            company_initials = "".join(word[0] for word in company_words[:2]).upper()
        else:
            company_initials = company_name[:2].upper()

        return render_template(
            "employer.html",
            company_name=company_name,
            company_email=company_email,
            company_initials=company_initials or "EM",
        )

    # =============================================================
    # FORGOT PASSWORD - SHARED WITH SEEKER
    # =============================================================
    @app.route("/forgot-password")
    def forgot_password_page():
        """Render forgot password page - shared with seeker"""
        return render_template(
            "forgot_password.html",
            login_url=url_for("employer_login"),
        )

    @app.route("/reset-password")
    def reset_password_page():
        """Render reset password page - shared with seeker"""
        session.clear()
        resp = make_response(render_template(
            "reset_password.html",
            login_url=url_for("employer_login"),
            forgot_password_url=url_for("forgot_password_page"),
        ))
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
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not company_name:
            return jsonify({"error": "Company name is required"}), 400
        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required"}), 400
        password_error = password_policy_error(password)
        if password_error:
            return jsonify({"error": password_error}), 400

        try:
            if auth_account_exists(email):
                return jsonify({
                    "error": "This email is already registered. Please sign in."
                }), 409
        except Exception as exc:
            print("ACCOUNT LOOKUP ERROR:", repr(exc))
            return jsonify({
                "error": "Unable to verify the account right now. Please try again."
            }), 503

        try:
            admin = get_supabase_admin_client()
            auth_client = create_supabase_auth_client()
            confirmation_redirect_url = (
                os.environ.get(
                    "EMPLOYER_EMAIL_CONFIRMATION_REDIRECT_URL",
                    "",
                ).strip()
                or url_for("employer_login", _external=True)
            )
            
            # Create auth user (password stored securely in auth.users)
            response = auth_client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "email_redirect_to": confirmation_redirect_url,
                    "data": {
                        "full_name": company_name,
                        "role": "employer"
                    }
                }
            })

            if not response.user:
                return jsonify({"error": "Failed to create account"}), 400

            # The employer ID is an internal database value. Users do not
            # need to create or enter it during registration.
            auth_user_id = str(response.user.id)
            employer_id = f"emp_{auth_user_id.replace('-', '')[:16]}"

            # Store the application role in the shared profiles table.
            admin.table("profiles").upsert({
                "id": auth_user_id,
                "full_name": company_name,
                "role": "employer"
            }, on_conflict="id").execute()

            # Supabase Auth stores the password. Keep a random legacy api_key
            # only because existing database schemas may require this column.
            admin.table("employers").insert({
                "user_id": auth_user_id,
                "company_name": company_name,
                "company_email": email,
                "employer_id": employer_id,
                "api_key": secrets.token_urlsafe(32)
            }).execute()

            email_confirmation_required = response.session is None
            return jsonify({
                "success": True,
                "message": (
                    "Registration successful! Please confirm your email before signing in."
                    if email_confirmation_required
                    else "Registration successful! You can now login."
                ),
                "email_confirmation_required": email_confirmation_required
            }), 201

        except Exception as e:
            print(f"EMPLOYER REGISTER ERROR: {repr(e)}")
            if is_email_rate_limit_error(e):
                return jsonify({"error": EMAIL_RATE_LIMIT_MESSAGE}), 429
            return jsonify({"error": "Unable to create the account. Please try again."}), 500

    @app.route("/api/employer/verify", methods=["POST"])
    def verify_employer_endpoint():
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()
        password = str(data.get("password") or "")

        if not email or "@" not in email:
            return jsonify({"error": "A valid company email is required."}), 400
        if not password:
            return jsonify({"error": "Password is required."}), 400

        try:
            auth_client = create_supabase_auth_client()
            auth_response = auth_client.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
        except Exception as e:
            print(f"EMPLOYER LOGIN ERROR: {repr(e)}")
            message = str(e).lower()
            if "email not confirmed" in message:
                return jsonify({
                    "error": "Please confirm your company email before signing in.",
                    "email_confirmation_required": True,
                }), 403
            return jsonify({"error": "Invalid email or password."}), 401

        if not auth_response.user or not auth_response.session:
            return jsonify({"error": "Invalid email or password."}), 401

        employer = get_employer_by_user_id(str(auth_response.user.id))
        if not employer:
            try:
                auth_client.auth.sign_out()
            except Exception:
                pass
            return jsonify({
                "error": "This email is not linked to an employer account."
            }), 403

        session.clear()
        session["auth_user_id"] = str(auth_response.user.id)
        session["employer_id"] = employer["employer_id"]
        session["company_name"] = employer.get("company_name")
        session["company_email"] = email
        session["role"] = "employer"

        return jsonify({
            "success": True,
            "message": "Login successful.",
            "employer_id": employer["employer_id"],
            "company_name": employer.get("company_name"),
            "company_email": email,
            "redirect": "/employer/dashboard",
        }), 200

    @app.route("/api/employer/resend-confirmation", methods=["POST"])
    def resend_employer_confirmation():
        data = request.get_json(silent=True) or {}
        email = str(data.get("email") or "").strip().lower()

        if not email or "@" not in email:
            return jsonify({"error": "A valid company email is required."}), 400

        try:
            auth_client = create_supabase_auth_client()
            confirmation_redirect_url = (
                os.environ.get(
                    "EMPLOYER_EMAIL_CONFIRMATION_REDIRECT_URL",
                    "",
                ).strip()
                or url_for("employer_login", _external=True)
            )
            auth_client.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": confirmation_redirect_url
                },
            })
            return jsonify({
                "success": True,
                "message": "Confirmation email sent. Please check your inbox."
            }), 200
        except Exception as e:
            print(f"RESEND CONFIRMATION ERROR: {repr(e)}")
            if is_email_rate_limit_error(e):
                return jsonify({"error": EMAIL_RATE_LIMIT_MESSAGE}), 429
            return jsonify({
                "error": "Unable to resend the confirmation email right now."
            }), 400

    @app.route("/api/auth/forgot-password", methods=["POST"])
    def forgot_password():
        """Send password reset email - shared with seeker"""
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()

        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required."}), 400

        try:
            if not auth_account_exists(email):
                return jsonify({"error": ACCOUNT_NOT_FOUND_MESSAGE}), 404

            auth_client = create_supabase_auth_client()
            reset_redirect_url = (
                os.environ.get(
                    "EMPLOYER_PASSWORD_RESET_REDIRECT_URL",
                    "",
                ).strip()
                or url_for("reset_password_page", _external=True)
            )
            auth_client.auth.reset_password_for_email(
                email,
                {"redirect_to": reset_redirect_url},
            )

            return jsonify({
                "success": True,
                "message": "Reset link sent! Please check your email."
            }), 200

        except Exception as e:
            print(f"PASSWORD RESET ERROR: {repr(e)}")
            if is_email_rate_limit_error(e):
                return jsonify({"error": EMAIL_RATE_LIMIT_MESSAGE}), 429
            return jsonify({
                "error": "Unable to send the reset link. Please try again."
            }), 500

    @app.route("/api/auth/update-password", methods=["POST"])
    def update_password():
        """Update password after reset - shared with seeker"""
        data = request.get_json(silent=True) or {}
        new_password = str(data.get("password", ""))
        access_token = str(data.get("access_token") or "")
        refresh_token = str(data.get("refresh_token") or "")

        password_error = password_policy_error(new_password)
        if password_error:
            return jsonify({"error": password_error}), 400

        if not access_token or not refresh_token:
            return jsonify({
                "error": "Invalid reset link. Please request a new reset link."
            }), 400

        try:
            supabase = create_supabase_auth_client()
            supabase.auth.set_session(access_token, refresh_token)

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
                "error": "The reset link is invalid or expired. Please request a new reset link."
            }), 400

    @app.route("/api/employer/logout", methods=["POST"])
    def employer_logout():
        session.clear()
        return jsonify({"success": True, "redirect": "/employer/login"}), 200

    @app.route("/api/employer/check-session", methods=["GET"])
    def check_employer_session():
        return jsonify({
            "logged_in": bool(
                session.get("auth_user_id")
                and session.get("employer_id")
                and session.get("role") == "employer"
            ),
            "employer_id": session.get("employer_id"),
            "company_name": session.get("company_name"),
            "company_email": session.get("company_email"),
        })

    # =============================================================
    # EMPLOYER AUTHENTICATION HELPER
    # =============================================================
    def employer_required(view_function):
        from functools import wraps
        @wraps(view_function)
        def decorated_function(*args, **kwargs):
            if (
                session.get("auth_user_id")
                and session.get("employer_id")
                and session.get("role") == "employer"
            ):
                return view_function(*args, **kwargs)

            if request.path.startswith("/api/"):
                return jsonify({"error": "Employer authentication required"}), 401
            return redirect(url_for('employer_login'))
        
        return decorated_function

    # =============================================================
    # JOB POSTING CRUD
    # =============================================================
    @app.route("/api/jobs", methods=["GET"])
    @employer_required
    def get_jobs():
        return jsonify(job_store.get_jobs(session["auth_user_id"]))

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    @employer_required
    def get_job(job_id):
        job = job_store.get_job(job_id, session["auth_user_id"])
        if job:
            return jsonify(job)
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs", methods=["POST"])
    @employer_required
    def create_job():
        data = request.get_json() or {}
        data["company"] = session.get("company_name") or ""
        missing = [f for f in REQUIRED_JOB_FIELDS if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
        try:
            new_job = job_store.create_job(data, session["auth_user_id"])
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Job creation failed")
            message = str(exc) if app.debug else "The database rejected the job."
            return jsonify({"error": f"Failed to save job: {message}"}), 500
        return jsonify(new_job), 201

    @app.route("/api/jobs/<job_id>", methods=["PUT"])
    @employer_required
    def update_job(job_id):
        data = request.get_json() or {}
        data["company"] = session.get("company_name") or ""
        try:
            job = job_store.update_job(
                job_id,
                data,
                session["auth_user_id"],
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Job update failed")
            message = str(exc) if app.debug else "The database rejected the update."
            return jsonify({"error": f"Failed to update job: {message}"}), 500
        if job:
            return jsonify(job)
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs/<job_id>", methods=["DELETE"])
    @employer_required
    def delete_job(job_id):
        employer_id = session["auth_user_id"]
        if job_store.get_job(job_id, employer_id) is None:
            return jsonify({"error": "Job not found"}), 404

        try:
            removed_applications = app_tracker.delete_applications_for_job(job_id)
            for application in removed_applications:
                delete_cover_letter_file(application.get("coverLetterFile"))

            job_store.delete_job(job_id, employer_id)
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
        owned_job_ids = {
            job["id"] for job in job_store.get_jobs(session["auth_user_id"])
        }
        applications = [
            application
            for application in app_tracker.get_applications()
            if application.get("jobId") in owned_job_ids
        ]
        return jsonify(applications)

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

        application = app_tracker.get_application(app_id)
        application_job_id = application.get("jobId") if application else None
        if not application_job_id or not job_store.get_job(
            application_job_id,
            session["auth_user_id"],
        ):
            return jsonify({"error": "Application not found"}), 404

        success = app_tracker.update_status(app_id, new_status, new_details)
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Application not found"}), 404

    @app.route("/api/applications/<app_id>", methods=["DELETE"])
    @employer_required
    def delete_application(app_id):
        application = app_tracker.get_application(app_id)
        application_job_id = application.get("jobId") if application else None
        if not application_job_id or not job_store.get_job(
            application_job_id,
            session["auth_user_id"],
        ):
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
        owned_job_ids = {
            job["id"] for job in job_store.get_jobs(session["auth_user_id"])
        }
        can_view_resume = any(
            application.get("jobId") in owned_job_ids
            and application.get("resumeId") == resume_id
            for application in app_tracker.get_applications()
        )
        if not can_view_resume:
            return jsonify({"error": "Resume not found"}), 404

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
    app.run(debug=True, port=5000)
