# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Pure pricing engine for the Cost Explorer "substitute" and "price
intelligence" modes.

Two concerns, both stdlib-only so they import and unit-test on any interpreter:

* :func:`substitute` - what a work item's unit rate becomes when one of the
  resources it consumes is re-priced (a cheaper supplier, a material swap). It
  applies an INCREMENTAL delta rather than recomputing the rate from the
  component sum. Cost data stores an authored position rate that does NOT equal
  the sum of its component line costs (abstract-variant / mass / scope rows
  inflate the raw sum to well above 100% of the rate), so recomputing from the
  parts would silently move the rate. Holding every other line fixed and moving
  only the swapped line keeps the published rate intact and reports an honest
  delta:  ``new_rate = old_rate + quantity * (new_price - old_price)``.

* :func:`price_stats` - the spread of a single resource's unit price across the
  price bases and works that carry it (min / p25 / median / p75 / max / mean),
  the "is this quote in line with the market" read.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Upper bound on any single price/quantity/rate fed into the substitution maths.
# Catalog ``base_price`` is a free ``String(50)`` column, so a malformed row can
# hold an absurd-exponent value like ``"1E9999999"`` that parses to a valid
# Decimal and then overflows the multiply below. Clamping every magnitude keeps
# the pure engine total-safe for any caller: the request schema guards the
# explicit-price path, and this guards the catalog-priced twin that reads a
# stored price straight out of the database.
MAX_ABS_PRICE = Decimal("1e12")


def _clamp_price(value: Decimal) -> Decimal:
    """Bound a parsed value to +/- :data:`MAX_ABS_PRICE`, non-finite -> 0."""
    if not value.is_finite():
        return Decimal(0)
    if value > MAX_ABS_PRICE:
        return MAX_ABS_PRICE
    if value < -MAX_ABS_PRICE:
        return -MAX_ABS_PRICE
    return value


def to_decimal(value: object) -> Decimal:
    """Parse a stored money/quantity value to Decimal, degrading to 0.

    Mirrors :func:`app.modules.cost_explorer.ranking.to_decimal`: money and
    quantities are stored as Decimal-compatible strings and may be blank, so
    anything unparseable becomes ``Decimal(0)`` instead of raising.
    """
    if value is None or value == "":
        return Decimal(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


@dataclass
class SubstitutionResult:
    """The effect of re-pricing one resource line on a work item's rate."""

    old_rate: Decimal
    new_rate: Decimal
    delta: Decimal
    delta_pct: float
    old_line_cost: Decimal
    new_line_cost: Decimal
    clamped: bool  # True when the raw new rate went below 0 and was floored


def substitute(
    item_rate: object,
    resource_quantity: object,
    old_unit_rate: object,
    new_unit_rate: object,
) -> SubstitutionResult:
    """Compute the new work-item rate after re-pricing one resource line.

    Args:
        item_rate: The work item's current authored unit rate.
        resource_quantity: Consumption norm of the resource per one item unit.
        old_unit_rate: The resource's unit price as it stands inside the item.
        new_unit_rate: The proposed replacement unit price (0 removes the line).

    Returns:
        A :class:`SubstitutionResult`. ``new_rate`` is floored at 0 (a swap can
        never drive a rate negative in the UI); ``clamped`` flags when that
        floor bit, while ``delta`` stays the true signed change so the caller
        can still see the magnitude.
    """
    rate = _clamp_price(to_decimal(item_rate))
    qty = _clamp_price(to_decimal(resource_quantity))
    old_price = _clamp_price(to_decimal(old_unit_rate))
    new_price = _clamp_price(to_decimal(new_unit_rate))

    old_line = qty * old_price
    new_line = qty * new_price
    delta = new_line - old_line

    raw_new = rate + delta
    clamped = raw_new < 0
    new_rate = Decimal(0) if clamped else raw_new

    delta_pct = float(delta / rate * 100) if rate > 0 else 0.0

    return SubstitutionResult(
        old_rate=rate,
        new_rate=new_rate,
        delta=delta,
        delta_pct=round(delta_pct, 2),
        old_line_cost=old_line,
        new_line_cost=new_line,
        clamped=clamped,
    )


@dataclass
class PriceStats:
    """Distribution of one resource's unit price across the rows that carry it."""

    count: int
    min: Decimal
    p25: Decimal
    median: Decimal
    p75: Decimal
    max: Decimal
    mean: Decimal


def _percentile(sorted_vals: list[Decimal], pct: float) -> Decimal:
    """Linear-interpolated percentile over a pre-sorted list (0 <= pct <= 1)."""
    if not sorted_vals:
        return Decimal(0)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = pct * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = Decimal(str(pos - lo))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def price_stats(prices: list[object]) -> PriceStats:
    """Summarise a set of unit prices, ignoring blanks and non-positive values.

    Non-positive prices are dropped (a 0 or blank price is "not quoted here",
    not a real data point), so the stats describe only the rows that actually
    carry a price. An empty input yields an all-zero, ``count=0`` result rather
    than raising, so a resource nobody prices renders cleanly.
    """
    vals = sorted(v for v in (to_decimal(p) for p in prices) if v > 0)
    if not vals:
        return PriceStats(0, Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0))
    # Quantise the mean to a money-friendly 2 dp. Every other stat is an exact
    # input value; an un-rounded 28-digit mean would read as a UI glitch.
    mean = (sum(vals, Decimal(0)) / Decimal(len(vals))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return PriceStats(
        count=len(vals),
        min=vals[0],
        p25=_percentile(vals, 0.25),
        median=_percentile(vals, 0.5),
        p75=_percentile(vals, 0.75),
        max=vals[-1],
        mean=mean,
    )
