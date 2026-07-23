# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Elemental and parametric cost modelling helpers for the 5D Cost Model.

Pure, database-free functions that build an early-stage cost estimate the way
an elemental cost plan does (for example NRM elemental method, or a simple
cost per m2 model). These sit alongside the EVM / budget service and are safe
to call from anywhere: they touch no session, no I/O and no global state.

Design goals (kept deliberately clear and simple for a worldwide user):

- International by default. No hardcoded currency, region, unit system or
  locale. Money stays Decimal-exact end to end. Areas, volumes and lengths are
  converted to canonical metric before any comparison, so a project measured
  in square feet and one measured in square metres benchmark identically.
- Explainable. A modelled total is always returned with the per-element
  breakdown and a plain-language note describing which elements, rates and
  factors built the number, so a user can trust it.
- Defensive. Zero or negative quantities, a missing rate, an unknown unit or a
  zero cost driver raise a clear ``ValueError`` that says what to fix, never a
  500, a NaN or an infinity.

Key concepts (see :data:`COST_MODEL_GLOSSARY` for one-line definitions):

- Elemental rate: the cost of one unit of an element, for example cost per m2
  of external wall, per m3 of concrete, or per unit of a fitting.
- Cost driver: the measured parameter that scales an element's cost, such as
  area, volume, length or a simple count.
- Gross floor area (GFA) basis: dividing the total by the gross floor area
  gives the headline benchmark, cost per m2 of GFA.
- Regional cost factor: a data-driven multiplier that adjusts base rates to a
  locality. The worldwide default is ``1`` (no adjustment); there is no
  hardcoded country anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.modules.costmodel.schemas import _serialise_money

# ── Canonical units ─────────────────────────────────────────────────────────
# Stored / compared values are always canonical metric: area in m2, volume in
# m3, length in m, and a dimensionless count. Every supported input unit maps
# to (dimension, factor-to-canonical). Factors are exact Decimals so an
# imperial quantity never drifts through binary float on the way to metric.

_CENTS = Decimal("0.01")

# dimension -> canonical unit token used when we report a converted quantity.
CANONICAL_UNITS: dict[str, str] = {
    "area": "m2",
    "volume": "m3",
    "length": "m",
    "count": "unit",
}

# normalised-unit-token -> (dimension, factor to the canonical metric unit).
_UNIT_TABLE: dict[str, tuple[str, Decimal]] = {
    # Area (canonical m2).
    "m2": ("area", Decimal("1")),
    "sqm": ("area", Decimal("1")),
    "sm": ("area", Decimal("1")),
    "cm2": ("area", Decimal("0.0001")),
    "mm2": ("area", Decimal("0.000001")),
    "km2": ("area", Decimal("1000000")),
    "ha": ("area", Decimal("10000")),
    "ft2": ("area", Decimal("0.09290304")),
    "sqft": ("area", Decimal("0.09290304")),
    "sf": ("area", Decimal("0.09290304")),
    "yd2": ("area", Decimal("0.83612736")),
    "sqyd": ("area", Decimal("0.83612736")),
    "ac": ("area", Decimal("4046.8564224")),
    "acre": ("area", Decimal("4046.8564224")),
    # Volume (canonical m3).
    "m3": ("volume", Decimal("1")),
    "cum": ("volume", Decimal("1")),
    "cm3": ("volume", Decimal("0.000001")),
    "l": ("volume", Decimal("0.001")),
    "liter": ("volume", Decimal("0.001")),
    "litre": ("volume", Decimal("0.001")),
    "ft3": ("volume", Decimal("0.028316846592")),
    "cft": ("volume", Decimal("0.028316846592")),
    "cf": ("volume", Decimal("0.028316846592")),
    "yd3": ("volume", Decimal("0.764554857984")),
    "cuyd": ("volume", Decimal("0.764554857984")),
    # Length (canonical m).
    "m": ("length", Decimal("1")),
    "mm": ("length", Decimal("0.001")),
    "cm": ("length", Decimal("0.01")),
    "km": ("length", Decimal("1000")),
    "ft": ("length", Decimal("0.3048")),
    "in": ("length", Decimal("0.0254")),
    "inch": ("length", Decimal("0.0254")),
    "yd": ("length", Decimal("0.9144")),
    "mi": ("length", Decimal("1609.344")),
    # Count (dimensionless).
    "unit": ("count", Decimal("1")),
    "units": ("count", Decimal("1")),
    "each": ("count", Decimal("1")),
    "ea": ("count", Decimal("1")),
    "nr": ("count", Decimal("1")),
    "no": ("count", Decimal("1")),
    "pcs": ("count", Decimal("1")),
    "item": ("count", Decimal("1")),
    "lsum": ("count", Decimal("1")),
    "ls": ("count", Decimal("1")),
}


