# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure change cost- and schedule-impact projection.

Rolls the set of APPROVED changes on a project (change orders, variation
orders, and the like) into a single earned-value-style view and into the
event payloads that announce each change on the project timeline.

Given every :class:`ApprovedChange`, :func:`project_impacts` produces an
:class:`ImpactProjection`: the total schedule slip in days, a per-kind
breakdown (how much cost and how many days each category of change carries),
and a per-currency breakdown. Money cannot be added across currencies, so the
projection never reports a single blended cost total; instead it keeps one
:class:`CurrencyImpact` bucket per currency and names a primary currency (the
one carrying the largest absolute cost) for headline display. Credits are
negative cost impacts and are summed with their sign; only the choice of
primary currency looks at the absolute value, while every reported total stays
signed.

:func:`to_timeline_events` turns the same changes into one
:class:`TimelineImpactEvent` per change, with the cost delta rendered as the
string form of its :class:`~decimal.Decimal` so it serializes losslessly under
the platform's money-as-string convention.

No database, no ORM, no ``app.*`` imports - stdlib only, money is always
:class:`~decimal.Decimal` and never float - so it unit-tests on the local
Python 3.11 runner exactly like the cycle-time and SLA engines. A thin service
layer gathers the approved change rows and feeds them in, and publishes the
returned events onto the timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Stable kind tokens for the approved-change record types this projection
# spans. Callers may pass other kind strings; they are grouped as-is.
KIND_CHANGE_ORDER = "change_order"
KIND_VARIATION_ORDER = "variation_order"


@dataclass(frozen=True)
class ApprovedChange:
    """One approved change feeding the projection.

    ``cost_impact`` is a signed :class:`~decimal.Decimal`: positive when the
    change adds cost, negative for a credit. ``schedule_impact_days`` is a
    signed whole-day count (acceleration may be negative). ``currency`` is the
    ISO code the cost is expressed in; an empty string is its own bucket rather
    than an error, so an unpriced change is still surfaced.
    """

    ref_id: str
    kind: str
    cost_impact: Decimal
    schedule_impact_days: int
    currency: str
    status: str
    approved_at: str | None = None


@dataclass(frozen=True)
class KindImpact:
    """Cost and schedule carried by all changes of one kind."""

    kind: str
    count: int
    total_cost: Decimal
    total_days: int


@dataclass(frozen=True)
class CurrencyImpact:
    """Signed cost total carried by all changes in one currency.

    Money is never summed across currencies, so the projection reports one of
    these per distinct currency rather than a single blended total.
    """

    currency: str
    total_cost: Decimal
    count: int


@dataclass(frozen=True)
class ImpactProjection:
    """Earned-value-style roll-up of every approved change on a project.

    ``total_schedule_delta_days`` is the signed sum of day impacts.
    ``by_kind`` and ``by_currency`` are sorted by kind and currency string
    respectively. ``primary_currency`` is the currency carrying the largest
    absolute cost (ties broken by currency string order); its signed bucket
    total is ``primary_currency_cost``. With no changes the primary currency is
    the empty string and its cost is ``Decimal("0")``.
    """

    approved_count: int
    total_schedule_delta_days: int
    by_kind: list[KindImpact]
    by_currency: list[CurrencyImpact]
    primary_currency: str
    primary_currency_cost: Decimal


@dataclass(frozen=True)
class TimelineImpactEvent:
    """Payload announcing one approved change on the project timeline.

    ``cost_delta`` is ``str(Decimal)`` so the signed money value round-trips
    losslessly as a JSON string, matching the platform money-as-string
    convention; credits keep their leading minus sign.
    """

    project_id: str
    ref_id: str
    kind: str
    cost_delta: str
    schedule_delta_days: int
    currency: str


def project_impacts(changes: list[ApprovedChange]) -> ImpactProjection:
    """Roll *changes* into an :class:`ImpactProjection`.

    Every cost total is an exact :class:`~decimal.Decimal` sum kept at full
    precision (no quantizing or rounding); day totals are plain ``int`` sums.
    Both per-kind and per-currency buckets carry their member count. The
    primary currency is chosen by largest absolute cost, with the currency
    string sort order breaking ties, but its reported total stays signed.
    """
    approved_count = len(changes)
    total_schedule_delta_days = sum((c.schedule_impact_days for c in changes), 0)

    kind_cost: dict[str, Decimal] = {}
    kind_days: dict[str, int] = {}
    kind_count: dict[str, int] = {}
    currency_cost: dict[str, Decimal] = {}
    currency_count: dict[str, int] = {}

    for change in changes:
        kind_cost[change.kind] = kind_cost.get(change.kind, Decimal("0")) + change.cost_impact
        kind_days[change.kind] = kind_days.get(change.kind, 0) + change.schedule_impact_days
        kind_count[change.kind] = kind_count.get(change.kind, 0) + 1
        currency_cost[change.currency] = currency_cost.get(change.currency, Decimal("0")) + change.cost_impact
        currency_count[change.currency] = currency_count.get(change.currency, 0) + 1

    by_kind = [
        KindImpact(
            kind=kind,
            count=kind_count[kind],
            total_cost=kind_cost[kind],
            total_days=kind_days[kind],
        )
        for kind in sorted(kind_cost)
    ]
    by_currency = [
        CurrencyImpact(
            currency=currency,
            total_cost=currency_cost[currency],
            count=currency_count[currency],
        )
        for currency in sorted(currency_cost)
    ]

    if by_currency:
        # Largest absolute cost wins; currency string order breaks ties.
        primary = min(by_currency, key=lambda b: (-abs(b.total_cost), b.currency))
        primary_currency = primary.currency
        primary_currency_cost = primary.total_cost
    else:
        primary_currency = ""
        primary_currency_cost = Decimal("0")

    return ImpactProjection(
        approved_count=approved_count,
        total_schedule_delta_days=total_schedule_delta_days,
        by_kind=by_kind,
        by_currency=by_currency,
        primary_currency=primary_currency,
        primary_currency_cost=primary_currency_cost,
    )


def to_timeline_events(project_id: str, changes: list[ApprovedChange]) -> list[TimelineImpactEvent]:
    """Render *changes* into one timeline event each, order preserved.

    ``cost_delta`` is the lossless string form of each change's signed
    :class:`~decimal.Decimal` cost, so credits keep their minus sign.
    """
    return [
        TimelineImpactEvent(
            project_id=project_id,
            ref_id=change.ref_id,
            kind=change.kind,
            cost_delta=str(change.cost_impact),
            schedule_delta_days=change.schedule_impact_days,
            currency=change.currency,
        )
        for change in changes
    ]


__all__ = [
    "KIND_CHANGE_ORDER",
    "KIND_VARIATION_ORDER",
    "ApprovedChange",
    "CurrencyImpact",
    "ImpactProjection",
    "KindImpact",
    "TimelineImpactEvent",
    "project_impacts",
    "to_timeline_events",
]
