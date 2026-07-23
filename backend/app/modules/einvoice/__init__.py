# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International electronic-invoicing library.

Outbound EN 16931 invoice writer in both syntaxes:
    * CII  - ZUGFeRD 2.1, Factur-X 1.0, XRechnung 3.0 (DACH/EU)
    * UBL  - Peppol BIS Billing 3.0 and plain EN 16931 UBL (worldwide)

One EN 16931 model, many country profiles (see ``profiles.py``); adding a
country is one registry entry. This is a pure library (no manifest, no router
of its own); the download endpoint lives in the finance module and renders
from the finance ``Invoice`` aggregate. The inbound counterpart is
``supplier_catalogs.peppol`` (UBL parser).
"""

from app.modules.einvoice.cii import (
    EInvoice,
    EInvoiceError,
    EInvoiceLine,
    Party,
    TaxSubtotal,
    build_cii_xml,
    profile_problems,
    validate,
    validate_semantics,
)
from app.modules.einvoice.profiles import (
    PROFILES,
    SUPPORTED_PROFILES,
    Profile,
    get_profile,
)
from app.modules.einvoice.service import (
    build_einvoice,
    problems_for,
    render_einvoice,
    render_einvoice_pdf,
)
from app.modules.einvoice.ubl import build_ubl_xml, is_credit_note

__all__ = [
    "PROFILES",
    "SUPPORTED_PROFILES",
    "EInvoice",
    "EInvoiceError",
    "EInvoiceLine",
    "Party",
    "Profile",
    "TaxSubtotal",
    "build_cii_xml",
    "build_einvoice",
    "build_ubl_xml",
    "get_profile",
    "is_credit_note",
    "problems_for",
    "profile_problems",
    "render_einvoice",
    "render_einvoice_pdf",
    "validate",
    "validate_semantics",
]
