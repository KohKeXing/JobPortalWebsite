import json
import os
import urllib.request
import urllib.error
import datetime
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
    jsonify,
)
from werkzeug.utils import secure_filename

# Import application tracking module
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

# JOBS DATABASE
JOBS_DATABASE = [
  {
    "id": "job-1",
    "title": "Senior React Engineer",
    "company": "Synthetix Solutions",
    "location": "Kuala Lumpur, Malaysia (Remote)",
    "salary": "RM 8,000 - RM 13,000 / month",
    "type": "Remote",
    "tags": ["Software & Tech", "React", "TypeScript", "Vite", "Tailwind CSS"],
    "logo_color": "bg-blue-600 text-white",
    "icon": "SS",
    "featured": True,
    "category": "Software & Tech",
    "posted": "2026-07-07",
    "description": "Synthetix Solutions is seeking an exceptional Senior React Engineer to design and build our next-generation web platforms.\n\nKey Responsibilities:\n• Build high-performance, accessible components using React and TypeScript.\n• Optimize client-side state managers and integrate RESTful backend services.\n• Maintain high visual quality using Tailwind CSS and modern web standards.\n\nQualifications:\n• 3+ years experience with React/TypeScript in production environments.\n• High attention to typography, margins, and user experience patterns."
  },
  {
    "id": "job-2",
    "title": "Lead Product Designer",
    "company": "PixelCraft Studio",
    "location": "Penang, Malaysia (Hybrid)",
    "salary": "RM 7,500 - RM 11,500 / month",
    "type": "Hybrid",
    "tags": ["Design & Creative", "UI/UX", "Figma", "Design Systems"],
    "logo_color": "bg-pink-600 text-white",
    "icon": "PS",
    "featured": True,
    "category": "Design & Creative",
    "posted": "2026-07-08",
    "description": "PixelCraft Studio is looking for a Lead Product Designer to champion our collaborative systems and canvas features.\n\nKey Responsibilities:\n• Define and scale our cross-platform layout visual patterns in Figma.\n• Lead UX research and design interactive high-fidelity user flows.\n• Collaborate closely with engineering to build flawless responsive UI.\n\nQualifications:\n• 4+ years product design experience with an outstanding design portfolio.\n• Passion for detail-oriented styling, typography, and motion design."
  },
  {
    "id": "job-3",
    "title": "Growth Marketing Manager",
    "company": "SaaSify Group",
    "location": "Kuala Lumpur, Malaysia",
    "salary": "RM 5,500 - RM 8,500 / month",
    "type": "Full-time",
    "tags": ["Marketing & Sales", "SEO", "Analytics", "Campaigns"],
    "logo_color": "bg-orange-600 text-white",
    "icon": "SG",
    "featured": False,
    "category": "Marketing & Sales",
    "posted": "2026-07-05",
    "description": "SaaSify Group is looking for a Growth Marketing Manager to design, coordinate, and execute marketing strategies.\n\nKey Responsibilities:\n• Devise SEO, content, and paid advertising strategies to scale user acquisition.\n• Monitor campaign conversions, perform A/B testing, and audit marketing attribution metrics.\n• Formulate digital branding campaigns and design promotional channels.\n\nQualifications:\n• 2+ years leading campaigns in SaaS or high-growth tech firms.\n• Analytical mindset with deep experience in search console and marketing tools."
  },
  {
    "id": "job-4",
    "title": "Healthcare Data Analyst",
    "company": "Helix Health",
    "location": "Petaling Jaya, Selangor, Malaysia",
    "salary": "RM 4,500 - RM 7,000 / month",
    "type": "Contract",
    "tags": ["Software & Tech", "Data Analysis", "SQL", "Python", "Tableau"],
    "logo_color": "bg-teal-600 text-white",
    "icon": "HH",
    "featured": False,
    "category": "Software & Tech",
    "posted": "2026-07-06",
    "description": "Helix Health is seeking a Healthcare Data Analyst to build and maintain our telemetry and clinical operations pipelines.\n\nKey Responsibilities:\n• Query database servers using optimized SQL commands to audit performance metrics.\n• Construct interactive dashboards for tracking operational workflows and key performance outcomes.\n• Translate clinical research criteria into structured quantitative models.\n\nQualifications:\n• 2+ years querying databases, compiling metrics, and visualizing complex telemetry datasets."
  },
  {
    "id": "job-5",
    "title": "Senior Financial Analyst",
    "company": "CapitalTrust Inc.",
    "location": "Kuala Lumpur, Malaysia",
    "salary": "RM 6,000 - RM 9,500 / month",
    "type": "Full-time",
    "tags": ["Finance & Legal", "Modeling", "Forecasting", "Excel"],
    "logo_color": "bg-cyan-600 text-white",
    "icon": "CI",
    "featured": True,
    "category": "Finance & Legal",
    "posted": "2026-07-04",
    "description": "CapitalTrust Inc. is seeking an analyst to handle modeling, budgeting, and performance analytics.\n\nKey Responsibilities:\n• Build sophisticated financial models to support strategic decisions and forecasting.\n• Analyze market trends, perform competitor analysis, and audit operating costs.\n• Deliver executive-level dashboards outlining budget variances and investment risks.\n\nQualifications:\n• 3+ years experience in investment modeling, consulting, or corporate finance."
  },
  {
    "id": "job-6",
    "title": "Customer Support Lead",
    "company": "Nimbus Cloud Technologies",
    "location": "Kuala Lumpur, Malaysia (Remote)",
    "salary": "RM 3,500 - RM 5,500 / month",
    "type": "Remote",
    "tags": ["Customer Support", "Zendesk", "Communication", "Management"],
    "logo_color": "bg-red-600 text-white",
    "icon": "NC",
    "featured": False,
    "category": "Customer Support",
    "posted": "2026-07-09",
    "description": "Nimbus Cloud Technologies is seeking a Customer Support Lead to coordinate our helpdesk systems.\n\nKey Responsibilities:\n• Manage Zendesk ticketing flows and mentor support specialists.\n• Analyze customer satisfaction ratings, response times, and Escalation protocols.\n• Drive continuous improvement of customer-facing resources and help articles.\n\nQualifications:\n• 2+ years managing customer support teams or scaling ticketing workflows."
  }
]

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

