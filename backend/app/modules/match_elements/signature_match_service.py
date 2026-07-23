# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Deterministic symbol-signature ranking service for match-elements.

:class:`SignatureMatchService` takes a structured element descriptor
(category + geometry quantities + properties already present in the
canonical JSON or a stored match-group record), computes a deterministic
:class:`ShapeSignature`, and ranks it against the built-in reference
library of symbol archetypes. Each suggestion carries a confidence score
in ``[0, 1]`` plus the contributing factors so a human reviewer can see
*why* a symbol ranked where it did.

HONESTY NOTE:
    This is NOT computer vision. There is no model, no pixel access, and
    no ML inference here. Raster CV symbol detection (turning drawing
    pixels into elements) is the separate ``cv-pipeline`` service
    (YOLO / PaddleOCR, roadmap Phase 3). This service only ranks
    *already-structured* descriptors. Confidence is an honest, fully
    explainable blend of category agreement, dimension-ratio fit and
    property keyword hits - it never fabricates certainty.

The service is intentionally stateless and dependency-free so it can be
unit-tested as pure logic; the optional descriptor-from-stored-group
helper takes its inputs from the caller (the router resolves and
authorises the group first), keeping IDOR enforcement in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.match_elements.symbol_signature import (
    ShapeSignature,
    SymbolArchetype,
    compute_signature,
    seed_library,
)

# Score-blend weights. Category agreement dominates because an exact
# category match is the strongest signal we have; geometry and keyword
# hints refine the ordering and let category-less descriptors still rank.
# The three weights sum to 1.0 so a perfect descriptor scores exactly 1.0.
_W_CATEGORY: float = 0.55
_W_RATIOS: float = 0.30
_W_KEYWORDS: float = 0.15

# Confidence-band thresholds. Mirror the platform's high/medium/low
# language so the UI renders the same traffic-light chips it uses for the
# vector/lexical matchers.
_BAND_HIGH: float = 0.70
_BAND_MEDIUM: float = 0.40


@dataclass(frozen=True)
class SymbolSuggestion:
    """One ranked symbol suggestion for a descriptor.

    Attributes:
        symbol: The matched archetype id (``"door"``, ``"pipe"``, ...).
        confidence: Honest score in ``[0, 1]`` - a weighted blend of
            category agreement, ratio fit and keyword hits.
        confidence_band: ``"high"`` / ``"medium"`` / ``"low"``.
        factors: Human-readable contributing factors, each ``{name,
            weight, contribution, detail}``, so the reviewer sees why.
        rank: 0-based position after sorting (0 = best).
    """

    symbol: str
    confidence: float
    confidence_band: str
    factors: list[dict[str, Any]] = field(default_factory=list)
    rank: int = 0


@dataclass(frozen=True)
class SymbolSuggestionResult:
    """The full result of a suggest-symbols call.

    Attributes:
        signature: The computed :class:`ShapeSignature` (echoed back so
            the UI can show what was fingerprinted).
        suggestions: Ranked suggestions, best first. Empty when the
            library is empty.
        note: Honest provenance string clarifying this is deterministic
            heuristic ranking, not CV/ML detection.
    """

    signature: ShapeSignature
    suggestions: list[SymbolSuggestion] = field(default_factory=list)
    note: str = (
        "Deterministic shape-signature heuristic over structured "
        "geometry/properties. Raster computer-vision symbol detection "
        "is the separate cv-pipeline service (roadmap Phase 3)."
    )


def _band_for(confidence: float) -> str:
    """Map a confidence score onto the high/medium/low band."""
    if confidence >= _BAND_HIGH:
        return "high"
    if confidence >= _BAND_MEDIUM:
        return "medium"
    return "low"


def _category_score(signature: ShapeSignature, archetype: SymbolArchetype) -> float:
    """Return 1.0 on exact category match, else a soft containment score.

    Exact slug membership is full marks. As a fallback, a substring
    overlap (either direction) earns partial credit so ``"ifcwallstd"``
    still leans toward ``wall`` - but only when the descriptor actually
    carried a category. A category-less descriptor scores 0 here and must
    rely on geometry + keywords.
    """
    cat = signature.category
    if not cat:
        return 0.0
    if cat in archetype.categories:
        return 1.0
    for known in archetype.categories:
        if known and (known in cat or cat in known):
            return 0.5
    return 0.0


