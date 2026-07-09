import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

# ====== 新增：引入申请跟踪模块 ======
from application_tracking import ApplicationTracking

# Persistent File System Structure Configurations
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
PROFILE_PATH = DATA_DIR / "profile.json"
PREFS_PATH = DATA_DIR / "preferences.json"

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

RESUME_TEMPLATES = {
    "modern": {
        "name": "Modern Professional",
        "industry": "Technology, business, and general corporate roles",
        "summary": "Clean layout with strong top accent border hierarchy and concise text margins.",
        "accent": "#2563eb",
        "pattern": "modern",
    },
    "executive": {
        "name": "Executive Classic",
        "industry": "Management, consulting, finance, and senior operations",
        "summary": "Traditional centered header banner focused on clear chronological leadership scope.",
        "accent": "#1f2937",
        "pattern": "executive",
    },
    "technical": {
        "name": "Technical Skills Split",
        "industry": "Software development, data infrastructure, and engineering",
        "summary": "Asymmetric two-column dark sidebar pattern designed to highlight core skill competencies.",
        "accent": "#0369a1",
        "pattern": "technical",
    }
}

DEFAULT_PROFILE = {
    "name": "Alex Mercer",
    "title": "Full Stack Software Engineer",
    "email": "alex.mercer@techflow.io",
    "phone": "+1 (555) 342-9180",
    "location": "San Francisco, CA",
    "summary": "Dynamic Systems Architect with over 4 years of experience building scalable applications and responsive microservices. Expert in TypeScript, Python, Flask, and React ecosystem architectures.",
    "skills": "TypeScript, React, Python, Flask, Node.js, Tailwind CSS, PostgreSQL, REST APIs, Git, CI/CD",
    "experience": "Lead Software Developer @ Prism Systems Ltd (2022 - Present)\n- Engineered robust front-end features using React, improving application speed by 25%.\n- Coordinated with product stakeholders to translate requirements into intuitive interactive interfaces.",
    "education": "Bachelor of Science in Computer Science\nUniversity of California, Berkeley",
    "projects": "CloudFlow Dashboard - High-throughput system metrics visualization hub.\nSafeAuth Engine - Custom lightweight middleware wrapper for secure cryptographic routing.",
}

# ====== 新增：实例化申请跟踪器 ======
app_tracker = ApplicationTracking()

