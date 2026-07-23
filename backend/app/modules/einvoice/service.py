# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Map a finance ``Invoice`` aggregate onto an EN 16931 :class:`EInvoice`
and render it as CII XML.

Kept ORM-free on purpose (takes plain dicts, exactly like
``finance.br_invoice_pdf.render_br_invoice_pdf``) so it is trivially testable
and the finance router can feed it the same ``invoice`` / ``line_items`` dicts
it already builds for the Brazilian PDF route.

German-specific fields (Leitweg-ID / buyer reference, explicit VAT rate,
seller and buyer master data) live under ``invoice['metadata']['einvoice']``,
mirroring the Brazilian ``metadata['br_fields']`` precedent. Anything the
caller passes explicitly (``seller`` / ``buyer``) wins over metadata.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.modules.einvoice.cii import (
    EInvoice,
    EInvoiceError,
    EInvoiceLine,
    Party,
    TaxSubtotal,
    build_cii_xml,
    validate,
)
from app.modules.einvoice.profiles import get_profile
from app.modules.einvoice.ubl import build_ubl_xml

_2P = Decimal("0.01")


def _dec(value: Any, default: str = "0") -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return Decimal(default)


def _is_true(value: Any) -> bool:
    """Read a permissive boolean flag (True / "true" / "yes" / "1")."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "1", "y"}


# BT-3 document type codes: 380 commercial invoice, 381 credit note.
_INVOICE_TYPE_CODE = "380"
_CREDIT_NOTE_TYPE_CODE = "381"


def _resolve_type_code(invoice: dict[str, Any], ei: dict[str, Any]) -> str:
    """Decide the BT-3 document type code from the invoice data.

    An explicit ``metadata.einvoice.type_code`` (or top-level ``type_code``)
    wins. Otherwise a credit flag (``credit_note`` / ``is_credit_note`` /
    ``invoice_direction == "credit_note"``) selects the credit note code 381,
    and everything else is a commercial invoice (380).
    """
    explicit = str(ei.get("type_code") or invoice.get("type_code") or "").strip()
    if explicit:
        return explicit
    flags = (
        ei.get("credit_note"),
        ei.get("is_credit_note"),
        invoice.get("credit_note"),
        invoice.get("is_credit_note"),
    )
    if any(_is_true(flag) for flag in flags):
        return _CREDIT_NOTE_TYPE_CODE
    if str(invoice.get("invoice_direction") or "").strip().lower() == "credit_note":
        return _CREDIT_NOTE_TYPE_CODE
    return _INVOICE_TYPE_CODE


def _coerce_party(value: Party | dict | None, *, fallback_name: str = "") -> Party:
    if isinstance(value, Party):
        return value
    d = dict(value or {})
    return Party(
        name=str(d.get("name") or fallback_name or "").strip(),
        country_code=str(d.get("country_code") or d.get("country") or "DE").strip() or "DE",
        vat_id=(d.get("vat_id") or d.get("ust_id") or None),
        tax_number=(d.get("tax_number") or d.get("steuernummer") or None),
        legal_id=(d.get("legal_id") or None),
        line1=(d.get("line1") or d.get("address") or None),
        postcode=(d.get("postcode") or d.get("zip") or None),
        city=(d.get("city") or None),
        email=(d.get("email") or None),
        contact_id_scheme=(d.get("electronic_address_scheme") or None),
        electronic_address=(d.get("electronic_address") or None),
    )


def build_einvoice(
    *,
    invoice: dict[str, Any],
    line_items: list[dict[str, Any]],
    profile: str,
    seller: Party | dict | None = None,
    buyer: Party | dict | None = None,
    seller_fallback_name: str = "",
    buyer_fallback_name: str = "",
) -> EInvoice:
    """Assemble an :class:`EInvoice` from finance invoice + line dicts.

    VAT handling for this first version is single-rate: the effective rate is
    taken from ``metadata.einvoice.vat_rate`` when present, else derived from
    ``tax_amount / amount_subtotal``. Per-line and multi-rate breakdowns are a
    follow-up. Retention is represented as a prepaid/withheld amount (BT-113)
    so the amount due reconciles (BR-CO-16).
    """
    meta = dict(invoice.get("metadata") or {})
    ei = dict(meta.get("einvoice") or {})

    subtotal = _dec(invoice.get("amount_subtotal"))
    tax_total = _dec(invoice.get("tax_amount"))
    retention = _dec(invoice.get("retention_amount"))
    currency = str(invoice.get("currency_code") or "EUR").strip() or "EUR"

    # Lines. Trust line amounts as the source of the document line total so
    # BR-CO-10 holds even if the stored header subtotal drifted by a cent.
    lines: list[EInvoiceLine] = []
    line_total = Decimal("0")
    # Effective VAT rate.
    if ei.get("vat_rate") not in (None, ""):
        rate = _dec(ei.get("vat_rate"))
    elif subtotal > 0:
        rate = (tax_total / subtotal * 100).quantize(_2P, rounding=ROUND_HALF_UP)
    else:
        rate = Decimal("0")
    category = str(ei.get("vat_category") or ("S" if rate > 0 else "Z"))

    for idx, li in enumerate(line_items, start=1):
        amount = _dec(li.get("amount"))
        lines.append(
            EInvoiceLine(
                line_id=str(li.get("line_id") or idx),
                name=str(li.get("description") or "-"),
                quantity=_dec(li.get("quantity"), "1"),
                unit=li.get("unit"),
                net_unit_price=_dec(li.get("unit_rate")),
                line_net_amount=amount,
                vat_rate=rate,
                vat_category=category,
            )
        )
        line_total += amount

    if not lines:
        raise EInvoiceError("invoice has no line items (BR-16)")

    # Totals recomputed so the document reconciles (BR-CO-10/13/15/16).
    tax_basis_total = line_total
    grand_total = tax_basis_total + tax_total
    prepaid = retention if retention > 0 else Decimal("0")
    due_payable = grand_total - prepaid

    tax_subtotals = [
        TaxSubtotal(
            category=category,
            rate=rate,
            basis=tax_basis_total,
            tax_amount=tax_total,
        )
    ]

    type_code = _resolve_type_code(invoice, ei)

    return EInvoice(
        profile=profile,
        invoice_number=str(invoice.get("invoice_number") or ""),
        issue_date=str(invoice.get("invoice_date") or ""),
        currency=currency,
        seller=_coerce_party(seller or ei.get("seller"), fallback_name=seller_fallback_name),
        buyer=_coerce_party(buyer or ei.get("buyer"), fallback_name=buyer_fallback_name),
        lines=lines,
        tax_subtotals=tax_subtotals,
        line_total=line_total,
        tax_basis_total=tax_basis_total,
        tax_total=tax_total,
        grand_total=grand_total,
        due_payable=due_payable,
        type_code=type_code,
        buyer_reference=(ei.get("buyer_reference") or ei.get("leitweg_id") or None),
        order_reference=(ei.get("order_reference") or None),
        due_date=(invoice.get("due_date") or None),
        payment_terms=(ei.get("payment_terms") or None),
        prepaid_amount=prepaid,
        note=(invoice.get("notes") or None),
    )


def render_einvoice(
    *,
    invoice: dict[str, Any],
    line_items: list[dict[str, Any]],
    profile: str,
    seller: Party | dict | None = None,
    buyer: Party | dict | None = None,
    seller_fallback_name: str = "",
    buyer_fallback_name: str = "",
    strict: bool = True,
) -> tuple[str, str, bytes]:
    """Return ``(filename, media_type, xml_bytes)`` for the invoice.

    ``direction`` unused for now; both payable and receivable render the same
    CII (party roles are already set by seller/buyer).
    """
    prof = get_profile(profile)
    if prof is None:
        raise EInvoiceError(f"unknown e-invoice profile {profile!r}")
    ei = build_einvoice(
        invoice=invoice,
        line_items=line_items,
        profile=profile,
        seller=seller,
        buyer=buyer,
        seller_fallback_name=seller_fallback_name,
        buyer_fallback_name=buyer_fallback_name,
    )
    xml = build_ubl_xml(ei, strict=strict) if prof.syntax == "ubl" else build_cii_xml(ei, strict=strict)
    safe_num = _safe_token(ei.invoice_number)
    filename = f"einvoice_{safe_num}_{profile}.xml"
    return filename, "application/xml", xml


def render_einvoice_pdf(
    *,
    invoice: dict[str, Any],
    line_items: list[dict[str, Any]],
    profile: str,
    seller: Party | dict | None = None,
    buyer: Party | dict | None = None,
    seller_fallback_name: str = "",
    buyer_fallback_name: str = "",
    strict: bool = True,
) -> tuple[str, str, bytes]:
    """Return ``(filename, "application/pdf", pdf)`` for a Factur-X/ZUGFeRD hybrid.

    Only CII profiles (zugferd/facturx/xrechnung/en16931) can be embedded in a
    PDF; UBL/Peppol is XML-only, so callers should use :func:`render_einvoice`
    for those.
    """
    from app.modules.einvoice.pdf_embed import build_facturx_pdf

    prof = get_profile(profile)
    if prof is None:
        raise EInvoiceError(f"unknown e-invoice profile {profile!r}")
    if prof.syntax != "cii":
        raise EInvoiceError(
            f"profile {profile!r} is UBL/XML-only; a hybrid PDF needs a CII profile "
            "(zugferd, facturx, xrechnung or en16931)"
        )
    ei = build_einvoice(
        invoice=invoice,
        line_items=line_items,
        profile=profile,
        seller=seller,
        buyer=buyer,
        seller_fallback_name=seller_fallback_name,
        buyer_fallback_name=buyer_fallback_name,
    )
    pdf = build_facturx_pdf(ei, strict=strict)
    safe_num = _safe_token(ei.invoice_number)
    filename = f"einvoice_{safe_num}_{profile}.pdf"
    return filename, "application/pdf", pdf


def problems_for(
    *,
    invoice: dict[str, Any],
    line_items: list[dict[str, Any]],
    profile: str,
    seller: Party | dict | None = None,
    buyer: Party | dict | None = None,
    seller_fallback_name: str = "",
    buyer_fallback_name: str = "",
) -> list[str]:
    """Validate without rendering - used by a dry-run endpoint / UI check."""
    ei = build_einvoice(
        invoice=invoice,
        line_items=line_items,
        profile=profile,
        seller=seller,
        buyer=buyer,
        seller_fallback_name=seller_fallback_name,
        buyer_fallback_name=buyer_fallback_name,
    )
    return validate(ei)


def _safe_token(raw: str) -> str:
    """ASCII-safe token for a Content-Disposition filename."""
    cleaned = (
        (raw or "invoice")
        .encode("ascii", errors="replace")
        .decode("ascii")
        .replace("\r", "")
        .replace("\n", "")
        .replace('"', "'")
        .replace("/", "-")
        .replace(" ", "_")
        .strip()
    )
    return cleaned[:80] or "invoice"