def _ratio_score(
    signature: ShapeSignature,
    archetype: SymbolArchetype,
) -> tuple[float, list[dict[str, Any]]]:
    """Score the descriptor's ratios against the archetype's ranges.

    Returns the weighted-mean fit over the ranges that the descriptor can
    actually evaluate (i.e. has the ratio for), plus a per-ratio factor
    list. Ranges the descriptor cannot evaluate are skipped rather than
    penalised - a door descriptor with no volume should not be docked for
    a planarity range it cannot test.
    """
    factors: list[dict[str, Any]] = []
    total_weight = 0.0
    weighted_fit = 0.0
    for rng in archetype.ratio_ranges:
        if rng.name not in signature.ratios:
            continue
        value = signature.ratios[rng.name]
        fit = rng.fit(value)
        total_weight += rng.weight
        weighted_fit += rng.weight * fit
        factors.append(
            {
                "name": f"ratio:{rng.name}",
                "weight": round(rng.weight, 4),
                "contribution": round(fit, 4),
                "detail": (
                    f"{rng.name}={value:g} vs [{rng.low:g}, {rng.high:g}] (±{rng.tolerance:g}) -> fit {fit:.2f}"
                ),
            },
        )
    if total_weight <= 0.0:
        return (0.0, factors)
    return (weighted_fit / total_weight, factors)


def _keyword_score(
    signature: ShapeSignature,
    archetype: SymbolArchetype,
) -> tuple[float, list[dict[str, Any]]]:
    """Score property-fingerprint hits against the archetype's hints.

    Each hint that appears (as a substring) in any fingerprint token earns
    a hit. Score = hits / total_hints, so the archetype's full keyword set
    must be present for a perfect keyword score. Archetypes with no hints
    score 0 here (neutral - keywords only ever help).
    """
    factors: list[dict[str, Any]] = []
    if not archetype.keyword_hints:
        return (0.0, factors)
    fingerprint = signature.property_fingerprint
    hits = 0
    for hint in sorted(archetype.keyword_hints):
        matched = any(hint in token for token in fingerprint)
        if matched:
            hits += 1
            factors.append(
                {
                    "name": f"keyword:{hint}",
                    "weight": 1.0,
                    "contribution": 1.0,
                    "detail": f"property hint '{hint}' present",
                },
            )
    return (hits / len(archetype.keyword_hints), factors)


