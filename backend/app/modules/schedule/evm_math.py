# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure earned-value (EVM) math for the 4D schedule slice.

This module is deliberately dependency-free: it imports nothing from the ORM,
the DB engine, FastAPI or the rest of the app. That keeps the earned-value
rollup a *pure* function that can be unit-tested in isolation (and on Python
3.11 locally, where importing ``service_4d`` would otherwise pull in
``app.database`` and require a live PostgreSQL cluster).

``service_4d`` re-exports :class:`EvmCostRow`, :class:`EvmSummary` and
:func:`compute_evm_summary` so existing call sites keep working unchanged.

EVM identities used here (PMBOK):

* PV  (BCWS): budgeted cost of work *scheduled* by the data date.
* EV  (BCWP): budgeted cost of work *performed* = BAC * progress%.
* AC  (ACWP): actual cost incurred to date.
* BAC: Budget At Completion = Σ planned cost.
* SV  = EV - PV ; CV = EV - AC.
* SPI = EV / PV ; CPI = EV / AC.
* EAC = BAC / CPI (CPI method) ; ETC = EAC - AC ; VAC = BAC - EAC.

Ratio / forecast fields are ``None`` rather than ``0`` when a denominator is
zero (division by zero is undefined), so the UI can render "not available"
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

# Money is quantized to 4 decimal places (the platform Decimal-as-string wire
# contract preserves full precision on the way out; rounding here only trims
# the long tails a Decimal division can produce).
_MONEY_Q = Decimal("0.0001")
_HUNDRED = Decimal("100")


def _q(value: Decimal) -> Decimal:
    """Quantize a money Decimal to 4 decimal places (banker's default)."""
    return value.quantize(_MONEY_Q)


@dataclass(frozen=True)
class EvmCostRow:
    """Minimal cost-loaded view of one activity for the EVM rollup.

    Decoupled from the ORM ``Activity`` so the rollup stays a pure function.
    ``cost_planned`` / ``cost_actual`` are the raw Decimal-or-None columns;
    ``progress_pct`` is the activity's stored progress string ("0".."100").
    """

    start_date: str | None
    end_date: str | None
    cost_planned: Decimal | None
    cost_actual: Decimal | None
    progress_pct: str | None


@dataclass
class EvmSummary:
    """Scalar earned-value metrics for a schedule at a data date.

    All nine money fields are :class:`~decimal.Decimal` (computed and
    accumulated in Decimal, never float) to honour the house "money is
    Decimal" rule; :meth:`to_json` serialises them as strings for the
    Decimal-as-string wire contract. Ratio fields (``spi`` / ``cpi``) stay
    plain ``float | None`` because they are dimensionless ratios, not money.
    The forecast block (``eac`` / ``etc`` / ``vac``) is ``None`` when the
    schedule carries no cost data or a denominator is zero.
    """

    planned_value: Decimal  # PV / BCWS, time-phased to the data date
    earned_value: Decimal  # EV / BCWP
    actual_cost: Decimal  # AC / ACWP
    budget_at_completion: Decimal  # BAC = Σ cost_planned
    schedule_variance: Decimal  # SV = EV - PV
    cost_variance: Decimal  # CV = EV - AC
    spi: float | None  # SPI = EV / PV (dimensionless ratio)
    cpi: float | None  # CPI = EV / AC (dimensionless ratio)
    estimate_at_completion: Decimal | None  # EAC = BAC / CPI
    estimate_to_complete: Decimal | None  # ETC = EAC - AC
    variance_at_completion: Decimal | None  # VAC = BAC - EAC
    has_cost_data: bool

    def to_json(self) -> dict[str, Any]:
        """Serialise to the wire contract.

        Money fields become strings (``str(Decimal)``) or JSON ``null``; the
        ``spi`` / ``cpi`` ratios stay numbers (float) or null; ``has_cost_data``
        stays a bool.
        """
        return {
            "planned_value": str(self.planned_value),
            "earned_value": str(self.earned_value),
            "actual_cost": str(self.actual_cost),
            "budget_at_completion": str(self.budget_at_completion),
            "schedule_variance": str(self.schedule_variance),
            "cost_variance": str(self.cost_variance),
            "spi": self.spi,
            "cpi": self.cpi,
            "estimate_at_completion": (
                str(self.estimate_at_completion) if self.estimate_at_completion is not None else None
            ),
            "estimate_to_complete": (str(self.estimate_to_complete) if self.estimate_to_complete is not None else None),
            "variance_at_completion": (
                str(self.variance_at_completion) if self.variance_at_completion is not None else None
            ),
            "has_cost_data": self.has_cost_data,
        }