def create_app():
    app = Flask(__name__, template_folder="templates")
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

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/resumes")
    def resumes():
        return render_template("resumes.html")

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
                "uploaded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
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

    # ---------------------------------------------------------
    # APPLICATION TRACKING API ROUTES
    # ---------------------------------------------------------
    @app.route("/api/applications", methods=["GET"])
    def get_applications():
        return jsonify(app_tracker.get_applications())

    @app.route("/api/applications", methods=["POST"])
    def add_application():
        data = request.get_json() or {}
        job_id = data.get("jobId")
        job_title = data.get("job")
        company = data.get("company")
        date = data.get("date") or datetime.datetime.now().strftime("%Y-%m-%d")
        details = data.get("details", "")
        if not job_id or not job_title or not company:
            return jsonify({"error": "jobId, job title and company are required"}), 400
        new_app = app_tracker.add_application(job_id, job_title, company, date, "Pending", details)
        return jsonify({"success": True, "application": new_app}), 201

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

        success = app_tracker.update_status(app_id, new_status, new_details)
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Application not found"}), 404

    # ---------------------------------------------------------
    # RESUME PORTAL API ENDPOINTS (MERGED FROM server.py)
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
        return jsonify(JOBS_DATABASE)

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
        1. Write a compelling, high-impact 3-4 sentence professional summary in 'personalInfo.summary'. Highlight core strengths, years of value, and target role relevance. Do NOT use generic text.
        2. Rewrite each 'experience' description to be extremely polished. Use strong active verbs (e.g., Spearheaded, Formulated, Orchestrated, Engineered). Expand brief sentences into professional bullet points (using bullet character '•' at the start of each line) emphasizing results and metrics.
        3. For the 'skills' array, expand the user's initial list with relevant high-demand industry skills that logically match their profile and target role (total of 10-15 solid skill keywords).
        4. Rewrite the 'projects' descriptions to showcase complexity, technical stack integration, and end-user benefits.
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
        2. If experience description, format as 2-3 high-quality professional bullets, starting with the bullet character "• " on separate lines.
        3. Focus on outcomes, efficiency gains, or technical proficiency.
        4. Return ONLY the polished text block, no introduction, wrapping, or markdown code syntax blocks.
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
            "created_at": datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
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
    filename = f"{source}_resume_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
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
    app.run(debug=True, host="0.0.0.0", port=3000)
