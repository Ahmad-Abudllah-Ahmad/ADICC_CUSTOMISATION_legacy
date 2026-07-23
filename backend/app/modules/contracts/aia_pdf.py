# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AIA G702/G703 payment-application PDF (US/CA/AU only).

Renders a two-part document mirroring the layout of the AIA standard forms:

* G702 - Application and Certificate for Payment (the summary face with the
  contract-sum-to-date math and the architect/owner certification block), and
* G703 - Continuation Sheet (one row per schedule-of-values line with the
  previous / this-period / stored / total / balance / retainage columns).

These are the official AIA copyrighted layouts only in spirit: this is a
clean-room functional equivalent that carries the same figures, suitable for
internal review and submission alongside the executed AIA forms. The PDF is
Unicode-safe via :mod:`app.core.pdf_fonts` (DejaVu Sans), so currency symbols
and accented names render rather than showing empty boxes.

The render function takes the dict produced by
``ContractsService.build_aia_application`` so all arithmetic stays in the pure,
unit-tested builders and the PDF layer only formats.
"""

# Copyright 2024-2026 OpenEstimate Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import html
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.pdf_fonts import BODY_FONT, BOLD_FONT, register_pdf_fonts

register_pdf_fonts()

PLACEHOLDER = "-"


def _money(value: Any, currency: str = "") -> str:
    """Format a Decimal money value as ``1,234,567.89`` with optional code."""
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal("0")
        if not d.is_finite():
            d = Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    body = f"{d.quantize(Decimal('0.01')):,.2f}"
    return f"{currency} {body}".strip() if currency else body


def _pct(value: Any) -> str:
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    return f"{d.quantize(Decimal('0.01'))}%"


def _txt(value: Any) -> str:
    if value in (None, ""):
        return PLACEHOLDER
    return html.escape(str(value))


def _safe_para(text: Any, style: ParagraphStyle) -> Paragraph:
    raw = "" if text is None else str(text)
    return Paragraph(html.escape(raw), style)


def render_aia_application_pdf(app: dict[str, Any]) -> bytes:
    """Render the AIA G702 + G703 application dict to PDF bytes.

    ``app`` is the structure returned by ``ContractsService.build_aia_application``.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="AIA G702/G703 Application for Payment",
    )

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("AIAH1", parent=base["Heading1"], fontName=BOLD_FONT, fontSize=14, alignment=TA_CENTER)
    h2 = ParagraphStyle("AIAH2", parent=base["Heading2"], fontName=BOLD_FONT, fontSize=10)
    body = ParagraphStyle("AIABody", parent=base["Normal"], fontName=BODY_FONT, fontSize=8)
    cell = ParagraphStyle("AIACell", parent=body, fontSize=7, leading=9)
    cell_r = ParagraphStyle("AIACellR", parent=cell, alignment=TA_RIGHT)
    cell_l = ParagraphStyle("AIACellL", parent=cell, alignment=TA_LEFT)

    currency = str(app.get("currency") or "")
    summary = app.get("summary", {}) or {}
    cert = app.get("certification", {}) or {}
    lines = app.get("lines", []) or []

    story: list[Any] = []
    story.append(Paragraph("Application and Certificate for Payment", h1))
    story.append(Paragraph("AIA Document G702 (functional equivalent)", body))
    story.append(Spacer(1, 6 * mm))

    # ── G702 header facts ──────────────────────────────────────────────
    header_rows = [
        ["Application No.", _txt(app.get("application_number")), "Period to", _txt(app.get("period_end"))],
        ["Application date", _txt(app.get("claim_date")), "Currency", _txt(currency or PLACEHOLDER)],
    ]
    header_tbl = Table(header_rows, colWidths=[40 * mm, 70 * mm, 40 * mm, 70 * mm])
    header_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("FONTNAME", (2, 0), (2, -1), BOLD_FONT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── G702 summary lines (1..9) ──────────────────────────────────────
    summary_rows = [
        ["1. Original contract sum", _money(summary.get("original_contract_sum"), currency)],
        ["2. Net change by change orders", _money(summary.get("change_orders_net"), currency)],
        ["3. Contract sum to date (1 + 2)", _money(summary.get("contract_sum_to_date"), currency)],
        ["4. Total completed and stored to date", _money(summary.get("total_completed_stored"), currency)],
        ["5. Retainage", _money(summary.get("retainage"), currency)],
        ["6. Total earned less retainage (4 - 5)", _money(summary.get("total_earned_less_retainage"), currency)],
        ["7. Less previous certificates for payment", _money(summary.get("previous_certificates_total"), currency)],
        ["8. Current payment due", _money(summary.get("current_payment_due"), currency)],
        ["9. Balance to finish including retainage", _money(summary.get("balance_to_finish"), currency)],
    ]
    summary_tbl = Table(summary_rows, colWidths=[150 * mm, 70 * mm])
    summary_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 7), (-1, 7), BOLD_FONT),
                ("BACKGROUND", (0, 7), (-1, 7), colors.whitesmoke),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(summary_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── Certification block ────────────────────────────────────────────
    story.append(Paragraph("Certification", h2))
    cert_rows = [
        ["Architect certified", _txt(cert.get("architect_certified_by")), _txt(cert.get("architect_certified_at"))],
        ["Owner certified", _txt(cert.get("owner_certified_by")), _txt(cert.get("owner_certified_at"))],
        ["Amount certified", _money(cert.get("certified_amount"), currency), ""],
    ]
    cert_tbl = Table(cert_rows, colWidths=[50 * mm, 90 * mm, 80 * mm])
    cert_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(cert_tbl)
    story.append(Spacer(1, 8 * mm))

    # ── G703 continuation sheet ────────────────────────────────────────
    story.append(Paragraph("Continuation Sheet - AIA Document G703 (functional equivalent)", h2))
    story.append(Spacer(1, 2 * mm))

    head = [
        _safe_para("A\nItem", cell_l),
        _safe_para("B\nDescription of work", cell_l),
        _safe_para("C\nScheduled value", cell_r),
        _safe_para("D\nFrom previous", cell_r),
        _safe_para("E\nThis period", cell_r),
        _safe_para("F\nStored", cell_r),
        _safe_para("G\nTotal completed", cell_r),
        _safe_para("%\n(G/C)", cell_r),
        _safe_para("H\nBalance to finish", cell_r),
        _safe_para("I\nRetainage", cell_r),
    ]
    data: list[list[Any]] = [head]
    for ln in lines:
        data.append(
            [
                _safe_para(ln.get("item_number"), cell_l),
                _safe_para(ln.get("description"), cell_l),
                Paragraph(_money(ln.get("scheduled_value")), cell_r),
                Paragraph(_money(ln.get("previous_value")), cell_r),
                Paragraph(_money(ln.get("this_period_value")), cell_r),
                Paragraph(_money(ln.get("materials_stored")), cell_r),
                Paragraph(_money(ln.get("total_completed_stored")), cell_r),
                Paragraph(_pct(ln.get("percent_complete")), cell_r),
                Paragraph(_money(ln.get("balance_to_finish")), cell_r),
                Paragraph(_money(ln.get("retainage")), cell_r),
            ]
        )

    # Totals row from the summary.
    data.append(
        [
            Paragraph("", cell_l),
            _safe_para("Grand total", cell_l),
            Paragraph(_money(summary.get("contract_sum_to_date")), cell_r),
            Paragraph("", cell_r),
            Paragraph("", cell_r),
            Paragraph("", cell_r),
            Paragraph(_money(summary.get("total_completed_stored")), cell_r),
            Paragraph("", cell_r),
            Paragraph(_money(summary.get("balance_to_finish")), cell_r),
            Paragraph(_money(summary.get("retainage")), cell_r),
        ]
    )

    col_widths = [
        16 * mm,
        58 * mm,
        28 * mm,
        28 * mm,
        26 * mm,
        22 * mm,
        30 * mm,
        16 * mm,
        28 * mm,
        26 * mm,
    ]
    g703_tbl = Table(data, colWidths=col_widths, repeatRows=1)
    g703_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                ("FONTNAME", (0, -1), (-1, -1), BOLD_FONT),
                ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(g703_tbl)

    doc.build(story)
    return buf.getvalue()


__all__ = ["render_aia_application_pdf"]