def create_app():
    app = Flask(__name__)
    app.secret_key = "resume-management-production-secure-token"
    ensure_storage()

    @app.context_processor
    def inject_profile():
        return {"current_profile": load_profile()}

    @app.route("/")
    def index():
        uploaded = get_uploaded_resume()
        generated = list_generated_resumes()
        prefs = load_json(PREFS_PATH, {"selected_template": "modern"})
        return render_template(
            "index.html",
            templates=RESUME_TEMPLATES,
            uploaded=uploaded,
            generated=generated,
            selected_template=prefs.get("selected_template", "modern"),
            profile=load_profile(),
        )

    # ---------------------------------------------------------
    # METHOD 1: UPLOAD EXISTING RESUME ACTIONS
    # ---------------------------------------------------------
    @app.route("/upload", methods=["POST"])
    def upload_resume():
        file = request.files.get("resume")
        if not file or not file.filename:
            flash("Please provide a valid PDF or DOCX file to upload.", "error")
            return redirect(url_for("index"))

        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            flash("Validation Failed: Only standard PDF and DOCX documents are accepted.", "error")
            return redirect(url_for("index"))

        clear_uploaded_resume()
        safe_name = secure_filename(file.filename)
        stored_name = f"resume_{uuid4().hex}{extension}"
        file.save(UPLOAD_DIR / stored_name)
        save_json(
            DATA_DIR / "uploaded_resume.json",
            {
                "original_name": safe_name,
                "stored_name": stored_name,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        )
        flash("Document storage updated. Your file has been securely cataloged.", "success")
        return redirect(url_for("index"))

    @app.route("/upload/delete", methods=["POST"])
    def delete_uploaded_resume():
        clear_uploaded_resume()
        flash("Stored document file successfully removed from registry.", "success")
        return redirect(url_for("index"))

    # ---------------------------------------------------------
    # METHOD 2: BUILD VIA RESUME LAYOUT TEMPLATES
    # ---------------------------------------------------------
    @app.route("/template/<template_id>")
    def template_builder(template_id):
        if template_id not in RESUME_TEMPLATES:
            flash("Requested structural style template configuration not found.", "error")
            return redirect(url_for("index"))
        return render_template(
            "builder.html",
            mode="template",
            template_id=template_id,
            template=RESUME_TEMPLATES[template_id],
            resume=empty_resume(),
        )

    @app.route("/template/<template_id>/save", methods=["POST"])
    def save_template_resume(template_id):
        if template_id not in RESUME_TEMPLATES:
            flash("Invalid template context assignment.", "error")
            return redirect(url_for("index"))
        resume = collect_resume_form(request.form)
        filename = save_resume_html(template_id, resume, "template")
        save_json(PREFS_PATH, {"selected_template": template_id})
        flash("Template configuration compiled and registered to storage pipelines.", "success")
        return redirect(url_for("preview_resume", filename=filename))

    # ---------------------------------------------------------
    # METHOD 3: AUTO-GENERATE FROM PROFILE REGISTRY
    # ---------------------------------------------------------
    @app.route("/auto-generate")
    def auto_generate():
        profile = load_profile()
        missing = required_profile_fields_missing(profile)
        if missing:
            flash(f"Generation Aborted: The following fields are mandatory: {', '.join(missing)}.", "error")
            return redirect(url_for("profile"))
        prefs = load_json(PREFS_PATH, {"selected_template": "modern"})
        template_id = prefs.get("selected_template", "modern")
        resume = resume_from_profile(profile)
        return render_template(
            "builder.html",
            mode="auto",
            template_id=template_id,
            template=RESUME_TEMPLATES[template_id],
            resume=resume,
        )

    @app.route("/auto-generate/save", methods=["POST"])
    def save_auto_resume():
        template_id = request.form.get("template_id", "modern")
        if template_id not in RESUME_TEMPLATES:
            template_id = "modern"
        resume = collect_resume_form(request.form)
        filename = save_resume_html(template_id, resume, "auto")
        flash("Automated profile compilation successful. Live preview loaded below.", "success")
        return redirect(url_for("preview_resume", filename=filename))

    # ---------------------------------------------------------
    # WORKSPACE CORE CHANNELS & PREFERENCE API ROUTERS
    # ---------------------------------------------------------
    @app.route("/templates/<template_id>/preference", methods=["POST"])
    def save_template_preference(template_id):
        if template_id in RESUME_TEMPLATES:
            save_json(PREFS_PATH, {"selected_template": template_id})
            flash("Workspace global template structure updated.", "success")
        return redirect(url_for("index"))

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        if request.method == "POST":
            profile_data = {key: request.form.get(key, "").strip() for key in DEFAULT_PROFILE}
            save_json(PROFILE_PATH, profile_data)
            flash("Central registry system variables updated.", "success")
            return redirect(url_for("profile"))
        return render_template("profile.html", profile=load_profile())

    @app.route("/resumes/<filename>")
    def preview_resume(filename):
        return send_from_directory(GENERATED_DIR, filename)

    @app.route("/uploads/<filename>")
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)

    # =============================================================
    # ====== 新增：APPLICATION TRACKING API ROUTES ======
    # =============================================================

    @app.route("/api/applications", methods=["GET"])
    def get_applications():
        """获取当前用户的所有申请（demo 中返回全部）"""
        return json.dumps(app_tracker.get_applications()), 200, {'Content-Type': 'application/json'}

    @app.route("/api/applications", methods=["POST"])
    def add_application():
        """新增申请（工作申请时调用）"""
        data = request.get_json()
        job_id = data.get("jobId")
        job_title = data.get("job")
        company = data.get("company")
        date = data.get("date") or datetime.now().strftime("%Y-%m-%d")
        details = data.get("details", "")
        if not job_id or not job_title or not company:
            return json.dumps({"error": "jobId, job title and company are required"}), 400, {'Content-Type': 'application/json'}
        new_app = app_tracker.add_application(job_id, job_title, company, date, "Pending", details)
        return json.dumps({"success": True, "application": new_app}), 201, {'Content-Type': 'application/json'}

    @app.route("/api/applications/<app_id>", methods=["PUT"])
    def update_application_status(app_id):
        """更新申请状态（仅 employer 可调用）"""
        role = request.headers.get("X-Role", "candidate")
        if role.lower() != "employer":
            return json.dumps({"error": "Only employer can update status"}), 403, {'Content-Type': 'application/json'}

        data = request.get_json()
        new_status = data.get("status")
        new_details = data.get("details")
        if not new_status:
            return json.dumps({"error": "Status is required"}), 400, {'Content-Type': 'application/json'}

        success = app_tracker.update_status(app_id, new_status, new_details)
        if success:
            return json.dumps({"success": True}), 200, {'Content-Type': 'application/json'}
        else:
            return json.dumps({"error": "Application not found"}), 404, {'Content-Type': 'application/json'}

    return app


