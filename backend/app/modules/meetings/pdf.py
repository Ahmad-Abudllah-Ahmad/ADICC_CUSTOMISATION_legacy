# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Reusable PDF renderer for confirmed meeting minutes.

The minutes document (present/absent, per-agenda discussion and decision,
action items with brought-forward and overdue markers, next meeting date and
summary) is the human-confirmed record - not the raw meeting row. This module
holds the single source of truth for rendering it to bytes so both the export
endpoint and the record-publishing module (one-tap publish-and-distribute)
produce the exact same document.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.meetings.models import Meeting, MinutesRecord


def minutes_pdf_filename(meeting: Meeting, content: dict) -> str:
    """Build the download filename for a meeting's minutes PDF."""
    safe_title = str(content.get("title") or meeting.title).replace(" ", "_")[:50]
    return f"minutes_{meeting.meeting_number}_{safe_title}.pdf"


def build_minutes_pdf(meeting: Meeting, minutes: MinutesRecord, project_name: str) -> bytes:
    """Render the confirmed meeting minutes to PDF bytes.

    Args:
        meeting: the meeting row (title, number, date, project).
        minutes: the confirmed minutes record (its ``content`` JSON is the
            source of truth for the rendered document, with the meeting row as
            fallback for a few header fields).
        project_name: display name of the owning project for the header.

    Returns:
        The rendered PDF as bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    from app.core.pdf_fonts import BODY_FONT, BOLD_FONT, register_pdf_fonts

    register_pdf_fonts()

    content: dict = minutes.content if isinstance(minutes.content, dict) else {}

    PAGE_WIDTH, PAGE_HEIGHT = A4
    MARGIN = 20 * mm
    USABLE_WIDTH = PAGE_WIDTH - 2 * MARGIN

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "MinutesTitle",
        parent=styles["Normal"],
        fontName=BOLD_FONT,
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=3 * mm,
    )
    style_subtitle = ParagraphStyle(
        "MinutesSubtitle",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6 * mm,
    )
    style_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName=BOLD_FONT,
        fontSize=12,
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    )
    style_body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
    )
    style_small = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=8,
        textColor=colors.HexColor("#777777"),
    )

    elements: list = []
    elements.append(Paragraph("Meeting Minutes", style_title))
    status_tag = "ISSUED" if minutes.status == "issued" else "DRAFT"
    elements.append(Paragraph(f"{escape(project_name)} &middot; {status_tag}", style_subtitle))
    elements.append(Paragraph(escape(str(content.get("title") or meeting.title)), style_heading))

    info_data = [
        ["Date:", str(content.get("meeting_date") or meeting.meeting_date or "N/A")],
        ["Location:", str(content.get("location") or "N/A") or "N/A"],
        ["Type:", str(content.get("meeting_type") or "").replace("_", " ").title()],
        ["Meeting #:", str(content.get("meeting_number") or meeting.meeting_number)],
        ["Chairperson:", str(content.get("chairperson") or "N/A") or "N/A"],
        ["Next meeting:", str(content.get("next_meeting_date") or "Not scheduled")],
    ]
    info_table = Table(info_data, colWidths=[32 * mm, USABLE_WIDTH - 32 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("FONTNAME", (1, 0), (1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(info_table)

    # Attendance (present / absent)
    present = content.get("attendees_present") or []
    absent = content.get("attendees_absent") or []
    if present or absent:
        elements.append(Paragraph("Attendance", style_heading))
        if present:
            names = ", ".join(escape(str(a.get("name") or "")) for a in present if isinstance(a, dict))
            elements.append(Paragraph(f"<b>Present:</b> {names}", style_body))
        if absent:
            names = ", ".join(escape(str(a.get("name") or "")) for a in absent if isinstance(a, dict))
            elements.append(Paragraph(f"<b>Absent / excused:</b> {names}", style_body))

    # Agenda with discussion + decision
    agenda = content.get("agenda") or []
    if agenda:
        elements.append(Paragraph("Agenda, discussion and decisions", style_heading))
        for idx, item in enumerate(agenda, 1):
            if not isinstance(item, dict):
                continue
            topic = escape(str(item.get("topic") or ""))
            num = escape(str(item.get("number") or idx))
            req = " <font color='#b45309'>(required)</font>" if item.get("required") else ""
            elements.append(Paragraph(f"<b>{num}. {topic}</b>{req}", style_body))
            if item.get("discussion"):
                elements.append(
                    Paragraph(f"&nbsp;&nbsp;<b>Discussion:</b> {escape(str(item['discussion']))}", style_small)
                )
            if item.get("decision"):
                elements.append(Paragraph(f"&nbsp;&nbsp;<b>Decision:</b> {escape(str(item['decision']))}", style_small))
            elements.append(Spacer(1, 1.5 * mm))

    # Action items
    actions = content.get("action_items") or []
    if actions:
        elements.append(Paragraph("Action items", style_heading))
        act_data = [["#", "Action", "Owner", "Due", "Status"]]
        for idx, ai in enumerate(actions, 1):
            if not isinstance(ai, dict):
                continue
            desc = str(ai.get("description") or "")
            if ai.get("brought_forward"):
                desc = f"[Brought forward] {desc}"
            status_str = str(ai.get("status") or "open").replace("_", " ").title()
            if ai.get("overdue"):
                status_str += " (overdue)"
            act_data.append([str(idx), desc, str(ai.get("owner") or ""), str(ai.get("due_date") or ""), status_str])
        act_table = Table(
            act_data,
            colWidths=[
                USABLE_WIDTH * 0.06,
                USABLE_WIDTH * 0.44,
                USABLE_WIDTH * 0.20,
                USABLE_WIDTH * 0.13,
                USABLE_WIDTH * 0.17,
            ],
        )
        act_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                    ("FONTNAME", (0, 1), (-1, -1), BODY_FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(act_table)

    # Summary
    if content.get("summary"):
        elements.append(Paragraph("Summary", style_heading))
        elements.append(Paragraph(escape(str(content["summary"])).replace("\n", "<br/>"), style_body))

    elements.append(Spacer(1, 8 * mm))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    issued_note = ""
    if minutes.status == "issued" and minutes.issued_at:
        issued_note = f" &middot; Issued {minutes.issued_at.strftime('%Y-%m-%d %H:%M UTC')}"
    elements.append(Paragraph(f"Generated: {stamp}{issued_note}", style_small))

    buf = io.BytesIO()

    def _header_footer(canvas_obj, doc):  # type: ignore[no-untyped-def]
        canvas_obj.saveState()
        canvas_obj.setFont(BODY_FONT, 7)
        canvas_obj.setFillColor(colors.HexColor("#999999"))
        canvas_obj.drawString(MARGIN, PAGE_HEIGHT - 12 * mm, f"{project_name} - Minutes")
        canvas_obj.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, f"Page {doc.page}")
        canvas_obj.restoreState()

    frame = Frame(MARGIN, MARGIN, USABLE_WIDTH, PAGE_HEIGHT - 2 * MARGIN, id="main")
    doc = BaseDocTemplate(buf, pagesize=A4)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_header_footer)])
    doc.build(elements)

    return buf.getvalue()
