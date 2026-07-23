"""Unit tests for the plain-language validation messages.

A non-expert should read a dry-run problem and know exactly which field to fill
and where. These tests pin that the guidance stays actionable (says "Add ...")
and free of the typographic characters the house style forbids.
"""

from decimal import Decimal

from app.modules.einvoice import problems_for
from app.modules.einvoice.cii import EInvoice, EInvoiceLine, Party, TaxSubtotal, validate_semantics


def _base_invoice() -> dict:
    return {
        "invoice_number": "INV-2026-1",
        "invoice_date": "2026-07-05",
        "currency_code": "EUR",
        "amount_subtotal": Decimal("100.00"),
        "tax_amount": Decimal("21.00"),
        "metadata": {
            "einvoice": {
                "vat_rate": "21",
                "seller": {
                    "name": "Iberia Construccion SL",
                    "vat_id": "ESB12345678",
                    "country_code": "ES",
                },
                "buyer": {"name": "Obras Municipales", "country_code": "ES"},
                "buyer_reference": "PO-1",
            }
        },
    }


def _lines() -> list[dict]:
    return [
        {
            "description": "Works",
            "unit": "m2",
            "quantity": Decimal("10"),
            "unit_rate": Decimal("10"),
            "amount": Decimal("100.00"),
        }
    ]


def _no_typographic_dashes(text: str) -> bool:
    # No em dash, en dash or smart quotes anywhere in user-facing guidance.
    return not any(ch in text for ch in ("—", "–", "‘", "’", "“", "”"))


def test_missing_seller_tax_id_message_is_actionable():
    inv = _base_invoice()
    inv["metadata"]["einvoice"]["seller"].pop("vat_id")
    problems = problems_for(invoice=inv, line_items=_lines(), profile="peppol")
    hit = [p for p in problems if "VAT id" in p or "tax number" in p]
    assert hit, problems
    msg = hit[0]
    assert msg.startswith("Add")
    assert "e-invoice settings" in msg
    assert _no_typographic_dashes(msg)


def test_missing_buyer_reference_message_names_the_field_and_place():
    inv = _base_invoice()
    inv["metadata"]["einvoice"].pop("buyer_reference")
    problems = problems_for(invoice=inv, line_items=_lines(), profile="peppol")
    hit = [p for p in problems if "Buyer reference" in p]
    assert hit, problems
    msg = hit[0]
    assert msg.startswith("Add")
    assert "BT-10" in msg  # keeps the technical anchor for experts
    assert "e-invoice settings" in msg  # tells a non-expert where to go
    assert _no_typographic_dashes(msg)


def test_xrechnung_message_mentions_leitweg():
    inv = _base_invoice()
    inv["metadata"]["einvoice"].pop("buyer_reference")
    inv["metadata"]["einvoice"]["seller"]["country_code"] = "DE"
    inv["metadata"]["einvoice"]["buyer"]["country_code"] = "DE"
    problems = problems_for(invoice=inv, line_items=_lines(), profile="xrechnung")
    hit = [p for p in problems if "Leitweg" in p]
    assert hit, problems
    assert hit[0].startswith("Add")
    assert _no_typographic_dashes(hit[0])


def test_missing_country_message_explains_the_format():
    inv = EInvoice(
        profile="peppol",
        invoice_number="INV-1",
        issue_date="2026-07-05",
        currency="EUR",
        seller=Party(name="Seller", country_code="", vat_id="ESB12345678"),
        buyer=Party(name="Buyer", country_code="ES"),
        lines=[
            EInvoiceLine(
                line_id="1",
                name="Works",
                quantity=Decimal("1"),
                unit="m2",
                net_unit_price=Decimal("100"),
                line_net_amount=Decimal("100.00"),
                vat_rate=Decimal("21"),
            )
        ],
        tax_subtotals=[TaxSubtotal("S", Decimal("21"), Decimal("100.00"), Decimal("21.00"))],
        line_total=Decimal("100.00"),
        tax_basis_total=Decimal("100.00"),
        tax_total=Decimal("21.00"),
        grand_total=Decimal("121.00"),
        due_payable=Decimal("121.00"),
    )
    problems = validate_semantics(inv)
    hit = [p for p in problems if "country code" in p]
    assert hit, problems
    assert "two letters" in hit[0]
    assert _no_typographic_dashes(hit[0])


def test_all_semantic_messages_are_clean_prose():
    # An empty invoice trips most rules at once; every message must be clean.
    inv = EInvoice(
        profile="peppol",
        invoice_number="",
        issue_date="",
        currency="",
        seller=Party(name="", country_code=""),
        buyer=Party(name="", country_code=""),
        lines=[],
        tax_subtotals=[],
        line_total=Decimal("0"),
        tax_basis_total=Decimal("0"),
        tax_total=Decimal("0"),
        grand_total=Decimal("0"),
        due_payable=Decimal("0"),
    )
    problems = validate_semantics(inv)
    assert problems
    for msg in problems:
        assert _no_typographic_dashes(msg), msg
