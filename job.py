import json
import uuid
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------
# Storage location
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
JOBS_FILE = DATA_DIR / "jobs.json"

# A small rotation of brand colors so newly posted jobs get a distinct look
# on the job cards, matching the seeded jobs below.
LOGO_COLOR_ROTATION = [
    "bg-blue-600 text-white",
    "bg-pink-600 text-white",
    "bg-emerald-600 text-white",
    "bg-orange-600 text-white",
    "bg-purple-600 text-white",
    "bg-teal-600 text-white",
    "bg-rose-600 text-white",
    "bg-cyan-600 text-white",
]

REQUIRED_JOB_FIELDS = ["title", "company", "location", "salary", "type", "description"]

# Seed data shown the first time the app runs, so both the job seeker page and
# the employer console aren't empty before any real jobs have been posted.
DEFAULT_JOBS = [
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
  },
  {
    "id": "job-7",
    "title": "Product Manager",
    "company": "Nexora Innovations",
    "location": "Petaling Jaya, Selangor, Malaysia",
    "salary": "RM 7,000 - RM 10,500 / month",
    "type": "Full-time",
    "tags": ["Product Management", "Roadmapping", "Agile", "Stakeholder Management"],
    "logo_color": "bg-purple-600 text-white",
    "icon": "NI",
    "featured": True,
    "category": "Product Management",
    "posted": "2026-07-10",
    "description": "Nexora Innovations is looking for a Product Manager to own the roadmap for our flagship platform.\n\nKey Responsibilities:\n• Define product strategy and translate it into a prioritized, actionable roadmap.\n• Partner closely with engineering and design to ship high-impact features.\n• Gather customer feedback and market insights to guide product decisions.\n\nQualifications:\n• 3+ years of product management experience, ideally in B2B SaaS.\n• Strong communication skills and comfort working across cross-functional teams."
  },
  {
    "id": "job-8",
    "title": "Backend Software Engineer",
    "company": "CodeForge Technologies",
    "location": "Cyberjaya, Malaysia (Hybrid)",
    "salary": "RM 6,500 - RM 10,000 / month",
    "type": "Hybrid",
    "tags": ["Software & Tech", "Python", "APIs", "PostgreSQL"],
    "logo_color": "bg-emerald-600 text-white",
    "icon": "CF",
    "featured": False,
    "category": "Software & Tech",
    "posted": "2026-07-11",
    "description": "CodeForge Technologies is hiring a Backend Software Engineer to build and scale our core services.\n\nKey Responsibilities:\n• Design and maintain RESTful APIs powering our web and mobile clients.\n• Optimize database queries and improve system reliability under load.\n• Collaborate with frontend engineers to define clean API contracts.\n\nQualifications:\n• 2+ years of backend development experience with Python or a similar language.\n• Solid understanding of relational databases and API design principles."
  },
  {
    "id": "job-9",
    "title": "UX Researcher",
    "company": "Bright Interface Co.",
    "location": "Kuala Lumpur, Malaysia",
    "salary": "RM 5,000 - RM 7,500 / month",
    "type": "Full-time",
    "tags": ["Design & Creative", "User Research", "Usability Testing", "Figma"],
    "logo_color": "bg-rose-600 text-white",
    "icon": "BI",
    "featured": False,
    "category": "Design & Creative",
    "posted": "2026-07-12",
    "description": "Bright Interface Co. is seeking a UX Researcher to uncover insights that shape our product experience.\n\nKey Responsibilities:\n• Plan and conduct usability studies, interviews, and surveys with real users.\n• Synthesize research findings into clear, actionable recommendations for designers and PMs.\n• Maintain a repository of research insights to inform future product decisions.\n\nQualifications:\n• 2+ years of UX research experience with a strong grasp of qualitative and quantitative methods.\n• Comfortable presenting findings to both design and non-design stakeholders."
  },
  {
    "id": "job-10",
    "title": "Legal Counsel",
    "company": "Meridian Law Partners",
    "location": "Kuala Lumpur, Malaysia",
    "salary": "RM 8,000 - RM 12,000 / month",
    "type": "Full-time",
    "tags": ["Finance & Legal", "Contracts", "Compliance", "Corporate Law"],
    "logo_color": "bg-cyan-600 text-white",
    "icon": "ML",
    "featured": False,
    "category": "Finance & Legal",
    "posted": "2026-07-13",
    "description": "Meridian Law Partners is seeking a Legal Counsel to support our growing corporate client base.\n\nKey Responsibilities:\n• Draft, review, and negotiate a wide range of commercial contracts.\n• Advise internal stakeholders on regulatory compliance and risk mitigation.\n• Manage relationships with external counsel on complex legal matters.\n\nQualifications:\n• 4+ years of experience in corporate or commercial law.\n• Admitted to practice with strong contract negotiation experience."
  },
  {
    "id": "job-11",
    "title": "Social Media Strategist",
    "company": "Buzzline Media",
    "location": "Kuala Lumpur, Malaysia (Remote)",
    "salary": "RM 4,000 - RM 6,500 / month",
    "type": "Remote",
    "tags": ["Marketing & Sales", "Social Media", "Content Strategy", "Analytics"],
    "logo_color": "bg-pink-600 text-white",
    "icon": "BM",
    "featured": False,
    "category": "Marketing & Sales",
    "posted": "2026-07-14",
    "description": "Buzzline Media is looking for a Social Media Strategist to grow our clients' brand presence online.\n\nKey Responsibilities:\n• Develop and execute social media content calendars across multiple platforms.\n• Track engagement metrics and adjust strategy based on performance data.\n• Collaborate with designers and copywriters to produce scroll-stopping content.\n\nQualifications:\n• 2+ years managing social media accounts for brands or agencies.\n• Strong eye for trends and data-driven storytelling."
  },
  {
    "id": "job-12",
    "title": "HR Business Partner",
    "company": "Talenta Group",
    "location": "Petaling Jaya, Selangor, Malaysia",
    "salary": "RM 5,500 - RM 8,000 / month",
    "type": "Full-time",
    "tags": ["Human Resources", "Employee Relations", "Talent Management", "Onboarding"],
    "logo_color": "bg-orange-600 text-white",
    "icon": "TG",
    "featured": False,
    "category": "Human Resources",
    "posted": "2026-07-15",
    "description": "Talenta Group is hiring an HR Business Partner to support our people operations as we scale.\n\nKey Responsibilities:\n• Partner with department leads on hiring plans, performance reviews, and employee relations.\n• Own the onboarding experience for new hires from offer to first 90 days.\n• Champion initiatives that improve employee engagement and retention.\n\nQualifications:\n• 3+ years of HR generalist or business partner experience.\n• Strong interpersonal skills and sound judgment handling sensitive matters."
  }
]


