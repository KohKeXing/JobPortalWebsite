from io import BytesIO
from flask import Flask, jsonify, render_template, request, send_file, session, redirect, url_for, make_response
from datetime import date, datetime, timedelta, timezone
import json
import os
import secrets
from urllib.parse import urlparse

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
CURRENT_YEAR = date.today().year
COMPANY_MEDIA_BUCKET = "company-media"
MAX_COMPANY_IMAGE_BYTES = 5 * 1024 * 1024
MAX_COMPANY_GALLERY_IMAGES = 6
MALAYSIA_TIMEZONE = timezone(timedelta(hours=8))
JOB_CONTROL_TABLE = "employer_job_controls"
INTERVIEW_TABLE = "employer_interviews"
NOTIFICATION_TABLE = "employer_notifications"
JOB_LIFECYCLE_STATUSES = {"draft", "published", "closed", "archived"}
INTERVIEW_TYPES = {"online", "physical", "phone"}
INTERVIEW_STATUSES = {"scheduled", "completed", "cancelled", "no_show"}
ALLOWED_COMPANY_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
EMPLOYER_PROFILE_FIELDS = (
    "id,user_id,employer_id,company_name,company_email,logo_url,logo_path,"
    "company_background,industry,company_size,location,website,founded_year,"
    "benefits,gallery,created_at,updated_at"
)
COMPANY_SIZE_OPTIONS = {
    "1-10 employees",
    "11-50 employees",
    "51-200 employees",
    "201-500 employees",
    "501-1000 employees",
    "1001-5000 employees",
    "5001+ employees",
}

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
        response = (
            admin.table("employers")
            .select(EMPLOYER_PROFILE_FIELDS)
            .eq("employer_id", employer_id.upper())
            .limit(1)
            .execute()
        )
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
            .select(EMPLOYER_PROFILE_FIELDS)
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


def _normalise_gallery(value):
    """Return gallery data as a safe list of {url, path} objects."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            value = []
    if not isinstance(value, list):
        return []

    gallery = []
    for item in value:
        if isinstance(item, str) and item:
            gallery.append({"url": item, "path": ""})
        elif isinstance(item, dict) and item.get("url"):
            gallery.append({
                "url": str(item.get("url")),
                "path": str(item.get("path") or ""),
            })
    return gallery[:MAX_COMPANY_GALLERY_IMAGES]


def _normalise_company_size(value):
    """Convert display/legacy employee ranges to one database-safe format."""
    text = str(value or "").strip()
    if not text:
        return ""

    text = (
        text.replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace(",", "")
    )
    text = " ".join(text.split()).lower()
    text = text.replace(" - ", "-").replace("- ", "-").replace(" -", "-")
    if not text.endswith(" employees"):
        text = f"{text} employees"
    return text if text in COMPANY_SIZE_OPTIONS else ""


def _serialise_employer(
    employer,
    include_account_email=True,
    include_storage_paths=False,
):
    gallery = _normalise_gallery(employer.get("gallery"))
    if not include_storage_paths:
        gallery = [{"url": item["url"]} for item in gallery]
    profile = {
        "employer_id": employer.get("employer_id") or "",
        "company_name": employer.get("company_name") or "",
        "logo_url": employer.get("logo_url") or "",
        "company_background": employer.get("company_background") or "",
        "industry": employer.get("industry") or "",
        "company_size": (
            _normalise_company_size(employer.get("company_size"))
            or employer.get("company_size")
            or ""
        ),
        "location": employer.get("location") or "",
        "website": employer.get("website") or "",
        "founded_year": employer.get("founded_year"),
        "benefits": employer.get("benefits") or "",
        "gallery": gallery,
        "created_at": employer.get("created_at"),
        "updated_at": employer.get("updated_at"),
    }
    if include_account_email:
        profile["company_email"] = employer.get("company_email") or ""
    return profile


def _public_storage_url(bucket, storage_path):
    result = bucket.get_public_url(storage_path)
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        data = result.get("data") if isinstance(result.get("data"), dict) else result
        return data.get("publicUrl") or data.get("public_url") or ""
    return ""


def _upload_company_image(admin, image, user_id, image_kind):
    if not image or not image.filename:
        raise ValueError("Please choose an image to upload.")

    mime_type = str(image.mimetype or "").lower()
    extension = ALLOWED_COMPANY_IMAGE_TYPES.get(mime_type)
    if not extension:
        raise ValueError("Only JPG, PNG, and WEBP images are allowed.")

    content = image.read(MAX_COMPANY_IMAGE_BYTES + 1)
    if not content:
        raise ValueError("The selected image is empty.")
    if len(content) > MAX_COMPANY_IMAGE_BYTES:
        raise ValueError("Each company image must be 5 MB or smaller.")

    storage_path = (
        f"{user_id}/{image_kind}-{secrets.token_hex(12)}.{extension}"
    )
    bucket = admin.storage.from_(COMPANY_MEDIA_BUCKET)
    bucket.upload(
        storage_path,
        content,
        file_options={
            "content-type": mime_type,
            "cache-control": "3600",
            "upsert": "false",
        },
    )
    public_url = _public_storage_url(bucket, storage_path)
    if not public_url:
        bucket.remove([storage_path])
        raise RuntimeError("Unable to create a public URL for the image.")
    return {"url": public_url, "path": storage_path}


def _remove_company_image(admin, storage_path):
    if not storage_path:
        return
    try:
        admin.storage.from_(COMPANY_MEDIA_BUCKET).remove([storage_path])
    except Exception:
        # A missing old image must not prevent the profile from being saved.
        pass


def _parse_date(value):
    """Parse an ISO date value and return None for an empty value."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError("Application deadline must be a valid date.") from exc


