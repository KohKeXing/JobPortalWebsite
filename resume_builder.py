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
import uuid
import datetime
import html
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from typing import Dict, Any, List

from werkzeug.utils import secure_filename
from supabase_client import get_supabase_client
from file_encryption import encrypt_bytes, decrypt_bytes


def _safe_decrypt(raw_content: bytes) -> bytes:
    """Decrypt storage content, but tolerate files uploaded before
    encryption was added — those are still plain PDF/DOCX bytes in the
    bucket, so a decrypt failure there is expected, not an error."""
    try:
        return decrypt_bytes(raw_content)
    except RuntimeError:
        return raw_content

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


# ======================================================================
# WEB APP BACKEND STORAGE AND DOCUMENT GENERATION
# ======================================================================

RESUME_BUCKET = "resume-uploads"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_RESUME_PAGES = 10
MAX_COVER_LETTER_PAGES = 5
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_COVER_LETTER_EXTENSIONS = {".pdf", ".docx"}
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}
RESUME_COLUMNS = (
    "id,name,type,file_name,stored_file_name,file_format,storage_bucket,"
    "storage_path,layout,data,last_modified,owner_key"
)


def _utc_timestamp():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _api_resume(row):
    """Map Supabase columns to the field names already used by the UI."""
    record = {
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("type"),
        "lastModified": row.get("last_modified"),
        "ownerKey": row.get("owner_key"),
    }
    if row.get("file_name") or row.get("stored_file_name"):
        record.update(
            {
                "fileName": row.get("file_name"),
                "storedFileName": row.get("stored_file_name"),
                "fileFormat": row.get("file_format"),
            }
        )
    if row.get("type") == "builder":
        record.update(
            {
                "layout": row.get("layout") or "modern",
                "data": row.get("data") or {},
            }
        )
    return record


def _validate_pdf(content, max_pages):
    """Validate that an uploaded PDF is readable and within the page limit."""
    try:
        reader = PdfReader(BytesIO(content))

        if reader.is_encrypted:
            raise ValueError(
                "Password-protected PDF files are not allowed."
            )

        page_count = len(reader.pages)
        print("Detected PDF pages:", page_count)

        if page_count == 0:
            raise ValueError(
                "The uploaded PDF does not contain any pages."
            )

        if page_count > max_pages:
            raise ValueError(
                f"The uploaded PDF has {page_count} pages. "
                f"The maximum allowed is {max_pages} pages."
            )

    except ValueError:
        raise
    except PdfReadError as exc:
        raise ValueError(
            "The uploaded PDF is corrupted or invalid."
        ) from exc
    except Exception as exc:
        raise ValueError(
            f"The uploaded PDF could not be read: {str(exc)}"
        ) from exc


