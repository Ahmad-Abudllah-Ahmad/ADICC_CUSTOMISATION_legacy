# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure change run-rate and cumulative change curve.

Where the earned-value impact projection answers "how much approved change do we
carry right now", this engine answers the trajectory question: how fast is change
arriving, how big has it grown against the original contract, and where is it
heading by completion. It isolates change-attributable growth and its slope,
which is distinct from a full estimate-at-completion.

Given every change order and variation projected to a :class:`ChangeEvent`
(placed on the timeline at its effective date and bucketed approved or pending),
:func:`build_run_rate` produces a :class:`RunRate`: the month-by-month cumulative
approved-plus-pending change value, the current change value as a percentage of
the original contract value, the intake rate (changes per month), and a simple
linear burn-rate forecast of the final change percentage at completion.

Whether a raw record contributes and in which bucket is decided here, per kind,
via :func:`classify_change_bucket`, and the effective date is resolved via
:func:`resolve_effective_date`, so both the status logic and the date choice stay
unit-testable. Money is a signed :class:`~decimal.Decimal` throughout (never a
float); exact sums are kept at full precision while the derived ratios and the
forecast are quantized for display.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on the
local Python 3.11 runner exactly like the impact and cycle-time engines. The
engine never reads the wall clock itself; the caller passes ``now`` in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# Stable kind tokens for the change-bearing record families this curve spans.
KIND_CHANGE_ORDER = "change_order"
KIND_VARIATION_REQUEST = "variation_request"
KIND_VARIATION_ORDER = "variation_order"

# Value buckets.
BUCKET_APPROVED = "approved"
BUCKET_PENDING = "pending"

_MONEY_Q = Decimal("0.01")
_RATE_Q = Decimal("0.0001")
_PCT_Q = Decimal("0.01")

# Change-order statuses whose value is committed vs. dead (adds no value).
_CO_APPROVED = frozenset({"approved", "executed", "closed"})
_CO_DEAD = frozenset({"rejected", "cancelled", "canceled", "withdrawn", "voided", "void"})
# Variation-order statuses that are dead; anything else on a VO is an in-force
# (issued and beyond) order carrying committed value.
_VO_DEAD = frozenset({"voided", "cancelled", "canceled", "void", "withdrawn"})
# Variation-request statuses that are dead, or that have moved on to a variation
# order which then carries the value (so counting the request too would double
# count). Anything else on a request is still pending pipeline value.
_VR_CLOSED = frozenset(
    {"rejected", "cancelled", "canceled", "withdrawn", "approved", "converted_to_vo", "closed", "issued"}
)


def classify_change_bucket(kind: str, status: str | None) -> str | None:
    """Bucket a change record by kind + status, or ``None`` to exclude it.

    A change order is approved once approved / executed / closed and pending
    while still in flight; a variation order is approved unless it is dead; a
    variation request only ever contributes pending pipeline value while it is
    undecided (once decided its downstream variation order carries the value).
    A dead record (rejected / cancelled / withdrawn / voided) contributes no
    value and returns ``None``.
    """
    s = (status or "").strip().lower()
    if kind == KIND_CHANGE_ORDER:
        if s in _CO_DEAD:
            return None
        if s in _CO_APPROVED:
            return BUCKET_APPROVED
        return BUCKET_PENDING
    if kind == KIND_VARIATION_ORDER:
        if s in _VO_DEAD:
            return None
        return BUCKET_APPROVED
    if kind == KIND_VARIATION_REQUEST:
        if s in _VR_CLOSED:
            return None
        return BUCKET_PENDING
    return None


def resolve_effective_date(
    bucket: str,
    created_at: date,
    submitted_at: date | None = None,
    approved_at: date | None = None,
) -> date:
    """Choose the date a change lands on the timeline.

    An approved change prefers its approval / agreement date, then its
    submission date, then its creation date; a pending change prefers its
    submission date, then its creation date. ``created_at`` is always present
    (every record carries a creation timestamp) so a date is always returned.
    """
    if bucket == BUCKET_APPROVED:
        return approved_at or submitted_at or created_at
    return submitted_at or created_at


@dataclass(frozen=True)
class ChangeEvent:
    """One change order or variation placed on the change-value timeline."""

    ref_id: str
    kind: str
    bucket: str
    cost: Decimal
    currency: str
    at: date


@dataclass(frozen=True)
class MonthlyPoint:
    """Cumulative change value through one ``YYYY-MM`` month.

    ``approved_value`` / ``pending_value`` are that month's deltas;
    ``cumulative_value`` is the running approved-plus-pending total through the
    month. ``change_pct`` is the cumulative value as a percentage of the
    contract value, or ``None`` when there is no usable contract value.
    """

    month: str
    approved_value: Decimal
    pending_value: Decimal
    cumulative_value: Decimal
    change_pct: Decimal | None


@dataclass(frozen=True)
class Forecast:
    """Simple linear burn-rate forecast of change at completion."""

    method: str
    elapsed_days: int
    total_days: int
    rate_per_day: Decimal
    final_change_value: Decimal
    final_change_pct: Decimal | None
    at_date: str


@dataclass(frozen=True)
class RunRate:
    """Change run-rate and cumulative curve for a project."""

    original_contract_value: Decimal | None
    currency: str
    change_count: int
    approved_value: Decimal
    pending_value: Decimal
    total_change_value: Decimal
    current_change_pct: Decimal | None
    intake_rate_per_month: float
    points: list[MonthlyPoint]
    forecast: Forecast | None


def _month_key(value: date) -> str:
    """The ``YYYY-MM`` bucket a date falls in."""
    return f"{value.year:04d}-{value.month:02d}"


