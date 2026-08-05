import json
import os
import urllib.request
import urllib.error
import datetime
import uuid
from io import BytesIO

from flask import (
    Flask, render_template, request, jsonify, send_file, session,
    redirect, url_for, make_response
)

# Import application tracking module
from application_tracking import ApplicationTracking, VALID_STATUSES

# Import Supabase Database + private Storage helpers.
from resume_builder import (
    ResumeStorage,
    download_cover_letter_file,
    save_cover_letter_file,
)

# Import the shared Supabase job storage.
from job import JobStorage
from bookmark import BookmarkStorage
from auth_service import AuthService, JOB_SEEKER_ROLE
from login_required import seeker_required
from supabase_client import create_supabase_auth_client

job_store = JobStorage()

# JSON schemas for Gemini response schema
RESUME_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "personalInfo": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "email": {"type": "STRING"},
                "phone": {"type": "STRING"},
                "location": {"type": "STRING"},
                "title": {"type": "STRING"},
                "website": {"type": "STRING"},
                "summary": {"type": "STRING", "description": "Compelling 3-4 sentence professional summary highlighting core values and strengths."}
            },
            "required": ["name", "email", "phone", "location", "title", "summary"]
        },
        "experience": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "company": {"type": "STRING"},
                    "role": {"type": "STRING"},
                    "startDate": {"type": "STRING"},
                    "endDate": {"type": "STRING"},
                    "description": {"type": "STRING", "description": "Polished, multi-line bullet-pointed description with each bullet starting on a new line with the '• ' character."}
                },
                "required": ["id", "company", "role", "startDate", "endDate", "description"]
            }
        },
        "education": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "school": {"type": "STRING"},
                    "degree": {"type": "STRING"},
                    "field": {"type": "STRING"},
                    "startDate": {"type": "STRING"},
                    "endDate": {"type": "STRING"}
                },
                "required": ["id", "school", "degree", "field", "startDate", "endDate"]
            }
        },
        "skills": {
            "type": "ARRAY",
            "items": {"type": "STRING"}
        },
        "projects": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "name": {"type": "STRING"},
                    "description": {"type": "STRING", "description": "Compelling project outcome, complexity, and technical details."},
                    "technologies": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "link": {"type": "STRING"}
                },
                "required": ["id", "name", "description", "technologies"]
            }
        }
    },
    "required": ["personalInfo", "experience", "education", "skills", "projects"]
}

MATCH_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "matchScore": {"type": "INTEGER", "description": "Match compatibility score between 0 and 100"},
        "analysis": {"type": "STRING", "description": "Markdown string with structural headings: ### Alignment Strengths, ### Critical Skill Gaps, and ### Tailoring Recommendations."}
    },
    "required": ["matchScore", "analysis"]
}

