import json
import os
import urllib.request
import urllib.error
import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory

# Import application tracking module
from application_tracking import ApplicationTracking

# Import resume storage module (handles real file uploads + JSON persistence)
from resume_builder import ResumeStorage, UPLOAD_DIR as RESUME_UPLOAD_DIR, save_cover_letter_file, COVER_LETTER_UPLOAD_DIR

# Import shared job storage (same data/jobs.json that employer_main.py writes to),
# so jobs posted by employers actually show up here for job seekers to browse.
from job import JobStorage

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

# Instantiate resume storage (real JSON file + on-disk uploads, survives restarts)
resume_store = ResumeStorage()

def create_app():
    app = Flask(__name__, template_folder="templates")
    app.secret_key = "resume-management-production-secure-token"

    @app.route("/")
    def index():
        return render_template("seeker.html")

    @app.route("/dashboard")
    def dashboard():
        # Serves the same page as "/" — seeker.html checks the URL on load and
        # opens straight to the Dashboard view. This used to render a separate
        # dashboard.html file that had drifted out of sync with the real one.
        return render_template("seeker.html")

    @app.route("/resumes")
    def resumes():
        return render_template("resumes.html")

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
        resume_id = data.get("resumeId")
        cover_letter_text = data.get("coverLetterText")
        cover_letter_file = data.get("coverLetterFile")
        cover_letter_original_name = data.get("coverLetterOriginalName")
        if not job_id or not job_title or not company:
            return jsonify({"error": "jobId, job title and company are required"}), 400
        new_app = app_tracker.add_application(
            job_id, job_title, company, date, "Pending", details,
            resume_id=resume_id,
            cover_letter_text=cover_letter_text,
            cover_letter_file=cover_letter_file,
            cover_letter_original_name=cover_letter_original_name,
        )
        return jsonify({"success": True, "application": new_app}), 201

    @app.route("/api/cover-letters/upload", methods=["POST"])
    def upload_cover_letter():
        file = request.files.get("coverLetter")
        if not file or not file.filename:
            return jsonify({"error": "No file was provided."}), 400
        try:
            record = save_cover_letter_file(file)
            return jsonify({"success": True, **record}), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/uploads/cover-letters/<filename>")
    def serve_cover_letter(filename):
        return send_from_directory(COVER_LETTER_UPLOAD_DIR, filename)

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
    # RESUME STORAGE API ROUTES (real Python/Flask persistence,
    # replacing the old browser-only localStorage approach)
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
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/resumes/builder", methods=["POST"])
    def create_builder_resume():
        body = request.get_json() or {}
        name = body.get("name", "Untitled Resume")
        layout = body.get("layout", "modern")
        data = body.get("data", {})
        record = resume_store.add_builder_resume(name, layout, data)
        return jsonify({"success": True, "resume": record}), 201

    @app.route("/api/resumes/<resume_id>", methods=["PUT"])
    def update_resume(resume_id):
        updates = request.get_json() or {}
        record = resume_store.update_resume(resume_id, updates)
        if record:
            return jsonify({"success": True, "resume": record}), 200
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/api/resumes/<resume_id>", methods=["DELETE"])
    def delete_resume(resume_id):
        success = resume_store.delete_resume(resume_id)
        if success:
            return jsonify({"success": True}), 200
        return jsonify({"error": "Resume not found"}), 404

    @app.route("/uploads/<filename>")
    def serve_uploaded_resume(filename):
        return send_from_directory(RESUME_UPLOAD_DIR, filename)

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


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=3000)