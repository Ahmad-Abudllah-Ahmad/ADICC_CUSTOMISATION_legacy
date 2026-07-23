# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""PDF report generation for a single daily site diary.

Renders one diary into a clean, single-document PDF using reportlab
(already a platform dependency - see ``boq/pdf_export.py`` for the same
conventions). The layout is:

- Header band: project name + diary date + status badge.
- Overview: site supervisor, labour / equipment counts, completeness.
- Weather: the day's weather readings (temperature, wind, precipitation,
  conditions), falling back to the diary's ``weather_summary`` snapshot
  when no granular records exist.
- Work performed / events: diary entries grouped by type (work,
  deliveries, inspections, incidents, visitors, general notes).
- Notes: the free-text diary notes block.
- Footer: author / supervisor line plus a generated-at timestamp and a
  page number on every page.

Security note (mirrors BUG-PDF01 / BUG-PDF02 in ``boq/pdf_export.py``):
    ReportLab's ``Paragraph`` parses a subset of HTML. Any string that
    originates outside the application (entry titles, descriptions,
    location labels, weather text, the project name, notes) is escaped
    with ``html.escape`` via :func:`_safe_para` before it reaches the
    parser, so a payload like ``<font color="white">x</font>`` renders
    inert and ``<img onerror=...>`` cannot crash paraparser.
