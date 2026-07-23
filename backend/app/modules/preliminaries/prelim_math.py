# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Pure preliminaries engine - all pricing logic, zero I/O.

This module imports nothing from :mod:`app.database`, SQLAlchemy, FastAPI or any
ORM model. It is the single source of truth for how a preliminaries line is
priced and how the lines roll up per category into the preliminaries total, so
every rule is unit-testable on any interpreter without a database, exactly like
``field_time.field_time_math`` and ``cvr.compute``.

Pricing:

* A *time-related* line is ``rate_per_period * periods`` - a resource that stands
  on site for a duration (site staff, standing plant, temporary works, welfare).
  The period unit (week, month) is a project convention; the math is unit-agnostic.
* A *fixed* line is its ``fixed_amount`` - a one-off charge independent of the
  programme length (mobilisation, set-up, final clean).

Money is ``Decimal`` throughout - never ``float`` - quantized to two places with
``ROUND_HALF_UP`` (the accounting default). The caller serialises the Decimals to
strings on the wire, matching the platform-wide money convention.

Every function accepts plain mappings (ORM rows rendered to dicts by the service,
or dicts / ``SimpleNamespace`` in tests) so it never depends on a concrete model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# The two kinds of preliminaries line.
TIME_RELATED = "time_related"
FIXED = "fixed"

# Money is quantized to 2 decimal places, half-up.
_MONEY_Q: Decimal = Decimal("0.01")

# Default grouping bucket for a line with no explicit category.
DEFAULT_CATEGORY = "general"


def to_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    """Coerce an arbitrary value to a finite ``Decimal``.

    Args:
        value: An int / float / str / Decimal (or None).
        default: What to return when ``value`` is None or cannot be parsed.

    Returns:
        The parsed ``Decimal``, or ``default`` for None / non-numeric / non-finite
        input. A negative value is preserved (the schema layer rejects negatives;
        the math never silently flips a sign).
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value if value.is_finite() else default
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default
    return parsed if parsed.is_finite() else default


def quantize_money(value: object) -> Decimal:
    """Return ``value`` as a 2 dp ``Decimal`` money amount (half-up)."""
    return to_decimal(value).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


def _get(item: Mapping[str, Any], key: str, default: object = None) -> object:
    """Read ``key`` from a line mapping, tolerating a missing key."""
    return item.get(key, default) if isinstance(item, Mapping) else default


def normalize_item_type(value: object) -> str:
    """Return a canonical item type (``fixed`` or ``time_related``).

    Anything that is not exactly ``fixed`` resolves to ``time_related`` so an
    unknown or blank value prices as a duration item rather than raising.
    """
    return FIXED if str(value or "").strip().lower() == FIXED else TIME_RELATED


def normalize_category(value: object) -> str:
    """Return a trimmed category label, defaulting to ``general`` when blank."""
    text = str(value or "").strip()
    return text or DEFAULT_CATEGORY


def line_total(item: Mapping[str, Any]) -> Decimal:
    """Return the priced total for one preliminaries line as a 2 dp ``Decimal``.

    Time-related: ``rate_per_period * periods``. Fixed: ``fixed_amount``. The
    result is quantized to two places, half-up.

    Args:
        item: A mapping carrying ``item_type`` plus the fields for that type
            (``rate_per_period`` + ``periods``, or ``fixed_amount``).

    Returns:
        The line total (2 dp Decimal). Missing / unparseable numbers coerce to 0,
        so a half-filled draft line simply totals what has been entered so far.
    """
    if normalize_item_type(_get(item, "item_type")) == FIXED:
        return quantize_money(_get(item, "fixed_amount"))
    rate = to_decimal(_get(item, "rate_per_period"))
    periods = to_decimal(_get(item, "periods"))
    return (rate * periods).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CategoryTotal:
    """The priced roll-up for one preliminaries category.

    Attributes:
        category: The category label.
        time_related_total: Sum of the time-related lines in this category.
        fixed_total: Sum of the fixed lines in this category.
        total: ``time_related_total + fixed_total``.
        item_count: How many lines fell into this category.
    """

    category: str
    time_related_total: Decimal
    fixed_total: Decimal
    total: Decimal
    item_count: int


@dataclass(frozen=True)
class PrelimRollup:
    """The whole preliminaries roll-up for a project.

    Attributes:
        categories: Per-category totals, sorted by category label for stable
            output.
        time_related_total: Sum of every time-related line.
        fixed_total: Sum of every fixed line.
        grand_total: ``time_related_total + fixed_total`` - the preliminaries
            total that adds to the estimate.
        item_count: Total number of lines rolled up.
    """

    categories: list[CategoryTotal]
    time_related_total: Decimal
    fixed_total: Decimal
    grand_total: Decimal
    item_count: int


def rollup_by_category(items: Sequence[Mapping[str, Any]]) -> PrelimRollup:
    """Roll a project's preliminaries lines up per category and in total.

    How the totals are derived, so a user is never surprised by them:

    * Every line is priced by :func:`line_total` and added to its category
      bucket, split by whether the line is time-related or fixed.
    * The grand total is the sum of every line, which also equals the sum of the
      per-category totals - the figure that adds to the estimate.

    Args:
        items: The project's preliminaries lines (mappings).

    Returns:
        A :class:`PrelimRollup`. An empty input yields all-zero totals and no
        category rows.
    """
    time_related: dict[str, Decimal] = {}
    fixed: dict[str, Decimal] = {}
    counts: dict[str, int] = {}

    grand_time = Decimal("0")
    grand_fixed = Decimal("0")

    for item in items:
        category = normalize_category(_get(item, "category"))
        amount = line_total(item)
        counts[category] = counts.get(category, 0) + 1
        if normalize_item_type(_get(item, "item_type")) == FIXED:
            fixed[category] = fixed.get(category, Decimal("0")) + amount
            grand_fixed += amount
        else:
            time_related[category] = time_related.get(category, Decimal("0")) + amount
            grand_time += amount

    categories: list[CategoryTotal] = []
    for category in sorted(counts):
        time_amount = time_related.get(category, Decimal("0")).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
        fixed_amount = fixed.get(category, Decimal("0")).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
        categories.append(
            CategoryTotal(
                category=category,
                time_related_total=time_amount,
                fixed_total=fixed_amount,
                total=(time_amount + fixed_amount).quantize(_MONEY_Q, rounding=ROUND_HALF_UP),
                item_count=counts[category],
            ),
        )

    time_total = grand_time.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
    fixed_total = grand_fixed.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
    return PrelimRollup(
        categories=categories,
        time_related_total=time_total,
        fixed_total=fixed_total,
        grand_total=(time_total + fixed_total).quantize(_MONEY_Q, rounding=ROUND_HALF_UP),
        item_count=sum(counts.values()),
    )
