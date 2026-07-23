# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Deterministic symbol/shape signature recogniser for match-elements.

This module is a small, fully deterministic increment toward
"item #18 - ML quantity extraction / symbol recognition". It does NOT
do computer vision. There is no trained model, no raster pixel access,
no YOLO / PaddleOCR, and no heavy dependency. It works exclusively on
the *structured* descriptors that the canonical format (or an existing
match-group record) already carries: a category string, geometric
quantities (length / width / height / area / volume / diameter), and a
flat property dictionary.

HONESTY NOTE (read before extending):
    Full computer-vision symbol detection from raster drawings is a
    separate concern and lives in the standalone ``cv-pipeline`` service
    (YOLOv11 + PaddleOCR, roadmap Phase 3). That service turns *pixels*
    into structured elements. THIS module consumes the structured
    elements that already exist and ranks them against a built-in
    library of known symbol signatures. Do not claim CV / ML detection
    here that this code does not perform.

What it does, deterministically:
    1. Compute a *shape signature* from a descriptor:
         - a normalised category token,
         - the dominant dimension ratios (e.g. height/length for a
           door, width/height for a window), derived from quantities,
         - a small property fingerprint (sorted, normalised key=value
           pairs for known structural properties).
    2. Rank that signature against a built-in reference library of
       symbol archetypes (door, window, column, beam, wall, pipe, duct,
       fixture). Each archetype declares plausible ranges for its
       defining ratios plus expected keyword hints.
    3. Return ranked suggestions, each with a confidence score in
       ``[0, 1]`` and the list of contributing factors so the UI (and a
       human reviewer) can see *why* a symbol ranked where it did.

The output is a *suggestion*. Nothing is auto-applied. Confidence is an
honest blend of category agreement, dimension-ratio fit, and property
keyword hits - never a fabricated certainty.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ── Normalisation ────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_token(value: Any) -> str:
    """Lower-case, accent-fold and collapse a free-form value to a token.

    Args:
        value: Any value (``None`` is treated as empty).

    Returns:
        A normalised ASCII token with internal whitespace collapsed to a
        single space and surrounding whitespace stripped. Returns ``""``
        for empty / ``None`` input.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    return _WS_RE.sub(" ", text).strip()


def _slug(value: Any) -> str:
    """Collapse a value to a bare ``[a-z0-9]`` slug (no separators)."""
    token = _normalize_token(value)
    return _NON_ALNUM_RE.sub("", token)


# ── Quantity extraction ──────────────────────────────────────────────────
#
# Canonical-format quantities use SI suffixes (``length_m``, ``area_m2``,
# ``volume_m3``). Match-group rollups and ad-hoc descriptors may use bare
# keys (``length``, ``width``, ``height``, ``diameter``). We accept both
# and normalise to a metre-based internal dict so ratio maths is
# unit-consistent. Values below ``_EPS`` are treated as "absent" so a
# zero placeholder never poisons a ratio.

_EPS: float = 1e-9

# Map of canonical dimension name -> the descriptor keys that supply it,
# in priority order. The first present, positive value wins.
_DIMENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "length": ("length_m", "length", "len", "l"),
    "width": ("width_m", "width", "thickness_m", "thickness", "w"),
    "height": ("height_m", "height", "depth_m", "depth", "h"),
    "area": ("area_m2", "area", "a"),
    "volume": ("volume_m3", "volume", "v"),
    "diameter": ("diameter_m", "diameter", "dia", "nominal_size_mm", "d"),
}

# Keys whose source unit is millimetres and must be scaled to metres so
# they compose with the metre-based length/width/height in ratio maths.
_MM_KEYS: frozenset[str] = frozenset({"nominal_size_mm"})


def _coerce_float(value: Any) -> float | None:
    """Best-effort float coercion. Returns ``None`` for non-finite/invalid.

    Accepts numbers and numeric strings (``"240"``, ``"3.5"``). A leading
    unit-free numeric prefix is honoured so ``"240 mm"`` -> ``240.0``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"[-+]?\d*\.?\d+", text)
    if match is None:
        return None
    try:
        f = float(match.group(0))
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def extract_dimensions(quantities: dict[str, Any] | None) -> dict[str, float]:
    """Normalise a raw quantities dict to metre-based canonical dimensions.

    Args:
        quantities: Free-form measurement dict from a canonical element or
            a match-group rollup. May be ``None``.

    Returns:
        A dict containing only the canonical dimension names
        (``length`` / ``width`` / ``height`` / ``area`` / ``volume`` /
        ``diameter``) that resolved to a strictly positive metre value.
        Keys with no positive source value are omitted entirely so callers
        can rely on ``in`` checks.
    """
    if not quantities:
        return {}
    out: dict[str, float] = {}
    for canonical, aliases in _DIMENSION_ALIASES.items():
        for key in aliases:
            if key not in quantities:
                continue
            val = _coerce_float(quantities[key])
            if val is None or val <= _EPS:
                continue
            if key in _MM_KEYS:
                val = val / 1000.0
            out[canonical] = val
            break
    return out


