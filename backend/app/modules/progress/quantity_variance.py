# OpenConstructionERP - DataDrivenConstruction (DDC)
# DDC-CWICR-OE-2026
"""Pure quantity-variance engine for site progress.

Compares each BOQ position's DESIGN quantity (the quantity taken off /
estimated) against the EARNED quantity installed to date. The earned
quantity is derived from the position's latest recorded percent-complete:

    earned_quantity = design_quantity * percent_complete / 100

which is the quantity analogue of the earned-value (BCWP) bridge the
progress service already runs (position total x percent / 100). No new
storage is needed: both the design quantity (BOQ position) and the
percent-complete (progress entry) are already persisted.

The module is deliberately dependency-free (Decimal + dataclasses only, no
SQLAlchemy / FastAPI / Pydantic) so it can be unit-tested in isolation and
reused by any caller. Every division is guarded: a zero (or absent) design
quantity yields a None variance percent instead of raising.

All quantities are Decimal and stay exact - callers serialise them as
strings, never floats.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
# Variance percent is a derived ratio, so it is quantised to 3 dp (the same
# precision progress percentages carry) for a clean, deterministic value.
_PCT_QUANT = Decimal("0.001")

STATUS_OVER_RUN = "over_run"
STATUS_UNDER_RUN = "under_run"
STATUS_ON_TARGET = "on_target"


# --- Data carriers -----------------------------------------------------------


@dataclass(frozen=True)
class PositionQuantityInput:
    """Raw inputs for one position's variance computation.

    ``design_quantity`` and ``percent_complete`` are already coerced to
    Decimal by the caller; the optional label fields are carried through to
    the result untouched.
    """

    boq_position_id: str
    design_quantity: Decimal
    percent_complete: Decimal
    ordinal: str | None = None
    description: str | None = None
    unit: str | None = None


@dataclass(frozen=True)
class PositionQuantityVariance:
    """Design-vs-earned quantity variance for a single BOQ position."""

    boq_position_id: str
    design_quantity: Decimal
    earned_quantity: Decimal
    percent_complete: Decimal
    variance: Decimal
    variance_percent: Decimal | None
    status: str
    is_over_run: bool
    is_under_run: bool
    ordinal: str | None = None
    description: str | None = None
    unit: str | None = None


@dataclass(frozen=True)
class QuantityVarianceRollup:
    """Project-level rollup across the per-position variances."""

    position_count: int
    over_run_count: int
    under_run_count: int
    on_target_count: int
    design_quantity_total: Decimal
    earned_quantity_total: Decimal
    variance_total: Decimal
    variance_percent: Decimal | None


@dataclass(frozen=True)
class QuantityVarianceReport:
    """Full report: the per-position rows plus the project rollup."""

    positions: tuple[PositionQuantityVariance, ...]
    rollup: QuantityVarianceRollup


# --- Coercion / derivation ---------------------------------------------------


def to_decimal(value: object, default: Decimal = _ZERO) -> Decimal:
    """Coerce a stored value (str / int / float / Decimal / None) to Decimal.

    Blank, None, non-finite (NaN / Infinity) or unparseable values fall back
    to ``default`` so a missing design quantity contributes zero rather than
    raising.

    Args:
        value: The raw stored value.
        default: Fallback returned when ``value`` cannot be parsed finitely.

    Returns:
        A finite Decimal.
    """
    if isinstance(value, Decimal):
        return value if value.is_finite() else default
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        return default
    return result if result.is_finite() else default


def derive_earned_quantity(design_quantity: Decimal, percent_complete: Decimal) -> Decimal:
    """Earned (installed-to-date) quantity from design quantity and percent.

    ``earned = design_quantity * percent_complete / 100``. Dividing by 100 (a
    power of ten) keeps the Decimal exact, so no rounding is applied here -
    the caller decides on presentation precision.
    """
    return design_quantity * percent_complete / _HUNDRED


def _variance_percent(variance: Decimal, design_quantity: Decimal) -> Decimal | None:
    """Return ``variance / design * 100`` at 3 dp, or None when design is zero."""
    if design_quantity == _ZERO:
        return None
    pct = variance / design_quantity * _HUNDRED
    return pct.quantize(_PCT_QUANT, rounding=ROUND_HALF_UP)


# --- Per-position + rollup ---------------------------------------------------


def compute_position_variance(
    *,
    boq_position_id: str,
    design_quantity: Decimal,
    earned_quantity: Decimal,
    percent_complete: Decimal = _ZERO,
    ordinal: str | None = None,
    description: str | None = None,
    unit: str | None = None,
) -> PositionQuantityVariance:
    """Compute the quantity variance for a single position.

    ``variance = earned_quantity - design_quantity``. A position with more
    installed than designed is an over-run, less is an under-run, exactly
    equal is on-target (never flagged as either). ``variance_percent`` is
    ``variance / design_quantity * 100`` and is None when the design quantity
    is zero (guarded division).
    """
    variance = earned_quantity - design_quantity
    is_over_run = earned_quantity > design_quantity
    is_under_run = earned_quantity < design_quantity
    if is_over_run:
        status = STATUS_OVER_RUN
    elif is_under_run:
        status = STATUS_UNDER_RUN
    else:
        status = STATUS_ON_TARGET
    return PositionQuantityVariance(
        boq_position_id=boq_position_id,
        design_quantity=design_quantity,
        earned_quantity=earned_quantity,
        percent_complete=percent_complete,
        variance=variance,
        variance_percent=_variance_percent(variance, design_quantity),
        status=status,
        is_over_run=is_over_run,
        is_under_run=is_under_run,
        ordinal=ordinal,
        description=description,
        unit=unit,
    )


def summarize(rows: Sequence[PositionQuantityVariance]) -> QuantityVarianceRollup:
    """Roll the per-position variances up to project counts and totals.

    Totals are raw Decimal sums of design / earned / variance across the given
    rows; the aggregate ``variance_percent`` is guarded against a zero design
    total. Callers that mix units should read the counts, which are always
    dimensionless, alongside the totals.
    """
    design_total = _ZERO
    earned_total = _ZERO
    variance_total = _ZERO
    over_run = 0
    under_run = 0
    on_target = 0
    for row in rows:
        design_total += row.design_quantity
        earned_total += row.earned_quantity
        variance_total += row.variance
        if row.is_over_run:
            over_run += 1
        elif row.is_under_run:
            under_run += 1
        else:
            on_target += 1
    return QuantityVarianceRollup(
        position_count=len(rows),
        over_run_count=over_run,
        under_run_count=under_run,
        on_target_count=on_target,
        design_quantity_total=design_total,
        earned_quantity_total=earned_total,
        variance_total=variance_total,
        variance_percent=_variance_percent(variance_total, design_total),
    )


def build_report(inputs: Iterable[PositionQuantityInput]) -> QuantityVarianceReport:
    """Compute per-position variances (earned derived from percent) plus rollup.

    Earned quantity is derived from each input's percent-complete via
    :func:`derive_earned_quantity`; because a recorded percent never exceeds
    100, the derived earned quantity never exceeds the design quantity, so
    this path yields under-run / on-target rows only. The over-run branch is
    still computed correctly and is reachable when a caller supplies an earned
    quantity directly through :func:`compute_position_variance`.
    """
    positions = [
        compute_position_variance(
            boq_position_id=item.boq_position_id,
            design_quantity=item.design_quantity,
            earned_quantity=derive_earned_quantity(item.design_quantity, item.percent_complete),
            percent_complete=item.percent_complete,
            ordinal=item.ordinal,
            description=item.description,
            unit=item.unit,
        )
        for item in inputs
    ]
    return QuantityVarianceReport(positions=tuple(positions), rollup=summarize(positions))