# ── Glossary (plain-language, one line each) ────────────────────────────────

COST_MODEL_GLOSSARY: dict[str, str] = {
    "elemental_rate": (
        "The cost of one unit of an element, for example cost per m2 of wall, "
        "per m3 of concrete or per unit of a fitting."
    ),
    "cost_driver": (
        "The measured quantity that scales an element's cost, such as area, volume, length or a simple count."
    ),
    "gfa_basis": (
        "Gross floor area basis: the total divided by the gross floor area, "
        "giving the headline benchmark of cost per m2 of GFA."
    ),
    "regional_factor": (
        "A multiplier that adjusts base rates to a locality. The worldwide "
        "default is 1, meaning no regional adjustment."
    ),
    "element_total": ("An element's quantity multiplied by its elemental rate, in money."),
    "subtotal_base": ("The sum of every element total before the regional cost factor is applied."),
}


def explain(term: str) -> str:
    """Return a one-line plain-language definition of a cost-model concept.

    Args:
        term: A glossary key, for example ``"elemental_rate"`` or ``"gfa_basis"``.

    Returns:
        The plain-language definition.

    Raises:
        ValueError: When ``term`` is not a known concept. The message lists the
            available terms so the caller knows what to ask for.
    """
    key = (term or "").strip().lower()
    if key not in COST_MODEL_GLOSSARY:
        known = ", ".join(sorted(COST_MODEL_GLOSSARY))
        raise ValueError(f"Unknown cost-model term {term!r}. Known terms: {known}.")
    return COST_MODEL_GLOSSARY[key]


# ── Numeric parsing helpers ─────────────────────────────────────────────────


def _to_decimal(value: Any, *, field: str) -> Decimal:
    """Parse ``value`` to a finite Decimal or raise a clear input error.

    Args:
        value: The raw value (Decimal, int, float or numeric string).
        field: Human-readable field name used in the error message.

    Returns:
        A finite Decimal.

    Raises:
        ValueError: When ``value`` is missing or not a finite number.
    """
    if value is None:
        raise ValueError(f"{field} is missing. Enter a number.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a number, got {value!r}.") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite number, not NaN or infinity.")
    return result


