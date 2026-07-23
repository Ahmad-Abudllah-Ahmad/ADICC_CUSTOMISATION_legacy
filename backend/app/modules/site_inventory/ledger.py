# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure computation core for on-site material metering and stock.

Materials arrive on site (a goods receipt), get installed against a BoQ position
(consumption), are lost to breakage or theft (waste / shrinkage), or move between
storage locations (transfer). This module turns a flat list of such movements
into the numbers a site engineer and a cost controller need: stock on hand,
inventory turnover and days-on-hand, the waste ratio, and the material-cost
variance of what was actually consumed against what the estimate budgeted per
position.

Everything here is a plain value object plus a set of functions. It is
``Decimal``-exact and carries no ORM, database or FastAPI dependency, exactly
like :mod:`app.modules.postcalc.model`, so the whole core is trivially
constructed and asserted from plain values. The DB loaders that build
:class:`Movement` lists and the per-position budgets live in
:mod:`app.modules.site_inventory.service`.

Sign convention for stock on hand (the signed sum of movements):

* ``INBOUND``      adds to stock (+quantity)
* ``CONSUMPTION``  removes from stock (-quantity)
* ``WASTE``        removes from stock (-quantity)
* ``TRANSFER``     nets to zero for the whole project (material only relocates);
                   for a single location it is -quantity at the source and
                   +quantity at the destination.

Money is never a float: quantities and unit costs are :class:`decimal.Decimal`
throughout and every division is guarded, returning ``None`` rather than raising
when the denominator is zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

# Quantisation quanta - quantities to 4 dp, money to 2 dp, ratios to 6 dp,
# percentages and day counts to 2 dp. Matches the platform-wide convention used
# by ``postcalc`` and ``price_breakdown``.
_QTY_Q = Decimal("0.0001")
_MONEY_Q = Decimal("0.01")
_RATIO_Q = Decimal("0.000001")
_PCT_Q = Decimal("0.01")
_DAYS_Q = Decimal("0.01")

_ZERO = Decimal("0")


class MovementType(StrEnum):
    """The four kinds of stock movement recorded on site."""

    INBOUND = "INBOUND"  # material received into a storage location
    CONSUMPTION = "CONSUMPTION"  # material installed / used against a BoQ position
    WASTE = "WASTE"  # breakage, shrinkage, off-cut, theft
    TRANSFER = "TRANSFER"  # relocation between two storage locations


# Signed multiplier applied to a movement's (positive) quantity when rolling up
# the whole-project stock on hand. TRANSFER nets to zero because the material
# never leaves the project - it only changes location.
_ONHAND_SIGN: dict[str, Decimal] = {
    MovementType.INBOUND.value: Decimal("1"),
    MovementType.CONSUMPTION.value: Decimal("-1"),
    MovementType.WASTE.value: Decimal("-1"),
    MovementType.TRANSFER.value: _ZERO,
}


def _as_decimal(value: Decimal | str | int | None) -> Decimal:
    """Coerce a value to :class:`Decimal`, treating ``None`` as zero.

    Accepts a ``Decimal`` (returned unchanged), or a ``str`` / ``int`` that
    ``Decimal`` can parse. A ``float`` is deliberately routed through ``str`` so
    a caller that ignores the type hint still cannot inject binary-float noise
    into a money figure.
    """
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _movement_type_value(movement_type: str | MovementType) -> str:
    """Return the canonical string value of a movement type."""
    return movement_type.value if isinstance(movement_type, MovementType) else str(movement_type)


@dataclass(frozen=True)
class Movement:
    """One stock movement, as consumed by the pure functions here.

    A DB-free projection of a persisted ``StockMovement`` row. ``quantity`` and
    ``unit_cost`` are always non-negative magnitudes; the direction of a
    movement comes from its ``movement_type`` via the sign convention above, not
    from a negative quantity.
    """

    movement_type: str
    quantity: Decimal
    unit_cost: Decimal = _ZERO
    item_id: str | None = None
    location_id: str | None = None
    to_location_id: str | None = None
    boq_position_id: str | None = None
    occurred_at: datetime | None = None

    @property
    def line_cost(self) -> Decimal:
        """Extended cost of this movement = ``quantity * unit_cost``."""
        return _as_decimal(self.quantity) * _as_decimal(self.unit_cost)