def _parse_iso(value: str | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` (or full ISO datetime) prefix into a date."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def coerce_progress_value(raw: str | None) -> float:
    """Coerce a stored ``progress_pct`` string to a 0..100 float (clamped)."""
    try:
        value = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 100.0:
        return 100.0
    return value


def coerce_progress_decimal(raw: str | None) -> Decimal:
    """Coerce a stored ``progress_pct`` string to a 0..100 ``Decimal`` (clamped).

    Decimal sibling of :func:`coerce_progress_value` so progress never has to be
    routed through ``float`` before it multiplies a money amount.
    """
    if raw is None:
        return Decimal("0")
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0")
    if not value.is_finite():
        return Decimal("0")
    if value < Decimal("0"):
        return Decimal("0")
    if value > _HUNDRED:
        return _HUNDRED
    return value


def planned_value_for_dates(
    start_date: str | None,
    end_date: str | None,
    bac: float,
    as_of_date: date,
) -> float:
    """Time-phased planned value for one activity given its raw date strings.

    An activity whose planned end is on or before the data date contributes its
    full budget; one in progress contributes a linear proration over its
    planned ``[start, end]`` span; one not yet started (or with unparseable
    dates) contributes nothing. This mirrors the S-curve PV proration so the
    scalar PV and the final S-curve point agree.

    Kept as a ``float`` helper for the public unit surface; the scalar EVM
    rollup uses :func:`planned_value_decimal` so money stays Decimal.
    """
    if not bac:
        return 0.0
    start = _parse_iso(start_date)
    end = _parse_iso(end_date)
    if start is None or end is None:
        return 0.0
    if as_of_date >= end:
        return bac
    if as_of_date < start:
        return 0.0
    duration = max((end - start).days, 1)
    elapsed = (as_of_date - start).days
    return bac * (elapsed / duration)


def planned_value_decimal(
    start_date: str | None,
    end_date: str | None,
    bac: Decimal,
    as_of_date: date,
) -> Decimal:
    """Decimal time-phased planned value for one activity (no float math).

    Same proration rule as :func:`planned_value_for_dates` but the elapsed /
    duration ratio is computed in Decimal so the money amount is never tainted
    by a binary float.
    """
    if not bac:
        return Decimal("0")
    start = _parse_iso(start_date)
    end = _parse_iso(end_date)
    if start is None or end is None:
        return Decimal("0")
    if as_of_date >= end:
        return bac
    if as_of_date < start:
        return Decimal("0")
    duration = max((end - start).days, 1)
    elapsed = (as_of_date - start).days
    return bac * (Decimal(elapsed) / Decimal(duration))


def compute_evm_summary(rows: list[EvmCostRow], as_of_date: date) -> EvmSummary:
    """Roll a schedule's cost-loaded activities up to scalar EVM metrics.

    Pure function (no DB / no I/O). Money is accumulated and computed entirely
    in :class:`~decimal.Decimal` (progress and the PV proration are coerced to
    Decimal too) so no binary float ever touches a money amount. PV is
    time-phased to ``as_of_date`` exactly as the 4D dashboard's S-curve does.
    EV is BAC * progress%. AC is the captured ``cost_actual``. The forecast
    block uses the CPI-based identities (EAC = BAC / CPI). The ``spi`` / ``cpi``
    ratios are plain floats (EV/PV, EV/AC); all ratio / forecast fields are
    ``None`` when their denominator is zero so a caller never has to
    special-case divide-by-zero.
    """
    total_pv = Decimal("0")
    total_ev = Decimal("0")
    total_ac = Decimal("0")
    total_bac = Decimal("0")
    any_cost = False

    for row in rows:
        bac = row.cost_planned if row.cost_planned is not None else Decimal("0")
        ac = row.cost_actual if row.cost_actual is not None else Decimal("0")
        if row.cost_planned is not None or row.cost_actual is not None:
            any_cost = True
        progress = coerce_progress_decimal(row.progress_pct)
        pv = planned_value_decimal(row.start_date, row.end_date, bac, as_of_date)
        ev = bac * (progress / _HUNDRED) if bac else Decimal("0")
        total_pv += pv
        total_ev += ev
        total_ac += ac
        total_bac += bac

    # SPI / CPI are dimensionless ratios -> plain float. Undefined (None) when
    # their denominator is zero. Float division of two Decimals is the standard
    # EV/PV, EV/AC; we convert to float explicitly to keep the wire type stable.
    spi: float | None = float(total_ev / total_pv) if (any_cost and total_pv > 0) else None
    cpi: float | None = float(total_ev / total_ac) if (any_cost and total_ac > 0) else None

    # EAC via the CPI method: BAC / CPI. Undefined when CPI is unknown / zero.
    # Money stays Decimal; CPI is a float so we lift it back to Decimal first.
    eac: Decimal | None = (total_bac / Decimal(str(cpi))) if (cpi is not None and cpi > 0) else None
    etc: Decimal | None = (eac - total_ac) if eac is not None else None
    vac: Decimal | None = (total_bac - eac) if eac is not None else None

    return EvmSummary(
        planned_value=_q(total_pv),
        earned_value=_q(total_ev),
        actual_cost=_q(total_ac),
        budget_at_completion=_q(total_bac),
        schedule_variance=_q(total_ev - total_pv),
        cost_variance=_q(total_ev - total_ac),
        spi=round(spi, 4) if spi is not None else None,
        cpi=round(cpi, 4) if cpi is not None else None,
        estimate_at_completion=_q(eac) if eac is not None else None,
        estimate_to_complete=_q(etc) if etc is not None else None,
        variance_at_completion=_q(vac) if vac is not None else None,
        has_cost_data=any_cost,
    )


__all__ = [
    "EvmCostRow",
    "EvmSummary",
    "coerce_progress_decimal",
    "coerce_progress_value",
    "compute_evm_summary",
    "planned_value_decimal",
    "planned_value_for_dates",
]
