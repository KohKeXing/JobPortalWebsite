#!/usr/bin/env python3
import os
import json
import datetime
import random
from flask import Flask, jsonify, request, send_from_directory, render_template
from pydantic import BaseModel, Field
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app pointing template folder to 'templates'
app = Flask(__name__, template_folder='templates')

# Configure Port and Host
PORT = 3000
HOST = '0.0.0.0'

# Lazy initialize Google GenAI Client
# We try to import google-genai. If not available yet, we fallback to rule-based mock responses.
try:
    from google import genai
    from google.genai import types
    HAS_GEN_AI = True
except ImportError:
    HAS_GEN_AI = False

def get_ai_client():
    if not HAS_GEN_AI:
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        # Create client using modern official SDK structure
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Error initializing GenAI Client: {e}")
        return None

# ----------------------------------------------------
# PYDANTIC RESPONSE SCHEMAS FOR GEMINI STRUCTURAL OUTPUT
# ----------------------------------------------------
class PersonalInfoSchema(BaseModel):
    name: str
    email: str
    phone: str
    location: str
    title: str
    website: Optional[str] = None
    summary: str = Field(description="Compelling 3-4 sentence professional summary highlighting core values and strengths.")

class ExperienceItemSchema(BaseModel):
    id: str
    company: str
    role: str
    startDate: str
    endDate: str
    description: str = Field(description="Polished, multi-line bullet-pointed description with each bullet starting on a new line with the '• ' character.")

class EducationItemSchema(BaseModel):
    id: str
    school: str
    degree: str
    field: str
    startDate: str
    endDate: str

class ProjectItemSchema(BaseModel):
    id: str
    name: str
    description: str = Field(description="Compelling project outcome, complexity, and technical details.")
    technologies: List[str]
    link: Optional[str] = None

class ResumeResponseSchema(BaseModel):
    personalInfo: PersonalInfoSchema
    experience: List[ExperienceItemSchema]
    education: List[EducationItemSchema]
    skills: List[str]
    projects: List[ProjectItemSchema]

class MatchResponseSchema(BaseModel):
    matchScore: int = Field(description="Match compatibility score between 0 and 100")
    analysis: str = Field(description="Markdown string with structural headings: ### Alignment Strengths, ### Critical Skill Gaps, and ### Tailoring Recommendations.")

# ----------------------------------------------------
# JOBS DATABASE & ENDPOINTS
# ----------------------------------------------------
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

@app.route("/api/jobs", methods=["GET"])
def get_jobs():
    return jsonify(JOBS_DATABASE)

# ----------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------

# 1. Health check
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "hasApiKey": bool(os.environ.get("GEMINI_API_KEY")),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "backend": "python/flask"
    })

# 2. Auto-generate Resume from Profile (AI-powered)
@app.route("/api/resume/auto-generate", methods=["POST"])
def auto_generate():
    body = request.get_json() or {}
    profile = body.get("profile")
    target_role = body.get("targetRole")

    if not profile:
        return jsonify({"error": "Profile data is required."}), 400

    client = get_ai_client()
    if not client:
        # Fallback to rule-based mock generation if AI client is not configured
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
                    **profile.get("personalInfo", {}),
                    "summary": fallback_summary
                },
                "experience": fallback_experience,
                "education": profile.get("education", []),
                "skills": skills if skills else ["Teamwork", "Problem Solving", "Communication"],
                "projects": fallback_projects
            }
        })

    try:
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

        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a world-class professional resume architect who crafts high-performing CVs tailored to top-tier companies.",
                response_mime_type="application/json",
                response_schema=ResumeResponseSchema
            )
        )

        res_data = json.loads(response.text.strip())
        return jsonify({"data": res_data})
    except Exception as e:
        print("Gemini Auto-Generate Error:", e)
        return jsonify({"error": "Failed to generate resume with AI.", "details": str(e)}), 500

# 3. Improve Section API (Polishes an experience bullet, summary, or project)
@app.route("/api/resume/improve-section", methods=["POST"])
def improve_section():
    body = request.get_json() or {}
    text = body.get("text")
    sec_type = body.get("type", "experience")
    target_role = body.get("targetRole")

    if not text:
        return jsonify({"error": "Text is required."}), 400

    client = get_ai_client()
    if not client:
        fallback = f"• Spearheaded critical {sec_type} initiatives with strict adherence to industry standards.\n• Elevated key deliverables by implementing modern solution paradigms."
        return jsonify({"improvedText": fallback})

    try:
        prompt = f"""
        You are an expert professional resume editor.
        Improve the following resume section text ({sec_type}) to sound far more executive, impressive, and professional.
        
        Original Text:
        "{text}"

        {f"Target Role context: {target_role}" if target_role else ""}

        Instructions:
        1. Use high-impact active verbs (e.g. Spearheaded, Accelerated, Pioneered).
        2. If experience description, format as 2-3 high-quality professional bullets, starting with the bullet character "• " on separate lines.
        3. Focus on outcomes, efficiency gains, or technical proficiency.
        4. Return ONLY the polished text block, no introduction, wrapping, or markdown code syntax blocks.
        """

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )

        return jsonify({"improvedText": response.text.strip()})
    except Exception as e:
        print("Improve Section Error:", e)
        return jsonify({"error": "Failed to improve section.", "details": str(e)}), 500

# 4. Job Match Evaluation API (Checks resume alignment with a target job listing)
@app.route("/api/jobs/match", methods=["POST"])
def job_match():
    body = request.get_json() or {}
    resume_data = body.get("resumeData")
    job_listing = body.get("jobListing")

    if not resume_data or not job_listing:
        return jsonify({"error": "Resume data and job details are required."}), 400

    client = get_ai_client()
    if not client:
        score = random.randint(65, 92)
        co_title = job_listing.get("title", "Job Title")
        co_name = job_listing.get("company", "Company")
        reqs = job_listing.get("requirements", [])
        tech_rec = f", {', '.join(reqs[:2])}" if reqs else ""
        analysis = f"Evaluated resume compatibility against **{co_name} - {co_title}**.\n\n### Strengths:\n• Profile details match general keywords in {co_title}.\n• Experience references core collaborative processes.\n\n### Recommendation:\n• Inject more quantitative achievements.\n• Explicitly mention tech stacks like {tech_rec or 'required systems'}."
        return jsonify({
            "matchScore": score,
            "analysis": analysis
        })

    try:
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

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=MatchResponseSchema
            )
        )

        res_data = json.loads(response.text.strip())
        return jsonify(res_data)
    except Exception as e:
        print("Match API Error:", e)
        return jsonify({"error": "Failed to evaluate job match.", "details": str(e)}), 500

# ----------------------------------------------------
# TEMPLATE ROUTING (SERVES MODERN FLASK + JINJA FRONTEND)
# ----------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    print(f"[*] Launching Resume Portal Flask Server on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=True)
