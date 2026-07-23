"""Unit tests for the Factur-X / ZUGFeRD hybrid PDF builder."""

import io
from decimal import Decimal

import pytest
from pypdf import PdfReader

from app.modules.einvoice import build_einvoice
from app.modules.einvoice.cii import EInvoiceError, build_cii_xml
from app.modules.einvoice.pdf_embed import build_facturx_pdf


def _invoice() -> dict:
    return {
        "invoice_number": "RE-2026-0100",
        "invoice_direction": "receivable",
        "invoice_date": "2026-07-05",
        "due_date": "2026-08-04",
        "currency_code": "EUR",
        "amount_subtotal": Decimal("1000.00"),
        "tax_amount": Decimal("190.00"),
        "retention_amount": Decimal("0"),
        "amount_total": Decimal("1190.00"),
        "notes": None,
        "metadata": {
            "einvoice": {
                "seller": {
                    "name": "Bau GmbH",
                    "vat_id": "DE123456789",
                    "city": "Berlin",
                    "postcode": "10115",
                    "country_code": "DE",
                },
                "buyer": {"name": "Stadt Beispiel", "city": "Cork", "country_code": "DE"},
            }
        },
    }


def _lines() -> list[dict]:
    return [
        {
            "description": "Concrete C30/37",
            "unit": "m3",
            "quantity": Decimal("40"),
            "unit_rate": Decimal("20"),
            "amount": Decimal("800.00"),
        },
        {
            "description": "Formwork",
            "unit": "m2",
            "quantity": Decimal("100"),
            "unit_rate": Decimal("2"),
            "amount": Decimal("200.00"),
        },
    ]


def test_hybrid_pdf_embeds_the_cii_xml():
    ei = build_einvoice(invoice=_invoice(), line_items=_lines(), profile="zugferd")
    pdf = build_facturx_pdf(ei)

    # A real PDF.
    assert pdf[:5] == b"%PDF-"

    reader = PdfReader(io.BytesIO(pdf))
    # The CII XML is embedded under the Factur-X attachment name.
    assert "factur-x.xml" in reader.attachments
    embedded = reader.attachments["factur-x.xml"][0]
    assert embedded == build_cii_xml(ei)
    # It parses and carries the invoice number.
    assert b"RE-2026-0100" in embedded

    # Associated-file relationship at the catalog level.
    root = reader.trailer["/Root"]
    assert "/AF" in root
    # XMP metadata declares the Factur-X conformance.
    meta = root["/Metadata"].get_data()
    assert b"ConformanceLevel" in meta
    assert b"factur-x.xml" in meta


def test_hybrid_pdf_rejects_ubl_profiles():
    ei = build_einvoice(invoice=_invoice(), line_items=_lines(), profile="peppol")
    with pytest.raises(EInvoiceError):
        build_facturx_pdf(ei)
