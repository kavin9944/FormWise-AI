"""
FormWise AI – PDF Generator Module
Generates a filled-form PDF summary from student answers and AI analysis data.

Uses ReportLab to create a clean, professional PDF containing:
  - Form title and metadata
  - All fields with student answers
  - Required/Optional badges
  - Document checklist status
  - Disclaimer footer

Security: Never includes API keys, server paths, or raw uploaded content.
"""

import io
import datetime
import html
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------------
# Font Setup – Use Helvetica (built-in). Tamil text will be transliterated
# or displayed with a note if a Tamil Unicode font is not installed.
# ---------------------------------------------------------------------------
_FONT_BODY = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_OBLIQUE = "Helvetica-Oblique"


def _safe_text(
    value: Any,
    fallback: str = "—",
    max_len: Optional[int] = None,
    escape: bool = True
) -> str:
    """Safely convert a value to a display string for PDF rendering."""
    if value is None:
        text = fallback
    else:
        text = str(value).strip()
        if not text:
            text = fallback

    if max_len is not None and max_len > 0:
        text = text[:max_len]

    if escape:
        text = html.escape(text)

    return text


def _build_styles() -> Dict[str, ParagraphStyle]:
    """Build a dictionary of named ParagraphStyles for the PDF."""
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "FWTitle",
        parent=base["Title"],
        fontName=_FONT_BOLD,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1E3A5F"),
        spaceAfter=4,
        alignment=TA_CENTER,
    )

    styles["subtitle"] = ParagraphStyle(
        "FWSubtitle",
        parent=base["Normal"],
        fontName=_FONT_OBLIQUE,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#6B7280"),
        spaceAfter=8,
        alignment=TA_CENTER,
    )

    styles["section"] = ParagraphStyle(
        "FWSection",
        parent=base["Heading2"],
        fontName=_FONT_BOLD,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1E3A5F"),
        spaceBefore=16,
        spaceAfter=8,
    )

    styles["body"] = ParagraphStyle(
        "FWBody",
        parent=base["Normal"],
        fontName=_FONT_BODY,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#374151"),
    )

    styles["small"] = ParagraphStyle(
        "FWSmall",
        parent=base["Normal"],
        fontName=_FONT_BODY,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#9CA3AF"),
    )

    styles["disclaimer"] = ParagraphStyle(
        "FWDisclaimer",
        parent=base["Normal"],
        fontName=_FONT_OBLIQUE,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#DC2626"),
        alignment=TA_CENTER,
        spaceBefore=12,
    )

    styles["field_label"] = ParagraphStyle(
        "FWFieldLabel",
        parent=base["Normal"],
        fontName=_FONT_BOLD,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1F2937"),
    )

    styles["field_value"] = ParagraphStyle(
        "FWFieldValue",
        parent=base["Normal"],
        fontName=_FONT_BODY,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#374151"),
    )

    return styles