def _ratio(numerator: float, denominator: float) -> float | None:
    """Safe ratio. Returns ``None`` when the denominator is ~zero."""
    if abs(denominator) <= _EPS:
        return None
    return numerator / denominator


# ── Shape signature ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShapeSignature:
    """A deterministic, comparable fingerprint of one estimable element.

    Attributes:
        category: Normalised category slug (``""`` when unknown).
        ratios: Dimensionless dominant ratios derived from the element's
            geometry. Keys are stable names (``aspect``, ``slenderness``,
            ``planarity``). Values are positive floats. Missing ratios are
            simply absent.
        property_fingerprint: Sorted ``key=value`` tokens for recognised
            structural properties (material, is_external, ...). Used as a
            keyword-hint source, not as a hard filter.
        raw_dimensions: The metre-based canonical dimensions the signature
            was computed from, kept for explainability.
    """

    category: str
    ratios: dict[str, float] = field(default_factory=dict)
    property_fingerprint: tuple[str, ...] = ()
    raw_dimensions: dict[str, float] = field(default_factory=dict)


# Property keys that carry symbol-relevant structural meaning. Other
# free-form properties are ignored so noise (GUIDs, timestamps) does not
# dilute the keyword-hint signal.
_FINGERPRINT_KEYS: tuple[str, ...] = (
    "material",
    "material_class",
    "is_external",
    "is_loadbearing",
    "is_structural",
    "fire_rating",
    "system_type",
    "ifc_class",
    "ifc_predefined_type",
)