def _money(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places (money precision) using half-up rounding."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


# ── Unit conversion (metric and imperial in, canonical metric out) ──────────


def normalise_unit(unit: str) -> str:
    """Normalise a free-text unit token to the lookup key used internally.

    Handles superscripts (``m²`` / ``m³``), a caret exponent (``m^2``) and
    stray spaces or dots, then lower-cases. This keeps the mapping forgiving of
    however a user typed the unit without guessing at anything ambiguous.

    Args:
        unit: The raw unit string, for example ``"m2"``, ``"ft2"`` or ``"m3"``.

    Returns:
        The normalised token, for example ``"m2"``.
    """
    token = (unit or "").strip().lower()
    token = token.replace("²", "2").replace("³", "3")
    return token.replace("^", "").replace(" ", "").replace(".", "")


def unit_dimension(unit: str) -> str:
    """Return the physical dimension of a unit (area, volume, length or count).

    Args:
        unit: A supported unit token.

    Returns:
        One of ``"area"``, ``"volume"``, ``"length"``, ``"count"``.

    Raises:
        ValueError: When the unit is not supported.
    """
    token = normalise_unit(unit)
    entry = _UNIT_TABLE.get(token)
    if entry is None:
        raise ValueError(_unknown_unit_message(unit))
    return entry[0]


def _unknown_unit_message(unit: str) -> str:
    """Build a helpful error message for an unsupported unit."""
    return (
        f"Unsupported unit {unit!r}. Use a supported metric or imperial unit "
        f"(for example m2, ft2, m3, ft3, m, ft, or unit), or pass the value "
        f"already in a canonical unit (m2, m3, m)."
    )


def to_canonical_quantity(value: Any, unit: str) -> tuple[Decimal, str]:
    """Convert a quantity in any supported unit to its canonical metric value.

    Canonical means area in m2, volume in m3, length in m, and a plain count.
    Stored and compared values are always canonical, so a benchmark computed
    from imperial inputs matches one computed from metric inputs exactly.

    Args:
        value: The quantity to convert (Decimal, int, float or numeric string).
        unit: The unit ``value`` is expressed in, for example ``"ft2"``.

    Returns:
        A ``(canonical_value, canonical_unit)`` pair, for example
        ``(Decimal("9.290304"), "m2")`` for ``100`` ft2.

    Raises:
        ValueError: When the value is negative or not finite, or the unit is
            not supported.
    """
    quantity = _to_decimal(value, field="Quantity")
    if quantity < 0:
        raise ValueError(f"Quantity must be zero or positive, got {quantity}.")
    token = normalise_unit(unit)
    entry = _UNIT_TABLE.get(token)
    if entry is None:
        raise ValueError(_unknown_unit_message(unit))
    dimension, factor = entry
    return quantity * factor, CANONICAL_UNITS[dimension]


def from_canonical_quantity(value: Any, unit: str) -> Decimal:
    """Convert a canonical metric quantity back into any supported unit.

    Inverse of :func:`to_canonical_quantity` for display only; stored values
    stay canonical. For example ``9.290304`` m2 converts to ``100`` ft2.

    Args:
        value: The canonical quantity (m2 for area, m3 for volume, m for length).
        unit: The target unit to express the value in.

    Returns:
        The quantity in ``unit``.

    Raises:
        ValueError: When the value is negative or not finite, or the unit is
            not supported.
    """
    quantity = _to_decimal(value, field="Quantity")
    if quantity < 0:
        raise ValueError(f"Quantity must be zero or positive, got {quantity}.")
    token = normalise_unit(unit)
    entry = _UNIT_TABLE.get(token)
    if entry is None:
        raise ValueError(_unknown_unit_message(unit))
    _dimension, factor = entry
    return quantity / factor


def supported_units() -> dict[str, list[str]]:
    """Return the supported unit tokens grouped by dimension.

    Useful for a UI dropdown or a help panel so users can see exactly which
    metric and imperial units the model accepts.

    Returns:
        A mapping of dimension name to a sorted list of unit tokens.
    """
    grouped: dict[str, list[str]] = {dim: [] for dim in CANONICAL_UNITS}
    for token, (dimension, _factor) in _UNIT_TABLE.items():
        grouped[dimension].append(token)
    return {dim: sorted(tokens) for dim, tokens in grouped.items()}


# ── Pure cost primitives ────────────────────────────────────────────────────


def element_total(quantity: Any, unit_rate: Any) -> Decimal:
    """Return an element total: quantity multiplied by its elemental rate.

    The unit cancels (rate is money per unit, quantity is that same unit), so
    the result is money and no unit conversion is needed here. All arithmetic
    is Decimal, so cents never drift.

    Args:
        quantity: The element unit quantity (zero or positive).
        unit_rate: The elemental rate, money per unit (zero or positive). A zero
            rate is a well-defined zero total; a missing rate is an error.

    Returns:
        The element total, rounded to 2 places.

    Raises:
        ValueError: When quantity or rate is missing, non-finite or negative.
    """
    qty = _to_decimal(quantity, field="Quantity")
    rate = _to_decimal(unit_rate, field="Unit rate (elemental rate)")
    if qty < 0:
        raise ValueError(f"Quantity must be zero or positive, got {qty}.")
    if rate < 0:
        raise ValueError(f"Unit rate (elemental rate) must be zero or positive, got {rate}.")
    return _money(qty * rate)


def apply_regional_factor(amount: Any, factor: Any = Decimal("1")) -> Decimal:
    """Apply a data-driven regional cost factor to a money amount.

    The factor adjusts a base rate to a locality. It is data-driven with a
    documented worldwide default of ``1`` (no adjustment); there is no
    hardcoded country. A factor must be strictly positive, since a zero or
    negative multiplier is never a valid regional adjustment.

    Args:
        amount: The base money amount.
        factor: The regional multiplier. Defaults to ``1`` (worldwide default).

    Returns:
        The adjusted amount, rounded to 2 places.

    Raises:
        ValueError: When the amount or factor is non-finite, or the factor is
            zero or negative.
    """
    base = _to_decimal(amount, field="Amount")
    mult = _to_decimal(factor, field="Regional cost factor")
    if mult <= 0:
        raise ValueError(
            "Regional cost factor must be greater than zero. Use 1 for the worldwide default (no regional adjustment)."
        )
    return _money(base * mult)


def cost_per_driver(total: Any, driver_quantity: Any, driver_unit: str = "m2") -> Decimal:
    """Return cost per canonical unit of a cost driver, for example cost per m2.

    The driver quantity is converted to its canonical metric unit first, so the
    benchmark is comparable across projects regardless of whether the driver was
    entered in metric or imperial units. This is how the headline cost per m2 of
    gross floor area is computed (pass the GFA as the driver).

    Args:
        total: The money total to spread over the driver.
        driver_quantity: The cost driver quantity (for example the GFA).
        driver_unit: The unit of ``driver_quantity``. Defaults to ``"m2"``.

    Returns:
        Cost per canonical unit of the driver, rounded to 2 places.

    Raises:
        ValueError: When the total is non-finite, or the driver is zero,
            negative or in an unsupported unit. A zero driver is guarded
            explicitly so division by zero can never reach the caller.
    """
    total_dec = _to_decimal(total, field="Total")
    canonical_qty, canonical_unit = to_canonical_quantity(driver_quantity, driver_unit)
    if canonical_qty <= 0:
        raise ValueError(
            f"Cost driver must be greater than zero to compute a cost per "
            f"{canonical_unit}. Enter a positive {driver_unit} value."
        )
    return _money(total_dec / canonical_qty)


# ── Elemental estimate model ────────────────────────────────────────────────


class ElementInput(BaseModel):
    """One element in an elemental cost plan.

    An element is a measured item of construction (for example external walls,
    a slab, or a door set) with a quantity, a unit and an elemental rate. Money
    fields accept Decimal-as-string in JSON, mirroring the rest of this module.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(default="", max_length=255, description="Element name, for example 'External walls'.")
    quantity: Decimal = Field(default=Decimal("0"), description="Element unit quantity in 'unit'.")
    unit: str = Field(default="unit", max_length=20, description="Unit of measure, for example m2, m3 or unit.")
    unit_rate: Decimal | None = Field(
        default=None,
        description="Elemental rate, money per unit. Required (a missing rate is an input error).",
    )

    @field_serializer("quantity", "unit_rate", when_used="json")
    def _ser_money(self, v: Decimal | None) -> str | None:
        return _serialise_money(v)


class ElementCostBreakdown(BaseModel):
    """Explainability row: how one element contributed to the total."""

    name: str
    quantity: Decimal = Decimal("0")
    unit: str = "unit"
    # Canonical metric view of the quantity so users can compare like with like.
    canonical_quantity: Decimal = Decimal("0")
    canonical_unit: str = "unit"
    unit_rate: Decimal = Decimal("0")
    base_total: Decimal = Decimal("0")
    adjusted_total: Decimal = Decimal("0")

    @field_serializer(
        "quantity",
        "canonical_quantity",
        "unit_rate",
        "base_total",
        "adjusted_total",
        when_used="json",
    )
    def _ser_money(self, v: Decimal) -> str | None:
        return _serialise_money(v)


class ElementalEstimate(BaseModel):
    """A parametric / elemental cost estimate with a full breakdown.

    The total is built as: sum of (element quantity x elemental rate), then
    multiplied by the regional cost factor. The per-element breakdown and the
    plain-language ``notes`` explain exactly how the number was reached.
    Currency is a caller-supplied label so the model stays currency-agnostic.
    """

    currency: str = ""
    element_count: int = 0
    regional_factor: Decimal = Decimal("1")
    subtotal_base: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    # Gross floor area basis (optional). When supplied, cost_per_gfa is the
    # headline benchmark: total divided by the GFA in canonical m2.
    gfa_canonical: Decimal | None = None
    gfa_unit: str | None = None
    cost_per_gfa: Decimal | None = None
    elements: list[ElementCostBreakdown] = Field(default_factory=list)
    notes: str = ""

    @field_serializer(
        "regional_factor",
        "subtotal_base",
        "total",
        "gfa_canonical",
        "cost_per_gfa",
        when_used="json",
    )
    def _ser_money(self, v: Decimal | None) -> str | None:
        return _serialise_money(v)


def build_elemental_estimate(
    elements: Sequence[ElementInput],
    *,
    regional_factor: Any = Decimal("1"),
    gross_floor_area: Any = None,
    gross_floor_area_unit: str = "m2",
    currency: str = "",
) -> ElementalEstimate:
    """Build an elemental cost estimate from a list of elements.

    Each element total is its quantity multiplied by its elemental rate. The
    element subtotal is then scaled by a data-driven regional cost factor
    (worldwide default 1). If a gross floor area is supplied, the headline
    benchmark cost per m2 of GFA is added. The result carries a per-element
    breakdown and a plain-language note so the total is fully explainable.

    Args:
        elements: The elements to price. Must not be empty.
        regional_factor: The regional cost multiplier. Defaults to ``1``.
        gross_floor_area: Optional gross floor area for the cost per m2 benchmark.
        gross_floor_area_unit: Unit of ``gross_floor_area``. Defaults to ``"m2"``.
        currency: Optional currency label carried through to the result.

    Returns:
        An :class:`ElementalEstimate` with totals, breakdown and notes.

    Raises:
        ValueError: When the element list is empty, an element has a missing or
            negative rate, a negative quantity, an unsupported unit, or the
            gross floor area is zero or negative.
    """
    if not elements:
        raise ValueError(
            "Add at least one element to build an elemental cost estimate. Each "
            "element needs a quantity, a unit and a cost per unit (the elemental rate)."
        )

    factor = _to_decimal(regional_factor, field="Regional cost factor")
    if factor <= 0:
        raise ValueError(
            "Regional cost factor must be greater than zero. Use 1 for the worldwide default (no regional adjustment)."
        )

    breakdown: list[ElementCostBreakdown] = []
    subtotal = Decimal("0")

    for index, element in enumerate(elements):
        label = element.name.strip() or f"Element {index + 1}"
        if element.unit_rate is None:
            raise ValueError(
                f"Element '{label}' has no cost per unit (elemental rate). Enter a rate, or remove the element."
            )
        base = element_total(element.quantity, element.unit_rate)
        adjusted = _money(base * factor)
        canonical_qty, canonical_unit = to_canonical_quantity(element.quantity, element.unit)

        breakdown.append(
            ElementCostBreakdown(
                name=label,
                quantity=_to_decimal(element.quantity, field="Quantity"),
                unit=element.unit,
                canonical_quantity=canonical_qty,
                canonical_unit=canonical_unit,
                unit_rate=_to_decimal(element.unit_rate, field="Unit rate (elemental rate)"),
                base_total=base,
                adjusted_total=adjusted,
            )
        )
        subtotal += base

    subtotal = _money(subtotal)
    total = _money(subtotal * factor)

    gfa_canonical: Decimal | None = None
    cost_per_gfa: Decimal | None = None
    gfa_unit_label: str | None = None
    if gross_floor_area is not None:
        gfa_canonical, _canonical_unit = to_canonical_quantity(gross_floor_area, gross_floor_area_unit)
        gfa_unit_label = gross_floor_area_unit
        cost_per_gfa = cost_per_driver(total, gross_floor_area, gross_floor_area_unit)

    ccy = f" {currency}" if currency else ""
    notes = (
        f"Elemental cost estimate built from {len(breakdown)} element(s). Each element "
        f"total is its quantity times its cost per unit (the elemental rate). The element "
        f"subtotal is {subtotal}{ccy}. A regional cost factor of {factor} was applied "
        f"(1 = worldwide default, no adjustment), giving a total of {total}{ccy}."
    )
    if cost_per_gfa is not None and gfa_canonical is not None:
        notes += (
            f" Cost per m2 of gross floor area (GFA) is {cost_per_gfa}{ccy}, the total "
            f"divided by {gfa_canonical} m2 of GFA."
        )

    return ElementalEstimate(
        currency=currency,
        element_count=len(breakdown),
        regional_factor=factor,
        subtotal_base=subtotal,
        total=total,
        gfa_canonical=gfa_canonical,
        gfa_unit=gfa_unit_label,
        cost_per_gfa=cost_per_gfa,
        elements=breakdown,
        notes=notes,
    )