def _month_index(value: date) -> int:
    """Absolute month ordinal, so month spans can be differenced arithmetically."""
    return value.year * 12 + (value.month - 1)


def _pct(value: Decimal, contract_value: Decimal | None) -> Decimal | None:
    """``value`` as a percentage of *contract_value*, quantized, or ``None``."""
    if contract_value is None or contract_value <= 0:
        return None
    return (value / contract_value * 100).quantize(_PCT_Q, rounding=ROUND_HALF_UP)


def _linear_forecast(
    cumulative_now: Decimal,
    contract_value: Decimal | None,
    project_start: date | None,
    project_end: date | None,
    now: date,
) -> Forecast | None:
    """Extrapolate the current change burn-rate to the project completion date.

    Fits the simplest line: the change value has grown from zero at the project
    start to ``cumulative_now`` today, so the per-day rate is
    ``cumulative_now / elapsed_days`` and the projected value at completion is
    that rate across the full duration. Once the project is at or past its end
    date the projection is just the current value. Returns ``None`` when the
    contract value or the project dates are missing or non-positive, so a
    forecast is only offered when it can be grounded.
    """
    if contract_value is None or contract_value <= 0:
        return None
    if project_start is None or project_end is None:
        return None
    elapsed_days = (now - project_start).days
    total_days = (project_end - project_start).days
    if elapsed_days <= 0 or total_days <= 0:
        return None

    rate_per_day = cumulative_now / Decimal(elapsed_days)
    if now >= project_end:
        final_value = cumulative_now
    else:
        final_value = rate_per_day * Decimal(total_days)

    return Forecast(
        method="linear_burn_rate",
        elapsed_days=elapsed_days,
        total_days=total_days,
        rate_per_day=rate_per_day.quantize(_RATE_Q, rounding=ROUND_HALF_UP),
        final_change_value=final_value.quantize(_MONEY_Q, rounding=ROUND_HALF_UP),
        final_change_pct=_pct(final_value, contract_value),
        at_date=project_end.isoformat(),
    )


def _primary_currency(events: list[ChangeEvent]) -> str:
    """The currency carrying the largest absolute change cost (ties by string)."""
    totals: dict[str, Decimal] = {}
    for ev in events:
        totals[ev.currency] = totals.get(ev.currency, Decimal("0")) + ev.cost
    if not totals:
        return ""
    return min(totals.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[0]


def build_run_rate(
    events: list[ChangeEvent],
    *,
    contract_value: Decimal | None,
    project_start: date | None,
    project_end: date | None,
    now: date,
) -> RunRate:
    """Roll *events* into a :class:`RunRate` curve, rate and forecast.

    The cumulative curve sums every event's cost naively (exact for a
    single-currency project, matching the impact projection's roll-up); the
    ``currency`` names the primary currency for display. The intake rate is the
    change count over the number of months from the first change to *now*
    (at least one). The forecast is grounded only when the contract value and
    project dates allow it.
    """
    if not events:
        return RunRate(
            original_contract_value=contract_value,
            currency="",
            change_count=0,
            approved_value=Decimal("0"),
            pending_value=Decimal("0"),
            total_change_value=Decimal("0"),
            current_change_pct=_pct(Decimal("0"), contract_value),
            intake_rate_per_month=0.0,
            points=[],
            forecast=_linear_forecast(Decimal("0"), contract_value, project_start, project_end, now),
        )

    ordered = sorted(events, key=lambda ev: (ev.at, ev.ref_id))
    currency = _primary_currency(ordered)

    # Per-month approved / pending deltas.
    month_approved: dict[str, Decimal] = {}
    month_pending: dict[str, Decimal] = {}
    for ev in ordered:
        key = _month_key(ev.at)
        if ev.bucket == BUCKET_APPROVED:
            month_approved[key] = month_approved.get(key, Decimal("0")) + ev.cost
        else:
            month_pending[key] = month_pending.get(key, Decimal("0")) + ev.cost

    approved_total = sum(month_approved.values(), Decimal("0"))
    pending_total = sum(month_pending.values(), Decimal("0"))
    total_change = approved_total + pending_total

    points: list[MonthlyPoint] = []
    cumulative = Decimal("0")
    for month in sorted(set(month_approved) | set(month_pending)):
        approved = month_approved.get(month, Decimal("0"))
        pending = month_pending.get(month, Decimal("0"))
        cumulative += approved + pending
        points.append(
            MonthlyPoint(
                month=month,
                approved_value=approved,
                pending_value=pending,
                cumulative_value=cumulative,
                change_pct=_pct(cumulative, contract_value),
            )
        )

    # Intake rate: changes per month across the active span (first change to now,
    # at least one month so a burst inside a single month is not divided away).
    first_month = _month_index(ordered[0].at)
    span_months = max(1, _month_index(now) - first_month + 1)
    intake_rate = round(len(ordered) / span_months, 2)

    return RunRate(
        original_contract_value=contract_value,
        currency=currency,
        change_count=len(ordered),
        approved_value=approved_total,
        pending_value=pending_total,
        total_change_value=total_change,
        current_change_pct=_pct(total_change, contract_value),
        intake_rate_per_month=intake_rate,
        points=points,
        forecast=_linear_forecast(total_change, contract_value, project_start, project_end, now),
    )


__all__ = [
    "BUCKET_APPROVED",
    "BUCKET_PENDING",
    "KIND_CHANGE_ORDER",
    "KIND_VARIATION_ORDER",
    "KIND_VARIATION_REQUEST",
    "ChangeEvent",
    "Forecast",
    "MonthlyPoint",
    "RunRate",
    "build_run_rate",
    "classify_change_bucket",
    "resolve_effective_date",
]