def compute_signature(descriptor: dict[str, Any]) -> ShapeSignature:
    """Compute a deterministic :class:`ShapeSignature` for a descriptor.

    Args:
        descriptor: A loose dict with optional keys ``category`` (str),
            ``quantities`` (dict), and ``properties`` (dict). Mirrors the
            shape carried by a canonical-format element and the rollup of
            a stored match group.

    Returns:
        A :class:`ShapeSignature`. Deterministic: the same descriptor
        always yields an equal signature (ratios rounded to a stable
        precision, fingerprint sorted).
    """
    category = _slug(descriptor.get("category"))
    dims = extract_dimensions(descriptor.get("quantities"))

    ratios: dict[str, float] = {}
    # "aspect": longer horizontal extent over shorter horizontal extent -
    # distinguishes slender rectangles (a door panel) from squarish ones
    # (a fixture footprint). Computed from the two largest linear extents
    # among {length, width, height} so it works regardless of which pair a
    # given source supplies (a door arrives as height+width, a beam as
    # length+width). Always >= 1 so ordering is stable.
    linear = sorted(
        (dims[k] for k in ("length", "width", "height") if k in dims),
        reverse=True,
    )
    if len(linear) >= 2:
        r = _ratio(linear[0], linear[1])
        if r is not None:
            ratios["aspect"] = round(r, 4)
    # "slenderness": vertical extent over the larger horizontal extent -
    # high for columns/pipes (tall, thin), low for slabs/walls panels.
    if "height" in dims:
        plan = max((dims.get(k, 0.0) for k in ("length", "width", "diameter")), default=0.0)
        r = _ratio(dims["height"], plan)
        if r is not None:
            ratios["slenderness"] = round(r, 4)
    # "planarity": area over volume (1/thickness proxy) - high for thin
    # plate-like things (walls, ducts), low for chunky members.
    if "area" in dims and "volume" in dims:
        r = _ratio(dims["area"], dims["volume"])
        if r is not None:
            ratios["planarity"] = round(r, 4)
    # "roundness": diameter present at all is itself a strong round-symbol
    # hint (pipes, columns); encode as a flag-like 1.0 so archetypes can
    # reward it.
    if "diameter" in dims:
        ratios["roundness"] = 1.0

    props = descriptor.get("properties") or {}
    fingerprint: list[str] = []
    if isinstance(props, dict):
        for key in _FINGERPRINT_KEYS:
            if key not in props:
                continue
            val = props[key]
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            fingerprint.append(f"{key}={_normalize_token(val)}")
    fingerprint.sort()

    return ShapeSignature(
        category=category,
        ratios=ratios,
        property_fingerprint=tuple(fingerprint),
        raw_dimensions=dims,
    )


# ── Reference library ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RatioRange:
    """An inclusive plausible range for one named ratio.

    A descriptor's ratio inside ``[low, high]`` scores full marks; outside
    it decays smoothly toward zero over ``tolerance`` (in the ratio's own
    units), so a near-miss still contributes a little. ``weight`` scales
    this ratio's contribution to the archetype score.
    """

    name: str
    low: float
    high: float
    tolerance: float
    weight: float = 1.0

    def fit(self, value: float) -> float:
        """Return a 0..1 fit for ``value`` against this range.

        Inside the range -> ``1.0``. Outside -> linear decay over
        ``tolerance``, clamped at ``0.0``.
        """
        if self.low <= value <= self.high:
            return 1.0
        if self.tolerance <= _EPS:
            return 0.0
        gap = self.low - value if value < self.low else value - self.high
        return max(0.0, 1.0 - gap / self.tolerance)


@dataclass(frozen=True)
class SymbolArchetype:
    """A known symbol with the signature ranges that recognise it.

    Attributes:
        symbol: Stable symbol id (``"door"``, ``"window"``, ...).
        categories: Category slugs that strongly imply this symbol. An
            exact category match is the single biggest score contributor.
        ratio_ranges: Plausible ranges for defining ratios.
        keyword_hints: Property-fingerprint substrings that nudge the
            score up (e.g. ``"system_type=pipe"`` for a pipe).
    """

    symbol: str
    categories: frozenset[str]
    ratio_ranges: tuple[RatioRange, ...] = ()
    keyword_hints: frozenset[str] = frozenset()