def call_gemini(prompt, system_instruction=None, response_schema=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
        
    model = "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    contents = [{
        "parts": [{"text": prompt}]
    }]
    
    config = {}
    if system_instruction:
        config["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    
    if response_schema:
        config["responseMimeType"] = "application/json"
        config["responseSchema"] = response_schema
        
    payload = {
        "contents": contents,
        "generationConfig": config
    }
    
    req_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build-python"
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return text
    except urllib.error.HTTPError as e:
        error_details = e.read().decode("utf-8")
        print(f"[-] Gemini API HTTP Error ({e.code}): {error_details}")
        return None
    except Exception as e:
        print(f"[-] Gemini API Connection Error: {e}")
        return None

# Instantiate application tracker
app_tracker = ApplicationTracking()

# Instantiate shared Supabase storage classes.
resume_store = ResumeStorage()
bookmark_store = BookmarkStorage()
auth_service = AuthService()

def create_app():
    app = Flask(__name__, template_folder="templates")
    app.config["MAX_CONTENT_LENGTH"] = 11 * 1024 * 1024
    app.config["SECRET_KEY"] = os.environ.get(
        "FLASK_SECRET_KEY",
        "local-development-secret-change-me",
    )
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    def get_bookmark_owner_key():
        """Use the authenticated user ID as the bookmark owner."""
        return session["user_id"]

    # =========================================================
    # AUTHENTICATION PAGES
    # =========================================================
    @app.route("/login")
    def login_page():
        if (
            session.get("user_id")
            and session.get("role") == JOB_SEEKER_ROLE
        ):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/register")
    def register_page():
        if (
            session.get("user_id")
            and session.get("role") == JOB_SEEKER_ROLE
        ):
            return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/forgot-password")
    def forgot_password_page():
        """Render forgot password page"""
        return render_template("forgot_password.html")

    @app.route("/reset-password")
    def reset_password_page():
        """Render reset password page - Force logout to prevent auto-login"""
        # Clear all session data to prevent auto-login
        session.clear()
        
        # Create response with cleared session
        resp = make_response(render_template("reset_password.html"))
        
        # Clear all cookies that might cause auto-login
        resp.set_cookie('session', '', expires=0)
        resp.set_cookie('supabase-auth-token', '', expires=0)
        resp.set_cookie('sb-refresh-token', '', expires=0)
        resp.set_cookie('sb-access-token', '', expires=0)
        
        return resp

    # =========================================================
    # AUTHENTICATION API
    # =========================================================
    @app.route("/api/auth/register", methods=["POST"])
    def register_user():
        data = request.get_json(silent=True) or {}
        full_name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))

        if not full_name:
            return jsonify({"error": "Full name is required."}), 400
        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required."}), 400
        if len(password) < 6:
            return jsonify({
                "error": "Password must contain at least 6 characters."
            }), 400

        user, error = auth_service.register_user(
            email=email,
            password=password,
            full_name=full_name,
        )
        if error:
            return jsonify({"error": error}), 400

        return jsonify({
            "success": True,
            "message": "Registration successful. Please sign in.",
            "user": {
                "id": user.get("id"),
                "full_name": user.get("full_name"),
                "role": user.get("role"),
            },
        }), 201

    @app.route("/api/auth/login", methods=["POST"])
    def login_user():
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))

        if not email or not password:
            return jsonify({
                "error": "Email and password are required."
            }), 400

        user, error = auth_service.login_user(email, password)
        if error:
            return jsonify({"error": error}), 401

        session.clear()
        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["full_name"] = user.get("full_name", "")
        session["role"] = user.get("role", JOB_SEEKER_ROLE)
        session["access_token"] = user.get("access_token")
        session["refresh_token"] = user.get("refresh_token")

        return jsonify({
            "success": True,
            "redirect": "/dashboard",
            "user": {
                "id": session["user_id"],
                "email": session["email"],
                "full_name": session["full_name"],
                "role": session["role"],
            },
        }), 200

    @app.route("/api/auth/logout", methods=["POST"])
    def logout_user():
        session.clear()
        return jsonify({
            "success": True,
            "redirect": "/login",
        })

    @app.route("/logout-direct")
    def logout_direct():
        """Direct logout - clears everything and redirects to login"""
        session.clear()
        resp = make_response(redirect(url_for('login_page')))
        resp.set_cookie('session', '', expires=0)
        resp.set_cookie('supabase-auth-token', '', expires=0)
        resp.set_cookie('sb-refresh-token', '', expires=0)
        resp.set_cookie('sb-access-token', '', expires=0)
        return resp

    @app.route("/api/auth/me")
    def current_user():
        if not session.get("user_id"):
            return jsonify({"authenticated": False}), 401

        return jsonify({
            "authenticated": True,
            "user": {
                "id": session.get("user_id"),
                "email": session.get("email"),
                "full_name": session.get("full_name"),
                "role": session.get("role"),
            },
        })

    @app.route("/api/auth/forgot-password", methods=["POST"])
    def forgot_password():
        """Send a Supabase recovery email back to this app's reset page."""
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()

        if not email or "@" not in email:
            return jsonify({"error": "A valid email is required."}), 400

        try:
            # Creating the client also loads the project's .env file.
            auth_client = create_supabase_auth_client()

            # Set PASSWORD_RESET_REDIRECT_URL in .env for production. During
            # local development, this resolves to the host that served the form.
            reset_redirect_url = (
                os.environ.get("PASSWORD_RESET_REDIRECT_URL", "").strip()
                or url_for("reset_password_page", _external=True)
            )

            auth_client.auth.reset_password_for_email(
                email,
                {"redirect_to": reset_redirect_url},
            )

            return jsonify({
                "success": True,
                "message": (
                    "If this email is registered, you will receive a reset "
                    "link shortly."
                ),
            }), 200

        except Exception as e:
            # Do not reveal whether an account exists, but keep the real error
            # in the server log so redirect allow-list problems are visible.
            print("PASSWORD RESET EMAIL ERROR:", repr(e))
            return jsonify({
                "success": True,
                "message": "If this email is registered, you will receive a reset link shortly."
            }), 200

    @app.route("/api/auth/update-password", methods=["POST"])
    def update_password():
        """Update password after reset"""
        data = request.get_json(silent=True) or {}
        new_password = str(data.get("password", ""))
        access_token = str(data.get("access_token") or "")
        refresh_token = str(data.get("refresh_token") or "")

        if len(new_password) < 6:
            return jsonify({
                "error": "Password must contain at least 6 characters."
            }), 400

        if not access_token or not refresh_token:
            return jsonify({
                "error": (
                    "Invalid or incomplete reset link. Please request a new "
                    "password reset."
                )
            }), 400

        try:
            supabase = create_supabase_auth_client()

            # A recovery redirect supplies both tokens. Supabase requires both
            # values to create the temporary authenticated recovery session.
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
                "error": (
                    "The reset link is invalid or expired. Please request a "
                    "new reset link."
                )
            }), 400

    # =========================================================
    # MANUAL RESET - FOR DEVELOPMENT ONLY (REMOVE IN PRODUCTION)
    # =========================================================
    @app.route("/api/auth/manual-reset", methods=["POST"])
    def manual_reset():
        """Manual password reset for development (REMOVE IN PRODUCTION)"""
        try:
            data = request.get_json() or {}
            email = data.get("email", "").strip().lower()
            new_password = data.get("new_password", "")
            
            if not email or not new_password:
                return jsonify({"error": "Email and new password required"}), 400
            
            if len(new_password) < 6:
                return jsonify({"error": "Password must be at least 6 characters"}), 400
            
            from supabase_client import get_supabase_admin_client
            admin = get_supabase_admin_client()
            
            # Find user by email - FIXED for newer Supabase versions
            response = admin.auth.admin.list_users()
            
            # Check if response is a list directly (newer versions)
            if isinstance(response, list):
                users = response
            # Check if response has data attribute (older versions)
            elif hasattr(response, 'data'):
                users = response.data
            else:
                users = []
            
            target_user = None
            for user in users:
                if user.email == email:
                    target_user = user
                    break
            
            if not target_user:
                return jsonify({"error": "User not found"}), 404
            
            # Update password - FIXED for newer Supabase versions
            try:
                # Try the newer method
                admin.auth.admin.update_user_by_id(
                    target_user.id,
                    {"password": new_password}
                )
            except AttributeError:
                # Fallback for older versions
                admin.auth.admin.update_user(
                    target_user.id,
                    {"password": new_password}
                )
            
            return jsonify({
                "success": True,
                "message": f"Password reset for {email} successfully! You can now login with your new password."
            }), 200
            
        except Exception as e:
            print(f"Manual reset error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    # =========================================================
    # PROFILE API
    # =========================================================
    @app.route("/api/profile", methods=["GET"])
    @seeker_required
    def get_profile():
        profile = auth_service.get_profile(session["user_id"])
        if not profile:
            return jsonify({"error": "Profile not found."}), 404
        profile["email"] = session.get("email", "")
        return jsonify(profile)

    @app.route("/api/profile", methods=["PUT"])
    @seeker_required
    def update_profile():
        data = request.get_json(silent=True) or {}

        full_name = str(data.get("full_name", "")).strip()
        if not full_name:
            return jsonify({"error": "Full name is required."}), 400

        skills = data.get("skills", [])
        if not isinstance(skills, list):
            return jsonify({"error": "Skills must be a list."}), 400

        profile = auth_service.update_profile(
            session["user_id"],
            {
                "full_name": full_name,
                "headline": str(data.get("headline", "")).strip(),
                "phone": str(data.get("phone", "")).strip(),
                "bio": str(data.get("bio", "")).strip(),
                "skills": skills,
                "avatar": data.get("avatar"),
            },
        )
        if not profile:
            return jsonify({"error": "Profile update failed."}), 500

        session["full_name"] = profile.get("full_name", full_name)
        profile["email"] = session.get("email", "")
        return jsonify({"success": True, "profile": profile})

    # =========================================================
    # PROTECTED SEEKER PAGES
    # =========================================================
    @app.route("/")
    def index():
        """Root route - redirect to dashboard if logged in, else login"""
        if session.get("user_id") and session.get("role") == JOB_SEEKER_ROLE:
            return render_template("seeker.html")
        return redirect(url_for("login_page"))

    @app.route("/dashboard")
    def dashboard():
        """Dashboard - redirect to login if not authenticated"""
        if session.get("user_id") and session.get("role") == JOB_SEEKER_ROLE:
            return render_template("seeker.html")
        return redirect(url_for("login_page"))

    @app.route("/resumes")
    @seeker_required
    def resumes():
        return render_template("resumes.html")

    # ---------------------------------------------------------
    # APPLICATION TRACKING API ROUTES
    # ---------------------------------------------------------
    @app.route("/api/applications", methods=["GET"])
    @seeker_required
    def get_applications():
        return jsonify(app_tracker.get_applications())

    @app.route("/api/applications", methods=["POST"])
    @seeker_required
    def add_application():
        data = request.get_json() or {}
        job_id = data.get("jobId")
        job_title = data.get("job")
        company = data.get("company")
        date = data.get("date") or datetime.datetime.now().strftime("%Y-%m-%d")
        details = data.get("details", "")
        resume_id = data.get("resumeId")
        cover_letter_text = data.get("coverLetterText")
        cover_letter_file = data.get("coverLetterFile")
        cover_letter_original_name = data.get("coverLetterOriginalName")
        if not job_id or not job_title or not company:
            return jsonify({"error": "jobId, job title and company are required"}), 400
        if not resume_id:
            return jsonify({"error": "A resume must be selected to apply."}), 400
        selected_resume = resume_store.get_resume(resume_id)
        if not selected_resume:
            return jsonify({"error": "The selected resume was not found."}), 400
        if not selected_resume.get("storedFileName"):
            return jsonify({
                "error": "Save the selected builder resume as PDF or DOCX before applying."
            }), 400
        if not cover_letter_text and not cover_letter_file:
            return jsonify({"error": "A cover letter (written or uploaded) is required to apply."}), 400

        existing = app_tracker.get_applications()
        if any(a["jobId"] == job_id for a in existing):
            return jsonify({"error": "You have already applied to this job."}), 409

        new_app = app_tracker.add_application(
            job_id, job_title, company, date, "Pending", details,
            resume_id=resume_id,
            cover_letter_text=cover_letter_text,
            cover_letter_file=cover_letter_file,
            cover_letter_original_name=cover_letter_original_name,
        )
        return jsonify({"success": True, "application": new_app}), 201

    # ---------------------------------------------------------
    # BOOKMARK CRUD API ROUTES (Supabase Database)
    # ---------------------------------------------------------
    @app.route("/api/bookmarks", methods=["GET"])
    @seeker_required
    def get_bookmarks():
        try:
            return jsonify(
                bookmark_store.get_job_ids(get_bookmark_owner_key())
            )
        except Exception:
            app.logger.exception("Could not load bookmarks")
            return jsonify({"error": "Could not load bookmarks."}), 500

    @app.route("/api/bookmarks/<job_id>", methods=["POST"])
    @seeker_required
    def add_bookmark(job_id):
        try:
            if job_store.get_job(job_id) is None:
                return jsonify({"error": "Job not found."}), 404

            created = bookmark_store.add_bookmark(
                get_bookmark_owner_key(),
                job_id,
            )
            bookmarks = bookmark_store.get_job_ids(
                get_bookmark_owner_key()
            )
            return jsonify({
                "success": True,
                "created": created,
                "jobId": job_id,
                "bookmarks": bookmarks,
            }), 201 if created else 200
        except Exception:
            app.logger.exception("Could not add bookmark")
            return jsonify({"error": "Could not add bookmark."}), 500

    @app.route("/api/bookmarks/<job_id>", methods=["DELETE"])
    @seeker_required
    def delete_bookmark(job_id):
        try:
            removed = bookmark_store.delete_bookmark(
                get_bookmark_owner_key(),
                job_id,
            )
            bookmarks = bookmark_store.get_job_ids(
                get_bookmark_owner_key()
            )
            return jsonify({
                "success": True,
                "removed": removed,
                "jobId": job_id,
                "bookmarks": bookmarks,
            })
        except Exception:
            app.logger.exception("Could not delete bookmark")
            return jsonify({"error": "Could not delete bookmark."}), 500

    @app.route("/api/cover-letters/upload", methods=["POST"])
    @seeker_required
    def upload_cover_letter():
        file = request.files.get("coverLetter")
        if not file or not file.filename:
            return jsonify({"error": "No file was provided."}), 400

        try:
            record = save_cover_letter_file(file)
            return jsonify({"success": True, **record}), 201
        except ValueError as exc:
            app.logger.warning("Cover-letter validation failed: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Cover-letter upload failed")
            return jsonify({
                "error": f"Could not upload the cover letter: {str(exc)}"
            }), 500

    @app.route("/uploads/cover-letters/<filename>")
    def serve_cover_letter(filename):
        stored_file = download_cover_letter_file(filename)
        if stored_file is None:
            return jsonify({"error": "Cover letter not found"}), 404
        return send_file(
            BytesIO(stored_file["content"]),
            mimetype=stored_file["content_type"],
            download_name=stored_file["file_name"],
            as_attachment=False,
        )

    @app.route("/api/applications/<app_id>", methods=["PUT"])
    def update_application_status(app_id):
        role = request.headers.get("X-Role", "candidate")
        if role.lower() != "employer":
            return jsonify({"error": "Only employer can update status"}), 403

        data = request.get_json() or {}
        new_status = data.get("status")
        new_details = data.get("details")
        if not new_status:
            return jsonify({"error": "Status is required"}), 400
        if new_status not in VALID_STATUSES:
            return jsonify({
                "error": f"Status must be one of: {', '.join(VALID_STATUSES)}"
            }), 400

        success = app_tracker.update_status(app_id, new_status, new_details)
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Application not found"}), 404

    # ---------------------------------------------------------
    # RESUME STORAGE API ROUTES (Supabase Database + private Storage)
    # ---------------------------------------------------------
    @app.route("/api/resumes", methods=["GET"])
    def get_resumes():
        return jsonify(resume_store.get_resumes())

    @app.route("/api/resumes/upload", methods=["POST"])
    def upload_resume():
        file = request.files.get("resume")
        if not file or not file.filename:
            return jsonify({"error": "No file was provided."}), 400

        try:
            record = resume_store.add_uploaded_resume(file)
            return jsonify({"success": True, "resume": record}), 201
        except ValueError as exc:
            app.logger.warning("Resume validation failed: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Resume upload failed")
            return jsonify({
                "error": f"Could not upload the resume: {str(exc)}"
            }), 500

    @app.route("/api/resumes/builder", methods=["POST"])
    def create_builder_resume():
        body = request.get_json() or {}
        name = body.get("name", "Untitled Resume")
        layout = body.get("layout", "modern")
        data = body.get("data", {})
        output_format = body.get("outputFormat")
        try:
            record = resume_store.add_builder_resume(
                name,
                layout,
                data,
                output_format,
            )
            return jsonify({"success": True, "resume": record}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            app.logger.exception("Builder resume generation failed")
            return jsonify({
                "error": "Could not generate and save the resume file."
            }), 500

    @app.route("/api/resumes/<resume_id>", methods=["PUT"])
    def update_resume(resume_id):
        updates = request.get_json() or {}
        try:
            record = resume_store.update_resume(resume_id, updates)
            if record:
                return jsonify({"success": True, "resume": record}), 200
            return jsonify({"error": "Resume not found"}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            app.logger.exception("Resume update/generation failed")
            return jsonify({
                "error": "Could not update and generate the resume file."
            }), 500

    @app.route("/api/resumes/<resume_id>", methods=["DELETE"])
    def delete_resume(resume_id):
        success = resume_store.delete_resume(resume_id)
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    def serve_uploaded_resume(filename):
        stored_file = resume_store.download_uploaded_resume(filename)
        if stored_file is None:
            return jsonify({"error": "Resume file not found"}), 404
        return send_file(
            BytesIO(stored_file["content"]),
            mimetype=stored_file["content_type"],
            download_name=stored_file["file_name"],
            as_attachment=False,
        )

    # ---------------------------------------------------------
    # RESUME PORTAL API ENDPOINTS
    # ---------------------------------------------------------
    @app.route("/api/health")
    def api_health():
        return jsonify({
            "status": "ok",
            "hasApiKey": bool(os.environ.get("GEMINI_API_KEY")),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "backend": "python/flask"
        })

    @app.route("/api/jobs")
    def api_jobs():
        return jsonify(job_store.get_jobs())

    @app.route("/api/resume/auto-generate", methods=["POST"])
    def api_auto_generate():
        body = request.get_json() or {}
        profile = body.get("profile")
        target_role = body.get("targetRole")
        
        if not profile:
            return jsonify({"error": "Profile data is required."}), 400
            
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            skills = profile.get("skills", [])
            title = profile.get("personalInfo", {}).get("title") or target_role or "Specialist"
            fallback_summary = f"Professional {title} with proven expertise in {', '.join(skills[:3]) if skills else 'development'}. Committed to driving results and delivering clean, efficient solutions."
            
            fallback_experience = []
            for item in profile.get("experience", []):
                fallback_experience.append({
                    **item,
                    "description": item.get("description") or "• Led key initiatives and delivered business-critical requirements.\n• Collaborated with cross-functional teams to implement scalable updates."
                })
                
            fallback_projects = []
            for item in profile.get("projects", []):
                fallback_projects.append({
                    **item,
                    "description": item.get("description") or "Developed robust application features using standard industry patterns."
                })
                
            return jsonify({
                "fallback": True,
                "data": {
                    "personalInfo": {
                        **(profile.get("personalInfo") or {}),
                        "summary": fallback_summary
                    },
                    "experience": fallback_experience,
                    "education": profile.get("education") or [],
                    "skills": skills if skills else ["Teamwork", "Problem Solving", "Communication"],
                    "projects": fallback_projects
                }
            })

        prompt = f"""
        You are an expert executive resume writer and career coach.
        Generate a professional, high-impact resume in structured JSON based on the user's profile and optional target role.
        
        USER PROFILE:
        {json.dumps(profile, indent=2)}
        
        TARGET ROLE:
        {target_role or profile.get("personalInfo", {}).get("title") or "Professional matching their background"}

        CRITICAL INSTRUCTIONS:
        1. Write a compelling, high-impact 3-4 sentence professional summary in 'personalInfo.summary'.
        2. Rewrite each 'experience' description to be extremely polished using strong active verbs.
        3. For the 'skills' array, expand with relevant high-demand industry skills (10-15 total).
        4. Rewrite the 'projects' descriptions to showcase complexity and technical details.
        5. Retain all IDs and dates exactly.
        """
        
        system_instruction = "You are a world-class professional resume architect who crafts high-performing resumes tailored to top-tier companies."
        
        try:
            res_text = call_gemini(prompt, system_instruction=system_instruction, response_schema=RESUME_RESPONSE_SCHEMA)
            if res_text:
                res_data = json.loads(res_text.strip())
                return jsonify({"data": res_data})
            else:
                return jsonify({"error": "Failed to generate resume text from Gemini."}), 500
        except Exception as e:
            return jsonify({"error": "Gemini API execution error", "details": str(e)}), 500

    @app.route("/api/resume/improve-section", methods=["POST"])
    def api_improve_section():
        body = request.get_json() or {}
        text = body.get("text")
        sec_type = body.get("type", "experience")
        target_role = body.get("targetRole")
        
        if not text:
            return jsonify({"error": "Text is required."}), 400
            
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            fallback = f"• Spearheaded critical {sec_type} initiatives with strict adherence to industry standards.\n• Elevated key deliverables by implementing modern solution paradigms."
            return jsonify({"improvedText": fallback})
            
        prompt = f"""
        You are an expert professional resume editor.
        Improve the following resume section text ({sec_type}) to sound far more executive, impressive, and professional.
        
        Original Text:
        "{text}"

        {f'Target Role context: {target_role}' if target_role else ""}

        Instructions:
        1. Use high-impact active verbs (e.g. Spearheaded, Accelerated, Pioneered).
        2. If experience description, format as 2-3 high-quality professional bullets.
        3. Focus on outcomes, efficiency gains, or technical proficiency.
        4. Return ONLY the polished text block.
        """
        
        try:
            res_text = call_gemini(prompt)
            if res_text:
                return jsonify({"improvedText": res_text.strip()})
            else:
                return jsonify({"error": "Failed to polish text from Gemini."}), 500
        except Exception as e:
            return jsonify({"error": "Gemini API execution error", "details": str(e)}), 500

    @app.route("/api/jobs/match", methods=["POST"])
    def api_jobs_match():
        body = request.get_json() or {}
        resume_data = body.get("resumeData")
        job_listing = body.get("jobListing")
        
        if not resume_data or not job_listing:
            return jsonify({"error": "Resume data and job details are required."}), 400
            
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            import random
            score = random.randint(65, 92)
            co_title = job_listing.get("title", "Job Title")
            co_name = job_listing.get("company", "Company")
            reqs = job_listing.get("requirements", [])
            tech_rec = f", {', '.join(reqs[:2])}" if reqs else ""
            analysis = f"Evaluated resume compatibility against **{co_name} - {co_title}**.\n\n### Strengths:\n• Profile details match general keywords in {co_title}.\n• Experience references core collaborative processes.\n\n### Recommendation:\n• Inject more quantitative achievements.\n• Explicitly mention tech stacks like {tech_rec if tech_rec else 'required systems'}."
            
            return jsonify({
                "matchScore": score,
                "analysis": analysis
            })
            
        prompt = f"""
        Analyze the alignment between the candidate's resume data and the target job description.
        Provide a match score (0-100) and a comprehensive, bulleted assessment in markdown.
        
        RESUME:
        {json.dumps(resume_data, indent=2)}
        
        JOB LISTING:
        {json.dumps(job_listing, indent=2)}

        Return structured JSON matching this schema:
        {{
          "matchScore": number (integer from 0 to 100),
          "analysis": "Markdown string containing: \\n### Alignment Strengths\\n• ...\\n### Skill Gaps / Areas to Improve\\n• ...\\n### Specific recommendations to customize this resume for this job."
        }}
        """
        
        try:
            res_text = call_gemini(prompt, response_schema=MATCH_RESPONSE_SCHEMA)
            if res_text:
                res_data = json.loads(res_text.strip())
                return jsonify(res_data)
            else:
                return jsonify({"error": "Failed to match job with Gemini."}), 500
        except Exception as e:
            return jsonify({"error": "Gemini API execution error", "details": str(e)}), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=3000)
