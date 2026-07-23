# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Factur-X / ZUGFeRD hybrid PDF builder.

A hybrid e-invoice is a human-readable PDF that carries the machine-readable
EN 16931 CII XML embedded inside it as an associated file, with the Factur-X
XMP metadata that lets a receiver find and trust the XML. ZUGFeRD 2.1 (Germany)
and Factur-X 1.0 (France) are the same thing under two names, and the hybrid
concept is used internationally.

This module renders the readable page with reportlab (already a dependency)
and embeds the CII with pypdf (already a dependency), setting the associated
-file relationship (/AF + /AFRelationship) and the Factur-X XMP that a hybrid
invoice needs. The embedded CII is the legally operative content and is fully
EN 16931 valid (see ``cii.py``).

Note on strict PDF/A-3b: full PDF/A-3b conformance (OutputIntent + ICC colour
profile) is not asserted here. The file is a correct Factur-X hybrid carrying
the XML with the right relationship and metadata; if a receiver demands strict
PDF/A-3b, run the output through a PDF/A post-processor. The XML path (used by
every automated receiver) is unaffected.
"""

from __future__ import annotations

import io
from decimal import Decimal

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    StreamObject,
    create_string_object,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.modules.einvoice.cii import EInvoice, _money, build_cii_xml
from app.modules.einvoice.profiles import get_profile

# Factur-X / ZUGFeRD attachment filename (2.1 uses factur-x.xml for both).
_ATTACHMENT_NAME = "factur-x.xml"

# Conformance level written into the XMP per profile.
_CONFORMANCE = {
    "en16931": "EN 16931",
    "zugferd": "EN 16931",
    "facturx": "EN 16931",
    "xrechnung": "XRECHNUNG",
}


def _readable_pdf(inv: EInvoice) -> bytes:
    """Render a compact one-page, international invoice PDF (reportlab)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left = 20 * mm
    top = height - 25 * mm

    def line(y: float, text: str, *, size: int = 9, bold: bool = False) -> None:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(left, y, text)

    def right(y: float, text: str, *, size: int = 9, bold: bool = False) -> None:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawRightString(width - 20 * mm, y, text)

    line(top, "INVOICE", size=16, bold=True)
    right(top, f"{inv.invoice_number}", size=12, bold=True)
    y = top - 8 * mm
    right(y, f"Date: {inv.issue_date}")
    if inv.due_date:
        right(y - 5 * mm, f"Due: {inv.due_date}")

    # Parties
    y = top - 20 * mm
    line(y, "From", bold=True)
    line(y - 5 * mm, inv.seller.name)
    seller_loc = " ".join(x for x in (inv.seller.postcode, inv.seller.city) if x)
    if seller_loc:
        line(y - 10 * mm, seller_loc)
    if inv.seller.vat_id:
        line(y - 15 * mm, f"VAT: {inv.seller.vat_id}")

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left + 90 * mm, y, "Bill to")
    c.setFont("Helvetica", 9)
    c.drawString(left + 90 * mm, y - 5 * mm, inv.buyer.name)
    buyer_loc = " ".join(x for x in (inv.buyer.postcode, inv.buyer.city) if x)
    if buyer_loc:
        c.drawString(left + 90 * mm, y - 10 * mm, buyer_loc)
    if inv.buyer_reference:
        c.drawString(left + 90 * mm, y - 15 * mm, f"Ref: {inv.buyer_reference}")

    # Line table header
    ty = y - 30 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(left, ty, "Description")
    c.drawRightString(left + 95 * mm, ty, "Qty")
    c.drawString(left + 100 * mm, ty, "Unit")
    c.drawRightString(left + 140 * mm, ty, "Unit price")
    c.drawRightString(width - 20 * mm, ty, f"Net ({inv.currency})")
    c.setLineWidth(0.4)
    c.line(left, ty - 2 * mm, width - 20 * mm, ty - 2 * mm)

    c.setFont("Helvetica", 8)
    ry = ty - 7 * mm
    for ln in inv.lines:
        c.drawString(left, ry, (ln.name or "-")[:60])
        c.drawRightString(left + 95 * mm, ry, _num(ln.quantity))
        c.drawString(left + 100 * mm, ry, (ln.unit or "")[:8])
        c.drawRightString(left + 140 * mm, ry, _money(ln.net_unit_price))
        c.drawRightString(width - 20 * mm, ry, _money(ln.line_net_amount))
        ry -= 5 * mm
        if ry < 40 * mm:  # keep it one page for the v1 layout
            break

    # Totals
    c.setLineWidth(0.4)
    c.line(left + 100 * mm, ry - 1 * mm, width - 20 * mm, ry - 1 * mm)
    ry -= 6 * mm

    def total_row(label: str, amount: Decimal, *, bold: bool = False) -> None:
        nonlocal ry
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawRightString(left + 140 * mm, ry, label)
        c.drawRightString(width - 20 * mm, ry, f"{_money(amount)} {inv.currency}")
        ry -= 5 * mm

    total_row("Net total", inv.tax_basis_total)
    total_row("VAT", inv.tax_total)
    total_row("Grand total", inv.grand_total, bold=True)
    if inv.prepaid_amount:
        total_row("Retention / prepaid", inv.prepaid_amount)
    total_row("Amount due", inv.due_payable, bold=True)

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(
        left,
        20 * mm,
        "This PDF carries an embedded EN 16931 e-invoice (Factur-X / ZUGFeRD). "
        "The embedded XML is the operative document.",
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def _num(value: Decimal) -> str:
    q = value.normalize()
    return f"{q:f}"


def _xmp(profile_name: str) -> bytes:
    """Factur-X XMP metadata packet (identifies the embedded CII)."""
    conformance = _CONFORMANCE.get(profile_name, "EN 16931")
    return (
        """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
  </rdf:Description>
  <rdf:Description rdf:about=""
      xmlns:fx="urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#">
   <fx:DocumentType>INVOICE</fx:DocumentType>
   <fx:DocumentFileName>"""
        + _ATTACHMENT_NAME
        + """</fx:DocumentFileName>
   <fx:Version>1.0</fx:Version>
   <fx:ConformanceLevel>"""
        + conformance
        + """</fx:ConformanceLevel>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    ).encode("utf-8")


def _embed_cii(pdf_bytes: bytes, xml_bytes: bytes, profile_name: str) -> bytes:
    """Embed the CII XML as a Factur-X associated file and add the XMP."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    writer.append(reader)

    # Embedded file stream.
    ef = DecodedStreamObject()
    ef.set_data(xml_bytes)
    ef[NameObject("/Type")] = NameObject("/EmbeddedFile")
    ef[NameObject("/Subtype")] = NameObject("/text#2Fxml")
    ef_ref = writer._add_object(ef)

    filespec = DictionaryObject()
    filespec[NameObject("/Type")] = NameObject("/Filespec")
    filespec[NameObject("/F")] = create_string_object(_ATTACHMENT_NAME)
    filespec[NameObject("/UF")] = create_string_object(_ATTACHMENT_NAME)
    filespec[NameObject("/AFRelationship")] = NameObject("/Data")
    filespec[NameObject("/Desc")] = create_string_object("Factur-X/ZUGFeRD invoice")
    ef_dict = DictionaryObject()
    ef_dict[NameObject("/F")] = ef_ref
    ef_dict[NameObject("/UF")] = ef_ref
    filespec[NameObject("/EF")] = ef_dict
    filespec_ref = writer._add_object(filespec)

    # Catalog: /Names /EmbeddedFiles and /AF (associated files).
    root = writer._root_object
    names_arr = ArrayObject([create_string_object(_ATTACHMENT_NAME), filespec_ref])
    ef_tree = DictionaryObject()
    ef_tree[NameObject("/Names")] = names_arr
    names_dict = DictionaryObject()
    names_dict[NameObject("/EmbeddedFiles")] = ef_tree
    root[NameObject("/Names")] = names_dict
    root[NameObject("/AF")] = ArrayObject([filespec_ref])

    # XMP metadata stream on the catalog.
    meta = StreamObject()
    meta.set_data(_xmp(profile_name))
    meta[NameObject("/Type")] = NameObject("/Metadata")
    meta[NameObject("/Subtype")] = NameObject("/XML")
    root[NameObject("/Metadata")] = writer._add_object(meta)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def build_facturx_pdf(inv: EInvoice, *, strict: bool = True) -> bytes:
    """Build a Factur-X / ZUGFeRD hybrid PDF for a CII-profile invoice."""
    profile = get_profile(inv.profile)
    if profile is None or profile.syntax != "cii":
        from app.modules.einvoice.cii import EInvoiceError

        raise EInvoiceError(f"hybrid PDF needs a CII profile (zugferd/facturx/xrechnung/en16931), got {inv.profile!r}")
    xml_bytes = build_cii_xml(inv, strict=strict)
    pdf_bytes = _readable_pdf(inv)
    return _embed_cii(pdf_bytes, xml_bytes, inv.profile)
