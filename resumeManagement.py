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


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
GENERATED_DIR = DATA_DIR / "generated"
PROFILE_PATH = DATA_DIR / "profile.json"
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
        "industry": "Technology, business, and general roles",
        "summary": "Clean layout with strong section hierarchy and concise highlights.",
        "accent": "#2563eb",
        "pattern": "modern",
    },
    "executive": {
        "name": "Executive Classic",
        "industry": "Management, consulting, finance, and senior roles",
        "summary": "Traditional structure focused on achievements and leadership scope.",
        "accent": "#1f2937",
        "pattern": "executive",
    },
    "creative": {
        "name": "Creative Portfolio",
        "industry": "Design, marketing, media, and communications",
        "summary": "More expressive presentation for projects, strengths, and outcomes.",
        "accent": "#0f766e",
        "pattern": "creative",
    },
    "minimal": {
        "name": "Minimal Focus",
        "industry": "Fresh graduates, internships, and entry-level roles",
        "summary": "Light, simple resume with generous spacing and easy scanning.",
        "accent": "#7c3aed",
        "pattern": "minimal",
    },
    "technical": {
        "name": "Technical Skills",
        "industry": "Software, data, engineering, and IT support",
        "summary": "Two-column pattern that makes skills, tools, and projects stand out.",
        "accent": "#0369a1",
        "pattern": "technical",
    },
    "academic": {
        "name": "Academic Formal",
        "industry": "Education, research, scholarship, and government roles",
        "summary": "Structured and formal with clear sections for credentials.",
        "accent": "#854d0e",
        "pattern": "academic",
    },
}

DEFAULT_PROFILE = {
    "name": "Alex Mercer",
    "title": "Full Stack Engineer",
    "email": "alex.mercer@techflow.io",
    "phone": "+1 (555) 342-9180",
    "location": "San Francisco, CA",
    "summary": "Dynamic Software Engineer with over 4 years of experience building scalable single-page applications and microservices. Expert in TypeScript, React, and Node.js with a passion for clean code and intuitive user interfaces.",
    "skills": "TypeScript, React, Python, Flask, Node.js, Tailwind CSS, PostgreSQL, REST APIs, Git, CI/CD",
    "experience": "Software Developer @ Prism Systems Ltd\nEngineered robust front-end features using React, Vite, and Tailwind CSS, improving application speed by 25%.\nCoordinated with designers and product owners to translate complex requirements into clean interactive interfaces.",
    "education": "Bachelor of Science in Computer Science\nUniversity of California, Berkeley",
    "projects": "CloudFlow Dashboard - Infrastructure management dashboard with real-time health metrics.\nSafeAuth Engine - Custom authentication library for secure routing.",
}


def create_app():
    app = Flask(__name__)
    app.secret_key = "resume-management-demo-secret"
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

    @app.route("/upload", methods=["POST"])
    def upload_resume():
        file = request.files.get("resume")
        if not file or not file.filename:
            flash("Please choose a PDF or DOCX resume to upload.", "error")
            return redirect(url_for("index"))

        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            flash("Only PDF and DOCX files are supported.", "error")
            return redirect(url_for("index"))

        clear_uploaded_resume()
        safe_name = secure_filename(file.filename)
        stored_name = f"uploaded_resume_{uuid4().hex}{extension}"
        destination = UPLOAD_DIR / stored_name
        file.save(destination)
        save_json(
            DATA_DIR / "uploaded_resume.json",
            {
                "original_name": safe_name,
                "stored_name": stored_name,
                "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        )
        flash("Resume uploaded successfully. You can replace or delete it anytime.", "success")
        return redirect(url_for("index"))

    @app.route("/upload/delete", methods=["POST"])
    def delete_uploaded_resume():
        clear_uploaded_resume()
        flash("Uploaded resume deleted.", "success")
        return redirect(url_for("index"))

    @app.route("/template/<template_id>")
    def template_builder(template_id):
        if template_id not in RESUME_TEMPLATES:
            flash("Template not found.", "error")
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
            flash("Template not found.", "error")
            return redirect(url_for("index"))
        resume = collect_resume_form(request.form)
        filename = save_resume_html(template_id, resume, "template")
        save_json(PREFS_PATH, {"selected_template": template_id})
        flash("Resume created from template and saved.", "success")
        return redirect(url_for("preview_resume", filename=filename))

    @app.route("/auto-generate")
    def auto_generate():
        profile = load_profile()
        missing = required_profile_fields_missing(profile)
        if missing:
            flash(f"Profile is missing: {', '.join(missing)}.", "error")
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
        flash("Auto-generated resume saved and ready to download.", "success")
        return redirect(url_for("preview_resume", filename=filename))

    @app.route("/templates/<template_id>/preference", methods=["POST"])
    def save_template_preference(template_id):
        if template_id in RESUME_TEMPLATES:
            save_json(PREFS_PATH, {"selected_template": template_id})
            flash("Template preference saved.", "success")
        return redirect(url_for("index"))

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        if request.method == "POST":
            profile_data = {key: request.form.get(key, "").strip() for key in DEFAULT_PROFILE}
            save_json(PROFILE_PATH, profile_data)
            flash("Profile saved. It can now be used to auto-generate a resume.", "success")
            return redirect(url_for("profile"))
        return render_template("profile.html", profile=load_profile())

    @app.route("/resumes/<filename>")
    def preview_resume(filename):
        return send_from_directory(GENERATED_DIR, filename)

    @app.route("/uploads/<filename>")
    def uploaded_file(filename):
        return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)

    return app


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
        resumes.append({"filename": path.name, "created_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")})
    return resumes