@dataclass(frozen=True)
class PositionVariance:
    """Material-cost variance of one BoQ position: actual consumed vs budget."""

    position_id: str
    budgeted_cost: Decimal
    actual_cost: Decimal
    variance: Decimal  # actual - budget; positive means over budget
    variance_pct: Decimal | None  # None when the budget is zero (guarded)
    consumed_quantity: Decimal

    @property
    def is_over_budget(self) -> bool:
        """True when more was spent on the material than the estimate allowed."""
        return self.variance > _ZERO

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view (money 2 dp, quantity 4 dp, percentage 2 dp)."""
        return {
            "position_id": self.position_id,
            "budgeted_cost": _q(self.budgeted_cost, _MONEY_Q),
            "actual_cost": _q(self.actual_cost, _MONEY_Q),
            "variance": _q(self.variance, _MONEY_Q),
            "variance_pct": _q(self.variance_pct, _PCT_Q),
            "consumed_quantity": _q(self.consumed_quantity, _QTY_Q),
            "is_over_budget": self.is_over_budget,
        }


@dataclass(frozen=True)
class MaterialVarianceSummary:
    """Project rollup of the per-position material-cost variance."""

    total_budgeted_cost: Decimal
    total_actual_cost: Decimal
    total_variance: Decimal
    variance_pct: Decimal | None
    position_count: int
    over_budget_count: int
    lines: list[PositionVariance] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of the whole variance report."""
        return {
            "total_budgeted_cost": _q(self.total_budgeted_cost, _MONEY_Q),
            "total_actual_cost": _q(self.total_actual_cost, _MONEY_Q),
            "total_variance": _q(self.total_variance, _MONEY_Q),
            "variance_pct": _q(self.variance_pct, _PCT_Q),
            "position_count": self.position_count,
            "over_budget_count": self.over_budget_count,
            "lines": [line.to_dict() for line in self.lines],
        }