# ---------------------------------------------------------
# PERSISTENT SYSTEM UTILITIES & UTILITY COMPILERS
# ---------------------------------------------------------
def ensure_storage():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    if not PROFILE_PATH.exists():
        save_json(PROFILE_PATH, DEFAULT_PROFILE)
    if not PREFS_PATH.exists():
        save_json(PREFS_PATH, {"selected_template": "modern"})


def load_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_profile():
    return load_json(PROFILE_PATH, DEFAULT_PROFILE)


def get_uploaded_resume():
    metadata = load_json(DATA_DIR / "uploaded_resume.json", None)
    if not metadata:
        return None
    stored_name = metadata.get("stored_name")
    if not stored_name or not (UPLOAD_DIR / stored_name).exists():
        return None
    return metadata


def clear_uploaded_resume():
    metadata = load_json(DATA_DIR / "uploaded_resume.json", None)
    if metadata and metadata.get("stored_name"):
        path = UPLOAD_DIR / metadata["stored_name"]
        if path.exists():
            path.unlink()
    metadata_path = DATA_DIR / "uploaded_resume.json"
    if metadata_path.exists():
        metadata_path.unlink()


def list_generated_resumes():
    resumes = []
    for path in sorted(GENERATED_DIR.glob("*.html"), reverse=True):
        resumes.append({
            "filename": path.name,
            "created_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        })
    return resumes


def empty_resume():
    return {
        "name": "", "title": "", "contact": "", "summary": "",
        "skills": "", "experience": "", "education": "", "projects": ""
    }


def resume_from_profile(profile):
    return {
        "name": profile.get("name", ""),
        "title": profile.get("title", ""),
        "contact": " | ".join(
            item for item in [profile.get("email"), profile.get("phone"), profile.get("location")] if item
        ),
        "summary": profile.get("summary", ""),
        "skills": profile.get("skills", ""),
        "experience": profile.get("experience", ""),
        "education": profile.get("education", ""),
        "projects": profile.get("projects", ""),
    }


def required_profile_fields_missing(profile):
    required = ["name", "title", "email", "summary", "skills", "experience", "education"]
    return [field for field in required if not profile.get(field, "").strip()]


def collect_resume_form(form):
    resume = empty_resume()
    for key in resume:
        resume[key] = form.get(key, "").strip()
    return resume


def save_resume_html(template_id, resume, source):
    filename = f"{source}_resume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    template = RESUME_TEMPLATES[template_id]
    html = render_resume_document(template, resume)
    (GENERATED_DIR / filename).write_text(html, encoding="utf-8")
    return filename


def render_resume_document(template, resume):
    accent = template["accent"]
    pattern = template.get("pattern", "modern")

    name = escape_html(resume.get('name', ''))
    title = escape_html(resume.get('title', ''))
    contact = escape_html(resume.get('contact', ''))
    summary = resume.get('summary', '')
    skills = resume.get('skills', '')
    experience = resume.get('experience', '')
    education = resume.get('education', '')
    projects = resume.get('projects', '')

    def render_section(title, content, format_as_badges=False):
        if not content: return ""
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines: return ""

        html = f'<div class="section-block"><h2>{title}</h2>'
        if format_as_badges:
            html += '<div class="badge-container">'
            items = []
            for line in lines:
                items.extend([i.strip() for i in line.split(',') if i.strip()])
            for item in items:
                html += f'<span class="custom-badge">{escape_html(item)}</span>'
            html += '</div>'
        elif len(lines) > 1:
            html += '<ul>'
            for line in lines:
                html += f'<li>{escape_html(line)}</li>'
            html += '</ul>'
        else:
            html += f'<p>{escape_html(content)}</p>'
        html += '</div>'
        return html

    styles = f"""
    <style>
        :root {{ 
            --accent: {accent}; 
            --dark-bg: #0f172a;
            --text-dark: #1e293b;
            --text-muted: #64748b;
        }}
        * {{ box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            color: var(--text-dark); 
            margin: 0; 
            background: #f1f5f9; 
            padding: 20px;
        }}
        .resume-container {{ 
            max-width: 820px; 
            margin: 20px auto; 
            background: white; 
            box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            min-height: 1050px;
        }}
        h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 24px; margin-bottom: 12px; padding-bottom: 5px; }}
        p, li {{ font-size: 13.5px; line-height: 1.6; color: #334155; }}
        ul {{ padding-left: 20px; }}
        .badge-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
        .custom-badge {{ background: #f1f5f9; color: var(--text-dark); font-size: 11px; padding: 4px 10px; border-radius: 6px; font-weight: 500; border: 1px solid #e2e8f0; }}
        
        .theme-modern {{ border-top: 8px solid var(--accent); padding: 40px; }}
        .theme-modern h1 {{ margin: 0; font-size: 32px; color: var(--accent); font-weight: 800; }}
        .theme-modern .subtitle {{ font-size: 16px; color: var(--text-muted); margin-top: 4px; }}
        .theme-modern .contact-bar {{ display: flex; flex-wrap: wrap; gap: 15px; margin-top: 12px; padding-bottom: 20px; border-bottom: 1px solid #e2e8f0; font-size: 12.5px; color: var(--text-muted); }}
        .theme-modern h2 {{ color: var(--accent); border-bottom: 2px solid #f1f5f9; }}

        .theme-executive .header-banner {{ background: var(--dark-bg); color: white; padding: 40px; text-align: center; }}
        .theme-executive .header-banner h1 {{ margin: 0; font-size: 34px; color: white; }}
        .theme-executive .header-banner .subtitle {{ color: var(--accent); font-size: 16px; text-transform: uppercase; margin-top: 6px; }}
        .theme-executive .header-banner .contact-bar {{ margin-top: 15px; font-size: 13px; color: #94a3b8; }}
        .theme-executive .content-body {{ padding: 40px; }}
        .theme-executive h2 {{ color: var(--dark-bg); border-bottom: 1px solid var(--dark-bg); }}

        .theme-technical {{ display: grid; grid-template-columns: 260px 1fr; min-height: 1050px; }}
        .theme-technical .sidebar {{ background: #0f172a; color: #f8fafc; padding: 40px 25px; }}
        .theme-technical .sidebar h1 {{ font-size: 24px; color: white; margin: 0; }}
        .theme-technical .sidebar .subtitle {{ font-size: 13px; color: var(--accent); margin-top: 5px; text-transform: uppercase; }}
        .theme-technical .sidebar .contact-info {{ margin-top: 30px; font-size: 12px; color: #94a3b8; line-height: 1.8; }}
        .theme-technical .sidebar h2 {{ color: white; border-bottom: 1px solid #334155; }}
        .theme-technical .sidebar .custom-badge {{ background: #1e293b; color: #cbd5e1; border-color: #334155; }}
        .theme-technical .main-pane {{ padding: 40px; background: white; }}
        .theme-technical .main-pane h2 {{ color: #0f172a; border-bottom: 2px solid #f1f5f9; }}
    </style>
    """

    if pattern == "modern":
        body_content = f"""
        <div class="theme-modern">
            <h1>{name}</h1>
            <div class="subtitle">{title}</div>
            <div class="contact-bar">{contact}</div>
            {render_section('Summary', summary)}
            {render_section('Skills Cluster', skills, format_as_badges=True)}
            {render_section('Professional Experience', experience)}
            {render_section('Education & Credentials', education)}
            {render_section('Featured Deployments', projects)}
        </div>
        """
    elif pattern == "executive":
        body_content = f"""
        <div class="theme-executive">
            <div class="header-banner">
                <h1>{name}</h1>
                <div class="subtitle">{title}</div>
                <div class="contact-bar">{contact}</div>
            </div>
            <div class="content-body">
                {render_section('Executive Profile', summary)}
                {render_section('Core Competencies', skills, format_as_badges=True)}
                {render_section('Chronological Experience', experience)}
                {render_section('Education Qualifications', education)}
                {render_section('Key Projects', projects)}
            </div>
        </div>
        """
    else:
        body_content = f"""
        <div class="theme-technical">
            <div class="sidebar">
                <h1>{name}</h1>
                <div class="subtitle">{title}</div>
                <div class="contact-info">{contact.replace('|', '<br>')}</div>
                {render_section('Core Expertise', skills, format_as_badges=True)}
                {render_section('Education', education)}
            </div>
            <div class="main-pane">
                {render_section('Professional Summary', summary)}
                {render_section('Work History', experience)}
                {render_section('Key Projects & Deployments', projects)}
            </div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{name} - Resume Output Matrix</title>
  {styles}
</head>
<body>
    <div class="resume-container">
        {body_content}
    </div>
</body>
</html>"""


def escape_html(value):
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
