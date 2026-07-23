# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Regional configuration for South Africa.

All figures are drawn from public South African standards and regulations.
Money is represented as Decimal-as-string, in line with the platform money
convention. Province location factors are indicative starting points, not an
official index, and are meant to be edited per organisation.
"""

from decimal import Decimal
from typing import Any

# PPPFA system threshold: 80/20 applies up to and including this value, 90/10
# above it. Expressed as a string (ZAR), parsed to Decimal where arithmetic
# is needed (see router).
PPPFA_THRESHOLD_ZAR = "50000000"

PACK_CONFIG: dict[str, Any] = {
    # ── Identity ─────────────────────────────────────────────────────────────
    "region_code": "ZA",
    "countries": ["ZA"],
    "default_currency": "ZAR",
    "default_locale": "en-ZA",
    "measurement_system": "metric",
    "paper_size": "A4",
    "date_format": "YYYY/MM/DD",
    "number_format": "1 234.56",
    # ── Standards ────────────────────────────────────────────────────────────
    "standards": [
        {
            "code": "SANS_1200",
            "name": "SANS 1200 Standardized Specification for Civil Engineering Construction",
            "regulator": "South African Bureau of Standards (SABS)",
            "scope": "civil",
            "sections": [
                {"code": "A", "title": "General"},
                {"code": "C", "title": "Site clearance"},
                {"code": "D", "title": "Earthworks"},
                {"code": "DB", "title": "Earthworks (pipe trenches)"},
                {"code": "G", "title": "Concrete (structural)"},
                {"code": "GA", "title": "Concrete (small works)"},
                {"code": "GE", "title": "Precast concrete"},
                {"code": "H", "title": "Structural steelwork"},
                {"code": "L", "title": "Medium-pressure pipelines"},
                {"code": "LD", "title": "Sewers"},
                {"code": "LE", "title": "Stormwater drainage"},
                {"code": "M", "title": "Roads (general)"},
                {"code": "ME", "title": "Subbase"},
                {"code": "MF", "title": "Base"},
                {"code": "MG", "title": "Bituminous surface treatment"},
                {"code": "MH", "title": "Asphalt base and surfacing"},
            ],
        },
        {
            "code": "ASAQS_SSMBW",
            "name": "ASAQS Standard System of Measuring Building Work",
            "regulator": "Association of South African Quantity Surveyors (ASAQS)",
            "scope": "building",
            "description": "Measurement standard for building work, the SA counterpart to SANS 1200 for buildings.",
        },
    ],
    # ── Contract types (CIDB-endorsed suite) ─────────────────────────────────
    "contract_types": [
        {
            "code": "GCC_2015",
            "name": "GCC 2015 - General Conditions of Contract for Construction Works",
            "publisher": "SAICE",
        },
        {
            "code": "JBCC",
            "name": "JBCC Principal Building Agreement",
            "publisher": "Joint Building Contracts Committee",
        },
        {"code": "NEC4_ECC", "name": "NEC4 Engineering and Construction Contract", "publisher": "NEC"},
        {"code": "FIDIC", "name": "FIDIC Conditions of Contract", "publisher": "FIDIC"},
    ],
    # ── Contractor grading (CIDB) ────────────────────────────────────────────
    "contractor_grading": {
        "regulator": "Construction Industry Development Board (CIDB)",
        "legislation": "CIDB Act 38 of 2000",
        "classes_of_work": [
            {"code": "CE", "name": "Civil Engineering"},
            {"code": "GB", "name": "General Building"},
            {"code": "EB", "name": "Electrical Engineering (Building)"},
            {"code": "EP", "name": "Electrical Engineering (Infrastructure)"},
            {"code": "ME", "name": "Mechanical Engineering"},
            {"code": "SB-SQ", "name": "Specialist works"},
        ],
        # Indicative ZAR tender-value ceilings per grade, reflecting the schedule
        # the CIDB revised on 7 October 2019. Periodically updated; confirm
        # against the current Register of Contractors.
        "grade_value_ceilings_zar_indicative": [
            {"grade": 1, "tender_value_ceiling": "500000"},
            {"grade": 2, "tender_value_ceiling": "1000000"},
            {"grade": 3, "tender_value_ceiling": "3000000"},
            {"grade": 4, "tender_value_ceiling": "6000000"},
            {"grade": 5, "tender_value_ceiling": "10000000"},
            {"grade": 6, "tender_value_ceiling": "20000000"},
            {"grade": 7, "tender_value_ceiling": "60000000"},
            {"grade": 8, "tender_value_ceiling": "200000000"},
            {"grade": 9, "tender_value_ceiling": "no upper limit"},
        ],
        "note": "Tender value ceilings are indicative (post 7 October 2019 schedule) and periodically revised by the CIDB.",
    },
    # ── Procurement (PPPFA + FIDPM) ──────────────────────────────────────────
    "procurement": {
        "preferential_framework": {
            "legislation": "PPPFA Act 5 of 2000 (2022 Regulations)",
            "regulator": "National Treasury",
            "threshold_zar": PPPFA_THRESHOLD_ZAR,
            "systems": [
                {
                    "name": "80/20",
                    "applies_when": "tender value up to and including R50 million",
                    "price_weight": 80,
                    "preference_weight": 20,
                },
                {
                    "name": "90/10",
                    "applies_when": "tender value above R50 million",
                    "price_weight": 90,
                    "preference_weight": 10,
                },
            ],
            "price_points_formula": "Ps = W * (1 - (Pt - P_min) / P_min)",
            "preference_points_basis": "B-BBEE status level or other specific goals, capped at 20 (or 10) points.",
        },
        "delivery_framework": {
            "name": "National Treasury Framework for Infrastructure Delivery and Procurement Management (FIDPM 2019)",
            "stages": [
                {"stage": 0, "name": "Project initiation"},
                {"stage": 1, "name": "Infrastructure planning"},
                {"stage": 2, "name": "Prefeasibility"},
                {"stage": 3, "name": "Feasibility"},
                {"stage": 4, "name": "Design development"},
                {"stage": 5, "name": "Design documentation"},
                {"stage": 6, "name": "Works"},
                {"stage": 7, "name": "Handover"},
                {"stage": 8, "name": "Package completion"},
                {"stage": 9, "name": "Close-out"},
            ],
        },
    },
    # ── Tax rules ────────────────────────────────────────────────────────────
    "tax_rules": [
        {
            "code": "ZA_VAT",
            "name": "Value-Added Tax (VAT)",
            "type": "vat",
            "legislation": "Value-Added Tax Act 89 of 1991",
            "regulator": "South African Revenue Service (SARS)",
            "standard_rate_pct": "15",
            "effective_from": "2018-04-01",
            "note": "No reduced tier. Basic foodstuffs and exports are zero-rated; some supplies are exempt.",
        },
    ],
    # ── Provinces (indicative location factors, base Gauteng = 1.00) ─────────
    "provinces": [
        {"name": "Gauteng", "location_factor_indicative": "1.00"},
        {"name": "Western Cape", "location_factor_indicative": "1.02"},
        {"name": "KwaZulu-Natal", "location_factor_indicative": "1.01"},
        {"name": "Eastern Cape", "location_factor_indicative": "0.95"},
        {"name": "Free State", "location_factor_indicative": "0.93"},
        {"name": "Mpumalanga", "location_factor_indicative": "0.96"},
        {"name": "Limpopo", "location_factor_indicative": "0.92"},
        {"name": "North West", "location_factor_indicative": "0.94"},
        {"name": "Northern Cape", "location_factor_indicative": "0.90"},
    ],
    "provinces_note": "Location factors are indicative starting points relative to Gauteng, not an official index. Edit them to match your own cost data.",
    # ── Units (metric defaults) ──────────────────────────────────────────────
    "default_units": {
        "length": "m",
        "area": "m2",
        "volume": "m3",
        "weight": "kg",
        "temperature": "°C",
    },
    # ── VAT rates (consumed by app.core.tax aggregation) ─────────────────────
    # Stored as Decimal to match the regional-pack vat_rates convention
    # (see tests/unit/test_regional_pack_vat_completeness.py). ZA = South
    # Africa, distinct from SA = Saudi Arabia in the Middle East pack.
    "vat_rates": {
        "ZA": {"standard": Decimal("0.15"), "zero": Decimal("0.00")},
    },
    # ── Cost database integration ────────────────────────────────────────────
    "cost_database_integrations": [
        {
            "code": "CWICR_ZA_JOHANNESBURG",
            "name": "CWICR South Africa (Johannesburg)",
            "region_code": "ZA_JOHANNESBURG",
            "currency": "ZAR",
            "enabled": True,
            "note": "Published. Cost rows download on demand from the CWICR data repo; the BGE-M3 vector snapshot loads via 'python -m scripts.seed_cwicr_v3 --regions ZA_JOHANNESBURG'.",
        },
    ],
}
