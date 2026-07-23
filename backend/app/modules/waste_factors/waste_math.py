# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure net-to-gross waste-factor engine.

Converts a net measured quantity into the gross procurement quantity by
multiplying it by a waste, lap or coverage factor (``gross = net * factor``).
The factor is ``>= 1``: ``1.10`` means order 10 percent more than the drawn
quantity to cover offcuts, laps and breakage.

Stdlib only (``decimal`` + ``dataclasses``) so the engine imports on any
interpreter and its tests run without a database or SQLAlchemy on the path.
Quantities quantize to 4 decimal places with ``ROUND_HALF_UP``; every value is a
``Decimal``, never a float, so a large takeoff quantity never drifts.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Quantities are carried to 4 decimal places (matches the takeoff / BOQ grid).
QTY_PLACES: Decimal = Decimal("0.0001")
# A stored factor must be at least 1 (a factor below 1 would drop quantity).
FACTOR_MIN: Decimal = Decimal("1")
# Fallback multiplier for a category with no library entry: pass the net
# quantity through unchanged rather than silently inflate or shrink it.
DEFAULT_FACTOR: Decimal = Decimal("1.0")


def quantize_qty(value: Decimal) -> Decimal:
    """Round a quantity to 4 decimal places, half-up.

    Args:
        value: Any Decimal quantity.

    Returns:
        The value quantized to :data:`QTY_PLACES` using ``ROUND_HALF_UP``.
    """
    return Decimal(value).quantize(QTY_PLACES, rounding=ROUND_HALF_UP)


def normalize_category(category: str) -> str:
    """Canonical lookup key for a category: trimmed and case-folded.

    Keeps ``"Rebar"``, ``" rebar "`` and ``"REBAR"`` resolving to the same
    library entry so the estimator does not have to match casing exactly.
    """
    return category.strip().casefold()


def apply(net_qty: Decimal, factor: Decimal) -> Decimal:
    """Return the gross quantity for one line: ``gross = net * factor``.

    Args:
        net_qty: The net measured (drawn) quantity.
        factor: The waste / lap / coverage multiplier (``>= 1`` in normal use).

    Returns:
        The gross quantity, quantized to 4 decimal places. Pure ``Decimal``
        arithmetic, no float, so the result never drifts on large inputs.
    """
    return quantize_qty(Decimal(net_qty) * Decimal(factor))


@dataclass(frozen=True)
class NetLine:
    """One net input line for batch conversion."""

    category: str
    net_qty: Decimal


@dataclass(frozen=True)
class GrossLine:
    """One converted line: the resolved factor and the gross quantity.

    ``matched`` is ``False`` when the category had no library entry and the
    default factor (1.0) was used, so a caller can flag pass-through lines.
    """

    category: str
    net_qty: Decimal
    factor: Decimal
    gross_qty: Decimal
    matched: bool


def resolve_factor(
    category: str,
    factors: Mapping[str, Decimal],
    default: Decimal = DEFAULT_FACTOR,
) -> tuple[Decimal, bool]:
    """Resolve the factor for one category, case-insensitively.

    Args:
        category: The material / work category to look up.
        factors: Mapping of category -> factor (any casing / surrounding
            whitespace; it is normalized here).
        default: Factor to return when the category is absent.

    Returns:
        A ``(factor, matched)`` pair. ``matched`` is ``False`` when the
        category was not found and ``default`` was returned.
    """
    lookup = {normalize_category(key): value for key, value in factors.items()}
    key = normalize_category(category)
    if key in lookup:
        return Decimal(lookup[key]), True
    return Decimal(default), False


def batch_net_to_gross(
    lines: Iterable[NetLine],
    factors: Mapping[str, Decimal],
    default: Decimal = DEFAULT_FACTOR,
) -> list[GrossLine]:
    """Convert every net line to gross, resolving the factor by category.

    Unmatched categories fall back to ``default`` (1.0) and are flagged
    ``matched=False``. The ``factors`` map is normalized once up front so a
    large takeoff resolves in a single pass without rebuilding the lookup.

    Args:
        lines: The net lines to convert.
        factors: Mapping of category -> factor for the library in scope.
        default: Factor applied to categories absent from ``factors``.

    Returns:
        One :class:`GrossLine` per input line, in the same order.
    """
    lookup = {normalize_category(key): value for key, value in factors.items()}
    default_dec = Decimal(default)
    result: list[GrossLine] = []
    for line in lines:
        key = normalize_category(line.category)
        matched = key in lookup
        factor = Decimal(lookup[key]) if matched else default_dec
        result.append(
            GrossLine(
                category=line.category,
                net_qty=quantize_qty(Decimal(line.net_qty)),
                factor=factor,
                gross_qty=apply(line.net_qty, factor),
                matched=matched,
            ),
        )
    return result
