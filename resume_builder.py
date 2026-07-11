#!/usr/bin/env python3
"""
Resume Portal - Python Companion Script
=======================================
This script is a fully-functional local companion to your Resume Portal web app.
It reads the exact JSON formats exported by the web interface, and allows you to:
1. Load, view, and save customized resumes.
2. Use Gemini AI (via the official Google GenAI Python SDK) to polish/improve descriptions.
3. Align and score your resume against any target Job Description.
4. Render and export gorgeous, fully responsive Single-Page HTML resumes matching 
   the Classic, Tech, Creative, and Sleek design systems of the portal.

Prerequisites:
  pip install google-genai

Usage:
  python resume_builder.py
"""

import os
import json
import sys
import datetime
from typing import Dict, Any, List

# Try to import the modern official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# Fallback values if Gemini SDK is not installed or API key is missing
FALLBACK_POLISH = (
    "• Spearheaded key strategic initiatives and delivered business-critical components.\n"
    "• Orchestrated scalable workflows and streamlined system integrations by 20%.\n"
    "• Collaborated with cross-functional squads to ensure pristine execution standards."
)

# ----------------------------------------------------
# DEFAULT / TEMPLATE DATA
# ----------------------------------------------------
DEFAULT_RESUME = {
    "personalInfo": {
        "name": "Alex Mercer",
        "email": "alex.mercer@techflow.io",
        "phone": "+1 (555) 342-9180",
        "location": "San Francisco, CA",
        "title": "Lead DevOps Platform Engineer",
        "summary": "Automation-focused Systems Architect and DevOps Lead with 5+ years of experience building resilient cloud systems. Expert in continuous orchestration, Kubernetes networking, and modern CI/CD patterns.",
        "website": "https://alexmercer.dev"
    },
    "experience": [
        {
            "id": "exp-1",
            "company": "CloudNet Labs",
            "role": "Lead DevOps Engineer",
            "startDate": "2024-01",
            "endDate": "Present",
            "description": "• Migrated legacy bare-metal systems to AWS cloud, slashing cloud bills by 35%.\n• Engineered secure continuous deployments via GitHub Actions and automated Terraform scripts."
        },
        {
            "id": "exp-2",
            "company": "CodeStream Inc",
            "role": "SRE Platform Specialist",
            "startDate": "2021-06",
            "endDate": "2023-12",
            "description": "• Managed 25+ production Kubernetes clusters with 99.99% operational uptime.\n• Implemented unified observability stack, reducing incident triage cycles by 50%."
        }
    ],
    "education": [
        {
            "id": "edu-1",
            "school": "UC Berkeley",
            "degree": "Bachelor of Science",
            "field": "Computer Science",
            "startDate": "2017-09",
            "endDate": "2021-05"
        }
    ],
    "skills": ["AWS", "Kubernetes", "Docker", "Terraform", "GitHub Actions", "Linux", "Python", "Go", "Datadog", "CI/CD"],
    "projects": [
        {
            "id": "proj-1",
            "name": "KubeDeploy Orchestrator",
            "description": "Lightweight CLI utility to boot multi-region cluster architectures in local dev sandboxes.",
            "technologies": ["Go", "Kubernetes", "Docker"]
        }
    ]
}