def _normalise_deadline(value):
    deadline = _parse_date(value)
    if deadline and deadline < date.today():
        raise ValueError("Application deadline cannot be in the past.")
    return deadline.isoformat() if deadline else None


def _parse_interview_datetime(value):
    if not value:
        raise ValueError("Interview date and time are required.")
    try:
        interview_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Interview date and time are invalid.") from exc
    if interview_at.tzinfo is None:
        interview_at = interview_at.replace(tzinfo=MALAYSIA_TIMEZONE)
    interview_at = interview_at.astimezone(MALAYSIA_TIMEZONE)
    if interview_at <= datetime.now(MALAYSIA_TIMEZONE):
        raise ValueError("Interview date and time must be in the future.")
    return interview_at


def _job_controls_by_id(admin, user_id, job_ids):
    job_ids = [str(job_id) for job_id in job_ids if job_id]
    if not job_ids:
        return {}
    try:
        response = (
            admin.table(JOB_CONTROL_TABLE)
            .select("job_id,lifecycle_status,application_deadline,published_at,closed_at,archived_at,updated_at")
            .eq("employer_user_id", user_id)
            .in_("job_id", job_ids)
            .execute()
        )
        return {str(row["job_id"]): row for row in (response.data or [])}
    except Exception:
        # Existing job CRUD stays available until the one-time migration is run.
        return {}


def _decorate_jobs(jobs, user_id):
    safe_jobs = [dict(job) for job in (jobs or [])]
    admin = get_supabase_admin_client()
    controls = _job_controls_by_id(
        admin,
        user_id,
        [job.get("id") for job in safe_jobs],
    )
    today = date.today()
    for job in safe_jobs:
        control = controls.get(str(job.get("id")), {})
        stored_status = str(control.get("lifecycle_status") or "published").lower()
        deadline = _parse_date(control.get("application_deadline"))
        effective_status = stored_status
        if stored_status == "published" and deadline and deadline < today:
            effective_status = "expired"
        job["lifecycleStatus"] = effective_status
        job["storedLifecycleStatus"] = stored_status
        job["applicationDeadline"] = deadline.isoformat() if deadline else ""
    return safe_jobs


def _upsert_job_control(admin, user_id, job_id, lifecycle_status, deadline):
    status = str(lifecycle_status or "published").strip().lower()
    if status not in JOB_LIFECYCLE_STATUSES:
        raise ValueError(
            "Job status must be Draft, Published, Closed, or Archived."
        )
    deadline_value = _normalise_deadline(deadline)
    now = datetime.now(MALAYSIA_TIMEZONE).isoformat()
    payload = {
        "job_id": str(job_id),
        "employer_user_id": user_id,
        "lifecycle_status": status,
        "application_deadline": deadline_value,
        "updated_at": now,
    }
    if status == "published":
        payload["published_at"] = now
    elif status == "closed":
        payload["closed_at"] = now
    elif status == "archived":
        payload["archived_at"] = now
    response = (
        admin.table(JOB_CONTROL_TABLE)
        .upsert(payload, on_conflict="employer_user_id,job_id")
        .execute()
    )
    if not response.data:
        raise RuntimeError("Unable to save job lifecycle information.")
    return response.data[0]


def _application_user_id(application):
    for key in (
        "ownerKey", "owner_key",
        "userId", "user_id", "applicantId", "applicant_id", "seekerId",
        "seeker_id",
    ):
        value = application.get(key)
        if value:
            return str(value)
    return ""


def _application_candidate_name(application):
    for key in (
        "candidateName",
        "applicantName",
        "fullName",
        "full_name",
        "name",
    ):
        value = str(application.get(key) or "").strip()
        if value:
            return value
    return "Applicant"


def _resume_candidate_name(application):
    """Best-effort name for applications created before owner_key existed."""
    resume_id = application.get("resumeId") or application.get("resume_id")
    if not resume_id:
        return ""
    try:
        resume = resume_store.get_resume(resume_id) or {}
        data = resume.get("data") if isinstance(resume.get("data"), dict) else {}
        personal_info = (
            data.get("personalInfo")
            if isinstance(data.get("personalInfo"), dict)
            else {}
        )
        return str(personal_info.get("name") or "").strip()
    except Exception:
        return ""


