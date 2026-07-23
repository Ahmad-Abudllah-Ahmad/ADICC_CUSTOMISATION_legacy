# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""E-invoice profile registry.

The invoice model is EN 16931, which is the *international* semantic standard
behind e-invoicing in the EU and a growing list of countries. A "profile" here
binds that shared model to a concrete country/network flavour: the syntax
(CII or UBL), the guideline identifier (BT-24 CustomizationID), an optional
UBL ProfileID (BT-23), and the few conditionally mandatory rules that differ
per flavour.

Adding a new country = adding one :class:`Profile` entry. Nothing about the
builder is Germany-specific; XRechnung is just one profile among many, and the
UBL/Peppol profile makes the same invoice usable across every Peppol country
(EU, UK, Australia, New Zealand, Singapore, ...).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- guideline / customization identifiers --------------------------------

EN16931 = "urn:cen.eu:en16931:2017"  # plain EN 16931 (CII or UBL)
XRECHNUNG = "urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_3.0"
PEPPOL_CUSTOMIZATION = "urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0"
PEPPOL_PROFILE = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"

# National CIUS (country-specific specifications) that stay EN 16931 compliant
# and travel on the Peppol network. Each has its own CustomizationID (BT-24) but
# reuses the Peppol billing ProfileID (BT-23).
NLCIUS = "urn:cen.eu:en16931:2017#compliant#urn:fdc:nen.nl:nlcius:v1.0"  # Netherlands
PEPPOL_AUNZ = "urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:aunz:3.0"  # Australia / New Zealand
PEPPOL_SG = "urn:cen.eu:en16931:2017#conformant#urn:fdc:peppol.eu:2017:poacc:billing:international:sg:3.0"  # Singapore


@dataclass(frozen=True)
class Profile:
    """A concrete e-invoice flavour (syntax + identifiers + local rules)."""

    name: str
    syntax: str  # "cii" or "ubl"
    guideline: str  # BT-24 (CustomizationID)
    profile_id: str | None = None  # BT-23 (UBL ProfileID, e.g. Peppol)
    buyer_ref_required: bool = False  # BT-10 mandatory
    order_ref_alternative: bool = False  # BT-13 may satisfy the BT-10 rule
    region: str = "international"
    label: str = ""


# Registry. Keys are the ?format= values accepted by the endpoint.
PROFILES: dict[str, Profile] = {
    # --- international / cross-border ---
    "en16931": Profile("en16931", "cii", EN16931, region="EU", label="EN 16931 (CII)"),
    "ubl": Profile("ubl", "ubl", EN16931, region="international", label="EN 16931 (UBL)"),
    "peppol": Profile(
        "peppol",
        "ubl",
        PEPPOL_CUSTOMIZATION,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="international",
        label="Peppol BIS Billing 3.0",
    ),
    # --- country flavours (all built on the same EN 16931 model) ---
    "zugferd": Profile("zugferd", "cii", EN16931, region="DE/FR", label="ZUGFeRD 2.1"),
    "facturx": Profile("facturx", "cii", EN16931, region="FR/DE", label="Factur-X 1.0"),
    "xrechnung": Profile(
        "xrechnung",
        "cii",
        XRECHNUNG,
        buyer_ref_required=True,
        region="DE",
        label="XRechnung 3.0",
    ),
    # --- national Peppol CIUS (same EN 16931 model, own CustomizationID) ---
    "nlcius": Profile(
        "nlcius",
        "ubl",
        NLCIUS,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="NL",
        label="NLCIUS (Netherlands)",
    ),
    "ehf": Profile(
        "ehf",
        "ubl",
        PEPPOL_CUSTOMIZATION,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="NO",
        label="EHF Billing 3.0 (Norway)",
    ),
    "peppol_aunz": Profile(
        "peppol_aunz",
        "ubl",
        PEPPOL_AUNZ,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="AU/NZ",
        label="Peppol A-NZ Billing 3.0 (Australia / New Zealand)",
    ),
    "peppol_sg": Profile(
        "peppol_sg",
        "ubl",
        PEPPOL_SG,
        profile_id=PEPPOL_PROFILE,
        buyer_ref_required=True,
        order_ref_alternative=True,
        region="SG",
        label="Peppol SG Billing 3.0 (Singapore)",
    ),
}

SUPPORTED_PROFILES: tuple[str, ...] = tuple(PROFILES)


def get_profile(name: str) -> Profile | None:
    """Look up a profile by its ?format= key (case-insensitive)."""
    return PROFILES.get((name or "").strip().lower())