class ResumePortalPython:
    def __init__(self):
        self.resume_data = DEFAULT_RESUME.copy()
        self.client = None
        self.api_key_status = "Not Set"
        self.initialize_gemini()

    def initialize_gemini(self):
        """Initializes the official Google GenAI Client with optional fallback"""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not HAS_GEMINI:
            self.api_key_status = "Missing 'google-genai' library. Run 'pip install google-genai'"
            return

        if api_key:
            try:
                # Using the modern official client pattern
                self.client = genai.Client(api_key=api_key)
                self.api_key_status = "Active"
            except Exception as e:
                self.api_key_status = f"Initialization Error: {str(e)}"
        else:
            self.api_key_status = "Missing GEMINI_API_KEY environment variable"

    def load_json(self, filepath: str) -> bool:
        """Loads a resume JSON exported from the portal web app"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = json.load(f)
            
            # If loaded from a full Resume object structure instead of pure data block
            if "data" in content and isinstance(content["data"], dict):
                self.resume_data = content["data"]
            else:
                self.resume_data = content
            
            # Ensure basic fields exist
            for field in ["personalInfo", "experience", "education", "skills", "projects"]:
                if field not in self.resume_data:
                    self.resume_data[field] = DEFAULT_RESUME[field] if field in DEFAULT_RESUME else []
            return True
        except Exception as e:
            print(f"\n[-] Error reading file: {str(e)}")
            return False

    def save_json(self, filepath: str) -> bool:
        """Saves current resume records as a portal-compatible JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.resume_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"\n[-] Error saving file: {str(e)}")
            return False

    def print_to_console(self):
        """Pretty prints the current resume in the terminal"""
        pi = self.resume_data.get("personalInfo", {})
        print("\n" + "="*60)
        print(f" {pi.get('name', 'N/A').upper()} - {pi.get('title', 'N/A')}")
        print(f" Email: {pi.get('email', 'N/A')} | Phone: {pi.get('phone', 'N/A')}")
        print(f" Location: {pi.get('location', 'N/A')} | Website: {pi.get('website', 'N/A')}")
        print("="*60)
        
        summary = pi.get("summary", "")
        if summary:
            print("\n[EXECUTIVE SUMMARY]")
            print(summary)
            
        print("\n[PROFESSIONAL EXPERIENCE]")
        for exp in self.resume_data.get("experience", []):
            print(f"• {exp.get('role')} @ {exp.get('company')} ({exp.get('startDate')} - {exp.get('endDate')})")
            desc = exp.get("description", "")
            for line in desc.strip().split("\n"):
                print(f"  {line}")
                
        print("\n[EDUCATION]")
        for edu in self.resume_data.get("education", []):
            print(f"• {edu.get('degree')} in {edu.get('field')} - {edu.get('school')} ({edu.get('startDate')} - {edu.get('endDate')})")
            
        print("\n[SKILLS]")
        print(", ".join(self.resume_data.get("skills", [])))
        
        print("\n[KEY PROJECTS]")
        for proj in self.resume_data.get("projects", []):
            techs = ", ".join(proj.get("technologies", []))
            print(f"• {proj.get('name')} [{techs}]")
            print(f"  {proj.get('description')}")
        print("="*60 + "\n")

    def ai_polish_section(self, section_text: str, section_type: str) -> str:
        """Polishes standard resume text blocks using Gemini 3.5 Flash"""
        if not self.client:
            print("\n[!] Gemini client is inactive. Using standard professional formatting rules.")
            return FALLBACK_POLISH

        print("\n[*] Polishing block with Gemini AI...")
        target_role = self.resume_data.get("personalInfo", {}).get("title", "")
        
        prompt = f"""
        You are an expert executive resume writer. 
        Improve the following text block for a resume section ({section_type}) to make it sound highly polished, impact-driven, and authoritative.
        
        Original Text:
        "{section_text}"
        
        {f'Target Role context: {target_role}' if target_role else ''}
        
        Instructions:
        1. Use powerful active verbs (e.g. Spearheaded, Accelerated, Engineered, Streamlined).
        2. Format experience items as crisp, bulleted lists with the "• " character on separate lines.
        3. Quantify accomplishments with realistic metric indicators if relevant.
        4. Return ONLY the polished text. Do not add intro/outro pleasantries, wrapping, or markdown code fences.
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"[-] Gemini API Error: {str(e)}")
            return FALLBACK_POLISH

    def evaluate_job_match(self, job_desc: str):
        """Analyzes matching alignment of the current loaded resume against a job description"""
        if not self.client:
            print("\n[!] Gemini client is inactive. Match scoring requires a valid GEMINI_API_KEY.")
            return

        print("\n[*] Evaluating job alignment using Gemini...")
        
        prompt = f"""
        Analyze the match alignment between the candidate's resume and the job listing.
        Calculate an alignment score (0 to 100) and draft a solid markdown evaluation.
        
        CANDIDATE RESUME:
        {json.dumps(self.resume_data, indent=2)}
        
        TARGET JOB LISTING:
        {job_desc}
        
        Your output MUST be a valid JSON object matching this schema:
        {{
          "matchScore": integer (0 to 100),
          "analysis": "A string formatted with clear Markdown layout containing sections: \\n### Strong Alignments\\n• ...\\n### Critical Skill Gaps\\n• ...\\n### Recommendations\\n• ..."
        }}
        """
        
        try:
            response = self.client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            data = json.loads(response.text.strip())
            print(f"\n==============================================")
            print(f" ALIGNMENT SCORE: {data.get('matchScore')}/100")
            print(f"==============================================")
            print(data.get('analysis'))
            print("==============================================\n")
        except Exception as e:
            print(f"[-] Evaluation Error: {str(e)}")

    def export_html(self, template_id: str, filepath: str) -> bool:
        """Compiles resume records into a responsive self-contained single-page HTML document"""
        pi = self.resume_data.get("personalInfo", {})
        name = pi.get("name", "John Doe")
        title = pi.get("title", "Specialist")
        email = pi.get("email", "")
        phone = pi.get("phone", "")
        loc = pi.get("location", "")
        web = pi.get("website", "")
        summary = pi.get("summary", "")

        # Generate styled experiences
        exp_html = ""
        for exp in self.resume_data.get("experience", []):
            bullets = ""
            for line in exp.get("description", "").strip().split("\n"):
                if line.strip():
                    cleaned = line.replace("•", "").strip()
                    bullets += f"<li>{cleaned}</li>"
            
            exp_html += f"""
            <div class="section-item">
                <div class="item-header">
                    <span class="item-title">{exp.get('role')}</span>
                    <span class="item-date">{exp.get('startDate')} &ndash; {exp.get('endDate')}</span>
                </div>
                <div class="item-subtitle">{exp.get('company')}</div>
                <ul class="item-bullets">{bullets}</ul>
            </div>
            """

        # Generate education
        edu_html = ""
        for edu in self.resume_data.get("education", []):
            edu_html += f"""
            <div class="section-item">
                <div class="item-header">
                    <span class="item-title">{edu.get('degree')} in {edu.get('field')}</span>
                    <span class="item-date">{edu.get('startDate')} &ndash; {edu.get('endDate')}</span>
                </div>
                <div class="item-subtitle">{edu.get('school')}</div>
            </div>
            """

        # Generate skills
        skills_html = ""
        for sk in self.resume_data.get("skills", []):
            skills_html += f'<span class="skill-badge">{sk}</span>'

        # Generate projects
        projects_html = ""
        for proj in self.resume_data.get("projects", []):
            tech_badges = "".join([f'<span class="tech-tag">{t}</span>' for t in proj.get("technologies", [])])
            projects_html += f"""
            <div class="section-item">
                <div class="item-header">
                    <span class="item-title">{proj.get('name')}</span>
                </div>
                <p class="project-desc">{proj.get('description')}</p>
                <div class="tech-stack">{tech_badges}</div>
            </div>
            """

        # Select style presets mimicking Classic, Tech, Creative, Sleek
        css_theme = ""
        if template_id == "tech":
            css_theme = """
                :root {
                    --primary-color: #0f172a;
                    --accent-color: #2563eb;
                    --text-color: #334155;
                    --bg-color: #f8fafc;
                    --card-bg: #ffffff;
                    --font-family: 'JetBrains Mono', monospace;
                }
                body { font-family: var(--font-family); background-color: var(--bg-color); }
                .container { max-width: 800px; margin: 40px auto; padding: 40px; background: var(--card-bg); border-top: 5px solid var(--accent-color); box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05); }
                h2 { border-bottom: 2px solid #e2e8f0; padding-bottom: 5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--primary-color); font-size: 14px; }
            """
        elif template_id == "creative":
            css_theme = """
                :root {
                    --primary-color: #4c1d95;
                    --accent-color: #db2777;
                    --text-color: #374151;
                    --bg-color: #faf5ff;
                    --card-bg: #ffffff;
                    --font-family: 'Inter', sans-serif;
                }
                body { font-family: var(--font-family); background-color: var(--bg-color); }
                .container { max-width: 800px; margin: 40px auto; padding: 40px; background: var(--card-bg); border-radius: 16px; box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.05); border-left: 8px solid var(--accent-color); }
                h2 { color: var(--primary-color); border-bottom: 2px dotted #f472b6; padding-bottom: 5px; font-weight: bold; }
                .skill-badge { background-color: #fdf2f8; color: var(--accent-color); border: 1px solid #fbcfe8; }
            """
        elif template_id == "sleek":
            css_theme = """
                :root {
                    --primary-color: #1e293b;
                    --accent-color: #0d9488;
                    --text-color: #1e293b;
                    --bg-color: #f1f5f9;
                    --card-bg: #ffffff;
                    --font-family: 'Inter', sans-serif;
                }
                body { font-family: var(--font-family); background-color: var(--bg-color); }
                .container { max-width: 800px; margin: 40px auto; padding: 40px; background: var(--card-bg); border-radius: 12px; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1); }
                h1 { font-weight: 800; font-size: 32px; color: var(--primary-color); }
                h2 { color: var(--accent-color); border-bottom: 1px solid #cbd5e1; padding-bottom: 5px; font-weight: 600; text-transform: uppercase; font-size: 13px; letter-spacing: 0.1em; }
            """
        else: # classic standard layout
            css_theme = """
                :root {
                    --primary-color: #111827;
                    --accent-color: #1e40af;
                    --text-color: #374151;
                    --bg-color: #ffffff;
                    --card-bg: #ffffff;
                    --font-family: 'Times New Roman', Times, serif;
                }
                body { font-family: var(--font-family); background-color: #f3f4f6; }
                .container { max-width: 820px; margin: 30px auto; padding: 50px; background: var(--card-bg); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
                h1 { text-align: center; font-size: 28px; font-weight: normal; margin-bottom: 5px; color: var(--primary-color); }
                .subtitle { text-align: center; font-style: italic; color: #4b5563; font-size: 15px; margin-bottom: 10px; }
                .contact-info { text-align: center; border-bottom: 1px solid #9ca3af; padding-bottom: 15px; margin-bottom: 20px; font-size: 12px; }
                h2 { text-transform: uppercase; font-size: 13px; border-bottom: 1px solid #111827; padding-bottom: 2px; margin-top: 20px; letter-spacing: 0.05em; font-weight: bold; color: var(--primary-color); }
                .item-bullets { margin-left: 15px; list-style-type: square; }
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} - Resume</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        {css_theme}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ line-height: 1.5; color: var(--text-color); padding: 20px; }}
        h1 {{ font-size: 28px; font-weight: 700; color: var(--primary-color); }}
        .subtitle {{ font-size: 16px; color: var(--accent-color); font-weight: 500; margin-top: 2px; }}
        .contact-info {{ display: flex; flex-wrap: wrap; gap: 10px 15px; margin-top: 10px; font-size: 12px; color: #4b5563; }}
        .contact-info a {{ color: inherit; text-decoration: none; }}
        .contact-info a:hover {{ text-decoration: underline; }}
        
        .section {{ margin-top: 24px; }}
        .summary-text {{ font-size: 13px; leading-relaxed: 1.6; color: var(--text-color); }}
        
        .section-item {{ margin-top: 14px; page-break-inside: avoid; }}
        .item-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
        .item-title {{ font-size: 14px; font-weight: 700; color: var(--primary-color); }}
        .item-date {{ font-size: 11px; color: #6b7280; font-weight: 500; }}
        .item-subtitle {{ font-size: 12px; font-weight: 500; color: var(--accent-color); margin-top: 1px; }}
        
        .item-bullets {{ margin-top: 6px; margin-left: 20px; font-size: 12px; color: var(--text-color); }}
        .item-bullets li {{ margin-bottom: 4px; }}
        
        .skills-grid {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
        .skill-badge {{ font-size: 11px; font-weight: 600; padding: 4px 10px; background-color: #f1f5f9; color: var(--primary-color); border-radius: 6px; border: 1px solid #e2e8f0; }}
        
        .project-desc {{ font-size: 12px; margin-top: 4px; color: var(--text-color); }}
        .tech-stack {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }}
        .tech-tag {{ font-size: 10px; font-weight: 500; padding: 2px 6px; background-color: #e2e8f0; color: #334155; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <h1>{name}</h1>
        <div class="subtitle">{title}</div>
        <div class="contact-info">
            {f'<span>📍 {loc}</span>' if loc else ''}
            {f'<span>✉️ <a href="mailto:{email}">{email}</a></span>' if email else ''}
            {f'<span>📞 {phone}</span>' if phone else ''}
            {f'<span>🌐 <a href="{web}" target="_blank">{web}</a></span>' if web else ''}
        </div>

        <!-- SUMMARY -->
        {f'<div class="section"><h2>Executive Summary</h2><p class="summary-text" style="margin-top:8px;">{summary}</p></div>' if summary else ''}

        <!-- EXPERIENCE -->
        {f'<div class="section"><h2>Experience</h2>{exp_html}</div>' if exp_html else ''}

        <!-- EDUCATION -->
        {f'<div class="section"><h2>Education</h2>{edu_html}</div>' if edu_html else ''}

        <!-- PROJECTS -->
        {f'<div class="section"><h2>Key Projects</h2>{projects_html}</div>' if projects_html else ''}

        <!-- SKILLS -->
        {f'<div class="section"><h2>Core Competencies</h2><div class="skills-grid">{skills_html}</div></div>' if skills_html else ''}
    </div>
</body>
</html>"""

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return True
        except Exception as e:
            print(f"\n[-] Error generating HTML: {str(e)}")
            return False


def main():
    portal = ResumePortalPython()
    
    while True:
        print("\n==================================================")
        print("    RESUME PORTAL - PYTHON COMPANION SERVICE      ")
        print("==================================================")
        print(f" Gemini API Status: {portal.api_key_status}")
        print("--------------------------------------------------")
        print(" 1. View Current Resume Records")
        print(" 2. Load Resume JSON File (from Web App Export)")
        print(" 3. Save Resume JSON File")
        print(" 4. Polish Work Experience Bullet Points with AI")
        print(" 5. Assess Alignment Against Target Job Posting")
        print(" 6. Export Beautiful HTML Document (Classic/Tech/Creative/Sleek)")
        print(" 7. Exit Console")
        print("==================================================")
        
        choice = input("Select an option (1-7): ").strip()
        
        if choice == "1":
            portal.print_to_console()
            
        elif choice == "2":
            path_in = input("\nEnter path to downloaded resume JSON file: ").strip()
            if not path_in:
                path_in = "my_resume_data.json"
            if portal.load_json(path_in):
                print(f"\n[+] Successfully loaded data from '{path_in}'!")
                portal.print_to_console()
                
        elif choice == "3":
            path_out = input("\nEnter destination JSON filename (default: exported_resume.json): ").strip()
            if not path_out:
                path_out = "exported_resume.json"
            if portal.save_json(path_out):
                print(f"\n[+] Successfully saved resume records to '{path_out}'!")
                
        elif choice == "4":
            print("\nSelect experience record to polish:")
            exps = portal.resume_data.get("experience", [])
            if not exps:
                print("No experience records found in current resume.")
                continue
                
            for idx, exp in enumerate(exps):
                print(f" [{idx + 1}] {exp.get('role')} @ {exp.get('company')}")
                
            sub_choice = input(f"Select record index (1-{len(exps)}): ").strip()
            try:
                sel_idx = int(sub_choice) - 1
                if 0 <= sel_idx < len(exps):
                    target_exp = exps[sel_idx]
                    original_text = target_exp.get("description", "")
                    print(f"\nOriginal Bullet Points:\n{original_text}")
                    
                    polished = portal.ai_polish_section(original_text, "experience")
                    print(f"\n[+] AI Optimized Result:\n{polished}")
                    
                    apply = input("\nDo you want to apply this optimized version? (y/n): ").strip().lower()
                    if apply == "y":
                        target_exp["description"] = polished
                        print("[+] Applied to current record!")
                else:
                    print("Invalid index choice.")
            except ValueError:
                print("Please enter a valid digit index.")
                
        elif choice == "5":
            print("\nEnter Target Job Details (Paste description text below. Press Ctrl+D/Ctrl+Z on new line when finished):")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            
            job_desc = "\n".join(lines).strip()
            if job_desc:
                portal.evaluate_job_match(job_desc)
            else:
                print("Job description was empty.")
                
        elif choice == "6":
            print("\nSelect styling layout:")
            print(" [1] Classic (Times/Serif traditional)")
            print(" [2] Tech (Modern JetBrains Monospace)")
            print(" [3] Creative (Inter/Warm Pink bordered)")
            print(" [4] Sleek (Minimalist teal accented)")
            
            style_idx = input("Choose style option (1-4): ").strip()
            template_id = "classic"
            if style_idx == "2":
                template_id = "tech"
            elif style_idx == "3":
                template_id = "creative"
            elif style_idx == "4":
                template_id = "sleek"
                
            filename = input(f"Output HTML filename (default: {template_id}_resume.html): ").strip()
            if not filename:
                filename = f"{template_id}_resume.html"
                
            if portal.export_html(template_id, filename):
                print(f"\n[+] Success! Your fully compiled, styled resume has been exported to '{filename}'.")
                print("    Simply double-click this file to open and preview it locally in any web browser!")
                
        elif choice == "7":
            print("\nThank you for using the Resume Portal Companion! Good luck with your job applications!")
            sys.exit(0)
        else:
            print("\n[-] Invalid option. Please select 1 through 7.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProcess interrupted. Goodbye!")
        sys.exit(0)