"""

from __future__ import annotations

import html
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.pdf_branding import branded_cover_brand, branded_doc_metadata, branded_header_logo
from app.core.pdf_fonts import BODY_FONT, BOLD_FONT, register_pdf_fonts

# Register the bundled Unicode (DejaVu) faces so Cyrillic / Greek / accented
# Latin text renders as glyphs rather than tofu boxes. Idempotent and safe.
register_pdf_fonts()

# Page geometry (A4, matching the BOQ export so both reports look related).
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 20 * mm
MARGIN_RIGHT = 20 * mm
MARGIN_TOP = 22 * mm
MARGIN_BOTTOM = 18 * mm
USABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT

# Human-readable labels for the diary entry types declared in schemas.py.
_ENTRY_TYPE_LABELS: dict[str, str] = {
    "visitor": "Visitors",
    "event": "Events",
    "delivery": "Materials delivered",
    "completion": "Work performed",
    "incident_summary": "Safety and incidents",
    "inspection_summary": "Inspections",
    "photo_note": "Photo notes",
    "general": "General notes",
}
# Display order for the entry sections (work first, housekeeping last).
_ENTRY_TYPE_ORDER: tuple[str, ...] = (
    "completion",
    "event",
    "delivery",
    "inspection_summary",
    "incident_summary",
    "visitor",
    "photo_note",
    "general",
)


def _safe_para(text: Any, style: ParagraphStyle) -> Paragraph:
    """Construct a ``Paragraph`` from possibly-untrusted user input.

    HTML metacharacters in ``text`` are escaped via ``html.escape`` so
    ReportLab's paraparser sees inert characters, not markup. ``None``
    becomes an empty string; other non-string values are coerced through
    ``str`` before escaping.

    Args:
        text: The value to render. May be ``None`` or any type.
        style: The paragraph style to apply.

    Returns:
        A ``Paragraph`` with the escaped text.
    """
    if text is None:
        rendered = ""
    elif isinstance(text, str):
        rendered = text
    else:
        rendered = str(text)
    return Paragraph(html.escape(rendered, quote=True), style)


def _fmt_number(value: Any, decimals: int = 1) -> str:
    """Format a numeric value (int / float / Decimal) for display.

    Args:
        value: The value to format. ``None`` renders as a dash.
        decimals: Number of decimal places to keep.

    Returns:
        A formatted string, or ``"-"`` when the value is missing or not
        numeric.
    """
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number == int(number):
        return str(int(number))
    return f"{number:.{decimals}f}"


def _build_styles() -> dict[str, ParagraphStyle]:
    """Build the paragraph styles used throughout the diary PDF."""
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "Brand",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=16,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "header_date": ParagraphStyle(
            "HeaderDate",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=11,
            textColor=colors.HexColor("#e8e8ee"),
            alignment=TA_LEFT,
        ),
        "status": ParagraphStyle(
            "Status",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=11,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=11,
            textColor=colors.HexColor("#16213e"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=9,
            textColor=colors.HexColor("#666666"),
        ),
        "value": ParagraphStyle(
            "Value",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=9,
            textColor=colors.HexColor("#1a1a2e"),
        ),
        "cell": ParagraphStyle(
            "Cell",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=8,
            textColor=colors.HexColor("#333333"),
            leading=11,
        ),
        "cell_head": ParagraphStyle(
            "CellHead",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=8,
            textColor=colors.white,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=9,
            textColor=colors.HexColor("#333333"),
            leading=13,
        ),
        "empty": ParagraphStyle(
            "Empty",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=9,
            textColor=colors.HexColor("#999999"),
        ),
    }


def _make_footer(author_line: str, generated_date: str) -> Any:
    """Return an ``onPage`` callback drawing the footer on every page.

    Args:
        author_line: Pre-escaped, plain-text author / supervisor line.
        generated_date: The generated-at timestamp string.

    Returns:
        A ``func(canvas, doc)`` callable for a reportlab PageTemplate.
    """

    def _footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN_LEFT, 13 * mm, PAGE_WIDTH - MARGIN_RIGHT, 13 * mm)
        canvas.setFont(BODY_FONT, 7)
        canvas.setFillColor(colors.HexColor("#999999"))
        # Footer carries the workspace brand (issue #284) plus the supervisor
        # line; the brand falls back to the default name when none is set.
        brand = branded_cover_brand()
        left_text = author_line or brand
        canvas.drawString(MARGIN_LEFT, 9 * mm, left_text[:120])
        canvas.drawString(MARGIN_LEFT, 6 * mm, f"{brand}  |  Generated: {generated_date}")
        canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()
        # The uploaded white-label logo (if any) appears top-right in the header
        # margin on every page; the dark title band stays inside the content
        # frame, so they do not overlap. Issue #284 follow-up.
        branded_header_logo(canvas, doc)

    return _footer


def _build_header(
    project_name: str,
    diary_date: str,
    status: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the dark header band with project, date and status."""
    header = Table(
        [
            [
                _safe_para(project_name or "Daily Site Diary", styles["brand"]),
                Paragraph(html.escape((status or "open").upper(), quote=True), styles["status"]),
            ],
            [
                Paragraph(f"Daily Site Diary &nbsp;&middot;&nbsp; {html.escape(diary_date)}", styles["header_date"]),
                "",
            ],
        ],
        colWidths=[USABLE_WIDTH * 0.7, USABLE_WIDTH * 0.3],
    )
    header.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#16213e")),
                ("SPAN", (1, 0), (1, 1)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("TOPPADDING", (0, 0), (0, 0), 4 * mm),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4 * mm),
            ]
        )
    )
    return [header, Spacer(1, 5 * mm)]