def generate_filled_pdf(
    form_title: str,
    fields: List[Dict[str, Any]],
    student_answers: Dict[str, Any],
    analysis_data: Optional[Dict[str, Any]] = None,
    checklist_items: Optional[List[Dict[str, Any]]] = None,
    readiness_score: Optional[float] = None,
    readiness_status: Optional[str] = None,
) -> bytes:
    """
    Generates a PDF summary of the student's form responses.

    Parameters:
        form_title: The form title from AI analysis.
        fields: List of field definition dicts from Gemini analysis.
        student_answers: Dict mapping field_id/field_name to student's answer.
        analysis_data: Optional full analysis dict (for summaries, tips).
        checklist_items: Optional list of checklist item dicts.
        readiness_score: Optional readiness score (0-100).
        readiness_status: Optional status string.

    Returns:
        PDF file content as bytes.
    """
    buffer = io.BytesIO()
    styles = _build_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=_safe_text(form_title, "FormWise AI – Form Summary", escape=False),
        author="FormWise AI",
    )

    story = []

    # =========================================================================
    # 1. Header
    # =========================================================================
    story.append(Paragraph(_safe_text(form_title, "Application Form", escape=True), styles["title"]))
    story.append(Paragraph("Generated by FormWise AI – Smart Form Assistant", styles["subtitle"]))

    gen_date = datetime.datetime.now().strftime("%d %B %Y, %I:%M %p")
    story.append(Paragraph(f"Date: {gen_date}", styles["small"]))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D1D5DB")))
    story.append(Spacer(1, 8))

    # =========================================================================
    # 2. Summary (if available)
    # =========================================================================
    if analysis_data and isinstance(analysis_data, dict):
        summary_en = analysis_data.get("summary_english", "")
        if summary_en:
            story.append(Paragraph("Form Summary", styles["section"]))
            story.append(Paragraph(_safe_text(summary_en, escape=True), styles["body"]))
            story.append(Spacer(1, 6))

    # =========================================================================
    # 3. Readiness Score (if available)
    # =========================================================================
    if readiness_score is not None:
        story.append(Paragraph("Application Readiness", styles["section"]))
        score_text = f"Score: {round(readiness_score)}/100"
        if readiness_status:
            status_labels = {
                "ready_to_submit": "Ready to Submit",
                "almost_ready": "Almost Ready",
                "in_progress": "In Progress",
                "not_started": "Not Started",
            }
            label = status_labels.get(readiness_status, readiness_status)
            escaped_label = html.escape(str(label))
            score_text += f"  •  Status: {escaped_label}"
        story.append(Paragraph(score_text, styles["body"]))
        story.append(Spacer(1, 6))

    # =========================================================================
    # 4. Fields and Answers Table
    # =========================================================================
    story.append(Paragraph("Form Fields &amp; Student Answers", styles["section"]))

    if not fields:
        story.append(Paragraph("No form fields were detected.", styles["body"]))
    else:
        # Build table data
        table_data = [
            [
                Paragraph("<b>#</b>", styles["field_label"]),
                Paragraph("<b>Field / Question</b>", styles["field_label"]),
                Paragraph("<b>Type</b>", styles["field_label"]),
                Paragraph("<b>Student Answer</b>", styles["field_label"]),
                Paragraph("<b>Status</b>", styles["field_label"]),
            ]
        ]

        for idx, field in enumerate(fields, 1):
            field_id = str(field.get("field_id") or field.get("field_name") or f"field_{idx}")
            field_name = str(field.get("field_name") or field_id)
            raw_question = str(field.get("question") or field.get("label") or field_name).strip() or "—"
            raw_field_type = str(field.get("field_type") or "text").strip() or "text"
            is_required = bool(field.get("is_required", False))

            # Look up answer: try field_id, field_name, unescaped raw question
            answer = student_answers.get(field_id)
            if answer is None:
                answer = student_answers.get(field_name)
            if answer is None:
                answer = student_answers.get(raw_question)
            if answer is None and field.get("question"):
                answer = student_answers.get(str(field.get("question")).strip())

            # Determine whether answer was provided for badge coloring
            is_provided = (answer is not None and str(answer).strip() != "" and str(answer).strip() != "Not provided")
            badge = "Required" if is_required else "Optional"
            badge_color = "#DC2626" if is_required and not is_provided else (
                "#059669" if is_provided else "#6B7280"
            )

            # Safely prepare display strings (slice raw first, then HTML-escape)
            question_display = _safe_text(raw_question, max_len=80, escape=True)
            field_type_display = _safe_text(raw_field_type.capitalize(), max_len=30, escape=True)
            answer_display = _safe_text(answer, fallback="Not provided", max_len=200, escape=True)

            row = [
                Paragraph(str(idx), styles["field_value"]),
                Paragraph(question_display, styles["field_value"]),
                Paragraph(field_type_display, styles["field_value"]),
                Paragraph(answer_display, styles["field_value"]),
                Paragraph(f'<font color="{badge_color}">{badge}</font>', styles["field_value"]),
            ]
            table_data.append(row)

        col_widths = [25, 200, 55, 200, 55]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFF6FF")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 8))

    # =========================================================================
    # 5. Document Checklist (if available)
    # =========================================================================
    if checklist_items and isinstance(checklist_items, list) and len(checklist_items) > 0:
        story.append(Paragraph("Document Checklist", styles["section"]))

        cl_data = [
            [
                Paragraph("<b>Document</b>", styles["field_label"]),
                Paragraph("<b>Type</b>", styles["field_label"]),
                Paragraph("<b>Status</b>", styles["field_label"]),
            ]
        ]

        for item in checklist_items:
            raw_title = item.get("title_en") or item.get("doc_id") or "Document"
            title = _safe_text(raw_title, max_len=100, escape=True)
            mandatory = "Mandatory" if item.get("is_mandatory") else "Optional"
            matched = item.get("matched_document_id") or item.get("confirmed_doc_id")
            if matched:
                status = "✓ Confirmed"
                status_color = "#059669"
            elif item.get("suggested_document_id"):
                status = "Suggested"
                status_color = "#D97706"
            else:
                status = "Missing"
                status_color = "#DC2626"

            cl_data.append([
                Paragraph(title, styles["field_value"]),
                Paragraph(mandatory, styles["field_value"]),
                Paragraph(f'<font color="{status_color}">{status}</font>', styles["field_value"]),
            ])

        cl_table = Table(cl_data, colWidths=[250, 80, 100], repeatRows=1)
        cl_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FEF3C7")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(cl_table)
        story.append(Spacer(1, 8))

    # =========================================================================
    # 6. General Tips (if available)
    # =========================================================================
    if analysis_data and isinstance(analysis_data, dict):
        tips = analysis_data.get("general_tips_english", "")
        if tips:
            story.append(Paragraph("General Tips", styles["section"]))
            story.append(Paragraph(_safe_text(tips, escape=True), styles["body"]))
            story.append(Spacer(1, 6))

    # =========================================================================
    # 7. Disclaimer
    # =========================================================================
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E5E7EB")))
    story.append(Paragraph(
        "DISCLAIMER: This is a student-generated preview created by FormWise AI. "
        "It is NOT an official submission and should NOT be treated as a completed application. "
        "Students must verify all information and submit through official channels.",
        styles["disclaimer"]
    ))

    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
