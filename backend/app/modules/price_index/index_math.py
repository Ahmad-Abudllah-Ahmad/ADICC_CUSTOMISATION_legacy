# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure Decimal math for base-to-current cost-index adjustment.

This module is deliberately free of I/O, ORM and ``float``. Every value is a
:class:`decimal.Decimal` so a rate carried from an old library or a foreign
benchmark keeps every digit on the way to today's money and the project's
region.

Two independent multipliers are resolved from the stored data:

* a *temporal* factor - the ratio of the construction cost index at the target
  period to the index at the base period (:func:`resolve_factor`);
* a *location* factor - the ratio of the regional cost factor at the target
  region to the factor at the base region (:func:`location_multiplier`).

The adjusted amount is ``amount * temporal_factor * location_factor`` rounded
to two decimal places with ``ROUND_HALF_UP`` (:func:`adjust`).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

__all__ = [
    "FACTOR_QUANTUM",
    "MONEY_QUANTUM",
    "PeriodNotFoundError",
    "adjust",
    "combined_factor",
    "location_multiplier",
    "period_for_date",
    "quantize_factor",
    "resolve_factor",
    "to_decimal",
]

# Dimensionless factors are carried at six decimal places - fine enough for
# any index ratio while keeping the reported number tidy and stable.
FACTOR_QUANTUM: Decimal = Decimal("0.000001")

# Money is rounded to two decimal places, the universal minor-unit width used
# across the estimate. Currencies with a different minor unit are a display
# concern handled at the UI layer, not here.
MONEY_QUANTUM: Decimal = Decimal("0.01")


class PeriodNotFoundError(ValueError):
    """Raised when a period is absent from the cost-index series.

    A rate can only be escalated between periods the series actually carries
    an index point for; a missing period is a user error, not a silent no-op.
    """

    def __init__(self, period: str) -> None:
        self.period = period
        super().__init__(f"period {period!r} not found in cost-index series")


def to_decimal(value: Decimal | str | int) -> Decimal:
    """Coerce a supported scalar to a finite :class:`~decimal.Decimal`.

    Args:
        value: A ``Decimal``, decimal ``str`` or ``int``. A ``float`` is
            accepted defensively but routed through ``str`` first so a binary
            artefact such as ``0.1`` never leaks into the math; ``bool`` is
            rejected because a factor is never a flag.

    Returns:
        The value as a finite ``Decimal``.

    Raises:
        ValueError: If the value cannot be parsed or is not finite.
    """
    if isinstance(value, bool):  # bool is an int subclass - reject explicitly
        raise ValueError("boolean is not a valid numeric value")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"cannot parse {value!r} as a decimal") from exc
    if not dec.is_finite():
        raise ValueError("value must be finite (no NaN / Infinity)")
    return dec


def quantize_factor(value: Decimal | str | int) -> Decimal:
    """Round a dimensionless factor to :data:`FACTOR_QUANTUM` (6 dp, HALF_UP)."""
    return to_decimal(value).quantize(FACTOR_QUANTUM, rounding=ROUND_HALF_UP)


def period_for_date(day: date) -> str:
    """Return the ISO year-month period ``"YYYY-MM"`` a date falls in.

    An index series carries at most one point per month, so a rate captured on
    any day of a month escalates from that whole month's index point. The day
    component is deliberately dropped: only the year and month select the
    period. This is the bridge from a stored ``price_as_of`` capture date (or a
    target date) to the period keys :func:`resolve_factor` looks up.

    Args:
        day: The calendar date a rate was captured on, or the date a rate is
            being brought to.

    Returns:
        The zero-padded ``"YYYY-MM"`` period string; for example
        ``date(2019, 3, 7)`` becomes ``"2019-03"``.
    """
    return f"{day.year:04d}-{day.month:02d}"


def _normalise(points: Mapping[str, Decimal | str | int]) -> dict[str, Decimal]:
    """Build a ``{key: Decimal}`` lookup, skipping blank keys."""
    out: dict[str, Decimal] = {}
    for key, raw in points.items():
        if not isinstance(key, str) or not key.strip():
            continue
        out[key.strip()] = to_decimal(raw)
    return out


