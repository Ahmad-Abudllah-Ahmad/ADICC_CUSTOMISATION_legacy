# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure production-norm expansion math.

A production norm carries the productivity coefficients behind one unit of a
work item: how many labor-hours, how many machine-hours and how much of each
material a unit consumes. Multiplying those per-unit coefficients by a work
quantity yields the *unpriced* resource demand - the hours and material
takeoff an estimator sees before any pricing is applied.

Everything here is deliberately free of SQLAlchemy, FastAPI and I/O so the
math can be unit-tested without a database. Callers (the service layer) build
the small :class:`NormCoefficients` value object from an ORM row and hand it to
:func:`expand`.

All arithmetic uses :class:`decimal.Decimal`; results are quantised to four
decimal places with ``ROUND_HALF_UP`` so the same inputs always yield the same
strings (no binary-float drift). Amounts never touch ``float``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Resource demand is reported to 4 decimal places - fine enough for fractional
# labour-hours and small material factors (e.g. 0.0125 h/kg) while staying
# stable across platforms.
_QUANT = Decimal("0.0001")


def _to_decimal(value: Decimal | int | str) -> Decimal:
    """Coerce a coefficient / quantity to a finite :class:`Decimal`.

    Accepts a ``Decimal``, an ``int`` or a decimal *string* (the storage form
    used across the cost spine). A ``float`` is refused on purpose - money,
    rates and factors are never allowed to enter the pipeline as binary
    floats. A ``NaN`` / ``Infinity`` is rejected so a poisoned coefficient can
    never propagate into a takeoff.

    Args:
        value: The raw coefficient or quantity.

    Returns:
        The value as a finite ``Decimal``.

    Raises:
        TypeError: If ``value`` is a ``float`` or an unsupported type.
        ValueError: If ``value`` cannot be parsed or is not finite.
    """
    if isinstance(value, bool):  # bool is an int subclass; never a coefficient
        raise TypeError("coefficient must not be a bool")
    if isinstance(value, float):
        raise TypeError("coefficient must be Decimal/int/str, not float")
    if isinstance(value, Decimal):
        dec = value
    else:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid decimal value: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError("value must be finite (no NaN / Infinity)")
    return dec


def _q4(value: Decimal) -> Decimal:
    """Quantise a Decimal to four decimal places, half-up."""
    return value.quantize(_QUANT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class MaterialCoefficient:
    """Per-unit demand for one material inside a production norm.

    Attributes:
        name: Human-readable material name (e.g. "Gypsum plaster").
        unit: Unit the material is measured in (kg, m3, l, pcs, ...).
        qty_per_unit: Quantity of the material consumed per unit of the work
            item. Decimal or decimal-string; never a float.
    """

    name: str
    unit: str
    qty_per_unit: Decimal | int | str


@dataclass(frozen=True)
class NormCoefficients:
    """The unpriced productivity coefficients for one unit of a work item.

    Attributes:
        labor_hours_per_unit: Labour-hours consumed per unit of the work item.
        machine_hours_per_unit: Machine-hours consumed per unit of the work
            item.
        materials: Ordered material coefficients. Order is preserved verbatim
            in the expansion output so the result is deterministic.
    """

    labor_hours_per_unit: Decimal | int | str
    machine_hours_per_unit: Decimal | int | str
    materials: tuple[MaterialCoefficient, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MaterialDemand:
    """Expanded, unpriced demand for one material.

    Attributes:
        name: Material name, carried through from the coefficient.
        unit: Material unit, carried through from the coefficient.
        qty: Total quantity required, quantised to four decimal places.
    """

    name: str
    unit: str
    qty: Decimal


@dataclass(frozen=True)
class ExpansionResult:
    """The full unpriced resource demand behind a quantity of a work item.

    Attributes:
        labor_hours: Total labour-hours, quantised to four decimal places.
        machine_hours: Total machine-hours, quantised to four decimal places.
        materials: Per-material demand, in the same order as the norm's
            material coefficients.
    """

    labor_hours: Decimal
    machine_hours: Decimal
    materials: tuple[MaterialDemand, ...]

    def as_dict(self) -> dict[str, object]:
        """Render the result as plain Decimal-as-string JSON primitives.

        Every numeric value becomes a fixed-point decimal *string* (e.g.
        ``"3.6000"``) so it round-trips through JSON without float precision
        loss, matching the platform's Decimal-as-string wire contract.
        """
        return {
            "labor_hours": format(self.labor_hours, "f"),
            "machine_hours": format(self.machine_hours, "f"),
            "materials": [{"name": m.name, "unit": m.unit, "qty": format(m.qty, "f")} for m in self.materials],
        }


def expand(norm: NormCoefficients, quantity: Decimal | int | str) -> ExpansionResult:
    """Expand a work item's quantity into unpriced resource demand.

    Multiplies each per-unit coefficient of ``norm`` by ``quantity`` to obtain
    the total labour-hours, machine-hours and material quantities behind the
    work. The result is deliberately unpriced: it answers "how many hours and
    how much material", not "how much money".

    Args:
        norm: The per-unit productivity coefficients of the work item.
        quantity: The work quantity to expand. Decimal, int or decimal-string;
            never a float. Must be finite and non-negative.

    Returns:
        An :class:`ExpansionResult` with every figure quantised to four
        decimal places.

    Raises:
        TypeError: If ``quantity`` or any coefficient is a float.
        ValueError: If ``quantity`` is negative or any value is non-finite.
    """
    qty = _to_decimal(quantity)
    if qty < 0:
        raise ValueError("quantity must be non-negative")

    labor = _q4(_to_decimal(norm.labor_hours_per_unit) * qty)
    machine = _q4(_to_decimal(norm.machine_hours_per_unit) * qty)
    materials = tuple(
        MaterialDemand(
            name=mat.name,
            unit=mat.unit,
            qty=_q4(_to_decimal(mat.qty_per_unit) * qty),
        )
        for mat in norm.materials
    )
    return ExpansionResult(labor_hours=labor, machine_hours=machine, materials=materials)


def expand_many(
    pairs: Iterable[tuple[NormCoefficients, Decimal | int | str]],
) -> list[ExpansionResult]:
    """Expand several ``(norm, quantity)`` pairs, preserving order.

    A thin convenience wrapper over :func:`expand` for the batch endpoint. It
    performs no lookup and swallows no error - a bad pair raises exactly as the
    single-item call would.

    Args:
        pairs: Iterable of ``(norm, quantity)`` tuples.

    Returns:
        One :class:`ExpansionResult` per input pair, in input order.
    """
    return [expand(norm, quantity) for norm, quantity in pairs]