class JobStorage:
    """Real Python persistence for job postings: plain JSON file I/O on disk.

    This is the single shared source of truth for job listings — both
    seeker_main.py (job seeker browsing) and employer_main.py (employer
    CRUD) import this same class and read/write the same data/jobs.json
    file, so a job posted by an employer actually shows up for job seekers,
    and vice versa. Previously seeker_main.py had its own separate
    hardcoded job list that never connected to anything the employer did.
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not JOBS_FILE.exists():
            self._write(DEFAULT_JOBS)

    def _read(self):
        try:
            return json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write(self, jobs):
        JOBS_FILE.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_jobs(self):
        return self._read()

    def get_job(self, job_id):
        for job in self._read():
            if job["id"] == job_id:
                return job
        return None

    def create_job(self, data):
        jobs = self._read()
        color = LOGO_COLOR_ROTATION[len(jobs) % len(LOGO_COLOR_ROTATION)]

        new_job = {
            "id": "job-" + uuid.uuid4().hex[:10],
            "title": data["title"].strip(),
            "company": data["company"].strip(),
            "location": data["location"].strip(),
            "salary": data["salary"].strip(),
            "type": data["type"].strip(),
            "description": data["description"].strip(),
            "tags": data.get("tags", []),
            "featured": bool(data.get("featured", False)),
            "category": data.get("category", "").strip(),
            "posted": datetime.utcnow().strftime("%Y-%m-%d"),
            "logo_color": color,
            "icon": data["company"][:2].upper() if data.get("company") else "JP",
        }
        jobs.append(new_job)
        self._write(jobs)
        return new_job

    def update_job(self, job_id, data):
        jobs = self._read()
        for job in jobs:
            if job["id"] == job_id:
                for field in REQUIRED_JOB_FIELDS + ["category"]:
                    if field in data:
                        job[field] = data[field].strip() if isinstance(data[field], str) else data[field]
                if "tags" in data:
                    job["tags"] = data["tags"]
                if "featured" in data:
                    job["featured"] = bool(data["featured"])
                if data.get("company"):
                    job["icon"] = data["company"][:2].upper()
                self._write(jobs)
                return job
        return None

    def delete_job(self, job_id):
        jobs = self._read()
        remaining = [j for j in jobs if j["id"] != job_id]
        if len(remaining) == len(jobs):
            return False
        self._write(remaining)
        return True