# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure Decimal build-up math for all-in labor and crew rates.

This module is deliberately free of any framework, ORM or I/O dependency so
the rate arithmetic can be unit-tested in isolation and reused identically by
the service layer. Every monetary value is a :class:`decimal.Decimal`; there
is no float anywhere in the pipeline and every rounding step uses
``ROUND_HALF_UP`` at the minor-currency unit (2 decimal places).

All-in rate model (documented order)
------------------------------------
An all-in hourly rate is the productive base wage plus a set of on-cost
components. Two component kinds exist:

* ``percentage`` - a percentage of the **base wage** (statutory charges,
  insurance, leave provision, overtime uplift, supervision expressed as a
  percentage, ...).
* ``fixed`` - a flat amount of currency per hour (small tools and
  consumables allowance, a per-hour levy, ...).

The build-up is evaluated in a fixed, documented order regardless of how the
caller interleaves the components:

1. Start from the base wage.
2. Apply every ``percentage`` component, each computed on the base wage, in
   the order given. Percentages are NOT compounded on one another, so the
   result is independent of their relative order and stays transparent.
3. Add every ``fixed`` component, in the order given. Fixed amounts are added
   last so a flat allowance is never inflated by a percentage on-cost.

``all_in_rate = base_wage + sum(base_wage * pct / 100) + sum(fixed)``

Crew (composite) rate model
---------------------------
A crew blends several trades. Each member carries a headcount ``count`` and an
``all_in_rate``. The total crew cost per hour is the sum of ``count *
all_in_rate`` over the members; the blended hourly rate is that total divided
by the total headcount (the average cost of one person-hour). A crew with no
members has a total and a blended rate of zero.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PERCENTAGE = "percentage"
FIXED = "fixed"

_CENTS = Decimal("0.01")
_HUNDRED = Decimal("100")
_ZERO = Decimal("0.00")


def _to_decimal(value: Decimal | int | str | None) -> Decimal:
    """Coerce an input to a finite ``Decimal``, defaulting to zero.

    Accepts the ``Decimal`` the money contract carries as well as plain
    ``int`` / ``str`` for ergonomic call sites and tests. ``None``, an empty
    string, an unparseable value, or a non-finite ``Decimal`` (``NaN`` /
    ``Infinity``) all collapse to ``Decimal("0")`` so the arithmetic can never
    raise or propagate a poisoned value.

    Args:
        value: The raw input value.

    Returns:
        A finite ``Decimal``.
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal("0")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _q(value: Decimal) -> Decimal:
    """Quantize a ``Decimal`` to the minor currency unit with ROUND_HALF_UP."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _normalize_kind(kind: str) -> str:
    """Return the canonical component kind.

    Any value that is not exactly ``percentage`` (case-insensitive) is treated
    as ``fixed`` so an unknown or blank kind degrades to a flat amount rather
    than raising.
    """
    return PERCENTAGE if str(kind).strip().lower() == PERCENTAGE else FIXED


@dataclass(frozen=True)
class OnCost:
    """One on-cost component fed into the build-up.

    Attributes:
        label: Human-readable name (e.g. "Statutory charges").
        kind: ``percentage`` or ``fixed``.
        value: The percentage (when ``percentage``) or the currency amount per
            hour (when ``fixed``).
    """

    label: str
    kind: str
    value: Decimal


@dataclass(frozen=True)
class OnCostLine:
    """One evaluated on-cost row in the build-up breakdown.

    Attributes:
        label: The component label.
        kind: The canonical component kind (``percentage`` / ``fixed``).
        value: The input percentage or fixed amount, echoed back.
        amount: The currency-per-hour contribution of this component.
        subtotal: The running all-in rate after this component is applied.
    """

    label: str
    kind: str
    value: Decimal
    amount: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class RateBuildUp:
    """The full all-in rate build-up result.

    Attributes:
        base_wage: The productive base wage (quantized).
        lines: The ordered on-cost contributions.
        percentage_total: Sum of the percentage contributions (currency/hour).
        fixed_total: Sum of the fixed contributions (currency/hour).
        all_in_rate: The fully loaded hourly rate.
    """

    base_wage: Decimal
    lines: list[OnCostLine] = field(default_factory=list)
    percentage_total: Decimal = _ZERO
    fixed_total: Decimal = _ZERO
    all_in_rate: Decimal = _ZERO


@dataclass(frozen=True)
class CrewMemberInput:
    """One trade line fed into a crew blend.

    Attributes:
        trade: The trade name (e.g. "Bricklayer").
        count: How many people of this trade are in the crew.
        all_in_rate: The all-in hourly rate for one person of this trade.
    """

    trade: str
    count: int
    all_in_rate: Decimal