def _build_overview(
    diary: Any,
    supervisor_name: str | None,
    completeness: Decimal | float | None,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the overview block (supervisor, labour, equipment, score)."""
    completeness_text = "-"
    if completeness is not None:
        try:
            completeness_text = f"{float(completeness) * 100:.0f}%"
        except (TypeError, ValueError):
            completeness_text = "-"

    rows = [
        [
            Paragraph("Site supervisor", styles["label"]),
            _safe_para(supervisor_name or "Not recorded", styles["value"]),
            Paragraph("Labour on site", styles["label"]),
            Paragraph(str(getattr(diary, "labour_count", 0) or 0), styles["value"]),
        ],
        [
            Paragraph("Completeness", styles["label"]),
            Paragraph(completeness_text, styles["value"]),
            Paragraph("Equipment on site", styles["label"]),
            Paragraph(str(getattr(diary, "equipment_count", 0) or 0), styles["value"]),
        ],
    ]
    table = Table(
        rows,
        colWidths=[USABLE_WIDTH * 0.22, USABLE_WIDTH * 0.28, USABLE_WIDTH * 0.22, USABLE_WIDTH * 0.28],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f6fa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#eeeeee")),
            ]
        )
    )
    return [Paragraph("Overview", styles["section"]), table]


def _build_weather(
    diary: Any,
    weather_records: list[Any],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the weather section.

    Prefers granular ``WeatherRecord`` rows. When none exist, falls back
    to the diary's ``weather_summary`` JSON snapshot, and finally to an
    empty-state line.
    """
    flow: list[Any] = [Paragraph("Weather", styles["section"])]

    if weather_records:
        header = [
            Paragraph("Time", styles["cell_head"]),
            Paragraph("Source", styles["cell_head"]),
            Paragraph("Temp (C)", styles["cell_head"]),
            Paragraph("Wind (km/h)", styles["cell_head"]),
            Paragraph("Precip (mm)", styles["cell_head"]),
            Paragraph("Conditions", styles["cell_head"]),
        ]
        data: list[list[Any]] = [header]
        for rec in weather_records:
            captured = getattr(rec, "captured_at", None)
            time_text = captured.strftime("%H:%M") if isinstance(captured, datetime) else "-"
            data.append(
                [
                    Paragraph(time_text, styles["cell"]),
                    _safe_para(getattr(rec, "source", "") or "-", styles["cell"]),
                    Paragraph(_fmt_number(getattr(rec, "temperature_c", None)), styles["cell"]),
                    Paragraph(_fmt_number(getattr(rec, "wind_speed_kmh", None)), styles["cell"]),
                    Paragraph(_fmt_number(getattr(rec, "precipitation_mm", None)), styles["cell"]),
                    _safe_para(getattr(rec, "conditions_text", None) or "-", styles["cell"]),
                ]
            )
        table = Table(
            data,
            colWidths=[
                USABLE_WIDTH * 0.12,
                USABLE_WIDTH * 0.16,
                USABLE_WIDTH * 0.14,
                USABLE_WIDTH * 0.16,
                USABLE_WIDTH * 0.16,
                USABLE_WIDTH * 0.26,
            ],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6fa")]),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ]
            )
        )
        flow.append(table)
        return flow

    summary = getattr(diary, "weather_summary", None) or {}
    if isinstance(summary, dict) and summary:
        parts = [f"{html.escape(str(k))}: {html.escape(str(v))}" for k, v in summary.items()]
        flow.append(Paragraph(" &nbsp;&middot;&nbsp; ".join(parts), styles["body"]))
    else:
        flow.append(Paragraph("No weather recorded for this day.", styles["empty"]))
    return flow


def _build_entries(
    entries: list[Any],
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    """Build the grouped diary-entry sections (work, deliveries, etc.)."""
    flow: list[Any] = [Paragraph("Site record", styles["section"])]

    if not entries:
        flow.append(Paragraph("No entries recorded for this diary.", styles["empty"]))
        return flow

    grouped: dict[str, list[Any]] = {}
    for entry in entries:
        grouped.setdefault(getattr(entry, "entry_type", "general") or "general", []).append(entry)

    # Stable ordering: known types first in display order, then any others.
    ordered_types = [t for t in _ENTRY_TYPE_ORDER if t in grouped]
    ordered_types += [t for t in grouped if t not in _ENTRY_TYPE_ORDER]

    for entry_type in ordered_types:
        bucket = sorted(
            grouped[entry_type],
            key=lambda e: getattr(e, "entry_time", None) or datetime.min.replace(tzinfo=UTC),
        )
        label = _ENTRY_TYPE_LABELS.get(entry_type, entry_type.replace("_", " ").title())
        block: list[Any] = [
            Paragraph(
                f"<b>{html.escape(label)}</b> ({len(bucket)})",
                styles["body"],
            )
        ]
        rows: list[list[Any]] = []
        for entry in bucket:
            etime = getattr(entry, "entry_time", None)
            time_text = etime.strftime("%H:%M") if isinstance(etime, datetime) else ""
            title = getattr(entry, "title", "") or ""
            description = getattr(entry, "description", "") or ""
            detail = title
            if description:
                detail = (
                    f"<b>{html.escape(title)}</b><br/>{html.escape(description)}" if title else html.escape(description)
                )
            else:
                detail = html.escape(title) if title else "-"
            rows.append(
                [
                    Paragraph(html.escape(time_text), styles["cell"]),
                    Paragraph(detail, styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[USABLE_WIDTH * 0.12, USABLE_WIDTH * 0.88])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.2 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * mm),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#eeeeee")),
                ]
            )
        )
        block.append(table)
        block.append(Spacer(1, 3 * mm))
        flow.append(KeepTogether(block))

    return flow


