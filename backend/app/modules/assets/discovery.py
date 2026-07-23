# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Asset-candidate discovery from BIM element data.

The Asset Register is empty until a human flags BIM elements as tracked
assets - one at a time, in the 3D viewer. That makes the whole module
dead-on-arrival for a real model with thousands of elements.

This module scores each BIM element on how likely it is to be a real-world
*managed* asset (a pump, an air-handling unit, a door, a fire extinguisher)
versus pure geometry (a wall, a slab). It is a pure function of the
element's category / type / family / properties, so it is fully unit
-tested and never touches the DB.

The result feeds a "Discover assets" flow: the user reviews ranked
candidates and bulk-promotes the real ones. AI-suggests / human-confirms -
nothing is auto-flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["CandidateScore", "score_candidate", "extract_suggested_asset_info"]

# Categories that are almost always managed assets in FM (serviceable
# equipment with manufacturers, serials and warranties). Matched
# case-insensitively as substrings against the element's category /
# element_type / family.
_ASSET_CATEGORY_HINTS: dict[str, int] = {
    "mechanical equipment": 50,
    "air terminal": 45,
    "air handling": 50,
    "ahu": 50,
    "pump": 50,
    "boiler": 50,
    "chiller": 50,
    "fan": 45,
    "duct accessor": 35,
    "pipe accessor": 35,
    "valve": 40,
    "electrical equipment": 50,
    "electrical fixture": 40,
    "lighting fixture": 40,
    "lighting device": 35,
    "fire alarm": 45,
    "fire protection": 45,
    "sprinkler": 40,
    "extinguisher": 45,
    "security device": 40,
    "communication device": 35,
    "data device": 35,
    "nurse call": 40,
    "plumbing fixture": 40,
    "sanitary": 35,
    "specialty equipment": 45,
    "elevator": 50,
    "lift": 45,
    "escalator": 50,
    "generator": 50,
    "transformer": 50,
    "switchgear": 50,
    "distribution board": 45,
    "panel board": 40,
    "door": 25,
    "window": 15,
    "curtain panel": 10,
}

# Pure-geometry categories that are NOT managed assets - strong negative.
_GEOMETRY_CATEGORY_HINTS: tuple[str, ...] = (
    "wall",
    "floor",
    "roof",
    "ceiling",
    "slab",
    "ramp",
    "stair",
    "railing",
    "column",
    "beam",
    "framing",
    "foundation",
    "topography",
    "site",
    "grid",
    "level",
    "reference",
    "reveal",
    "cornice",
    "generic model",
)

# Property keys that, when present and non-empty, signal a real asset
# (manufacturers fill these in; geometry never has them).
_ASSET_PROPERTY_KEYS: dict[str, int] = {
    "manufacturer": 25,
    "model": 12,
    "serial": 20,
    "serial number": 20,
    "serial_number": 20,
    "mark": 8,
    "asset tag": 25,
    "asset_tag": 25,
    "warranty": 20,
    "omniclass": 6,
    "uniformat": 6,
    "mounting": 4,
}

# How candidate property names map onto canonical asset_info keys when we
# pre-fill the promotion form.
_PROPERTY_TO_ASSET_INFO: dict[str, str] = {
    "manufacturer": "manufacturer",
    "model": "model",
    "type name": "model",
    "type_name": "model",
    "serial": "serial_number",
    "serial number": "serial_number",
    "serial_number": "serial_number",
    "mark": "asset_tag",
    "asset tag": "asset_tag",
    "asset_tag": "asset_tag",
}


@dataclass(slots=True)
class CandidateScore:
    """Discovery score for one BIM element."""

    score: int  # 0-100, higher = more likely a managed asset
    reasons: list[str]
    is_candidate: bool  # score >= threshold


def _haystack(
    element_type: str | None,
    properties: dict[str, Any] | None,
) -> str:
    """Lower-cased blob of the element's classifying strings."""
    parts: list[str] = [element_type or ""]
    props = properties or {}
    for key in ("category", "family", "family name", "family_name", "type name", "type_name"):
        val = props.get(key)
        if isinstance(val, str):
            parts.append(val)
    return " ".join(parts).lower()


def score_candidate(
    *,
    element_type: str | None,
    properties: dict[str, Any] | None,
    already_tracked: bool = False,
    threshold: int = 35,
) -> CandidateScore:
    """Score how likely a BIM element is a managed asset.

    Pure: depends only on the element's classifying strings and property
    keys. Returns a 0-100 score, human-readable reasons, and whether it
    clears ``threshold``. Already-tracked elements are never candidates
    (they are assets already).
    """
    if already_tracked:
        return CandidateScore(score=0, reasons=["already_tracked"], is_candidate=False)

    hay = _haystack(element_type, properties)
    props = properties or {}
    score = 0
    reasons: list[str] = []

    # Strong negative for pure geometry categories.
    for neg in _GEOMETRY_CATEGORY_HINTS:
        if neg in hay:
            return CandidateScore(
                score=0,
                reasons=[f"geometry:{neg}"],
                is_candidate=False,
            )

    # Positive category hints (take the strongest single match).
    best_cat = 0
    best_cat_name = ""
    for hint, weight in _ASSET_CATEGORY_HINTS.items():
        if hint in hay and weight > best_cat:
            best_cat = weight
            best_cat_name = hint
    if best_cat:
        score += best_cat
        reasons.append(f"category:{best_cat_name}")

    # Property-presence signals.
    lowered = {str(k).lower(): v for k, v in props.items()}
    for key, weight in _ASSET_PROPERTY_KEYS.items():
        val = lowered.get(key)
        if isinstance(val, str) and val.strip():
            score += weight
            reasons.append(f"prop:{key}")

    score = max(0, min(100, score))
    return CandidateScore(
        score=score,
        reasons=reasons,
        is_candidate=score >= threshold,
    )


def extract_suggested_asset_info(properties: dict[str, Any] | None) -> dict[str, str]:
    """Pre-fill canonical asset_info from a candidate's BIM properties.

    Used to seed the promotion form so the user does not retype the
    manufacturer / model / mark the model already carries. Only non-empty
    string values are lifted; later mappings win for the same target key
    only when the earlier one was empty.
    """
    props = properties or {}
    lowered = {str(k).lower(): v for k, v in props.items()}
    out: dict[str, str] = {}
    for prop_key, target in _PROPERTY_TO_ASSET_INFO.items():
        if target in out:
            continue
        val = lowered.get(prop_key)
        if isinstance(val, str) and val.strip():
            out[target] = val.strip()
    return out
