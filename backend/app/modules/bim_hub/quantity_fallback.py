# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Fallback quantity extraction for BIM element ingest.

The two XLSX ingest paths (direct upload and the DDC-converter output) fill an
element's ``quantities`` map by matching a fixed list of column names. A DDC
export that labels its quantity columns differently - ``Qto_WallBaseQuantities.
NetVolume``, ``Volume (m3)``, localized headers, bare-unit headers - therefore
lands with an empty quantities map, and the honesty gate then reports a
geometrically-fine model as having no quantities at all (issue #347).

This module recovers those quantities from data the element already carries:

- :func:`derive_quantities_from_columns` reuses the BOQ side's proven column
  normaliser to map any differently-named numeric column to a canonical
  dimension (a net value is preferred over a gross one for the same dimension).
  These are real measured values, just under an unexpected header.
- :func:`derive_quantities_from_bbox` is a last resort: coarse quantities from
  the element's bounding box, chosen by element class. These are approximate,
  so callers tag them (``properties['quantities_source'] = 'geometry_bbox'``)
  and never let them overwrite a measured value.

Both return canonical dimension keys (``area`` / ``volume`` / ``length``, plus
``weight`` for the column path); each call site maps those to its own quantity
key convention (``area_m2`` on upload, ``Area`` on the converter path).
"""

from __future__ import annotations

from typing import Any

# bim_hub already depends on boq.cad_import in a dozen places; boq.cad_import
# does not import bim_hub, so this is a one-way, non-circular reuse of the
# battle-tested column normaliser rather than a second copy of it.
from app.modules.boq.cad_import import _norm_col, _to_float

# Canonical physical dimensions we recover by fuzzy column name. ``count`` is
# deliberately excluded: its synonyms (number / nr / qty) match too many
# unrelated identifier columns to use as a blind fallback.
_COLUMN_DIMS = ("area", "volume", "length", "weight")


def derive_quantities_from_columns(source: dict[str, Any]) -> dict[str, float]:
    """Recover canonical quantities from arbitrarily-named numeric columns.

    Scans every ``source`` cell, normalises its column name to a canonical
    dimension (``_norm_col`` handles the ``Qto_<set>.<Quantity>`` dotted form,
    unit suffixes, net/gross qualifiers and bare-unit headers) and keeps the
    first positive value per dimension. A net-qualified column wins over a
    gross or unqualified one for the same dimension, so a wall reports its
    net volume rather than its gross. Returns only the dimensions found.
    """
    best: dict[str, tuple[bool, float]] = {}
    for key, value in source.items():
        if value is None:
            continue
        dim = _norm_col(str(key))
        if dim not in _COLUMN_DIMS:
            continue
        fval = _to_float(value)
        if fval <= 0.0:
            continue
        is_net = "net" in str(key).lower()
        current = best.get(dim)
        if current is None or (is_net and not current[0]):
            best[dim] = (is_net, fval)
    return {dim: val for dim, (_is_net, val) in best.items()}


# Element-class hints for the bounding-box fallback, matched as case-insensitive
# substrings of the element type / category.
_LINEAR_TOKENS = (
    "beam",
    "column",
    "member",
    "framing",
    "pipe",
    "duct",
    "conduit",
    "cable",
    "rail",
    "girder",
    "truss",
    "rebar",
    "profile",
    "stud",
    "mullion",
)
_PLANAR_TOKENS = (
    "wall",
    "slab",
    "floor",
    "roof",
    "ceiling",
    "plate",
    "panel",
    "sheet",
    "glazing",
    "curtain",
    "cladding",
    "membrane",
    "screed",
    "topping",
)


def _bbox_extents(bbox: dict[str, Any]) -> tuple[float, float, float] | None:
    """Return the (dx, dy, dz) side lengths of a min/max bbox, or None."""
    keys = ("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")
    if any(bbox.get(k) is None for k in keys):
        return None
    dx = abs(_to_float(bbox.get("max_x")) - _to_float(bbox.get("min_x")))
    dy = abs(_to_float(bbox.get("max_y")) - _to_float(bbox.get("min_y")))
    dz = abs(_to_float(bbox.get("max_z")) - _to_float(bbox.get("min_z")))
    if dx <= 0.0 and dy <= 0.0 and dz <= 0.0:
        return None
    return dx, dy, dz


def derive_quantities_from_bbox(
    bbox: dict[str, Any] | None,
    element_type: str | None,
) -> dict[str, float]:
    """Coarse, approximate quantities from an element's bounding box.

    A genuine last resort for an element that carries geometry but no numeric
    quantity under any column. The dimension is chosen by element class:

    - linear members (beam, column, pipe, ...) -> ``length`` = longest extent;
    - planar elements (wall, slab, floor, ...) -> ``area`` = product of the two
      largest extents, plus ``volume`` when the element has real thickness;
    - everything else -> ``volume`` = the box volume.

    Values are estimates. Callers must tag them (so the UI and validation can
    show "estimated" rather than "measured") and must never overwrite a real
    measured value with them.
    """
    if not bbox:
        return {}
    extents = _bbox_extents(bbox)
    if extents is None:
        return {}
    dx, dy, dz = extents
    ordered = sorted((dx, dy, dz), reverse=True)
    etype = (element_type or "").lower()

    if any(tok in etype for tok in _LINEAR_TOKENS):
        return {"length": ordered[0]}
    if any(tok in etype for tok in _PLANAR_TOKENS):
        out = {"area": ordered[0] * ordered[1]}
        if ordered[2] > 0.0:
            out["volume"] = ordered[0] * ordered[1] * ordered[2]
        return out
    # Solid or unknown class: the box volume when it is genuinely 3D, else the
    # footprint area, else the single extent.
    if ordered[1] > 0.0 and ordered[2] > 0.0:
        return {"volume": dx * dy * dz}
    if ordered[1] > 0.0:
        return {"area": ordered[0] * ordered[1]}
    return {"length": ordered[0]}