def _serialise_interview(row):
    if not row:
        return None
    return {
        "id": str(row.get("id") or ""),
        "applicationId": str(row.get("application_id") or ""),
        "jobId": str(row.get("job_id") or ""),
        "interviewAt": row.get("interview_at"),
        "interviewType": row.get("interview_type") or "online",
        "locationOrLink": row.get("location_or_link") or "",
        "notes": row.get("notes") or "",
        "status": row.get("status") or "scheduled",
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _enrich_applications(applications, user_id):
    enriched = [dict(application) for application in (applications or [])]
    if not enriched:
        return enriched

    admin = get_supabase_admin_client()
    user_ids = sorted({
        _application_user_id(application)
        for application in enriched
        if _application_user_id(application)
    })
    profile_names = {}
    if user_ids:
        for identity_column in ("id", "user_id"):
            try:
                response = (
                    admin.table("profiles")
                    .select(f"{identity_column},full_name")
                    .in_(identity_column, user_ids)
                    .execute()
                )
                profile_names = {
                    str(row.get(identity_column)): str(
                        row.get("full_name") or ""
                    ).strip()
                    for row in (response.data or [])
                }
                if profile_names:
                    break
            except Exception:
                continue

        # Some projects keep the registered name only in Supabase Auth
        # metadata instead of public.profiles.  Use that as a second source so
        # the employer always sees the job seeker's registered name.
        for seeker_user_id in user_ids:
            if profile_names.get(seeker_user_id):
                continue
            try:
                auth_response = admin.auth.admin.get_user_by_id(seeker_user_id)
                auth_user = getattr(auth_response, "user", None)
                metadata = getattr(auth_user, "user_metadata", None) or {}
                registered_name = str(
                    metadata.get("full_name")
                    or metadata.get("name")
                    or ""
                ).strip()
                if registered_name:
                    profile_names[seeker_user_id] = registered_name
            except Exception:
                continue

    try:
        interview_response = (
            admin.table(INTERVIEW_TABLE)
            .select("*")
            .eq("employer_user_id", user_id)
            .execute()
        )
        interviews = {
            str(row.get("application_id")): _serialise_interview(row)
            for row in (interview_response.data or [])
        }
    except Exception:
        interviews = {}

    for application in enriched:
        user_id_value = _application_user_id(application)
        application["candidateName"] = (
            profile_names.get(user_id_value)
            or _resume_candidate_name(application)
            or _application_candidate_name(application)
        )
        application["interview"] = interviews.get(str(application.get("id")))
    return enriched


def _create_notification(
    admin,
    user_id,
    notification_type,
    title,
    message,
    dedupe_key,
    job_id=None,
    application_id=None,
):
    payload = {
        "employer_user_id": user_id,
        "notification_type": notification_type,
        "title": str(title)[:160],
        "message": str(message)[:500],
        "dedupe_key": str(dedupe_key)[:240],
        "related_job_id": str(job_id) if job_id else None,
        "related_application_id": (
            str(application_id) if application_id else None
        ),
    }
    admin.table(NOTIFICATION_TABLE).upsert(
        payload,
        on_conflict="employer_user_id,dedupe_key",
        ignore_duplicates=True,
    ).execute()


def _sync_employer_notifications(admin, user_id, jobs, applications):
    jobs_by_id = {str(job.get("id")): job for job in jobs}
    for application in applications:
        app_id = str(application.get("id") or "")
        if not app_id:
            continue
        job_id = str(application.get("jobId") or "")
        job = jobs_by_id.get(job_id, {})
        candidate = _application_candidate_name(application)
        job_title = job.get("title") or application.get("job") or "a job"
        _create_notification(
            admin,
            user_id,
            "new_application",
            "New application received",
            f"{candidate} applied for {job_title}.",
            f"application:{app_id}",
            job_id=job_id,
            application_id=app_id,
        )

    today = date.today()
    for job in jobs:
        deadline = _parse_date(job.get("applicationDeadline"))
        days_remaining = (deadline - today).days if deadline else None
        if job.get("lifecycleStatus") == "published" and days_remaining is not None and 0 <= days_remaining <= 3:
            job_id = str(job.get("id") or "")
            _create_notification(
                admin,
                user_id,
                "job_deadline",
                "Job deadline approaching",
                f"{job.get('title') or 'A job'} closes in {days_remaining} day(s).",
                f"deadline:{job_id}:{deadline.isoformat()}",
                job_id=job_id,
            )

    now = datetime.now(MALAYSIA_TIMEZONE)
    for application in applications:
        interview = application.get("interview") or {}
        if interview.get("status") != "scheduled" or not interview.get("interviewAt"):
            continue
        try:
            interview_at = datetime.fromisoformat(
                str(interview["interviewAt"]).replace("Z", "+00:00")
            ).astimezone(MALAYSIA_TIMEZONE)
        except (TypeError, ValueError):
            continue
        if now <= interview_at <= now + timedelta(hours=24):
            _create_notification(
                admin,
                user_id,
                "interview_reminder",
                "Interview reminder",
                f"Interview with {_application_candidate_name(application)} is within 24 hours.",
                f"interview-reminder:{interview.get('id')}:{interview_at.date().isoformat()}",
                job_id=application.get("jobId"),
                application_id=application.get("id"),
            )

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

        employer = get_employer_by_user_id(session["auth_user_id"])
        if employer:
            session["employer_id"] = employer.get("employer_id")
            session["company_name"] = employer.get("company_name")
            session["company_email"] = employer.get("company_email")

        company_name = str(session.get("company_name") or "Employer").strip()
        company_email = str(session.get("company_email") or "").strip()
        company_logo_url = str(
            (employer or {}).get("logo_url") or ""
        ).strip()
        employer_id = str(session.get("employer_id") or "").strip()
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
            company_logo_url=company_logo_url,
            employer_id=employer_id,
        )

    @app.route("/companies/<employer_id>")
    def company_profile_page(employer_id):
        employer = get_employer_from_db(employer_id)
        if not employer:
            return "Company profile not found.", 404

        can_edit = bool(
            session.get("role") == "employer"
            and session.get("auth_user_id") == employer.get("user_id")
        )
        return render_template(
            "company_profile.html",
            employer_id=employer.get("employer_id"),
            can_edit=can_edit,
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

            # Supabase assigns a concurrency-safe ID such as EMP001 using the
            # default created by company_profile_migration.sql.
            auth_user_id = str(response.user.id)

            # Store the application role in the shared profiles table.
            admin.table("profiles").upsert({
                "id": auth_user_id,
                "full_name": company_name,
                "role": "employer"
            }, on_conflict="id").execute()

            # Supabase Auth stores the password. Keep a random legacy api_key
            # only because existing database schemas may require this column.
            employer_response = admin.table("employers").insert({
                "user_id": auth_user_id,
                "company_name": company_name,
                "company_email": email,
                "api_key": secrets.token_urlsafe(32)
            }).execute()
            if not employer_response.data:
                raise RuntimeError("The employer profile could not be created.")
            employer_id = employer_response.data[0].get("employer_id")
            if not employer_id:
                raise RuntimeError("The employer ID was not generated.")

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
    # EMPLOYER PROFILE
    # =============================================================
    @app.route("/employer/company-profile")
    @employer_required
    def employer_company_profile_redirect():
        """Open the signed-in employer's editable public company page."""
        employer = get_employer_by_user_id(session["auth_user_id"])
        if not employer or not employer.get("employer_id"):
            return "Employer profile not found.", 404

        employer_id = str(employer["employer_id"]).upper()
        session["employer_id"] = employer_id
        return redirect(url_for(
            "company_profile_page",
            employer_id=employer_id,
        ))

    @app.route("/api/employer/profile", methods=["GET"])
    @employer_required
    def get_employer_profile():
        employer = get_employer_by_user_id(session["auth_user_id"])
        if not employer:
            return jsonify({"error": "Employer profile not found."}), 404
        return jsonify(_serialise_employer(
            employer,
            include_account_email=True,
            include_storage_paths=True,
        )), 200

    @app.route("/api/employer/profile", methods=["PUT"])
    @employer_required
    def update_employer_profile():
        return jsonify({
            "error": (
                "Company name cannot be changed after employer registration. "
                "Only the company logo can be updated from the employer profile."
            )
        }), 403

    @app.route("/api/employer/profile/logo", methods=["POST"])
    @employer_required
    def upload_employer_logo():
        image = request.files.get("logo")
        user_id = session["auth_user_id"]
        employer = get_employer_by_user_id(user_id)
        if not employer:
            return jsonify({"error": "Employer profile not found."}), 404

        admin = get_supabase_admin_client()
        uploaded = None
        try:
            uploaded = _upload_company_image(admin, image, user_id, "logo")
            response = (
                admin.table("employers")
                .update({
                    "logo_url": uploaded["url"],
                    "logo_path": uploaded["path"],
                })
                .eq("user_id", user_id)
                .execute()
            )
            if not response.data:
                raise RuntimeError("Employer profile not found.")

            _remove_company_image(admin, employer.get("logo_path"))
            updated = get_employer_by_user_id(user_id) or response.data[0]
            return jsonify({
                "success": True,
                "message": "Company logo updated successfully.",
                "profile": _serialise_employer(
                    updated,
                    include_account_email=True,
                    include_storage_paths=True,
                ),
            }), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            if uploaded:
                _remove_company_image(admin, uploaded.get("path"))
            app.logger.exception("Company logo upload failed")
            return jsonify({
                "error": "Unable to upload the company logo. Please try again."
            }), 500

    # =============================================================
    # PUBLIC / EDITABLE COMPANY PAGE
    # =============================================================
    @app.route("/api/companies/<employer_id>", methods=["GET"])
    def get_public_company_profile(employer_id):
        employer = get_employer_from_db(employer_id)
        if not employer:
            return jsonify({"error": "Company profile not found."}), 404
        return jsonify(_serialise_employer(
            employer,
            include_account_email=True,
            include_storage_paths=False,
        )), 200

    @app.route("/api/employer/company-profile", methods=["PUT"])
    @employer_required
    def update_company_profile():
        data = request.get_json(silent=True) or {}
        text_fields = {
            "company_background": 3000,
            "industry": 100,
            "location": 150,
            "website": 300,
            "benefits": 2000,
        }
        updates = {}
        for field, max_length in text_fields.items():
            value = str(data.get(field) or "").strip()
            if len(value) > max_length:
                label = field.replace("_", " ").capitalize()
                return jsonify({
                    "error": f"{label} must be {max_length} characters or fewer."
                }), 400
            updates[field] = value

        company_size_input = str(data.get("company_size") or "").strip()
        company_size = _normalise_company_size(company_size_input)
        if company_size_input and not company_size:
            return jsonify({
                "error": "Please select a valid company size."
            }), 400
        updates["company_size"] = company_size or None

        website = updates["website"]
        if website:
            parsed_website = urlparse(website)
            if parsed_website.scheme not in {"http", "https"} or not parsed_website.netloc:
                return jsonify({
                    "error": "Website must be a complete URL starting with http:// or https://."
                }), 400

        founded_year = data.get("founded_year")
        if founded_year in (None, ""):
            updates["founded_year"] = None
        else:
            try:
                founded_year = int(founded_year)
            except (TypeError, ValueError):
                return jsonify({"error": "Founded year must be a number."}), 400
            if founded_year < 1800 or founded_year > CURRENT_YEAR:
                return jsonify({
                    "error": f"Founded year must be between 1800 and {CURRENT_YEAR}."
                }), 400
            updates["founded_year"] = founded_year

        user_id = session["auth_user_id"]
        employer = get_employer_by_user_id(user_id)
        if not employer:
            return jsonify({"error": "Employer profile not found."}), 404

        try:
            admin = get_supabase_admin_client()
            update_query = admin.table("employers").update(updates)

            # Target the exact employer row. Some older records can contain a
            # legacy or differently formatted user_id, while the primary row
            # id remains stable.
            if employer.get("id"):
                update_query = update_query.eq("id", employer["id"])
            else:
                update_query = update_query.eq("user_id", user_id)

            response = update_query.execute()

            # Supabase/PostgREST can legitimately return an empty data array
            # after a successful UPDATE. Re-read the record instead of treating
            # an empty representation as a failed save.
            updated = get_employer_by_user_id(user_id)
            if not updated and getattr(response, "data", None):
                updated = response.data[0]
            if not updated:
                return jsonify({
                    "error": "The company was updated, but the profile could not be reloaded. Please refresh the page."
                }), 500

            return jsonify({
                "success": True,
                "message": "Company page updated successfully.",
                "profile": _serialise_employer(
                    updated,
                    include_account_email=True,
                    include_storage_paths=False,
                ),
            }), 200
        except Exception as exc:
            app.logger.exception("Company page update failed")
            detail = str(exc).strip()
            detail_lower = detail.lower()

            if "employers_company_size_check" in detail_lower:
                message = (
                    "The company-size database rule is outdated. "
                    "Run company_size_constraint_fix.sql in the Supabase SQL Editor, then save again."
                )
            elif "schema cache" in detail_lower or "could not find" in detail_lower:
                message = (
                    "The company profile database columns are missing or Supabase has not reloaded its schema. "
                    "Run company_profile_migration.sql in the Supabase SQL Editor, then restart Flask."
                )
            elif "row-level security" in detail_lower or "permission denied" in detail_lower:
                message = (
                    "Supabase denied the update. Check that SUPABASE_SERVICE_ROLE_KEY is configured in the Flask server."
                )
            elif "invalid input syntax" in detail_lower and "integer" in detail_lower:
                message = (
                    "A company profile database column has the wrong data type. Run the latest company profile SQL migration."
                )
            else:
                message = "Unable to update the company page. Please try again."

            return jsonify({
                "error": message
            }), 500

    @app.route("/api/employer/company-gallery", methods=["POST"])
    @employer_required
    def upload_company_gallery():
        images = [image for image in request.files.getlist("images") if image.filename]
        if not images:
            return jsonify({"error": "Please choose at least one image."}), 400

        user_id = session["auth_user_id"]
        employer = get_employer_by_user_id(user_id)
        if not employer:
            return jsonify({"error": "Employer profile not found."}), 404

        current_gallery = _normalise_gallery(employer.get("gallery"))
        available_slots = MAX_COMPANY_GALLERY_IMAGES - len(current_gallery)
        if available_slots <= 0:
            return jsonify({
                "error": f"The company gallery can contain up to {MAX_COMPANY_GALLERY_IMAGES} images."
            }), 400
        if len(images) > available_slots:
            return jsonify({
                "error": f"You can upload {available_slots} more gallery image(s)."
            }), 400

        admin = get_supabase_admin_client()
        uploaded = []
        try:
            for image in images:
                uploaded.append(_upload_company_image(
                    admin,
                    image,
                    user_id,
                    "gallery",
                ))
            new_gallery = current_gallery + uploaded
            response = (
                admin.table("employers")
                .update({"gallery": new_gallery})
                .eq("user_id", user_id)
                .execute()
            )
            if not response.data:
                raise RuntimeError("Employer profile not found.")
            updated = get_employer_by_user_id(user_id) or response.data[0]
            return jsonify({
                "success": True,
                "message": "Gallery updated successfully.",
                "profile": _serialise_employer(
                    updated,
                    include_account_email=True,
                    include_storage_paths=False,
                ),
            }), 200
        except ValueError as exc:
            for item in uploaded:
                _remove_company_image(admin, item.get("path"))
            return jsonify({"error": str(exc)}), 400
        except Exception:
            for item in uploaded:
                _remove_company_image(admin, item.get("path"))
            app.logger.exception("Company gallery upload failed")
            return jsonify({
                "error": "Unable to upload the gallery images. Please try again."
            }), 500

    @app.route("/api/employer/company-gallery", methods=["DELETE"])
    @employer_required
    def delete_company_gallery_image():
        data = request.get_json(silent=True) or {}
        image_url = str(data.get("url") or "").strip()
        if not image_url:
            return jsonify({"error": "Gallery image URL is required."}), 400

        user_id = session["auth_user_id"]
        employer = get_employer_by_user_id(user_id)
        if not employer:
            return jsonify({"error": "Employer profile not found."}), 404

        gallery = _normalise_gallery(employer.get("gallery"))
        target = next((item for item in gallery if item.get("url") == image_url), None)
        if not target:
            return jsonify({"error": "Gallery image not found."}), 404

        new_gallery = [item for item in gallery if item.get("url") != image_url]
        try:
            admin = get_supabase_admin_client()
            response = (
                admin.table("employers")
                .update({"gallery": new_gallery})
                .eq("user_id", user_id)
                .execute()
            )
            if not response.data:
                return jsonify({"error": "Employer profile not found."}), 404
            _remove_company_image(admin, target.get("path"))
            updated = get_employer_by_user_id(user_id) or response.data[0]
            return jsonify({
                "success": True,
                "message": "Gallery image removed.",
                "profile": _serialise_employer(
                    updated,
                    include_account_email=True,
                    include_storage_paths=False,
                ),
            }), 200
        except Exception:
            app.logger.exception("Company gallery deletion failed")
            return jsonify({
                "error": "Unable to remove the gallery image. Please try again."
            }), 500

    # =============================================================
    # JOB POSTING CRUD
    # =============================================================
    @app.route("/api/jobs", methods=["GET"])
    @employer_required
    def get_jobs():
        user_id = session["auth_user_id"]
        return jsonify(_decorate_jobs(job_store.get_jobs(user_id), user_id))

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    @employer_required
    def get_job(job_id):
        user_id = session["auth_user_id"]
        job = job_store.get_job(job_id, user_id)
        if job:
            return jsonify(_decorate_jobs([job], user_id)[0])
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs", methods=["POST"])
    @employer_required
    def create_job():
        data = request.get_json() or {}
        lifecycle_status = data.pop("lifecycleStatus", "published")
        application_deadline = data.pop("applicationDeadline", None)
        data["company"] = session.get("company_name") or ""
        missing = [f for f in REQUIRED_JOB_FIELDS if not data.get(f)]
        if missing:
            return jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400
        try:
            user_id = session["auth_user_id"]
            new_job = job_store.create_job(data, user_id)
            try:
                _upsert_job_control(
                    get_supabase_admin_client(),
                    user_id,
                    new_job["id"],
                    lifecycle_status,
                    application_deadline,
                )
            except Exception:
                job_store.delete_job(new_job["id"], user_id)
                raise
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Job creation failed")
            message = str(exc) if app.debug else (
                "The database rejected the job. Run the employer recruitment "
                "features SQL migration if it has not been installed."
            )
            return jsonify({"error": f"Failed to save job: {message}"}), 500
        return jsonify(_decorate_jobs([new_job], user_id)[0]), 201

    @app.route("/api/jobs/<job_id>", methods=["PUT"])
    @employer_required
    def update_job(job_id):
        data = request.get_json() or {}
        lifecycle_status = data.pop("lifecycleStatus", "published")
        application_deadline = data.pop("applicationDeadline", None)
        data["company"] = session.get("company_name") or ""
        try:
            user_id = session["auth_user_id"]
            job = job_store.update_job(
                job_id,
                data,
                user_id,
            )
            if job:
                _upsert_job_control(
                    get_supabase_admin_client(),
                    user_id,
                    job_id,
                    lifecycle_status,
                    application_deadline,
                )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            app.logger.exception("Job update failed")
            message = str(exc) if app.debug else "The database rejected the update."
            return jsonify({"error": f"Failed to update job: {message}"}), 500
        if job:
            return jsonify(_decorate_jobs([job], user_id)[0])
        return jsonify({"error": "Job not found"}), 404

    @app.route("/api/jobs/<job_id>/lifecycle", methods=["PATCH"])
    @employer_required
    def update_job_lifecycle(job_id):
        user_id = session["auth_user_id"]
        job = job_store.get_job(job_id, user_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        data = request.get_json(silent=True) or {}
        lifecycle_status = str(data.get("status") or "").strip().lower()
        if lifecycle_status not in JOB_LIFECYCLE_STATUSES:
            return jsonify({
                "error": "Status must be Draft, Published, Closed, or Archived."
            }), 400

        decorated_job = _decorate_jobs([job], user_id)[0]
        deadline_supplied = "applicationDeadline" in data
        deadline = (
            data.get("applicationDeadline")
            if deadline_supplied
            else decorated_job.get("applicationDeadline")
        )
        reopened_expired_job = (
            decorated_job.get("lifecycleStatus") == "expired"
            and lifecycle_status == "published"
            and not deadline_supplied
        )
        if reopened_expired_job:
            deadline = None

        try:
            _upsert_job_control(
                get_supabase_admin_client(),
                user_id,
                job_id,
                lifecycle_status,
                deadline,
            )
            updated_job = _decorate_jobs([job], user_id)[0]
            return jsonify({
                "success": True,
                "message": (
                    "Job reopened and the expired deadline was cleared."
                    if reopened_expired_job
                    else f"Job status changed to {lifecycle_status.title()}."
                ),
                "job": updated_job,
            }), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            app.logger.exception("Job lifecycle update failed")
            return jsonify({
                "error": (
                    "Unable to update the job status. Run the employer "
                    "recruitment features SQL migration first."
                )
            }), 500

    @app.route("/api/jobs/<job_id>/duplicate", methods=["POST"])
    @employer_required
    def duplicate_job(job_id):
        user_id = session["auth_user_id"]
        original = job_store.get_job(job_id, user_id)
        if not original:
            return jsonify({"error": "Job not found"}), 404

        duplicate_data = {
            key: original.get(key)
            for key in (
                "title", "company", "location", "salary", "type",
                "description", "category", "tags", "featured",
            )
        }
        duplicate_data["title"] = f"{str(original.get('title') or 'Job').strip()} Copy"
        duplicate_data["company"] = session.get("company_name") or ""
        try:
            duplicate = job_store.create_job(duplicate_data, user_id)
            try:
                _upsert_job_control(
                    get_supabase_admin_client(),
                    user_id,
                    duplicate["id"],
                    "draft",
                    None,
                )
            except Exception:
                job_store.delete_job(duplicate["id"], user_id)
                raise
            return jsonify(_decorate_jobs([duplicate], user_id)[0]), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            app.logger.exception("Job duplication failed")
            return jsonify({"error": "Unable to duplicate this job."}), 500

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
            try:
                admin = get_supabase_admin_client()
                admin.table(JOB_CONTROL_TABLE).delete().eq(
                    "employer_user_id", employer_id
                ).eq("job_id", str(job_id)).execute()
                admin.table(INTERVIEW_TABLE).delete().eq(
                    "employer_user_id", employer_id
                ).eq("job_id", str(job_id)).execute()
            except Exception:
                app.logger.warning(
                    "Job deleted but recruitment metadata cleanup was skipped",
                    exc_info=True,
                )
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
        user_id = session["auth_user_id"]
        owned_job_ids = {
            job["id"] for job in job_store.get_jobs(user_id)
        }
        applications = [
            application
            for application in app_tracker.get_applications()
            if application.get("jobId") in owned_job_ids
        ]
        return jsonify(_enrich_applications(applications, user_id))

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
            try:
                admin = get_supabase_admin_client()
                if new_status != "Interview":
                    (
                        admin.table(INTERVIEW_TABLE)
                        .update({
                            "status": "cancelled",
                            "updated_at": datetime.now(
                                MALAYSIA_TIMEZONE
                            ).isoformat(),
                        })
                        .eq("employer_user_id", session["auth_user_id"])
                        .eq("application_id", str(app_id))
                        .eq("status", "scheduled")
                        .execute()
                    )
                job = job_store.get_job(
                    application_job_id,
                    session["auth_user_id"],
                ) or {}
                candidate = _enrich_applications(
                    [application], session["auth_user_id"]
                )[0]["candidateName"]
                _create_notification(
                    admin,
                    session["auth_user_id"],
                    "status_update",
                    "Applicant status updated",
                    f"{candidate} was moved to {new_status} for {job.get('title') or 'a job'}.",
                    f"status:{app_id}:{new_status}:{datetime.now(MALAYSIA_TIMEZONE).isoformat()}",
                    job_id=application_job_id,
                    application_id=app_id,
                )
            except Exception:
                app.logger.exception("Status notification creation failed")
            return jsonify({"success": True}), 200
        return jsonify({"error": "Application not found"}), 404

    @app.route("/api/applications/<app_id>/interview", methods=["POST"])
    @employer_required
    def schedule_interview(app_id):
        user_id = session["auth_user_id"]
        application = app_tracker.get_application(app_id)
        job_id = application.get("jobId") if application else None
        job = job_store.get_job(job_id, user_id) if job_id else None
        if not application or not job:
            return jsonify({"error": "Application not found"}), 404
        if application.get("status") != "Interview":
            return jsonify({
                "error": (
                    "Change the applicant status to Interview before "
                    "scheduling a meeting."
                )
            }), 409

        data = request.get_json(silent=True) or {}
        interview_type = str(data.get("interviewType") or "").strip().lower()
        location_or_link = str(data.get("locationOrLink") or "").strip()
        notes = str(data.get("notes") or "").strip()
        if interview_type not in INTERVIEW_TYPES:
            return jsonify({
                "error": "Interview type must be Online, Physical, or Phone."
            }), 400
        if not location_or_link:
            return jsonify({
                "error": "Please provide the meeting link, location, or phone details."
            }), 400
        if len(location_or_link) > 500 or len(notes) > 2000:
            return jsonify({
                "error": "Interview location or notes are too long."
            }), 400

        try:
            interview_at = _parse_interview_datetime(data.get("interviewAt"))
            now = datetime.now(MALAYSIA_TIMEZONE).isoformat()
            response = (
                get_supabase_admin_client()
                .table(INTERVIEW_TABLE)
                .upsert({
                    "employer_user_id": user_id,
                    "application_id": str(app_id),
                    "job_id": str(job_id),
                    "interview_at": interview_at.isoformat(),
                    "interview_type": interview_type,
                    "location_or_link": location_or_link,
                    "notes": notes,
                    "status": "scheduled",
                    "updated_at": now,
                }, on_conflict="employer_user_id,application_id")
                .execute()
            )
            if not response.data:
                raise RuntimeError("Interview was not saved.")

            candidate = _enrich_applications(
                [application], user_id
            )[0]["candidateName"]
            _create_notification(
                get_supabase_admin_client(),
                user_id,
                "interview_scheduled",
                "Interview scheduled",
                f"Interview with {candidate} is scheduled for {interview_at.strftime('%d %b %Y, %I:%M %p')}.",
                f"interview-scheduled:{app_id}:{interview_at.isoformat()}",
                job_id=job_id,
                application_id=app_id,
            )
            return jsonify({
                "success": True,
                "message": "Interview scheduled successfully.",
                "interview": _serialise_interview(response.data[0]),
            }), 200
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            app.logger.exception("Interview scheduling failed")
            return jsonify({
                "error": (
                    "Unable to schedule the interview. Run the employer "
                    "recruitment features SQL migration first."
                )
            }), 500

    @app.route("/api/applications/<app_id>/interview", methods=["DELETE"])
    @employer_required
    def cancel_interview(app_id):
        user_id = session["auth_user_id"]
        application = app_tracker.get_application(app_id)
        job_id = application.get("jobId") if application else None
        if not application or not job_id or not job_store.get_job(job_id, user_id):
            return jsonify({"error": "Application not found"}), 404
        try:
            response = (
                get_supabase_admin_client()
                .table(INTERVIEW_TABLE)
                .update({
                    "status": "cancelled",
                    "updated_at": datetime.now(MALAYSIA_TIMEZONE).isoformat(),
                })
                .eq("employer_user_id", user_id)
                .eq("application_id", str(app_id))
                .execute()
            )
            if not response.data:
                return jsonify({"error": "Scheduled interview not found"}), 404
            return jsonify({
                "success": True,
                "message": "Interview cancelled.",
                "interview": _serialise_interview(response.data[0]),
            }), 200
        except Exception:
            app.logger.exception("Interview cancellation failed")
            return jsonify({"error": "Unable to cancel the interview."}), 500

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
    # EMPLOYER NOTIFICATIONS
    # =============================================================
    @app.route("/api/employer/notifications", methods=["GET"])
    @employer_required
    def get_employer_notifications():
        user_id = session["auth_user_id"]
        try:
            jobs = _decorate_jobs(job_store.get_jobs(user_id), user_id)
            owned_job_ids = {job.get("id") for job in jobs}
            applications = _enrich_applications([
                application
                for application in app_tracker.get_applications()
                if application.get("jobId") in owned_job_ids
            ], user_id)
            admin = get_supabase_admin_client()
            _sync_employer_notifications(admin, user_id, jobs, applications)
            response = (
                admin.table(NOTIFICATION_TABLE)
                .select("id,notification_type,title,message,related_job_id,related_application_id,is_read,created_at")
                .eq("employer_user_id", user_id)
                .order("created_at", desc=True)
                .limit(50)
                .execute()
            )
            return jsonify(response.data or []), 200
        except Exception:
            app.logger.exception("Employer notifications failed")
            return jsonify({
                "error": (
                    "Unable to load notifications. Run the employer recruitment "
                    "features SQL migration first."
                )
            }), 500

    @app.route("/api/employer/notifications/<notification_id>/read", methods=["PUT"])
    @employer_required
    def mark_employer_notification_read(notification_id):
        try:
            response = (
                get_supabase_admin_client()
                .table(NOTIFICATION_TABLE)
                .update({"is_read": True})
                .eq("id", notification_id)
                .eq("employer_user_id", session["auth_user_id"])
                .execute()
            )
            if not response.data:
                return jsonify({"error": "Notification not found"}), 404
            return jsonify({"success": True}), 200
        except Exception:
            return jsonify({"error": "Unable to update notification."}), 500

    @app.route("/api/employer/notifications/read-all", methods=["PUT"])
    @employer_required
    def mark_all_employer_notifications_read():
        try:
            get_supabase_admin_client().table(NOTIFICATION_TABLE).update({
                "is_read": True,
            }).eq("employer_user_id", session["auth_user_id"]).eq(
                "is_read", False
            ).execute()
            return jsonify({"success": True}), 200
        except Exception:
            return jsonify({"error": "Unable to update notifications."}), 500

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