def empty_resume():
    return {
        "name": "",
        "title": "",
        "contact": "",
        "summary": "",
        "skills": "",
        "experience": "",
        "education": "",
        "projects": "",
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
    body_class = f"resume-{pattern}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape_html(resume['name'])} Resume</title>
  <style>
    :root {{ --accent: {accent}; }}
    body {{ font-family: Arial, sans-serif; color: #111827; margin: 0; background: #eef2f6; }}
    .page {{ max-width: 880px; margin: 32px auto; background: white; border: 1px solid #e5e7eb; box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08); }}
    .header {{ padding: 46px 46px 0; }}
    .inner {{ padding: 12px 46px 46px; }}
    h1 {{ margin: 0; font-size: 35px; color: var(--accent); letter-spacing: 0; }}
    .title {{ margin-top: 6px; font-size: 18px; color: #475569; }}
    .contact {{ margin-top: 14px; font-size: 13px; color: #475569; }}
    h2 {{ margin: 28px 0 8px; color: var(--accent); font-size: 15px; text-transform: uppercase; letter-spacing: 0; border-bottom: 1px solid #dbe3ea; padding-bottom: 6px; }}
    p, li {{ line-height: 1.55; font-size: 14px; }}
    ul {{ margin-top: 8px; padding-left: 20px; }}
    .download-note {{ margin: 0 auto 24px; max-width: 880px; color: #475569; font-size: 13px; }}
    .resume-modern .page {{ border-top: 10px solid var(--accent); }}
    .resume-executive .page {{ border: 0; }}
    .resume-executive .header {{ background: #111827; color: white; padding: 44px 46px; }}
    .resume-executive .header h1, .resume-executive .header .title, .resume-executive .header .contact {{ color: white; }}
    .resume-executive .inner {{ padding-top: 34px; }}
    .resume-creative .page {{ border-radius: 22px; overflow: hidden; }}
    .resume-creative .header {{ padding: 42px 46px; background: linear-gradient(135deg, var(--accent), #38bdf8); color: white; }}
    .resume-creative .header h1, .resume-creative .header .title, .resume-creative .header .contact {{ color: white; }}
    .resume-creative .inner {{ padding-top: 34px; }}
    .resume-minimal .page {{ box-shadow: none; border-color: #d6dde6; }}
    .resume-minimal h1 {{ color: #111827; }}
    .resume-minimal h2 {{ color: #111827; border-bottom: 0; border-left: 4px solid var(--accent); padding-left: 10px; }}
    .resume-technical .page {{ display: grid; grid-template-columns: 280px 1fr; }}
    .resume-technical .header {{ background: #0f172a; color: white; padding: 38px 30px; min-height: 100%; }}
    .resume-technical .header h1, .resume-technical .header .title, .resume-technical .header .contact {{ color: white; }}
    .resume-technical .inner {{ padding: 38px; }}
    .resume-academic .page {{ border-top: 4px double var(--accent); }}
    .resume-academic h1 {{ font-family: Georgia, serif; color: #111827; }}
    .resume-academic h2 {{ font-family: Georgia, serif; color: var(--accent); }}
    @media print {{
      body {{ background: white; }}
      .page {{ margin: 0; border: 0; box-shadow: none; }}
      .download-note {{ display: none; }}
    }}
    @media (max-width: 760px) {{
      .resume-technical .page {{ display: block; }}
    }}
  </style>
</head>
<body class="{body_class}">
  <main class="page">
    <header class="header">
      <h1>{escape_html(resume['name'])}</h1>
      <div class="title">{escape_html(resume['title'])}</div>
      <div class="contact">{escape_html(resume['contact'])}</div>
    </header>
    <section class="inner">
      {section('Professional Summary', resume['summary'])}
      {section('Skills', resume['skills'])}
      {section('Experience', resume['experience'])}
      {section('Education', resume['education'])}
      {section('Projects', resume['projects'])}
    </section>
  </main>
  <p class="download-note">Use your browser print option and choose "Save as PDF" to download this resume.</p>
</body>
</html>"""


def section(title, value):
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 1:
        items = "".join(f"<li>{escape_html(line)}</li>" for line in lines)
        return f"<h2>{title}</h2><ul>{items}</ul>"
    return f"<h2>{title}</h2><p>{escape_html(value)}</p>"


def escape_html(value):
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    create_app().run(debug=True, port=port)
