import base64
import binascii
import json
import os
import re
import urllib.parse
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
from supabase_client import (
    ACCOUNT_NOT_FOUND_MESSAGE,
    EMAIL_RATE_LIMIT_MESSAGE,
    auth_account_exists,
    create_supabase_auth_client,
    get_supabase_admin_client,
    is_email_rate_limit_error,
    password_policy_error,
)

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
                    "description": {"type": "STRING", "description": "Polished, multi-line bullet-pointed description with each bullet starting on a new line with the 'Ã¢â‚¬Â¢ ' character."}
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


PROFILE_AVATAR_MAX_BYTES = 2 * 1024 * 1024
PROFILE_AVATAR_PREFIXES = (
    "data:image/png;base64,",
    "data:image/jpeg;base64,",
    "data:image/webp;base64,",
)
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Mobile/personal phone formats supported by the country selector in dashboard.html.
# Patterns are applied to national digits after an optional domestic leading zero
# has been removed.
PROFILE_PHONE_RULES = {
    "+60": {
        "pattern": re.compile(r"^1\d{8,9}$"),
        "strip_zero": True,
        "message": "Malaysia numbers must contain 10 or 11 digits including the leading 0.",
    },
    "+1": {
        "pattern": re.compile(r"^[2-9]\d{2}[2-9]\d{6}$"),
        "strip_zero": False,
        "message": "United States numbers must contain exactly 10 valid digits.",
    },
    "+44": {
        "pattern": re.compile(r"^7\d{9}$"),
        "strip_zero": True,
        "message": "United Kingdom mobile numbers must contain 11 digits including the leading 0.",
    },
    "+65": {
        "pattern": re.compile(r"^[689]\d{7}$"),
        "strip_zero": False,
        "message": "Singapore numbers must contain exactly 8 valid digits.",
    },
    "+61": {
        "pattern": re.compile(r"^4\d{8}$"),
        "strip_zero": True,
        "message": "Australian mobile numbers must contain 10 digits including the leading 0.",
    },
    "+91": {
        "pattern": re.compile(r"^[6-9]\d{9}$"),
        "strip_zero": False,
        "message": "Indian mobile numbers must contain exactly 10 valid digits.",
    },
    "+62": {
        "pattern": re.compile(r"^8\d{8,11}$"),
        "strip_zero": True,
        "message": "Indonesian mobile numbers must contain 10 to 13 digits including the leading 0.",
    },
    "+81": {
        "pattern": re.compile(r"^(?:70|80|90)\d{8}$"),
        "strip_zero": True,
        "message": "Japanese mobile numbers must contain 11 digits including the leading 0.",
    },
    "+86": {
        "pattern": re.compile(r"^1[3-9]\d{9}$"),
        "strip_zero": False,
        "message": "Chinese mobile numbers must contain exactly 11 valid digits.",
    },
}


def _normalise_spaces(value):
    return " ".join(str(value or "").strip().split())


def _valid_person_name(value):
    return (
        sum(character.isalpha() for character in value) >= 2
        and all(character.isalpha() or character == " " for character in value)
    )


def _normalise_profile_phone(raw_phone, country_code):
    rule = PROFILE_PHONE_RULES.get(country_code)
    if not rule:
        return None, "Please select a supported phone country."

    raw_phone = str(raw_phone or "").strip()
    digits = re.sub(r"\D", "", raw_phone)
    country_digits = country_code.lstrip("+")

    # Accept either a national number or a full number pasted into the field.
    if raw_phone.startswith("+") and digits.startswith(country_digits):
        digits = digits[len(country_digits):]
    if rule["strip_zero"] and digits.startswith("0"):
        digits = digits[1:]

    if not digits or not rule["pattern"].fullmatch(digits):
        return None, rule["message"]
    return f"{country_code} {digits}", None


def _validate_profile_avatar(avatar):
    if avatar is None:
        return None
    if not isinstance(avatar, str) or not avatar.startswith(PROFILE_AVATAR_PREFIXES):
        return "Profile photo must be a PNG, JPG or WEBP image."

    try:
        image_bytes = base64.b64decode(avatar.split(",", 1)[1], validate=True)
    except (IndexError, ValueError, binascii.Error):
        return "Profile photo data is invalid. Please choose the image again."

    if len(image_bytes) > PROFILE_AVATAR_MAX_BYTES:
        return "Profile photo must not exceed 2 MB."

    is_png = image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = image_bytes.startswith(b"\xff\xd8\xff")
    is_webp = (
        len(image_bytes) >= 12
        and image_bytes.startswith(b"RIFF")
        and image_bytes[8:12] == b"WEBP"
    )
    if not (is_png or is_jpeg or is_webp):
        return "Profile photo content is not a valid PNG, JPG or WEBP image."
    return None