# Built-in seed library. Ranges are deliberately broad and conservative -
# this is a heuristic recogniser, not a calibrated model. Each archetype's
# defining ratios reflect typical building-element proportions in metres.
_SEED_LIBRARY: tuple[SymbolArchetype, ...] = (
    SymbolArchetype(
        symbol="door",
        categories=frozenset({"door", "ifcdoor", "tur", "porte", "dver"}),
        ratio_ranges=(
            # Door leaf: ~2.1m high, ~0.9m wide -> aspect ~2.3, slender ~2.3.
            RatioRange("aspect", 1.6, 3.2, 1.2, weight=1.0),
            RatioRange("slenderness", 1.5, 3.5, 1.5, weight=0.8),
        ),
        keyword_hints=frozenset({"ifc_class=ifcdoor"}),
    ),
    SymbolArchetype(
        symbol="window",
        categories=frozenset({"window", "ifcwindow", "fenster", "fenetre", "okno"}),
        ratio_ranges=(
            # Windows tend squarer than doors and rarely floor-height.
            RatioRange("aspect", 0.6, 2.0, 1.0, weight=1.0),
            RatioRange("slenderness", 0.4, 1.6, 1.0, weight=0.8),
        ),
        keyword_hints=frozenset({"ifc_class=ifcwindow", "is_external=true"}),
    ),
    SymbolArchetype(
        symbol="column",
        categories=frozenset({"column", "ifccolumn", "stutze", "pilier", "kolonna"}),
        ratio_ranges=(
            # Tall and thin: slenderness well above 1.
            RatioRange("slenderness", 3.0, 40.0, 8.0, weight=1.0),
            RatioRange("aspect", 1.0, 2.5, 1.5, weight=0.4),
        ),
        keyword_hints=frozenset({"ifc_class=ifccolumn", "is_loadbearing=true"}),
    ),
    SymbolArchetype(
        symbol="beam",
        categories=frozenset({"beam", "ifcbeam", "trager", "poutre", "balka"}),
        ratio_ranges=(
            # Long and horizontal: high aspect, low slenderness.
            RatioRange("aspect", 4.0, 60.0, 12.0, weight=1.0),
            RatioRange("slenderness", 0.0, 0.6, 0.6, weight=0.6),
        ),
        keyword_hints=frozenset({"ifc_class=ifcbeam", "is_structural=true"}),
    ),
    SymbolArchetype(
        symbol="wall",
        categories=frozenset(
            {"wall", "ifcwall", "ifcwallstandardcase", "wand", "mur", "stena"},
        ),
        ratio_ranges=(
            # Plate-like elevation: aspect (longest/2nd-longest) >= ~2 for a
            # panel, much higher for long runs; planarity (area/volume)
            # high because walls are thin. Planarity is the strong signal.
            RatioRange("aspect", 2.0, 80.0, 15.0, weight=0.6),
            RatioRange("planarity", 3.0, 200.0, 40.0, weight=1.0),
        ),
        keyword_hints=frozenset({"ifc_class=ifcwall", "is_loadbearing=true"}),
    ),
    SymbolArchetype(
        symbol="pipe",
        categories=frozenset(
            {"pipe", "ifcpipesegment", "ifcpipe", "rohr", "tuyau", "truba"},
        ),
        ratio_ranges=(
            RatioRange("roundness", 1.0, 1.0, 0.0, weight=0.7),
            RatioRange("slenderness", 5.0, 500.0, 50.0, weight=1.0),
        ),
        keyword_hints=frozenset({"system_type=pipe", "ifc_class=ifcpipesegment"}),
    ),
    SymbolArchetype(
        symbol="duct",
        categories=frozenset(
            {"duct", "ifcductsegment", "ifcduct", "kanal", "gaine", "vozduhovod"},
        ),
        ratio_ranges=(
            RatioRange("aspect", 1.0, 4.0, 2.0, weight=0.5),
            RatioRange("slenderness", 4.0, 400.0, 40.0, weight=1.0),
        ),
        keyword_hints=frozenset({"system_type=duct", "ifc_class=ifcductsegment"}),
    ),
    SymbolArchetype(
        symbol="fixture",
        categories=frozenset(
            {
                "fixture",
                "ifcsanitaryterminal",
                "ifcfurnishingelement",
                "furniture",
                "armatur",
                "fixturefitting",
            },
        ),
        ratio_ranges=(
            # Compact, near-unit footprint, modest height.
            RatioRange("aspect", 1.0, 2.5, 1.5, weight=0.6),
            RatioRange("slenderness", 0.3, 2.0, 1.2, weight=0.6),
        ),
        keyword_hints=frozenset({"ifc_class=ifcsanitaryterminal"}),
    ),
)


def seed_library() -> tuple[SymbolArchetype, ...]:
    """Return the built-in symbol archetype library (immutable tuple)."""
    return _SEED_LIBRARY
