"""Build the ``PartnerPackManifest`` instance for the uk-jct pack.

Kept in its own module so unit tests can import the manifest without
triggering the package ``__init__`` side-effects.
"""

from __future__ import annotations

from app.core.partner_pack.manifest import PartnerBranding, PartnerPackManifest

MANIFEST = PartnerPackManifest(
    slug="uk-jct",
    partner_name="UK Construction Pack",
    partner_url=None,
    pack_version="0.2.0",
    description=(
        "Pre-configured for UK general contractors: RICS NRM 1+2 (2nd ed, 2021) "
        "with optional NRM 3 maintenance, JCT 2024 contract suite, BCIS cost "
        "benchmarks, CDM 2015 regulations and Building Safety Act 2022 (HRB) "
        "compliance."
    ),
    default_locale="en-GB",
    additional_locales={
        "en-GB": "locales/en-GB.json",
    },
    cwicr_regions=[
        # Only the UK-wide CWICR slug exists in the marketplace today.
        # Sub-regional (Manchester, Birmingham, Edinburgh) variants are
        # roadmap items; users can apply BCIS Location Factor in-app
        # for regional adjustment.
        "cwicr-uk-gbp",
    ],
    default_currency="GBP",
    default_tax_template="uk_vat_20",
    default_methodology="united_kingdom",
    validation_rule_packs=[
        "nrm_1_cost_planning",
        "nrm_2_detailed_measurement",
        "nrm_3_maintenance",
        "jct_2024_contract_clauses",
        "bcis_benchmarks",
        "cdm_2015",
        "bsa_2022",
    ],
    default_modules=[],   # empty = show all
    hidden_modules=[],
    branding=PartnerBranding(
        primary_color="#012169",   # Union flag blue
        accent_color="#C8102E",    # Union flag red
        logo_path="logo.svg",
        favicon_path=None,
        powered_by_text=None,      # use default co-branding string
    ),
    onboarding_script_path="onboarding.yaml",
    metadata={
        "country": "GB",
        "country_name_en": "United Kingdom",
        "regulator_refs": [
            "RICS NRM 1 (2nd ed, 2021)",
            "RICS NRM 2 (2nd ed, 2021)",
            "RICS NRM 3 (2014)",
            "JCT 2024",
            "BCIS",
            "CDM 2015",
            "Building Safety Act 2022",
        ],
        "support_email": "info@datadrivenconstruction.io",
        "regions": [
            # Aspirational regional CWICR slugs — not yet in marketplace.
            # When added, the onboarding wizard can preload them per
            # head-office region selection.
            "England — London",
            "England — Manchester",
            "England — Birmingham",
            "Scotland — Edinburgh",
            "Wales — Cardiff",
            "Northern Ireland — Belfast",
        ],
    },
)
