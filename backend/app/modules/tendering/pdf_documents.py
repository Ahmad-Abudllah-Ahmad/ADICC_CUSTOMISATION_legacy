# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Award letter and rejection notice PDF generation for tendering.

After bid analysis a buyer needs two documents to close a tender:

* an **award letter** for the winning bid, and
* a **rejection notice** for every other bidder.

Both are produced here as downloadable PDFs using ``reportlab`` - the same
library and document pattern the platform already uses for the BOQ cost
estimate (see ``backend/app/modules/boq/pdf_export.py``). We deliberately do
not hand-roll a PDF byte stream here (the legacy tender summary in
``router.py`` did that with the stdlib); reusing reportlab gives us Unicode
fonts (via ``app.core.pdf_fonts``), consistent typography, and locale-aware
money formatting for free.

Money correctness: every monetary value arrives as a Decimal-as-string (the
v3 §10 contract used across tendering) and is parsed straight into ``Decimal``
with no float intermediary, so the printed totals match the stored amounts
exactly. Untrusted strings (company names, package names, notes) are escaped
before being handed to reportlab's ``Paragraph`` so a crafted bid company name
cannot inject markup or crash the parser - the same defence boq/pdf_export.py
documents as BUG-PDF01/02.
"""

from __future__ import annotations

import html
import io
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
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

# Register the bundled Unicode (DejaVu) faces with reportlab. Idempotent and
# safe at import time because reportlab is imported at module level here.
register_pdf_fonts()

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_LEFT = 22 * mm
MARGIN_RIGHT = 22 * mm
MARGIN_TOP = 24 * mm
MARGIN_BOTTOM = 20 * mm
USABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT


def _to_decimal(value: Any) -> Decimal:
    """Parse a money value to Decimal exactly, never raising (defaults to 0)."""
    try:
        if value is None or value == "":
            return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _fmt_money(value: Decimal, currency: str = "") -> str:
    """Format a Decimal with thousands separators and optional currency code.

    Locale style mirrors boq/pdf_export.py: EUR uses ``1.234,56``, CHF uses
    ``1'234.56``, everything else uses ``1,234.56``. The amount stays Decimal
    until this presentation boundary so no float drift is introduced.
    """
    code = (currency or "").strip().upper()
    quantized = value.quantize(Decimal("0.01"))
    raw = f"{quantized:,.2f}"
    if code == "EUR":
        raw = raw.replace(",", "THOU").replace(".", ",").replace("THOU", ".")
    elif code == "CHF":
        raw = raw.replace(",", "'")
    return f"{raw} {code}".strip()


def _safe_para(text: Any, style: ParagraphStyle) -> Paragraph:
    """Construct a ``Paragraph`` from possibly-untrusted user input.

    HTML metacharacters are escaped so reportlab's paraparser sees inert
    characters, not markup (BUG-PDF01/02 defence). ``None`` becomes empty.
    Newlines in free text are turned into line breaks.
    """
    if text is None:
        rendered = ""
    elif isinstance(text, str):
        rendered = text
    else:
        rendered = str(text)
    escaped = html.escape(rendered, quote=True).replace("\n", "<br/>")
    return Paragraph(escaped, style)


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "Brand",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=18,
            textColor=colors.HexColor("#1a1a2e"),
            spaceAfter=2 * mm,
        ),
        "doc_title": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=15,
            textColor=colors.HexColor("#16213e"),
            spaceBefore=6 * mm,
            spaceAfter=4 * mm,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=9,
            textColor=colors.HexColor("#666666"),
            alignment=TA_RIGHT,
            leading=12,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            alignment=TA_LEFT,
        ),
        "value": ParagraphStyle(
            "Value",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=10,
            textColor=colors.HexColor("#1a1a2e"),
            alignment=TA_LEFT,
        ),
        "value_right": ParagraphStyle(
            "ValueRight",
            parent=base["Normal"],
            fontName=BOLD_FONT,
            fontSize=11,
            textColor=colors.HexColor("#1a1a2e"),
            alignment=TA_RIGHT,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=10,
            textColor=colors.HexColor("#1d1d1f"),
            leading=15,
            spaceAfter=3 * mm,
        ),
        "note": ParagraphStyle(
            "Note",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=9,
            textColor=colors.HexColor("#444444"),
            leading=13,
            leftIndent=4 * mm,
        ),
        "signoff": ParagraphStyle(
            "Signoff",
            parent=base["Normal"],
            fontName=BODY_FONT,
            fontSize=10,
            textColor=colors.HexColor("#1d1d1f"),
            leading=15,
            spaceBefore=8 * mm,
        ),
    }


def _footer(canvas: Any, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont(BODY_FONT, 7)
    canvas.setFillColor(colors.HexColor("#999999"))
    generated = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    canvas.drawString(MARGIN_LEFT, 12 * mm, f"OpenConstructionERP  |  Generated: {generated}")
    canvas.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#e5e5ea"))
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_LEFT, 15 * mm, PAGE_WIDTH - MARGIN_RIGHT, 15 * mm)
    canvas.restoreState()


def _document(buffer: io.BytesIO, title: str) -> BaseDocTemplate:
    frame = Frame(
        MARGIN_LEFT,
        MARGIN_BOTTOM + 4 * mm,
        USABLE_WIDTH,
        PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM - 4 * mm,
        id="main",
    )
    template = PageTemplate(id="main", frames=[frame], onPage=_footer)
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title=title,
        author="OpenConstructionERP",
        subject="Tender decision · DDC-CWICR-OE",
        creator="OpenConstructionERP · DataDrivenConstruction",
        producer="OpenConstructionERP / reportlab · datadrivenconstruction.io",
        keywords="DDC-CWICR-OE-2026,OpenConstructionERP,Tendering,DataDrivenConstruction",
    )
    doc.addPageTemplates([template])
    return doc


def _header_block(styles: dict[str, ParagraphStyle], doc_label: str, ref: str) -> list[Any]:
    """Brand on the left, document label + reference + date on the right."""
    today = datetime.now(tz=UTC).strftime("%d.%m.%Y")
    left = Paragraph("OpenConstructionERP", styles["brand"])
    right = Paragraph(
        f"<b>{html.escape(doc_label)}</b><br/>Ref: {html.escape(ref)}<br/>Date: {today}",
        styles["meta"],
    )
    table = Table([[left, right]], colWidths=[USABLE_WIDTH * 0.55, USABLE_WIDTH * 0.45])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.HexColor("#1a1a2e")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
            ]
        )
    )
    return [table, Spacer(1, 6 * mm)]


def _info_table(styles: dict[str, ParagraphStyle], rows: list[tuple[str, str]]) -> Table:
    data = [[Paragraph(label, styles["label"]), _safe_para(value, styles["value"])] for label, value in rows]
    table = Table(data, colWidths=[42 * mm, USABLE_WIDTH - 42 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * mm),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def generate_award_letter_pdf(
    *,
    package_name: str,
    package_ref: str,
    project_name: str,
    company_name: str,
    contact_email: str,
    awarded_amount: str,
    currency: str,
    awarded_at: str | None = None,
    awarded_by_name: str | None = None,
    notes: str | None = None,
) -> bytes:
    """Render a letter of award for the winning bid.

    All money arrives as Decimal-as-string and is formatted at the
    presentation boundary only.
    """
    buffer = io.BytesIO()
    styles = _build_styles()
    doc = _document(buffer, f"Letter of Award - {package_name}")

    amount_dec = _to_decimal(awarded_amount)
    flow: list[Any] = []
    flow.extend(_header_block(styles, "LETTER OF AWARD", package_ref))
    flow.append(Paragraph("Notification of Contract Award", styles["doc_title"]))

    flow.append(
        _info_table(
            styles,
            [
                ("Awarded to:", company_name),
                ("Project:", project_name or "-"),
                ("Tender package:", package_name),
                ("Award date:", _fmt_date(awarded_at)),
            ],
        )
    )
    flow.append(Spacer(1, 5 * mm))

    # Awarded amount, set off in a highlighted band.
    amount_tbl = Table(
        [
            [
                Paragraph("Awarded contract sum", styles["label"]),
                Paragraph(_fmt_money(amount_dec, currency), styles["value_right"]),
            ]
        ],
        colWidths=[USABLE_WIDTH * 0.6, USABLE_WIDTH * 0.4],
    )
    amount_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e8e8ee")),
                ("LINEABOVE", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
                ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#1a1a2e")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ]
        )
    )
    flow.append(amount_tbl)
    flow.append(Spacer(1, 6 * mm))

    greeting = f"Dear {company_name}," if company_name else "Dear Sir or Madam,"
    flow.append(_safe_para(greeting, styles["body"]))
    flow.append(
        Paragraph(
            "We are pleased to inform you that, following evaluation of the bids received for the "
            "tender package above, your offer has been selected as the successful bid. The award is "
            "made for the contract sum stated above, subject to the terms of the tender documents and "
            "any agreed clarifications.",
            styles["body"],
        )
    )
    flow.append(
        Paragraph(
            "Please treat this letter as formal notification of our intention to enter into a contract "
            "with you. Our team will be in touch to formalise the contract documentation and confirm "
            "the programme.",
            styles["body"],
        )
    )

    if notes:
        flow.append(Spacer(1, 2 * mm))
        flow.append(Paragraph("<b>Notes</b>", styles["body"]))
        flow.append(_safe_para(notes, styles["note"]))

    flow.append(Paragraph("Yours faithfully,", styles["signoff"]))
    signer = awarded_by_name or project_name or "The Project Team"
    flow.append(_safe_para(signer, styles["value"]))
    if contact_email:
        flow.append(_safe_para(contact_email, styles["label"]))

    doc.build(flow)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_rejection_letter_pdf(
    *,
    package_name: str,
    package_ref: str,
    project_name: str,
    company_name: str,
    contact_email: str,
    bid_amount: str | None = None,
    currency: str = "",
    winning_amount: str | None = None,
    rejected_at: str | None = None,
    signed_by_name: str | None = None,
    reason: str | None = None,
) -> bytes:
    """Render a rejection notice for an unsuccessful bidder.

    Optionally states the bidder's own submitted amount and the awarded sum
    (both Decimal-as-string) for transparency; both are formatted at the
    presentation boundary only.
    """
    buffer = io.BytesIO()
    styles = _build_styles()
    doc = _document(buffer, f"Notice of Outcome - {package_name}")

    flow: list[Any] = []
    flow.extend(_header_block(styles, "NOTICE OF TENDER OUTCOME", package_ref))
    flow.append(Paragraph("Notification of Unsuccessful Bid", styles["doc_title"]))

    info_rows = [
        ("Bidder:", company_name),
        ("Project:", project_name or "-"),
        ("Tender package:", package_name),
        ("Date:", _fmt_date(rejected_at)),
    ]
    flow.append(_info_table(styles, info_rows))
    flow.append(Spacer(1, 5 * mm))

    greeting = f"Dear {company_name}," if company_name else "Dear Sir or Madam,"
    flow.append(_safe_para(greeting, styles["body"]))
    flow.append(
        Paragraph(
            "Thank you for the time and effort you invested in preparing your bid for the tender "
            "package above. Following a careful evaluation of all submissions, we regret to inform you "
            "that your bid has not been selected on this occasion.",
            styles["body"],
        )
    )

    # Optional transparency block: bidder's amount and the awarded sum.
    detail_rows: list[tuple[str, str]] = []
    if bid_amount is not None and bid_amount != "":
        detail_rows.append(("Your submitted bid:", _fmt_money(_to_decimal(bid_amount), currency)))
    if winning_amount is not None and winning_amount != "":
        detail_rows.append(("Awarded contract sum:", _fmt_money(_to_decimal(winning_amount), currency)))
    if detail_rows:
        flow.append(_info_table(styles, detail_rows))
        flow.append(Spacer(1, 4 * mm))

    if reason:
        flow.append(Paragraph("<b>Reason</b>", styles["body"]))
        flow.append(_safe_para(reason, styles["note"]))
        flow.append(Spacer(1, 2 * mm))

    flow.append(
        Paragraph(
            "We value your interest in working with us and would welcome your participation in future "
            "tender opportunities. Should you wish to discuss the outcome, please do not hesitate to "
            "contact us.",
            styles["body"],
        )
    )

    flow.append(Paragraph("Yours faithfully,", styles["signoff"]))
    signer = signed_by_name or project_name or "The Project Team"
    flow.append(_safe_para(signer, styles["value"]))
    if contact_email:
        flow.append(_safe_para(contact_email, styles["label"]))

    doc.build(flow)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def _fmt_date(iso_str: str | None) -> str:
    """Render an ISO timestamp as ``dd.mm.YYYY``; fall back to today / raw."""
    if not iso_str:
        return datetime.now(tz=UTC).strftime("%d.%m.%Y")
    try:
        normalized = iso_str.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso_str)


__all__ = ["generate_award_letter_pdf", "generate_rejection_letter_pdf"]