class SignatureMatchService:
    """Rank a structured descriptor against the symbol-signature library.

    Stateless and deterministic: the same descriptor + library always
    yields the same ordering and the same confidence scores. AI/heuristic
    SUGGESTS; the human confirms downstream via the existing apply/confirm
    path - this service never writes anything.
    """

    def __init__(
        self,
        library: tuple[SymbolArchetype, ...] | None = None,
    ) -> None:
        """Create the service.

        Args:
            library: Override the built-in archetype library (used by
                tests for the empty-library / custom-library cases). When
                ``None``, the built-in :func:`seed_library` is used.
        """
        self._library: tuple[SymbolArchetype, ...] = seed_library() if library is None else library

    @property
    def library(self) -> tuple[SymbolArchetype, ...]:
        """The archetype library this service ranks against."""
        return self._library

    def suggest(
        self,
        descriptor: dict[str, Any],
        *,
        top_k: int = 5,
        min_confidence: float = 0.0,
    ) -> SymbolSuggestionResult:
        """Compute and rank symbol suggestions for a descriptor.

        Args:
            descriptor: Loose dict with optional ``category`` (str),
                ``quantities`` (dict) and ``properties`` (dict). Mirrors a
                canonical-format element or a stored match-group rollup.
            top_k: Maximum number of suggestions to return (best first).
            min_confidence: Drop suggestions scoring below this floor.
                ``0.0`` keeps everything in the library.

        Returns:
            A :class:`SymbolSuggestionResult` with the computed signature
            and the ranked suggestions. Deterministic ordering: by
            descending confidence, then ascending symbol id as a stable
            tie-break.
        """
        signature = compute_signature(descriptor)
        scored: list[SymbolSuggestion] = []

        for archetype in self._library:
            cat = _category_score(signature, archetype)
            ratio, ratio_factors = _ratio_score(signature, archetype)
            keyword, keyword_factors = _keyword_score(signature, archetype)

            confidence = _W_CATEGORY * cat + _W_RATIOS * ratio + _W_KEYWORDS * keyword
            # Clamp defensively - the blend is already bounded, but a future
            # weight edit must never leak a value outside [0, 1].
            confidence = max(0.0, min(1.0, confidence))

            factors: list[dict[str, Any]] = []
            if cat > 0.0:
                factors.append(
                    {
                        "name": "category",
                        "weight": round(_W_CATEGORY, 4),
                        "contribution": round(cat, 4),
                        "detail": (f"category '{signature.category or '∅'}' vs {sorted(archetype.categories)}"),
                    },
                )
            factors.extend(ratio_factors)
            factors.extend(keyword_factors)

            scored.append(
                SymbolSuggestion(
                    symbol=archetype.symbol,
                    confidence=round(confidence, 4),
                    confidence_band=_band_for(confidence),
                    factors=factors,
                ),
            )

        # Deterministic sort: confidence desc, then symbol asc (stable
        # tie-break so equal-confidence archetypes never reorder run-to-run).
        scored.sort(key=lambda s: (-s.confidence, s.symbol))

        # Re-stamp ``rank`` as the post-filter position so a min_confidence
        # cut never leaves holes in the rank sequence.
        result: list[SymbolSuggestion] = []
        for suggestion in scored:
            if suggestion.confidence < min_confidence:
                continue
            result.append(
                SymbolSuggestion(
                    symbol=suggestion.symbol,
                    confidence=suggestion.confidence,
                    confidence_band=suggestion.confidence_band,
                    factors=suggestion.factors,
                    rank=len(result),
                ),
            )
            if len(result) >= top_k:
                break

        return SymbolSuggestionResult(signature=signature, suggestions=result)


# Module-level singleton mirrors the ``get_service`` convention used by
# the rest of the match_elements module. Stateless, so a shared instance
# is safe across requests.
_signature_service_singleton: SignatureMatchService | None = None


def get_signature_service() -> SignatureMatchService:
    """Return the shared :class:`SignatureMatchService` instance."""
    global _signature_service_singleton
    if _signature_service_singleton is None:
        _signature_service_singleton = SignatureMatchService()
    return _signature_service_singleton


def descriptor_from_group_row(
    group_key: str | None,
    quantities: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build a suggest-symbols descriptor from a stored match-group row.

    The router resolves and authorises the :class:`MatchGroup` first, then
    passes its fields here. We never load the row ourselves so IDOR
    enforcement stays in one place (the router's session/project guard).

    The group's ``group_key`` is a pipe-string like
    ``"ifc_class:IfcWall|material:STB|thickness:240"``; we parse it into a
    flat properties dict and lift the category from whichever segment
    looks like a category/class/ifc_class field.

    Args:
        group_key: The composite key (``"field:value|field:value"``).
        quantities: The group's rolled-up quantities dict.
        metadata: The group's ``metadata`` JSON (may carry a richer
            ``properties`` / ``category`` already).

    Returns:
        A descriptor dict suitable for :meth:`SignatureMatchService.suggest`.
    """
    properties: dict[str, Any] = {}
    category = ""

    for segment in (group_key or "").split("|"):
        if ":" not in segment:
            continue
        field_name, _, value = segment.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()
        if not field_name or value in ("", "∅"):
            continue
        properties[field_name] = value
        if field_name in ("category", "class", "ifc_class", "ifcclass") and not category:
            category = value

    # Metadata may carry a pre-resolved category / properties that beat the
    # parsed key (e.g. the source adapter stored a clean ``category``).
    meta = metadata or {}
    if isinstance(meta, dict):
        meta_category = meta.get("category")
        if isinstance(meta_category, str) and meta_category.strip():
            category = meta_category.strip()
        meta_props = meta.get("properties")
        if isinstance(meta_props, dict):
            # Stored properties win over key-parsed ones (richer source).
            properties.update(meta_props)

    return {
        "category": category,
        "quantities": quantities or {},
        "properties": properties,
    }
