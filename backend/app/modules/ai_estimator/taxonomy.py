# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Trade-bucket taxonomy seed for the AI Estimate Builder grouping pass.

Stage 2 buckets every quantity group into a coarse trade so the review grid
can show a per-category summary and the AI group-refinement pass has a stable
label vocabulary to map onto. The buckets are derived from the CostEstimate
TOP-30/40 keyword analysis cross-checked with the CWICR
``classification.collection`` / ``department`` axes - the same ~15 trade
families a construction estimate is organised by, from earthworks through
finishing and MEP.

This is a deterministic keyword classifier, NOT machine learning: it tags a
group from its description / IFC class / classifier hint so that even with no
AI key the groups still carry a trade. The AI pass (when a key is present) may
rename or merge groups, but the trade vocabulary stays fixed so the UI never
sees a label it cannot render.
"""

from __future__ import annotations

# Ordered list of (trade_key, keyword tuple). Order matters: the first bucket
# whose keywords match wins, so the more-specific families (MEP, finishes)
# precede the broad structural ones. Keywords are lower-cased substrings
# matched against the normalised group text; they intentionally mix English
# and a handful of high-frequency German / Russian stems so a multilingual
# CWICR description still classifies without a translation hop.
TRADE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "demolition",
        ("demolition", "demolish", "strip out", "abriss", "rückbau", "снос", "демонтаж"),
    ),
    (
        "earthworks",
        ("earthwork", "excavat", "backfill", "grading", "trench", "soil", "erdarbeit", "aushub", "земляны", "грунт"),
    ),
    (
        "foundations",
        ("foundation", "footing", "pile", "raft", "pier", "fundament", "gründung", "фундамент", "свая"),
    ),
    (
        "structure",
        (
            "concrete",
            "reinforc",
            "rebar",
            "beam",
            "column",
            "slab",
            "structural steel",
            "stahlbeton",
            "bewehrung",
            "stütze",
            "бетон",
            "арматур",
            "колонн",
            "балк",
        ),
    ),
    (
        "masonry",
        ("masonry", "brick", "block", "blockwork", "mauerwerk", "ziegel", "кладк", "кирпич"),
    ),
    (
        "envelope",
        (
            "facade",
            "cladding",
            "curtain wall",
            "roof",
            "roofing",
            "waterproof",
            "insulation",
            "fassade",
            "dach",
            "dämmung",
            "фасад",
            "кровл",
            "гидроизол",
            "утеплен",
        ),
    ),
    (
        "openings",
        ("window", "door", "glazing", "fenster", "tür", "окн", "двер", "остеклен"),
    ),
    (
        "finishes",
        (
            "plaster",
            "render",
            "screed",
            "paint",
            "floor",
            "ceiling",
            "tiling",
            "tile",
            "putz",
            "estrich",
            "bodenbelag",
            "штукатур",
            "стяжк",
            "покраск",
            "плитк",
            "потол",
            "пол",
        ),
    ),
    (
        "mep_mechanical",
        ("hvac", "duct", "ventilation", "heating", "boiler", "chiller", "lüftung", "heizung", "вентиляц", "отоплен"),
    ),
    (
        "mep_plumbing",
        ("plumbing", "pipe", "drainage", "sanitary", "water supply", "sanitär", "rohr", "водопровод", "канализац"),
    ),
    (
        "mep_electrical",
        ("electric", "wiring", "cable", "lighting", "switchgear", "elektro", "kabel", "электр", "кабел", "освещен"),
    ),
    (
        "sitework",
        ("landscap", "paving", "fencing", "external works", "kerb", "außenanlage", "благоустройств", "озеленен"),
    ),
)

# Stable display order for the per-category summary block. A group that
# matches no keyword lands in ``other`` so the bucket is always present.
TRADE_ORDER: tuple[str, ...] = tuple(key for key, _ in TRADE_KEYWORDS) + ("other",)

# Human-readable default labels (English source; the UI translates via
# ``t('ai_estimator.trade.<key>', {defaultValue})``).
TRADE_LABELS: dict[str, str] = {
    "demolition": "Demolition",
    "earthworks": "Earthworks",
    "foundations": "Foundations",
    "structure": "Structure",
    "masonry": "Masonry",
    "envelope": "Envelope",
    "openings": "Openings",
    "finishes": "Finishes",
    "mep_mechanical": "Mechanical (HVAC)",
    "mep_plumbing": "Plumbing",
    "mep_electrical": "Electrical",
    "sitework": "Sitework",
    "other": "Other",
}


def classify_trade(*text_parts: str | None) -> str:
    """Return the trade bucket for a group from its descriptive text.

    Joins every supplied part (description, IFC class, classifier hint,
    category) into one lower-cased haystack and returns the first matching
    trade key, or ``"other"`` when nothing matches. Deterministic and
    side-effect-free so it works identically on the no-AI deterministic path.
    """
    haystack = " ".join(p for p in text_parts if p).lower()
    if not haystack.strip():
        return "other"
    for trade_key, keywords in TRADE_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return trade_key
    return "other"