def resolve_factor(
    series_points: Mapping[str, Decimal | str | int],
    base_period: str,
    target_period: str,
) -> Decimal:
    """Return the temporal escalation factor between two periods of one series.

    ``factor = index(target_period) / index(base_period)``. A factor above one
    means costs rose from the base period to the target period; below one means
    they fell; exactly one means no change (including a same-period request).

    Args:
        series_points: Mapping of period (``"YYYY-MM"``) to its index value for
            a single cost-index series.
        base_period: The period the source money is expressed in.
        target_period: The period to bring the money to.

    Returns:
        The ratio as a ``Decimal`` quantized to :data:`FACTOR_QUANTUM`.

    Raises:
        PeriodNotFoundError: If either period is absent from the series.
        ValueError: If the base period's index value is not strictly positive
            (division would be undefined or produce a negative multiplier).
    """
    lookup = _normalise(series_points)
    base_key = base_period.strip() if isinstance(base_period, str) else base_period
    target_key = target_period.strip() if isinstance(target_period, str) else target_period
    if base_key not in lookup:
        raise PeriodNotFoundError(base_period)
    if target_key not in lookup:
        raise PeriodNotFoundError(target_period)
    base_value = lookup[base_key]
    if base_value <= 0:
        raise ValueError(f"base period {base_period!r} has a non-positive index value")
    return quantize_factor(lookup[target_key] / base_value)


def location_multiplier(
    region_factors: Mapping[str, Decimal | str | int],
    base_region: str | None,
    target_region: str | None,
) -> Decimal:
    """Return the regional multiplier from a base region to a target region.

    ``factor = region(target) / region(base)``. A region with no stored factor
    (or a blank region code) is treated as the national baseline of ``1``, so
    quoting only a target region simply applies that region's own factor and
    quoting neither region leaves the amount unchanged.

    Args:
        region_factors: Mapping of region code to its regional cost factor.
        base_region: The region the source money reflects, or ``None``.
        target_region: The project's region, or ``None``.

    Returns:
        The ratio as a ``Decimal`` quantized to :data:`FACTOR_QUANTUM`.

    Raises:
        ValueError: If a stored base-region factor is not strictly positive.
    """
    lookup = _normalise(region_factors)

    def _resolve(region: str | None) -> Decimal:
        if not region or not region.strip():
            return Decimal("1")
        value = lookup.get(region.strip())
        if value is None or value <= 0:
            return Decimal("1")
        return value

    base_value = _resolve(base_region)
    target_value = _resolve(target_region)
    if base_value <= 0:
        raise ValueError("base region factor must be positive")
    return quantize_factor(target_value / base_value)


def combined_factor(
    temporal_factor: Decimal | str | int,
    location_factor: Decimal | str | int,
) -> Decimal:
    """Return the single applied multiplier ``temporal * location`` (6 dp)."""
    return quantize_factor(to_decimal(temporal_factor) * to_decimal(location_factor))


def adjust(
    amount: Decimal | str | int,
    temporal_factor: Decimal | str | int,
    location_factor: Decimal | str | int,
) -> Decimal:
    """Return the adjusted money amount rounded to :data:`MONEY_QUANTUM`.

    ``adjusted = amount * temporal_factor * location_factor`` computed in full
    Decimal precision and only then rounded to two decimal places with
    ``ROUND_HALF_UP``. Because the whole product is formed before rounding, the
    result never carries the sub-cent drift a ``float`` pipeline would.

    Args:
        amount: The source money amount in its base period and region.
        temporal_factor: The period-to-period multiplier
            (see :func:`resolve_factor`).
        location_factor: The region-to-region multiplier
            (see :func:`location_multiplier`).

    Returns:
        The adjusted amount as a ``Decimal`` quantized to two decimal places.
    """
    product = to_decimal(amount) * to_decimal(temporal_factor) * to_decimal(location_factor)
    return product.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
