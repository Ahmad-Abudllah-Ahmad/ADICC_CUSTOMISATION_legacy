# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Starter form / checklist templates.

A handful of realistic, ready-to-use templates seeded into the library at first
startup so the module is useful before a single template is authored. Pure data
- no imports beyond stdlib typing - so it is safe to load anywhere and easy to
extend. Each entry is a ``(name, category, description, tags, fields)`` tuple;
the service normalises the fields (deriving keys, filling defaults) and persists
them with ``is_seed=True`` and a null project (organisation-wide library).
"""

from __future__ import annotations

from typing import Any


def _f(key: str, ftype: str, label: str, **extra: Any) -> dict[str, Any]:
    """Build a field dict tersely."""
    return {"key": key, "type": ftype, "label": label, **extra}


STARTER_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "Site safety induction",
        "category": "safety",
        "description": (
            "Record that a worker has been inducted onto site: details captured, "
            "the key topics covered, and both signatures. Fill one per worker."
        ),
        "tags": ["safety", "induction", "onboarding"],
        "fields": [
            _f("worker_details", "section", "Worker details"),
            _f("worker_name", "short_text", "Worker name", required=True),
            _f("company_trade", "short_text", "Company / trade", required=True),
            _f("induction_date", "date", "Induction date", required=True),
            _f("topics", "section", "Induction topics covered"),
            _f(
                "site_rules",
                "checkbox",
                "Site rules and site-specific hazards explained",
                required=True,
            ),
            _f(
                "emergency",
                "checkbox",
                "Emergency procedures, assembly point and first aid explained",
                required=True,
            ),
            _f("ppe", "checkbox", "PPE requirements explained and PPE issued", required=True),
            _f(
                "permits",
                "checkbox",
                "Permit-to-work system and exclusion zones explained",
                required=True,
            ),
            _f(
                "card_verified",
                "single_choice",
                "Valid safety / training card verified",
                required=True,
                options=["Yes", "No", "Exempt"],
            ),
            _f("restrictions", "long_text", "Restrictions or notes", help_text="Any task the worker may not do yet."),
            _f("signoff", "section", "Sign off"),
            _f("worker_signature", "signature", "Worker signature", required=True),
            _f("inductor_signature", "signature", "Inductor signature", required=True),
        ],
    },
    {
        "name": "Concrete pour acceptance",
        "category": "quality",
        "description": (
            "Pre-pour and delivery acceptance check for a concrete pour. Confirms "
            "formwork, reinforcement and access are ready and the delivered mix is "
            "within spec before approval to pour."
        ),
        "tags": ["quality", "concrete", "acceptance", "pour"],
        "fields": [
            _f("pour_ref", "section", "Pour reference"),
            _f("element", "short_text", "Pour location / element", required=True),
            _f("mix", "short_text", "Concrete grade / mix", required=True),
            _f("planned_volume", "number", "Planned volume", required=True, unit="m3"),
            _f("pour_date", "date", "Pour date", required=True),
            _f("pre_pour", "section", "Pre-pour checks"),
            _f("formwork", "pass_fail_na", "Formwork position, dimensions and cleanliness", required=True),
            _f("reinforcement", "pass_fail_na", "Reinforcement fixed, cover and spacers correct", required=True),
            _f("cast_in", "pass_fail_na", "Cast-in items and penetrations in place", required=True),
            _f("access", "pass_fail_na", "Access, edge protection and lighting adequate", required=True),
            _f("delivery", "section", "Delivery checks"),
            _f("docket", "short_text", "Delivery docket number", required=True),
            _f("slump", "number", "Slump measured", unit="mm"),
            _f("temperature", "number", "Concrete temperature", unit="C"),
            _f("pour_photo", "photo", "Photo of pour area"),
            _f("signoff", "section", "Sign off"),
            _f("approved", "pass_fail_na", "Approved to pour", required=True),
            _f("engineer_signature", "signature", "Site engineer signature", required=True),
        ],
    },
    {
        "name": "Snag & handover checklist",
        "category": "handover",
        "description": (
            "Room-by-room snagging and handover readiness check. Walk the space, "
            "mark each element, list outstanding snags and rate overall readiness."
        ),
        "tags": ["handover", "snagging", "quality", "closeout"],
        "fields": [
            _f("location", "section", "Location"),
            _f("room", "short_text", "Room / area", required=True),
            _f("unit", "short_text", "Unit / plot"),
            _f("inspection_date", "date", "Inspection date", required=True),
            _f("condition", "section", "Condition"),
            _f("walls_ceilings", "pass_fail_na", "Walls, ceilings and paintwork", required=True),
            _f("floors", "pass_fail_na", "Floors and skirting", required=True),
            _f("doors_windows", "pass_fail_na", "Doors, windows and ironmongery", required=True),
            _f("sanitary", "pass_fail_na", "Sanitary ware and sealant", required=True),
            _f("electrical", "pass_fail_na", "Electrical fittings and sockets", required=True),
            _f("cleaning", "pass_fail_na", "Cleaning and finish", required=True),
            _f("snags_section", "section", "Snags"),
            _f("snags", "long_text", "Outstanding snags", help_text="One per line."),
            _f("readiness", "rating", "Overall readiness for handover", max_rating=5),
            _f("snag_photos", "photo", "Snag photos"),
            _f("signoff", "section", "Sign off"),
            _f("inspected_by", "signature", "Inspected by", required=True),
        ],
    },
]