def _validate_profile_payload(data):
    errors = {}
    cleaned = {}

    full_name = _normalise_spaces(data.get("full_name"))
    if not full_name:
        errors["full_name"] = "Full name is required."
    elif not 2 <= len(full_name) <= 80:
        errors["full_name"] = "Full name must contain between 2 and 80 characters."
    elif not _valid_person_name(full_name):
        errors["full_name"] = "Full name can contain letters and spaces only."
    else:
        cleaned["full_name"] = full_name

    headline = _normalise_spaces(data.get("headline"))
    if not headline:
        errors["headline"] = "Professional headline is required."
    elif not 3 <= len(headline) <= 120:
        errors["headline"] = "Professional headline must contain between 3 and 120 characters."
    elif CONTROL_CHAR_PATTERN.search(headline) or "<" in headline or ">" in headline:
        errors["headline"] = "Professional headline contains unsupported characters."
    else:
        cleaned["headline"] = headline

    formatted_phone, phone_error = _normalise_profile_phone(
        data.get("phone"), str(data.get("phone_country", "")).strip()
    )
    if phone_error:
        errors["phone"] = phone_error
    else:
        cleaned["phone"] = formatted_phone

    bio = str(data.get("bio", "")).strip()
    if not bio:
        errors["bio"] = "Professional bio is required."
    elif not 20 <= len(bio) <= 1000:
        errors["bio"] = "Professional bio must contain between 20 and 1,000 characters."
    elif CONTROL_CHAR_PATTERN.search(bio) or "<" in bio or ">" in bio:
        errors["bio"] = "Professional bio contains unsupported characters."
    else:
        cleaned["bio"] = bio

    skills = data.get("skills")
    cleaned_skills = []
    seen_skills = set()
    if not isinstance(skills, list):
        errors["skills"] = "Skills must be provided as a list."
    else:
        for raw_skill in skills:
            if not isinstance(raw_skill, str):
                errors["skills"] = "Every skill must be text."
                break
            skill = _normalise_spaces(raw_skill)
            if not skill:
                continue
            if len(skill) > 40:
                errors["skills"] = "Each skill must not exceed 40 characters."
                break
            if (
                CONTROL_CHAR_PATTERN.search(skill)
                or "<" in skill
                or ">" in skill
                or not any(character.isalnum() for character in skill)
            ):
                errors["skills"] = f'Unsupported skill value: "{skill}".'
                break
            key = skill.casefold()
            if key not in seen_skills:
                seen_skills.add(key)
                cleaned_skills.append(skill)

        if "skills" not in errors:
            if not cleaned_skills:
                errors["skills"] = "Enter at least one core skill."
            elif len(cleaned_skills) > 20:
                errors["skills"] = "Enter no more than 20 core skills."
            else:
                cleaned["skills"] = cleaned_skills

    if "avatar" in data:
        avatar = data.get("avatar")
        avatar_error = _validate_profile_avatar(avatar)
        if avatar_error:
            errors["avatar"] = avatar_error
        else:
            cleaned["avatar"] = avatar

    return cleaned, errors

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

    def _normalise_identity(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    def _safe_public_http_url(value):
        """Return only public HTTP(S) URLs that are safe to place in links."""
        candidate = str(value or "").strip()
        if re.match(r"^https?://", candidate, flags=re.IGNORECASE):
            return candidate
        return ""

    def _normalise_public_website_url(value):
        """Build a usable HTTP(S) company link, adding HTTPS when omitted."""
        candidate = str(value or "").strip()
        if not candidate:
            return ""

        if candidate.startswith("//"):
            candidate = f"https:{candidate}"
        elif not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
            candidate = f"https://{candidate.lstrip('/')}"

        try:
            parsed = urllib.parse.urlparse(candidate)
            hostname = str(parsed.hostname or "").strip().lower()
            if (
                parsed.scheme.lower() not in {"http", "https"}
                or not parsed.netloc
                or not hostname
                or "." not in hostname
                or re.search(r"\s", hostname)
                or parsed.username
                or parsed.password
            ):
                return ""
            # Accessing .port also validates malformed values such as
            # "example.com:not-a-port".
            parsed.port
        except (TypeError, ValueError):
            return ""

        return parsed.geturl()

    def _public_company_profile(employer_id):
        """Load and normalise one read-only company profile for job seekers."""
        public_id = str(employer_id or "").strip().upper()
        if not re.fullmatch(r"EMP\d{3,}", public_id):
            return None

        response = (
            get_supabase_admin_client()
            .table("employers")
            .select(
                "employer_id,company_name,company_email,logo_url,"
                "company_background,industry,company_size,location,website,"
                "founded_year,benefits,gallery"
            )
            .eq("employer_id", public_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None

        company = dict(rows[0])
        gallery_value = company.get("gallery") or []
        if isinstance(gallery_value, str):
            try:
                gallery_value = json.loads(gallery_value)
            except (TypeError, ValueError, json.JSONDecodeError):
                gallery_value = []

        gallery_urls = []
        if isinstance(gallery_value, list):
            for item in gallery_value:
                raw_url = (
                    item.get("url")
                    if isinstance(item, dict)
                    else item
                )
                safe_url = _safe_public_http_url(raw_url)
                if safe_url and safe_url not in gallery_urls:
                    gallery_urls.append(safe_url)

        company["gallery"] = gallery_urls
        company["logo_url"] = _safe_public_http_url(company.get("logo_url"))
        company["website_url"] = _normalise_public_website_url(
            company.get("website")
        )
        company["company_name"] = (
            str(company.get("company_name") or "Employer").strip()
        )
        words = re.findall(r"[A-Za-z0-9]+", company["company_name"])
        company["initials"] = (
            "".join(word[0] for word in words[:2]).upper()
            if words
            else "CO"
        )
        return company

    def _legacy_application_matches_current_seeker(application):
        """Safely recognise an old application that predates owner_key."""
        resume_id = application.get("resumeId")
        if not resume_id:
            return False
        try:
            resume = resume_store.get_resume(resume_id) or {}
            data = resume.get("data") if isinstance(resume.get("data"), dict) else {}
            personal_info = (
                data.get("personalInfo")
                if isinstance(data.get("personalInfo"), dict)
                else {}
            )
            resume_email = str(personal_info.get("email") or "").strip().lower()
            seeker_email = str(session.get("email") or "").strip().lower()
            if resume_email and seeker_email and resume_email == seeker_email:
                return True
            resume_name = _normalise_identity(personal_info.get("name"))
            seeker_name = _normalise_identity(session.get("full_name"))
            if resume_name and seeker_name and resume_name == seeker_name:
                return True
            # Uploaded resumes may not have structured personalInfo. Accept a
            # conservative filename/title prefix such as Alex_Rivera_Resume.
            resume_label = _normalise_identity(
                resume.get("name") or resume.get("fileName")
            )
            return bool(
                len(seeker_name) >= 5
                and resume_label
                and resume_label.startswith(seeker_name)
            )
        except Exception:
            return False

    def _legacy_resume_matches_current_seeker(resume):
        """Recognise an ownerless resume without exposing it to the browser."""
        data = resume.get("data") if isinstance(resume.get("data"), dict) else {}
        personal_info = (
            data.get("personalInfo")
            if isinstance(data.get("personalInfo"), dict)
            else {}
        )
        resume_email = str(personal_info.get("email") or "").strip().lower()
        seeker_email = str(session.get("email") or "").strip().lower()
        if resume_email and seeker_email and resume_email == seeker_email:
            return True

        resume_name = _normalise_identity(personal_info.get("name"))
        seeker_name = _normalise_identity(session.get("full_name"))
        if resume_name and seeker_name and resume_name == seeker_name:
            return True

        # Uploaded legacy files have no structured personal information.
        # Claim only a conservative filename/title prefix, for example
        # KohKeXing_Resume for the signed-in user Koh Ke Xing.
        resume_label = _normalise_identity(
            resume.get("name") or resume.get("fileName")
        )
        return bool(
            len(seeker_name) >= 5
            and resume_label
            and resume_label.startswith(seeker_name)
        )

    def _current_seeker_resumes():
        """Return only this account's resumes and safely claim legacy rows."""
        owner_key = session["user_id"]

        # Older versions saved owner_key as NULL. Migrate only rows whose
        # embedded email/name or filename clearly matches the signed-in user.
        for legacy_resume in resume_store.get_unowned_resumes():
            if not _legacy_resume_matches_current_seeker(legacy_resume):
                continue
            resume_store.claim_unowned_resume(
                legacy_resume.get("id"),
                owner_key,
            )

        return resume_store.get_resumes(owner_key=owner_key)

    def _current_seeker_applications():
        owner_key = session["user_id"]
        applications = app_tracker.get_applications_for_owner(owner_key)
        known_ids = {str(item.get("id")) for item in applications}

        # One-time compatibility for records created by the previous seeker
        # code, which did not send owner_key. Only claim a record when its
        # submitted resume name or email matches the signed-in profile.
        for legacy in app_tracker.get_applications():
            if legacy.get("ownerKey") or str(legacy.get("id")) in known_ids:
                continue
            if not _legacy_application_matches_current_seeker(legacy):
                continue
            if app_tracker.claim_legacy_application(
                legacy.get("id"), owner_key
            ):
                legacy["ownerKey"] = owner_key
                applications.append(legacy)
                known_ids.add(str(legacy.get("id")))
        return applications

    def _add_candidate_interviews(applications):
        safe_applications = [dict(item) for item in (applications or [])]
        application_ids = [
            str(item.get("id")) for item in safe_applications if item.get("id")
        ]
        if not application_ids:
            return safe_applications
        try:
            response = (
                get_supabase_admin_client()
                .table("employer_interviews")
                .select(
                    "application_id,interview_at,interview_type,"
                    "location_or_link,status"
                )
                .in_("application_id", application_ids)
                .execute()
            )
            interviews = {
                str(row.get("application_id")): {
                    "interviewAt": row.get("interview_at"),
                    "interviewType": row.get("interview_type") or "online",
                    "locationOrLink": row.get("location_or_link") or "",
                    "status": row.get("status") or "scheduled",
                }
                for row in (response.data or [])
            }
        except Exception:
            app.logger.warning(
                "Interview details are unavailable; run the recruitment migration",
                exc_info=True,
            )
            interviews = {}
        for application in safe_applications:
            application["interview"] = interviews.get(
                str(application.get("id"))
            )
        return safe_applications

    def _public_jobs():
        jobs = [dict(job) for job in (job_store.get_jobs() or [])]
        if not jobs:
            return []
        job_ids = [str(job.get("id")) for job in jobs if job.get("id")]
        controls = {}
        employer_profiles = []
        try:
            admin = get_supabase_admin_client()
            control_response = (
                admin.table("employer_job_controls")
                .select(
                    "job_id,employer_user_id,lifecycle_status,"
                    "application_deadline,updated_at"
                )
                .in_("job_id", job_ids)
                .execute()
            )
            for row in (control_response.data or []):
                controls[str(row.get("job_id"))] = row
            profile_response = (
                admin.table("employers")
                .select("user_id,employer_id,company_name,logo_url")
                .execute()
            )
            employer_profiles = profile_response.data or []
        except Exception:
            # Legacy jobs remain public until the one-time recruitment SQL is
            # installed. The application trigger is still the final guard.
            app.logger.warning(
                "Job lifecycle/company enrichment is unavailable",
                exc_info=True,
            )

        profiles_by_user = {
            str(row.get("user_id")): row
            for row in employer_profiles
            if row.get("user_id")
        }
        profiles_by_company = {
            _normalise_identity(row.get("company_name")): row
            for row in employer_profiles
            if row.get("company_name")
        }
        today = datetime.date.today()
        visible_jobs = []
        for job in jobs:
            control = controls.get(str(job.get("id")))
            lifecycle = str(
                (control or {}).get("lifecycle_status") or "published"
            ).lower()
            deadline_value = (control or {}).get("application_deadline")
            try:
                deadline = (
                    datetime.date.fromisoformat(str(deadline_value)[:10])
                    if deadline_value
                    else None
                )
            except ValueError:
                deadline = None
            if lifecycle != "published" or (deadline and deadline < today):
                continue

            owner_key = str(
                (control or {}).get("employer_user_id")
                or job.get("employerId")
                or job.get("employer_id")
                or job.get("ownerKey")
                or job.get("owner_key")
                or ""
            )
            employer = (
                profiles_by_user.get(owner_key)
                or profiles_by_company.get(
                    _normalise_identity(job.get("company"))
                )
                or {}
            )
            employer_public_id = str(employer.get("employer_id") or "")
            job["lifecycleStatus"] = "published"
            job["applicationDeadline"] = (
                deadline.isoformat() if deadline else ""
            )
            job["companyLogoUrl"] = employer.get("logo_url") or ""
            job["employerPublicId"] = employer_public_id
            job["companyProfileUrl"] = (
                f"/view-company/{employer_public_id}"
                if employer_public_id
                else ""
            )
            visible_jobs.append(job)
        return visible_jobs

    # =========================================================
    # AUTHENTICATION PAGES
    # =========================================================
    @app.route("/login")
    def login_page():
        """Always show the login page when the login URL is requested."""
        return render_template("login.html")

    @app.route("/register")
    def register_page():
        if (
            session.get("user_id")
            and session.get("role") == JOB_SEEKER_ROLE
        ):
            return redirect(url_for("seeker_page"))
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

        user, error = auth_service.register_user(
            email=email,
            password=password,
            full_name=full_name,
        )
        if error:
            if is_email_rate_limit_error(error):
                return jsonify({"error": EMAIL_RATE_LIMIT_MESSAGE}), 429
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

        try:
            if not auth_account_exists(email):
                return jsonify({"error": ACCOUNT_NOT_FOUND_MESSAGE}), 404
        except Exception as exc:
            print("ACCOUNT LOOKUP ERROR:", repr(exc))
            return jsonify({
                "error": "Unable to verify the account right now. Please try again."
            }), 503

        user, error = auth_service.login_user(email, password)
        if error:
            if error == "Invalid email or password.":
                error = "Incorrect password. Please try again."
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
            "redirect": url_for("seeker_page"),
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
            if not auth_account_exists(email):
                return jsonify({"error": ACCOUNT_NOT_FOUND_MESSAGE}), 404

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
                "message": "Reset link sent! Please check your email.",
            }), 200

        except Exception as e:
            print("PASSWORD RESET EMAIL ERROR:", repr(e))
            if is_email_rate_limit_error(e):
                return jsonify({"error": EMAIL_RATE_LIMIT_MESSAGE}), 429
            return jsonify({
                "error": "Unable to send the reset link. Please try again."
            }), 500

    @app.route("/api/auth/update-password", methods=["POST"])
    def update_password():
        """Update password after reset"""
        data = request.get_json(silent=True) or {}
        new_password = str(data.get("password", ""))
        access_token = str(data.get("access_token") or "")
        refresh_token = str(data.get("refresh_token") or "")

        password_error = password_policy_error(new_password)
        if password_error:
            return jsonify({"error": password_error}), 400

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
            
            password_error = password_policy_error(new_password)
            if password_error:
                return jsonify({"error": password_error}), 400
            
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

        cleaned_profile, field_errors = _validate_profile_payload(data)
        if field_errors:
            return jsonify({
                "error": "Please correct the highlighted profile fields.",
                "field_errors": field_errors,
            }), 400

        profile = auth_service.update_profile(
            session["user_id"],
            cleaned_profile,
        )
        if not profile:
            return jsonify({"error": "Profile update failed."}), 500

        session["full_name"] = profile.get(
            "full_name", cleaned_profile["full_name"]
        )
        profile["email"] = session.get("email", "")
        return jsonify({"success": True, "profile": profile})

    # =========================================================
    # PROTECTED SEEKER PAGES
    # =========================================================
    @app.route("/")
    def index():
        """Make the site root open the login page first."""
        return redirect(url_for("login_page"))

    @app.route("/seeker")
    @seeker_required
    def seeker_page():
        """Protected Explore Positions landing page for job seekers."""
        return render_template("seeker.html")

    @app.route("/dashboard")
    def dashboard():
        """Dashboard - redirect to login if not authenticated"""
        if session.get("user_id") and session.get("role") == JOB_SEEKER_ROLE:
            return render_template("dashboard.html")
        return redirect(url_for("login_page"))

    @app.route("/view-company/<employer_id>")
    def view_company(employer_id):
        """Public, read-only company background page for job seekers."""
        try:
            company = _public_company_profile(employer_id)
        except Exception:
            app.logger.exception(
                "Unable to load public company profile %s", employer_id
            )
            return render_template(
                "view_company.html",
                company=None,
                requested_employer_id=str(employer_id or "").upper(),
                load_error=(
                    "The company page could not be loaded right now. "
                    "Please try again shortly."
                ),
            ), 503

        if not company:
            return render_template(
                "view_company.html",
                company=None,
                requested_employer_id=str(employer_id or "").upper(),
                load_error="This company profile was not found.",
            ), 404

        return render_template(
            "view_company.html",
            company=company,
            requested_employer_id=company["employer_id"],
            load_error="",
        )

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
        return jsonify(
            _add_candidate_interviews(_current_seeker_applications())
        )

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
        selected_resume = resume_store.get_resume(
            resume_id,
            owner_key=session["user_id"],
        )
        if not selected_resume:
            return jsonify({"error": "The selected resume was not found."}), 400
        if not selected_resume.get("storedFileName"):
            return jsonify({
                "error": "Save the selected builder resume as PDF or DOCX before applying."
            }), 400
        if not cover_letter_text and not cover_letter_file:
            return jsonify({"error": "A cover letter (written or uploaded) is required to apply."}), 400

        available_job = next(
            (job for job in _public_jobs() if str(job.get("id")) == str(job_id)),
            None,
        )
        if not available_job:
            return jsonify({
                "error": "This job is no longer accepting applications."
            }), 409
        job_title = available_job.get("title") or job_title
        company = available_job.get("company") or company

        existing = app_tracker.get_applications_for_owner(session["user_id"])
        if any(a["jobId"] == job_id for a in existing):
            return jsonify({"error": "You have already applied to this job."}), 409

        new_app = app_tracker.add_application(
            job_id, job_title, company, date, "Pending", details,
            resume_id=resume_id,
            cover_letter_text=cover_letter_text,
            cover_letter_file=cover_letter_file,
            cover_letter_original_name=cover_letter_original_name,
            owner_key=session["user_id"],
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
            if not any(
                str(job.get("id")) == str(job_id) for job in _public_jobs()
            ):
                return jsonify({
                    "error": "This job is no longer available."
                }), 409

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
    @seeker_required
    def get_resumes():
        return jsonify(_current_seeker_resumes())

    @app.route("/api/resumes/upload", methods=["POST"])
    @seeker_required
    def upload_resume():
        file = request.files.get("resume")
        if not file or not file.filename:
            return jsonify({"error": "No file was provided."}), 400

        try:
            record = resume_store.add_uploaded_resume(
                file,
                owner_key=session["user_id"],
            )
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
    @seeker_required
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
                owner_key=session["user_id"],
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
    @seeker_required
    def update_resume(resume_id):
        updates = request.get_json() or {}
        try:
            record = resume_store.update_resume(
                resume_id,
                updates,
                owner_key=session["user_id"],
            )
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
    @seeker_required
    def delete_resume(resume_id):
        success = resume_store.delete_resume(
            resume_id,
            owner_key=session["user_id"],
        )
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    @seeker_required
    def serve_uploaded_resume(filename):
        stored_file = resume_store.download_uploaded_resume(
            filename,
            owner_key=session["user_id"],
        )
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
        return jsonify(_public_jobs())

    @app.route("/api/jobs/recommendations")
    def api_job_recommendations():
        return jsonify([
            {**job, "matchScore": 0} for job in _public_jobs()
        ])

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
                    "description": item.get("description") or "Ã¢â‚¬Â¢ Led key initiatives and delivered business-critical requirements.\nÃ¢â‚¬Â¢ Collaborated with cross-functional teams to implement scalable updates."
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
            fallback = f"Ã¢â‚¬Â¢ Spearheaded critical {sec_type} initiatives with strict adherence to industry standards.\nÃ¢â‚¬Â¢ Elevated key deliverables by implementing modern solution paradigms."
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
            analysis = f"Evaluated resume compatibility against **{co_name} - {co_title}**.\n\n### Strengths:\nÃ¢â‚¬Â¢ Profile details match general keywords in {co_title}.\nÃ¢â‚¬Â¢ Experience references core collaborative processes.\n\n### Recommendation:\nÃ¢â‚¬Â¢ Inject more quantitative achievements.\nÃ¢â‚¬Â¢ Explicitly mention tech stacks like {tech_rec if tech_rec else 'required systems'}."
            
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
          "analysis": "Markdown string containing: \\n### Alignment Strengths\\nÃ¢â‚¬Â¢ ...\\n### Skill Gaps / Areas to Improve\\nÃ¢â‚¬Â¢ ...\\n### Specific recommendations to customize this resume for this job."
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
