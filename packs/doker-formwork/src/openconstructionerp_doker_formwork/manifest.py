"""Manifest for the Doker formwork partner pack.

Pre-configures OpenConstructionERP for formwork (Schalung) and
concrete contractors operating in the DACH region. Activates DIN-, EN-,
VOB/C- and DGUV-compliant validation rule packs, ships a curated
catalogue of common Doka formwork systems with their DIN 18218
classes and typical reuse counts, and replaces the default onboarding
wizard with a 6-step Schalung flow that asks the questions a formwork
contractor actually needs to answer (company size, project type,
systems in inventory, default pour rate, BG-BAU membership, VOB/B vs
BGB default).

Cost regions:
    Berlin is the national index and is included by default. The pack
    additionally enables München (most DACH formwork inventories are
    dispatched from southern Germany / the Austrian border region) and
    Düsseldorf (NRW is the largest concrete-construction market by
    volume). Contractors can drop unused regions in the cost-DB UI.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.partner_pack.manifest import PartnerBranding, PartnerPackManifest

# Load the catalogue at import time so /api/v1/partner-pack/current can
# expose `metadata.doker_systems` without a separate filesystem round-trip.
_CATALOGUE_PATH = Path(__file__).parent / "catalogue" / "doker_systems.json"
try:
    _CATALOGUE = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    _DOKER_SYSTEMS = _CATALOGUE.get("systems", [])
except (OSError, json.JSONDecodeError):
    _DOKER_SYSTEMS = []


MANIFEST = PartnerPackManifest(
    slug="doker-formwork",
    partner_name="Doka Formwork",
    partner_url="https://www.doka.com",
    pack_version="0.2.0",
    description=(
        "Vorkonfiguriert für Schalungs- und Betonbau-Unternehmen in der DACH-Region: "
        "DIN 18218 Frischbetondruck, DIN EN 12812 Traggerüste, DIN EN 13670 Ausführung, "
        "DIN EN 206 Beton, VOB/C DIN 18331, DGUV 101-008 Arbeitssicherheit, "
        "Schalungszyklus-Qualität und -Ökonomie. Inklusive Katalog der gängigen "
        "Doka-Schalungssysteme (Frami Xlife, Framax Xlife plus, Alu-Star, "
        "Dokaflex, RS Xlife, Xclimb 60, Staxo 100) mit Lastklassen und "
        "Nutzungshäufigkeiten."
    ),
    default_locale="de",
    additional_locales={"de": "locales/de.json"},
    cwicr_regions=[
        "cwicr-de-berlin",
        "cwicr-de-muenchen",
        "cwicr-de-duesseldorf",
    ],
    default_currency="EUR",
    default_tax_template="de_vat_19",
    validation_rule_packs=[
        "din_18218_formwork_pressure",
        "din_en_12812_falsework",
        "din_en_13670_concrete_execution",
        "concrete_din_en_206",
        "vob_c_din_18331_concrete_works",
        "dguv_101_008_formwork_safety",
        "formwork_cycle_quality",
        "formwork_cycle_economics",
    ],
    default_modules=[],
    hidden_modules=[],
    branding=PartnerBranding(
        primary_color="#004899",  # Doka blue
        accent_color="#FEDC00",  # Doka yellow
        logo_path="logo.png",
        favicon_path=None,
        powered_by_text="Powered by OpenConstructionERP, in partnership with Doka Formwork",
    ),
    onboarding_script_path="onboarding.yaml",
    metadata={
        "industry": "formwork",
        "primary_market": "DACH",
        "focus": ["schalung", "beton", "bewehrung", "traggeruest", "arbeitssicherheit"],
        "regulatory_frameworks": [
            "DIN 18218:2010-01",
            "DIN EN 12812:2008",
            "DIN EN 13670:2011-03",
            "DIN EN 206:2021-06",
            "DIN 1045-2:2008-08",
            "DIN 1045-3:2012-03",
            "VOB/C DIN 18331:2019-09",
            "VOB/C DIN 18299:2019-09",
            "DGUV-Regel 101-008",
            "BetrSichV",
        ],
        "catalogue_paths": {
            "doker_systems": "catalogue/doker_systems.json",
        },
        "doker_systems": _DOKER_SYSTEMS,
    },
)