def _read_upload(
    file_storage,
    allowed_extensions,
    max_pages=None,
):
    original_name = file_storage.filename or "uploaded_file"
    extension = Path(original_name).suffix.lower()

    if extension not in allowed_extensions:
        raise ValueError("Only PDF and DOCX files are supported.")

    safe_name = secure_filename(original_name)
    if not safe_name:
        safe_name = f"uploaded_file{extension}"

    file_storage.stream.seek(0)
    content = file_storage.stream.read()

    print("Upload filename:", safe_name)
    print("Upload extension:", extension)
    print("Upload size:", len(content), "bytes")

    if not content:
        raise ValueError("The uploaded file is empty.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("The uploaded file must not exceed 10 MB.")

    # Page limits apply only to PDF files. DOCX files still upload normally.
    if extension == ".pdf" and max_pages is not None:
        _validate_pdf(content, max_pages)

    # Reset the stream in case another part of the application needs it.
    file_storage.stream.seek(0)
    return safe_name, extension, content


def _clean_text(value):
    return str(value or "").strip()


def _description_lines(value):
    lines = []
    for line in _clean_text(value).splitlines():
        cleaned = re.sub(r"^[\s\u2022\-*]+", "", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _output_format(value):
    output_format = _clean_text(value).lower().lstrip(".")
    if output_format not in {"pdf", "docx"}:
        raise ValueError("Choose either PDF or DOCX as the resume format.")
    return output_format


def _accent_hex(data, layout):
    defaults = {
        "modern": "#2563EB",
        "tech": "#0F766E",
        "elegant": "#7E22CE",
        "minimalist": "#334155",
    }
    accent = _clean_text((data or {}).get("accentColor"))
    if re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        return accent.upper()
    return defaults.get(layout, defaults["modern"])


def _generate_pdf_resume(name, layout, data):
    """Create a genuine, multi-page PDF resume in memory."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF generation requires reportlab. "
            "Run: python -m pip install reportlab"
        ) from exc

    data = data or {}
    info = data.get("personalInfo") or {}
    accent = colors.HexColor(_accent_hex(data, layout))
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=_clean_text(name) or "Resume",
        author=_clean_text(info.get("name")) or "JobPortal Candidate",
    )

    font_map = {
        "modern": ("Helvetica", "Helvetica-Bold"),
        "tech": ("Courier", "Courier-Bold"),
        "elegant": ("Times-Roman", "Times-Bold"),
        "minimalist": ("Times-Roman", "Times-Bold"),
    }
    body_font, bold_font = font_map.get(layout, font_map["modern"])
    centered_header = layout in {"elegant", "minimalist"}
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ResumeName",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=22,
        leading=26,
        textColor=accent,
        alignment=TA_CENTER if centered_header else TA_LEFT,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="ResumeTitle",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER if centered_header else TA_LEFT,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ResumeContact",
        parent=styles["Normal"],
        fontName=body_font,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#64748B"),
        alignment=TA_CENTER if centered_header else TA_LEFT,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="ResumeSection",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=10,
        leading=13,
        textColor=accent,
        spaceBefore=8,
        spaceAfter=5,
        uppercase=True,
    ))
    styles.add(ParagraphStyle(
        name="ResumeBody",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=9.2,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ResumeItemTitle",
        parent=styles["BodyText"],
        fontName=bold_font,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#0F172A"),
    ))
    styles.add(ParagraphStyle(
        name="ResumeDate",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#64748B"),
        alignment=2,
    ))
    styles.add(ParagraphStyle(
        name="ResumeBullet",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=8.8,
        leading=12,
        leftIndent=10,
        firstLineIndent=-7,
        bulletIndent=0,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2,
    ))

    story = []
    person_name = _clean_text(info.get("name")) or _clean_text(name)
    story.append(Paragraph(html.escape(person_name or "Candidate"), styles["ResumeName"]))
    if _clean_text(info.get("title")):
        story.append(Paragraph(
            html.escape(_clean_text(info.get("title"))),
            styles["ResumeTitle"],
        ))
    contact = [
        _clean_text(info.get("email")),
        _clean_text(info.get("phone")),
        _clean_text(info.get("location")),
        _clean_text(info.get("website")),
    ]
    contact = [html.escape(value) for value in contact if value]
    if contact:
        story.append(Paragraph(" &bull; ".join(contact), styles["ResumeContact"]))
    story.append(Table(
        [[""]],
        colWidths=[document.width],
        rowHeights=[1],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), accent),
            ("LINEBELOW", (0, 0), (-1, -1), 0, accent),
        ]),
    ))
    story.append(Spacer(1, 5))

    def add_section(title):
        story.append(Paragraph(html.escape(title.upper()), styles["ResumeSection"]))

    summary = _clean_text(info.get("summary"))
    if summary:
        add_section("Professional Summary")
        story.append(Paragraph(
            html.escape(summary).replace("\n", "<br/>"),
            styles["ResumeBody"],
        ))

    experiences = data.get("experience") or []
    if experiences:
        add_section("Experience")
        for item in experiences:
            role = html.escape(_clean_text(item.get("role")) or "Role")
            company = html.escape(_clean_text(item.get("company")))
            dates = " - ".join(
                value for value in [
                    _clean_text(item.get("startDate")),
                    _clean_text(item.get("endDate")),
                ] if value
            )
            block = [
                Table(
                    [[
                        Paragraph(role, styles["ResumeItemTitle"]),
                        Paragraph(html.escape(dates), styles["ResumeDate"]),
                    ]],
                    colWidths=[document.width * 0.72, document.width * 0.28],
                    style=TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ]),
                ),
            ]
            if company:
                block.append(Paragraph(company, styles["ResumeBody"]))
            for line in _description_lines(item.get("description")):
                block.append(Paragraph(
                    html.escape(line),
                    styles["ResumeBullet"],
                    bulletText="\u2022",
                ))
            block.append(Spacer(1, 4))
            story.append(KeepTogether(block))

    education = data.get("education") or []
    if education:
        add_section("Education")
        for item in education:
            qualification = " in ".join(
                value for value in [
                    _clean_text(item.get("degree")),
                    _clean_text(item.get("field")),
                ] if value
            )
            school = _clean_text(item.get("school"))
            dates = " - ".join(
                value for value in [
                    _clean_text(item.get("startDate")),
                    _clean_text(item.get("endDate")),
                ] if value
            )
            story.append(KeepTogether([
                Table(
                    [[
                        Paragraph(
                            html.escape(qualification or "Qualification"),
                            styles["ResumeItemTitle"],
                        ),
                        Paragraph(html.escape(dates), styles["ResumeDate"]),
                    ]],
                    colWidths=[document.width * 0.72, document.width * 0.28],
                    style=TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                    ]),
                ),
                Paragraph(html.escape(school), styles["ResumeBody"]),
                Spacer(1, 3),
            ]))

    projects = data.get("projects") or []
    if projects:
        add_section("Key Projects")
        for item in projects:
            block = [
                Paragraph(
                    html.escape(_clean_text(item.get("name")) or "Project"),
                    styles["ResumeItemTitle"],
                ),
            ]
            if _clean_text(item.get("description")):
                block.append(Paragraph(
                    html.escape(_clean_text(item.get("description"))),
                    styles["ResumeBody"],
                ))
            technologies = [
                _clean_text(value)
                for value in (item.get("technologies") or [])
                if _clean_text(value)
            ]
            if technologies:
                block.append(Paragraph(
                    "<b>Technologies:</b> " + html.escape(", ".join(technologies)),
                    styles["ResumeBody"],
                ))
            block.append(Spacer(1, 3))
            story.append(KeepTogether(block))

    skills = [
        _clean_text(value)
        for value in (data.get("skills") or [])
        if _clean_text(value)
    ]
    if skills:
        add_section("Core Skills")
        story.append(Paragraph(
            " &bull; ".join(html.escape(value) for value in skills),
            styles["ResumeBody"],
        ))

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#E2E8F0"))
        canvas.line(17 * mm, 11 * mm, A4[0] - 17 * mm, 11 * mm)
        canvas.setFont(body_font, 7.5)
        canvas.setFillColor(colors.HexColor("#94A3B8"))
        canvas.drawRightString(
            A4[0] - 17 * mm,
            7 * mm,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


def _generate_docx_resume(name, layout, data):
    """Create a genuine Microsoft Word DOCX resume in memory."""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Mm, Pt, RGBColor
    except ImportError as exc:
        raise RuntimeError(
            "DOCX generation requires python-docx. "
            "Run: python -m pip install python-docx"
        ) from exc

    data = data or {}
    info = data.get("personalInfo") or {}
    accent = _accent_hex(data, layout).lstrip("#")
    accent_color = RGBColor.from_string(accent)
    font_map = {
        "modern": "Aptos",
        "tech": "Consolas",
        "elegant": "Georgia",
        "minimalist": "Georgia",
    }
    font_name = font_map.get(layout, font_map["modern"])
    centered_header = layout in {"elegant", "minimalist"}

    document = Document()
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(15)
    section.bottom_margin = Mm(15)
    section.left_margin = Mm(18)
    section.right_margin = Mm(18)

    normal = document.styles["Normal"]
    normal.font.name = font_name
    normal.font.size = Pt(9.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)

    def set_paragraph_spacing(paragraph, before=0, after=0, line=1.05):
        paragraph.paragraph_format.space_before = Pt(before)
        paragraph.paragraph_format.space_after = Pt(after)
        paragraph.paragraph_format.line_spacing = line

    def shade_paragraph(paragraph, fill):
        properties = paragraph._p.get_or_add_pPr()
        shading = OxmlElement("w:shd")
        shading.set(qn("w:fill"), fill)
        properties.append(shading)

    def add_section_heading(title):
        paragraph = document.add_paragraph()
        set_paragraph_spacing(paragraph, before=7, after=3)
        run = paragraph.add_run(title.upper())
        run.bold = True
        run.font.name = font_name
        run.font.size = Pt(10)
        run.font.color.rgb = accent_color
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "2")
        bottom.set(qn("w:color"), accent)
        border.append(bottom)
        paragraph._p.get_or_add_pPr().append(border)

    header = document.add_paragraph()
    header.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER
        if centered_header
        else WD_ALIGN_PARAGRAPH.LEFT
    )
    set_paragraph_spacing(header, after=1)
    name_run = header.add_run(
        _clean_text(info.get("name")) or _clean_text(name) or "Candidate"
    )
    name_run.bold = True
    name_run.font.name = font_name
    name_run.font.size = Pt(21)
    name_run.font.color.rgb = accent_color

    if _clean_text(info.get("title")):
        title_paragraph = document.add_paragraph()
        title_paragraph.alignment = header.alignment
        set_paragraph_spacing(title_paragraph, after=2)
        title_run = title_paragraph.add_run(_clean_text(info.get("title")))
        title_run.font.name = font_name
        title_run.font.size = Pt(11)
        title_run.font.color.rgb = RGBColor(71, 85, 105)

    contact_values = [
        _clean_text(info.get("email")),
        _clean_text(info.get("phone")),
        _clean_text(info.get("location")),
        _clean_text(info.get("website")),
    ]
    contact_values = [value for value in contact_values if value]
    if contact_values:
        contact = document.add_paragraph()
        contact.alignment = header.alignment
        set_paragraph_spacing(contact, after=5)
        contact_run = contact.add_run("  •  ".join(contact_values))
        contact_run.font.name = font_name
        contact_run.font.size = Pt(8.5)
        contact_run.font.color.rgb = RGBColor(100, 116, 139)

    accent_bar = document.add_paragraph()
    set_paragraph_spacing(accent_bar, after=3)
    shade_paragraph(accent_bar, accent)
    accent_bar.add_run(" ")

    summary = _clean_text(info.get("summary"))
    if summary:
        add_section_heading("Professional Summary")
        paragraph = document.add_paragraph(summary)
        set_paragraph_spacing(paragraph, after=3)

    experiences = data.get("experience") or []
    if experiences:
        add_section_heading("Experience")
        for item in experiences:
            paragraph = document.add_paragraph()
            set_paragraph_spacing(paragraph, before=2, after=0)
            role = paragraph.add_run(_clean_text(item.get("role")) or "Role")
            role.bold = True
            dates = " - ".join(
                value for value in [
                    _clean_text(item.get("startDate")),
                    _clean_text(item.get("endDate")),
                ] if value
            )
            if dates:
                date_run = paragraph.add_run(f"  |  {dates}")
                date_run.italic = True
                date_run.font.color.rgb = RGBColor(100, 116, 139)
            company_name = _clean_text(item.get("company"))
            if company_name:
                company = document.add_paragraph(company_name)
                set_paragraph_spacing(company, after=1)
                company.runs[0].font.color.rgb = accent_color
            for line in _description_lines(item.get("description")):
                bullet = document.add_paragraph(line, style="List Bullet")
                set_paragraph_spacing(bullet, after=0)

    education = data.get("education") or []
    if education:
        add_section_heading("Education")
        for item in education:
            qualification = " in ".join(
                value for value in [
                    _clean_text(item.get("degree")),
                    _clean_text(item.get("field")),
                ] if value
            )
            dates = " - ".join(
                value for value in [
                    _clean_text(item.get("startDate")),
                    _clean_text(item.get("endDate")),
                ] if value
            )
            paragraph = document.add_paragraph()
            set_paragraph_spacing(paragraph, before=2, after=0)
            paragraph.add_run(qualification or "Qualification").bold = True
            if dates:
                date_run = paragraph.add_run(f"  |  {dates}")
                date_run.italic = True
                date_run.font.color.rgb = RGBColor(100, 116, 139)
            school = document.add_paragraph(_clean_text(item.get("school")))
            set_paragraph_spacing(school, after=1)

    projects = data.get("projects") or []
    if projects:
        add_section_heading("Key Projects")
        for item in projects:
            paragraph = document.add_paragraph()
            set_paragraph_spacing(paragraph, before=2, after=0)
            paragraph.add_run(
                _clean_text(item.get("name")) or "Project"
            ).bold = True
            if _clean_text(item.get("description")):
                description = document.add_paragraph(
                    _clean_text(item.get("description"))
                )
                set_paragraph_spacing(description, after=0)
            technologies = [
                _clean_text(value)
                for value in (item.get("technologies") or [])
                if _clean_text(value)
            ]
            if technologies:
                technology = document.add_paragraph()
                set_paragraph_spacing(technology, after=1)
                technology.add_run("Technologies: ").bold = True
                technology.add_run(", ".join(technologies))

    skills = [
        _clean_text(value)
        for value in (data.get("skills") or [])
        if _clean_text(value)
    ]
    if skills:
        add_section_heading("Core Skills")
        skills_paragraph = document.add_paragraph("  •  ".join(skills))
        set_paragraph_spacing(skills_paragraph, after=1)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("JobPortal Resume")
    footer_run.font.name = font_name
    footer_run.font.size = Pt(7.5)
    footer_run.font.color.rgb = RGBColor(148, 163, 184)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _generate_builder_document(name, layout, data, output_format):
    output_format = _output_format(output_format)
    if output_format == "pdf":
        return _generate_pdf_resume(name, layout, data)
    return _generate_docx_resume(name, layout, data)


class ResumeStorage:
    """Supabase Database and private Storage CRUD for resumes."""

    def __init__(self, client=None):
        self._provided_client = client

    @property
    def client(self):
        return self._provided_client or get_supabase_client()

    def get_resumes(self):
        response = (
            self.client.table("resumes")
            .select(RESUME_COLUMNS)
            .order("last_modified", desc=True)
            .execute()
        )
        return [_api_resume(row) for row in (response.data or [])]

    def get_resume(self, resume_id):
        response = (
            self.client.table("resumes")
            .select(RESUME_COLUMNS)
            .eq("id", resume_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return _api_resume(rows[0]) if rows else None

    def add_uploaded_resume(self, file_storage, owner_key=None):
        safe_name, extension, content = _read_upload(
            file_storage,
            ALLOWED_RESUME_EXTENSIONS,
            MAX_RESUME_PAGES,
        )

        stored_name = f"{uuid.uuid4().hex}{extension}"
        storage_path = f"unassigned/{stored_name}"
        bucket = self.client.storage.from_(RESUME_BUCKET)

        print("Validation passed.")
        print("Uploading to bucket:", RESUME_BUCKET)
        print("Storage path:", storage_path)

        try:
            bucket.upload(
                path=storage_path,
                file=encrypt_bytes(content),
                file_options={
                    "content-type": CONTENT_TYPES[extension],
                    "upsert": "false",
                },
            )
            print("Supabase file upload successful.")
        except Exception as exc:
            print("SUPABASE STORAGE ERROR:", repr(exc))
            raise RuntimeError(
                f"Supabase Storage upload failed: {str(exc)}"
            ) from exc

        row = {
            "id": "res-" + uuid.uuid4().hex[:12],
            "name": Path(safe_name).stem,
            "type": "upload",
            "file_name": safe_name,
            "stored_file_name": stored_name,
            "file_format": extension.lstrip("."),
            "storage_bucket": RESUME_BUCKET,
            "storage_path": storage_path,
            "last_modified": _utc_timestamp(),
            "owner_key": owner_key,
        }

        try:
            response = self.client.table("resumes").insert(row).execute()
            print("Resume database record created successfully.")
        except Exception as exc:
            print("SUPABASE DATABASE ERROR:", repr(exc))
            try:
                bucket.remove([storage_path])
                print("Uploaded file removed after database failure.")
            except Exception as cleanup_exc:
                print("FILE CLEANUP ERROR:", repr(cleanup_exc))
            raise RuntimeError(
                f"Resume database insert failed: {str(exc)}"
            ) from exc

        rows = response.data or []
        if not rows:
            try:
                bucket.remove([storage_path])
            except Exception:
                pass
            raise RuntimeError(
                "The resume was uploaded, but no database record was returned."
            )

        return _api_resume(rows[0])

    def _store_generated_document(
        self,
        name,
        layout,
        data,
        output_format,
    ):
        output_format = _output_format(output_format)
        content = _generate_builder_document(
            name,
            layout,
            data,
            output_format,
        )
        if not content:
            raise RuntimeError("The generated resume file is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("The generated resume must not exceed 10 MB.")

        safe_stem = secure_filename(
            Path(name or "resume").stem
        ) or "resume"
        extension = f".{output_format}"
        original_name = f"{safe_stem}{extension}"
        stored_name = f"{uuid.uuid4().hex}{extension}"
        storage_path = f"unassigned/{stored_name}"
        self.client.storage.from_(RESUME_BUCKET).upload(
            path=storage_path,
            file=encrypt_bytes(content),
            file_options={
                "content-type": CONTENT_TYPES[extension],
                "upsert": "false",
            },
        )
        return {
            "file_name": original_name,
            "stored_file_name": stored_name,
            "file_format": output_format,
            "storage_bucket": RESUME_BUCKET,
            "storage_path": storage_path,
        }

    def add_builder_resume(
        self,
        name,
        layout,
        data,
        output_format,
        owner_key=None,
    ):
        name = name or "Untitled Resume"
        layout = layout or "modern"
        data = data or {}
        stored_file = self._store_generated_document(
            name,
            layout,
            data,
            output_format,
        )
        row = {
            "id": "res-" + uuid.uuid4().hex[:12],
            "name": name,
            "type": "builder",
            "layout": layout,
            "data": data,
            **stored_file,
            "last_modified": _utc_timestamp(),
            "owner_key": owner_key,
        }
        try:
            response = self.client.table("resumes").insert(row).execute()
        except Exception:
            self.client.storage.from_(RESUME_BUCKET).remove(
                [stored_file["storage_path"]]
            )
            raise
        return _api_resume(response.data[0])

    def update_resume(self, resume_id, updates):
        existing_response = (
            self.client.table("resumes")
            .select(RESUME_COLUMNS)
            .eq("id", resume_id)
            .limit(1)
            .execute()
        )
        existing_rows = existing_response.data or []
        if not existing_rows:
            return None
        existing = existing_rows[0]

        field_map = {
            "name": "name",
            "layout": "layout",
            "data": "data",
        }
        changes = {
            database_field: updates[api_field]
            for api_field, database_field in field_map.items()
            if api_field in updates
        }
        changes["last_modified"] = _utc_timestamp()

        new_file = None
        builder_fields_changed = any(
            field in updates for field in ("name", "layout", "data", "outputFormat")
        )
        if existing.get("type") == "builder" and builder_fields_changed:
            output_format = (
                updates.get("outputFormat")
                or existing.get("file_format")
            )
            if not output_format:
                raise ValueError(
                    "Choose PDF or DOCX before saving this resume."
                )
            name = changes.get("name", existing.get("name"))
            layout = changes.get("layout", existing.get("layout") or "modern")
            data = changes.get("data", existing.get("data") or {})
            new_file = self._store_generated_document(
                name,
                layout,
                data,
                output_format,
            )
            changes.update(new_file)

        try:
            response = (
                self.client.table("resumes")
                .update(changes)
                .eq("id", resume_id)
                .execute()
            )
        except Exception:
            if new_file:
                self.client.storage.from_(RESUME_BUCKET).remove(
                    [new_file["storage_path"]]
                )
            raise

        old_storage_path = existing.get("storage_path")
        if (
            new_file
            and old_storage_path
            and old_storage_path != new_file["storage_path"]
        ):
            try:
                self.client.storage.from_(
                    existing.get("storage_bucket") or RESUME_BUCKET
                ).remove([old_storage_path])
            except Exception:
                # The new database/file record is valid even if an old object
                # was already missing.
                pass

        rows = response.data or []
        if rows:
            return _api_resume(rows[0])
        return self.get_resume(resume_id)

    def delete_resume(self, resume_id):
        response = (
            self.client.table("resumes")
            .select(RESUME_COLUMNS)
            .eq("id", resume_id)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return False

        row = rows[0]
        self.client.table("resumes").delete().eq("id", resume_id).execute()
        if row.get("storage_path"):
            self.client.storage.from_(
                row.get("storage_bucket") or RESUME_BUCKET
            ).remove([row["storage_path"]])
        return True

    def download_uploaded_resume(self, stored_filename):
        response = (
            self.client.table("resumes")
            .select(
                "id,file_name,file_format,storage_bucket,storage_path,"
                "stored_file_name,owner_key"
            )
            .eq("stored_file_name", stored_filename)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None

        row = rows[0]
        extension = "." + (row.get("file_format") or "pdf").lower()
        encrypted_content = self.client.storage.from_(
            row.get("storage_bucket") or RESUME_BUCKET
        ).download(row["storage_path"])
        content = _safe_decrypt(encrypted_content)
        return {
            "content": content,
            "file_name": row.get("file_name") or stored_filename,
            "content_type": CONTENT_TYPES.get(
                extension,
                "application/octet-stream",
            ),
            "resume_id": row.get("id"),
            "owner_key": row.get("owner_key"),
        }


def save_cover_letter_file(file_storage):
    """Upload a cover letter to the private resume bucket."""
    safe_name, extension, content = _read_upload(
        file_storage,
        ALLOWED_COVER_LETTER_EXTENSIONS,
        MAX_COVER_LETTER_PAGES,
    )
    stored_name = f"{uuid.uuid4().hex}{extension}"
    get_supabase_client().storage.from_(RESUME_BUCKET).upload(
        path=f"cover-letters/{stored_name}",
        file=encrypt_bytes(content),
        file_options={
            "content-type": CONTENT_TYPES[extension],
            "upsert": "false",
        },
    )
    return {
        "originalName": safe_name,
        "storedFileName": stored_name,
    }


def download_cover_letter_file(stored_filename):
    """Download a cover letter file from Supabase Storage."""
    extension = Path(stored_filename).suffix.lower()
    if extension not in ALLOWED_COVER_LETTER_EXTENSIONS:
        return None
    try:
        encrypted_content = get_supabase_client().storage.from_(RESUME_BUCKET).download(
            f"cover-letters/{stored_filename}"
        )
    except Exception:
        return None
    content = _safe_decrypt(encrypted_content)
    return {
        "content": content,
        "file_name": stored_filename,
        "content_type": CONTENT_TYPES[extension],
    }


def delete_cover_letter_file(stored_filename):
    """Delete a cover letter file from Supabase Storage."""
    if not stored_filename:
        return
    try:
        get_supabase_client().storage.from_(RESUME_BUCKET).remove(
            [f"cover-letters/{stored_filename}"]
        )
    except Exception:
        # The application row is still deleted even if an old file is missing.
        pass


# ======================================================================
# INTERACTIVE CLI COMPANION TOOL
# ======================================================================
# Everything below this point is the standalone terminal tool described
# in the module docstring at the top of this file. It only runs when you
# execute `python resume_builder.py` directly (see the __main__ guard at
# the bottom) — importing ResumeStorage above does not trigger any of it.
# ======================================================================

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