def _q(value: Decimal | None, quant: Decimal) -> str | None:
    """Quantise a ``Decimal`` to a string, passing ``None`` through unchanged."""
    if value is None:
        return None
    return str(value.quantize(quant, rounding=ROUND_HALF_UP))


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Divide two ``Decimal`` values, returning ``None`` when dividing by zero.

    The single guarded-division primitive every ratio in this module is built
    on, so "undefined" is represented uniformly as ``None`` and never as a raised
    ``ZeroDivisionError`` or a silent zero.
    """
    if denominator == _ZERO:
        return None
    return numerator / denominator


def signed_quantity(movement: Movement) -> Decimal:
    """Signed stock-on-hand contribution of a single movement.

    An unknown movement type contributes zero rather than raising, so a stray
    row can never poison a whole-project rollup; write-time validation (the
    schema ``Literal``) is what rejects bad types at the edge.
    """
    sign = _ONHAND_SIGN.get(_movement_type_value(movement.movement_type), _ZERO)
    return sign * _as_decimal(movement.quantity)


def stock_on_hand(movements: Iterable[Movement]) -> Decimal:
    """Whole-project stock on hand as the signed sum of every movement.

    Empty input yields ``Decimal('0')`` (nothing received, nothing on hand).
    """
    total = _ZERO
    for movement in movements:
        total += signed_quantity(movement)
    return total


def stock_on_hand_by_item(movements: Iterable[Movement]) -> dict[str, Decimal]:
    """Stock on hand per ``item_id`` (movements with no item id are ignored)."""
    totals: dict[str, Decimal] = {}
    for movement in movements:
        if movement.item_id is None:
            continue
        totals[movement.item_id] = totals.get(movement.item_id, _ZERO) + signed_quantity(movement)
    return totals


def stock_on_hand_by_location(movements: Iterable[Movement]) -> dict[str | None, Decimal]:
    """Stock on hand per storage location.

    Unlike the whole-project view, a ``TRANSFER`` is not net zero here: it
    subtracts its quantity from the source ``location_id`` and adds it to the
    destination ``to_location_id`` so each location's balance is correct.
    """
    totals: dict[str | None, Decimal] = {}
    for movement in movements:
        mtype = _movement_type_value(movement.movement_type)
        qty = _as_decimal(movement.quantity)
        if mtype == MovementType.TRANSFER.value:
            totals[movement.location_id] = totals.get(movement.location_id, _ZERO) - qty
            totals[movement.to_location_id] = totals.get(movement.to_location_id, _ZERO) + qty
            continue
        delta = _ONHAND_SIGN.get(mtype, _ZERO) * qty
        totals[movement.location_id] = totals.get(movement.location_id, _ZERO) + delta
    return totals


def location_delta(movement: Movement, location_id: str | None) -> Decimal:
    """Signed contribution of one movement to a single location's stock.

    For an ``INBOUND`` / ``CONSUMPTION`` / ``WASTE`` the movement only touches its
    own ``location_id``. A ``TRANSFER`` touches two: it subtracts at the source
    ``location_id`` and adds at the destination ``to_location_id``.
    """
    mtype = _movement_type_value(movement.movement_type)
    qty = _as_decimal(movement.quantity)
    if mtype == MovementType.TRANSFER.value:
        delta = _ZERO
        if movement.location_id == location_id:
            delta -= qty
        if movement.to_location_id == location_id:
            delta += qty
        return delta
    if movement.location_id != location_id:
        return _ZERO
    return _ONHAND_SIGN.get(mtype, _ZERO) * qty


def stock_on_hand_by_item_at_location(
    movements: Iterable[Movement],
    location_id: str | None,
) -> dict[str, Decimal]:
    """Stock on hand per ``item_id`` within a single storage location.

    Only movements that touch the location (as source or transfer destination)
    contribute, so the result lists exactly the items seen at that location.
    """
    totals: dict[str, Decimal] = {}
    for movement in movements:
        if movement.item_id is None:
            continue
        if movement.location_id != location_id and movement.to_location_id != location_id:
            continue
        totals[movement.item_id] = totals.get(movement.item_id, _ZERO) + location_delta(movement, location_id)
    return totals


def total_quantity(movements: Iterable[Movement], movement_type: str | MovementType) -> Decimal:
    """Sum the (positive) quantity of every movement of a given type."""
    wanted = _movement_type_value(movement_type)
    total = _ZERO
    for movement in movements:
        if _movement_type_value(movement.movement_type) == wanted:
            total += _as_decimal(movement.quantity)
    return total


def total_inbound(movements: Iterable[Movement]) -> Decimal:
    """Total quantity received (all ``INBOUND`` movements)."""
    return total_quantity(movements, MovementType.INBOUND)


def total_consumed(movements: Iterable[Movement]) -> Decimal:
    """Total quantity installed / used (all ``CONSUMPTION`` movements)."""
    return total_quantity(movements, MovementType.CONSUMPTION)


def total_wasted(movements: Iterable[Movement]) -> Decimal:
    """Total quantity lost to waste / shrinkage (all ``WASTE`` movements)."""
    return total_quantity(movements, MovementType.WASTE)


def consumed_cost(movements: Iterable[Movement]) -> Decimal:
    """Total actual cost of consumed material = sum of ``quantity * unit_cost``."""
    total = _ZERO
    for movement in movements:
        if _movement_type_value(movement.movement_type) == MovementType.CONSUMPTION.value:
            total += _as_decimal(movement.quantity) * _as_decimal(movement.unit_cost)
    return total


def waste_ratio(movements: Iterable[Movement]) -> Decimal | None:
    """Waste as a fraction of consumption = ``total_wasted / total_consumed``.

    Returns ``None`` when nothing has been consumed yet (guarded division), so a
    project with waste but no recorded consumption reads "undefined" rather than
    dividing by zero. The materials do not need to be listed twice: waste and
    consumption are summed from the same movement list in a single pass each.
    """
    consumed = total_consumed(movements)
    return safe_div(total_wasted(movements), consumed)


def average_inventory(opening: Decimal, closing: Decimal) -> Decimal:
    """Simple average inventory over a period = ``(opening + closing) / 2``."""
    return (_as_decimal(opening) + _as_decimal(closing)) / Decimal("2")


def inventory_turnover(consumed: Decimal, avg_inventory: Decimal) -> Decimal | None:
    """Inventory turnover = ``consumed / average_inventory`` over a period.

    Returns ``None`` when the average inventory is zero or negative (guarded), so
    turnover is only reported when there is a stock base to turn over.
    """
    avg = _as_decimal(avg_inventory)
    if avg <= _ZERO:
        return None
    return _as_decimal(consumed) / avg


def days_on_hand(
    avg_inventory: Decimal,
    consumed: Decimal,
    period_days: Decimal | int,
) -> Decimal | None:
    """Inventory days on hand = ``average_inventory * period_days / consumed``.

    This is ``period_days / turnover`` re-expressed to avoid a second guarded
    division: it answers "at the current burn rate, how many days will the
    stock on hand last". Returns ``None`` when nothing has been consumed or the
    period is non-positive, since the burn rate is then undefined.
    """
    consumed_d = _as_decimal(consumed)
    period_d = _as_decimal(period_days)
    if consumed_d <= _ZERO or period_d <= _ZERO:
        return None
    return _as_decimal(avg_inventory) * period_d / consumed_d


def variance_pct(actual: Decimal, budget: Decimal) -> Decimal | None:
    """Percentage variance of an actual cost against a budget.

    ``(actual - budget) / budget * 100``. Positive means over budget. Returns
    ``None`` when the budget is zero (guarded division), which is the honest
    answer for consumption booked against a position that carries no estimate.
    """
    budget_d = _as_decimal(budget)
    ratio = safe_div(_as_decimal(actual) - budget_d, budget_d)
    if ratio is None:
        return None
    return ratio * Decimal("100")


def period_days(movements: Iterable[Movement]) -> Decimal | None:
    """Span in days between the earliest and latest dated movement.

    Convenience for deriving a turnover window straight from the ledger.
    Returns ``None`` when fewer than two movements carry an ``occurred_at``.
    """
    stamps = [m.occurred_at for m in movements if m.occurred_at is not None]
    if len(stamps) < 2:
        return None
    span = max(stamps) - min(stamps)
    return Decimal(str(span.total_seconds())) / Decimal("86400")


def material_cost_variance(
    movements: Iterable[Movement],
    budgets: Mapping[str, Decimal],
) -> list[PositionVariance]:
    """Per-position material-cost variance: actual consumed cost vs BoQ budget.

    Consumption movements are grouped by ``boq_position_id`` and their extended
    costs summed into the actual material spend for each position. That actual is
    then compared against the budgeted material cost the estimate carries for the
    position (supplied in ``budgets`` as ``position_id -> Decimal``).

    The returned lines cover the union of positions that were consumed against
    and positions that carry a budget, so both a budgeted position with no
    consumption (actual zero) and consumption against an unbudgeted position
    (``variance_pct`` is ``None``) are reported. Consumption with no
    ``boq_position_id`` cannot be attributed and is excluded. Lines are ordered
    by ``position_id`` for a stable report.
    """
    actual_cost: dict[str, Decimal] = {}
    consumed_qty: dict[str, Decimal] = {}
    for movement in movements:
        if _movement_type_value(movement.movement_type) != MovementType.CONSUMPTION.value:
            continue
        position_id = movement.boq_position_id
        if position_id is None:
            continue
        qty = _as_decimal(movement.quantity)
        actual_cost[position_id] = actual_cost.get(position_id, _ZERO) + qty * _as_decimal(movement.unit_cost)
        consumed_qty[position_id] = consumed_qty.get(position_id, _ZERO) + qty

    position_ids = sorted(set(actual_cost) | set(budgets))
    lines: list[PositionVariance] = []
    for position_id in position_ids:
        budget = _as_decimal(budgets.get(position_id))
        actual = actual_cost.get(position_id, _ZERO)
        lines.append(
            PositionVariance(
                position_id=position_id,
                budgeted_cost=budget,
                actual_cost=actual,
                variance=actual - budget,
                variance_pct=variance_pct(actual, budget),
                consumed_quantity=consumed_qty.get(position_id, _ZERO),
            ),
        )
    return lines


def summarize_variance(variances: Iterable[PositionVariance]) -> MaterialVarianceSummary:
    """Roll per-position variance lines up into a single project summary."""
    lines = list(variances)
    total_budget = sum((line.budgeted_cost for line in lines), _ZERO)
    total_actual = sum((line.actual_cost for line in lines), _ZERO)
    over_budget = sum(1 for line in lines if line.is_over_budget)
    return MaterialVarianceSummary(
        total_budgeted_cost=total_budget,
        total_actual_cost=total_actual,
        total_variance=total_actual - total_budget,
        variance_pct=variance_pct(total_actual, total_budget),
        position_count=len(lines),
        over_budget_count=over_budget,
        lines=lines,
    )