def _build_notes(diary: Any, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Build the free-text notes block."""
    notes = (getattr(diary, "notes", None) or "").strip()
    flow: list[Any] = [Paragraph("Notes", styles["section"])]
    if notes:
        # Preserve author line breaks as <br/> after escaping.
        escaped = html.escape(notes).replace("\n", "<br/>")
        flow.append(Paragraph(escaped, styles["body"]))
    else:
        flow.append(Paragraph("No additional notes.", styles["empty"]))
    return flow


def generate_diary_pdf(
    diary: Any,
    *,
    project_name: str,
    entries: list[Any] | None = None,
    weather_records: list[Any] | None = None,
    supervisor_name: str | None = None,
    completeness: Decimal | float | None = None,
) -> bytes:
    """Render a single daily site diary into PDF bytes.

    Args:
        diary: The :class:`DailyDiary` ORM row (or any object exposing the
            same attributes: ``diary_date``, ``status``, ``labour_count``,
            ``equipment_count``, ``weather_summary``, ``notes``).
        project_name: Parent project name for the header.
        entries: Diary entries to render, grouped by type. Optional.
        weather_records: Granular weather readings for the day. Optional;
            falls back to ``diary.weather_summary`` when empty.
        supervisor_name: Display name of the site supervisor. Optional.
        completeness: Completeness score in the range ``0.0`` to ``1.0``.

    Returns:
        The rendered PDF document as bytes (starts with ``b"%PDF"``).
    """
    entries = entries or []
    weather_records = weather_records or []
    styles = _build_styles()

    diary_date = str(getattr(diary, "diary_date", "") or "")
    status_text = str(getattr(diary, "status", "open") or "open")
    generated_date = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    author_line = f"Supervisor: {supervisor_name}" if supervisor_name else "Site supervisor: not recorded"

    buffer = io.BytesIO()
    frame = Frame(
        MARGIN_LEFT,
        MARGIN_BOTTOM,
        USABLE_WIDTH,
        PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM,
        id="body",
    )
    template = PageTemplate(
        id="body",
        frames=[frame],
        onPage=_make_footer(author_line, generated_date),
    )
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=f"Daily Site Diary - {diary_date}",
        author=branded_doc_metadata()["author"],
        subject="Daily Site Diary",
        creator=branded_doc_metadata()["creator"],
        producer=branded_doc_metadata()["producer"],
        keywords=branded_doc_metadata()["keywords"],
    )
    doc.addPageTemplates([template])

    flowables: list[Any] = []
    flowables.extend(_build_header(project_name, diary_date, status_text, styles))
    flowables.extend(_build_overview(diary, supervisor_name, completeness, styles))
    flowables.extend(_build_weather(diary, weather_records, styles))
    flowables.extend(_build_entries(entries, styles))
    flowables.extend(_build_notes(diary, styles))

    doc.build(flowables)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