@dataclass(frozen=True)
class CrewMemberLine:
    """One evaluated crew member row.

    Attributes:
        trade: The trade name.
        count: The headcount for this trade (clamped to >= 0).
        all_in_rate: The all-in rate for one person (quantized).
        line_cost: ``count * all_in_rate`` - the crew cost per hour of this
            trade.
    """

    trade: str
    count: int
    all_in_rate: Decimal
    line_cost: Decimal


@dataclass(frozen=True)
class CrewBuildUp:
    """The full crew blend result.

    Attributes:
        members: The evaluated member rows.
        headcount: Total number of people across all trades.
        total_cost_per_hour: Sum of the member line costs.
        blended_hourly_rate: ``total_cost_per_hour / headcount`` - the average
            cost of one person-hour, or zero when the crew is empty.
    """

    members: list[CrewMemberLine] = field(default_factory=list)
    headcount: int = 0
    total_cost_per_hour: Decimal = _ZERO
    blended_hourly_rate: Decimal = _ZERO


def build_up(base_wage: Decimal | int | str, components: Sequence[OnCost]) -> RateBuildUp:
    """Build the fully loaded hourly rate from a base wage and on-costs.

    Percentage components are applied first (each on the base wage), then fixed
    per-hour amounts are added, following the documented order in the module
    docstring. Each contribution is rounded to the minor currency unit with
    ``ROUND_HALF_UP`` so the displayed line amounts sum exactly to the total.

    Args:
        base_wage: The productive base hourly wage.
        components: The on-cost components in the caller's order.

    Returns:
        A :class:`RateBuildUp` with the ordered breakdown and the all-in rate.
    """
    base = _q(_to_decimal(base_wage))

    percentage_lines: list[OnCostLine] = []
    fixed_lines: list[OnCostLine] = []
    percentage_total = Decimal("0")
    fixed_total = Decimal("0")

    # Pass 1: percentage components, each computed on the base wage.
    for component in components:
        if _normalize_kind(component.kind) != PERCENTAGE:
            continue
        value = _to_decimal(component.value)
        amount = _q(base * value / _HUNDRED)
        percentage_total += amount
        percentage_lines.append(
            OnCostLine(
                label=component.label,
                kind=PERCENTAGE,
                value=value,
                amount=amount,
                subtotal=_q(base + percentage_total),
            )
        )

    # Pass 2: fixed per-hour amounts, added on top of the burdened wage.
    burdened = base + percentage_total
    for component in components:
        if _normalize_kind(component.kind) != FIXED:
            continue
        value = _to_decimal(component.value)
        amount = _q(value)
        fixed_total += amount
        fixed_lines.append(
            OnCostLine(
                label=component.label,
                kind=FIXED,
                value=value,
                amount=amount,
                subtotal=_q(burdened + fixed_total),
            )
        )

    all_in = _q(base + percentage_total + fixed_total)
    return RateBuildUp(
        base_wage=base,
        lines=[*percentage_lines, *fixed_lines],
        percentage_total=_q(percentage_total),
        fixed_total=_q(fixed_total),
        all_in_rate=all_in,
    )


def all_in_rate(base_wage: Decimal | int | str, components: Sequence[OnCost]) -> Decimal:
    """Return only the fully loaded hourly rate for a base wage and on-costs.

    Thin wrapper over :func:`build_up` for callers that need the headline
    number without the breakdown.

    Args:
        base_wage: The productive base hourly wage.
        components: The on-cost components.

    Returns:
        The all-in hourly rate as a ``Decimal`` quantized to 2 places.
    """
    return build_up(base_wage, components).all_in_rate


def crew_rate(members: Sequence[CrewMemberInput]) -> CrewBuildUp:
    """Blend several trades into one composite crew rate.

    Computes the total crew cost per hour (sum of ``count * all_in_rate``) and
    the blended hourly rate (that total divided by the total headcount). All
    arithmetic is Decimal with ``ROUND_HALF_UP``; an empty crew, or one whose
    headcount is zero, yields a total and a blended rate of zero rather than
    dividing by zero.

    Args:
        members: The crew members, one per trade line.

    Returns:
        A :class:`CrewBuildUp` with per-member costs and the blended rate.
    """
    lines: list[CrewMemberLine] = []
    headcount = 0
    total = Decimal("0")

    for member in members:
        count = max(0, int(member.count))
        rate = _q(_to_decimal(member.all_in_rate))
        line_cost = _q(rate * Decimal(count))
        total += line_cost
        headcount += count
        lines.append(
            CrewMemberLine(
                trade=member.trade,
                count=count,
                all_in_rate=rate,
                line_cost=line_cost,
            )
        )

    total = _q(total)
    blended = _q(total / Decimal(headcount)) if headcount > 0 else _ZERO
    return CrewBuildUp(
        members=lines,
        headcount=headcount,
        total_cost_per_hour=total,
        blended_hourly_rate=blended,
    )
