# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, database-free helpers for assembly composite rates.

This module adds a small set of pure, side-effect-free functions that make
the assembly maths clear, correct, and safe for a worldwide audience. It is
deliberately independent of the database, the ORM, and any single locale so
it can be reused and unit-tested in isolation.

Design rules that keep the platform international and honest:

* No hardcoded currency, unit, or locale. Currency is data that travels with
  each component (or is passed in explicitly); the functions never assume one.
* Money is Decimal-exact. Every numeric input is coerced through ``Decimal``
  built from ``str(value)`` so there is no IEEE-754 drift, and no result is
  ever ``NaN`` or ``Infinity``.
* Never sum across currency codes. A composite rate mixing two currencies is a
  clean input error, not a silent, meaningless total.
* The regional factor is data-driven with a documented worldwide default of
  ``1.0`` (see ``DEFAULT_REGIONAL_FACTOR``), which means "no regional
  adjustment" and is correct anywhere on Earth.
* Every component carries an explicit unit; the breakdown surfaces it so a
  user can check what was added up.

Concepts, one line each (see also ``explain_concept``):

* component factor: how much of a component is needed per one unit of the
  assembly, for example 0.12 tonnes of rebar per cubic metre of wall.
* composite rate: the price for one unit of the assembly, built by adding up
  every component's factor times its unit rate.
* regional factor: a multiplier that adjusts the composite rate for a place;
  the worldwide default is 1.0, meaning no adjustment.
* waste allowance: an extra percentage that covers material lost or overhead
  during the work; the default is 0, meaning no extra.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# ── Documented worldwide defaults ─────────────────────────────────────────────
# A regional factor of exactly 1.0 means "apply no regional adjustment". It is
# the safe, neutral default for every country, so a caller that does not know
# (or care about) a region still gets the correct base rate.
DEFAULT_REGIONAL_FACTOR: Decimal = Decimal("1")

# A waste / overhead uplift of 0 percent means "add nothing". Callers opt in to
# a positive percentage when a trade or material needs it.
DEFAULT_WASTE_PCT: Decimal = Decimal("0")


# ── Plain-language glossary and status labels ─────────────────────────────────
# Kept as plain English strings here (the API layer can still translate them
# through the module's i18n bundle). The point is that no concept in this
# module is left unexplained for a first-time user.
_CONCEPTS: dict[str, str] = {
    "component_factor": (
        "How much of a component is needed per one unit of the assembly, "
        "for example 0.12 tonnes of rebar per cubic metre of wall."
    ),
    "composite_rate": (
        "The price for one unit of the assembly, built by adding up every component's factor times its unit rate."
    ),
    "regional_factor": (
        "A multiplier that adjusts the composite rate for a place; the worldwide default is 1.0, meaning no adjustment."
    ),
    "waste_allowance": (
        "An extra percentage that covers material lost or overhead during the work; the default is 0, meaning no extra."
    ),
}

# Plain labels for the validation status codes the assembly and BOQ layers use
# (see the Position.validation_status vocabulary). No colour words, no jargon.
_STATUS_LABELS: dict[str, str] = {
    "pending": "Not checked yet",
    "passed": "All checks passed",
    "warnings": "Passed, with warnings to review",
    "errors": "Has errors to fix",
}


def explain_concept(concept: str | None) -> str:
    """Return a one-line, plain-language explanation of an assembly concept.

    Args:
        concept: One of ``component_factor``, ``composite_rate``,
            ``regional_factor``, ``waste_allowance`` (case-insensitive).

    Returns:
        The explanation string, or an empty string for an unknown concept.
    """
    key = (concept or "").strip().lower()
    return _CONCEPTS.get(key, "")


def label_status(status_code: str | None) -> str:
    """Return a plain-language label for a validation status code.

    Args:
        status_code: A status code such as ``pending`` / ``passed`` /
            ``warnings`` / ``errors`` (case-insensitive).

    Returns:
        A short human-readable label. Unknown codes map to ``"Unknown status"``
        rather than raising, so a display path never breaks on new codes.
    """
    key = (status_code or "").strip().lower()
    return _STATUS_LABELS.get(key, "Unknown status")


# ── Numeric coercion helpers (Decimal-exact, never NaN / inf) ─────────────────


def _to_decimal(value: Any, *, field_name: str) -> Decimal:
    """Coerce any numeric-ish input to a finite ``Decimal``.

    Accepts int, float, and numeric strings (including a plain Decimal). A
    ``None``, a bool, a container, non-numeric text, or a non-finite value
    (``NaN`` / ``Infinity``) is a clean input error, so a caller never gets a
    ``NaN`` / ``inf`` back and no 500 escapes to the API.

    Raises:
        ValueError: If the value is missing or cannot be read as a finite
            number.
    """
    if value is None:
        raise ValueError(f"{field_name} is required (missing value)")
    # bool is an int subclass; True/False is almost certainly a mistake here.
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number, not a boolean")
    if isinstance(value, (Mapping, list, tuple, set)):
        raise ValueError(f"{field_name} must be a single number, not a container")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field_name} '{value}' is not a valid number") from exc
    if not dec.is_finite():
        raise ValueError(f"{field_name} must be finite (no NaN or Infinity)")
    return dec


def _non_negative(dec: Decimal, *, field_name: str) -> Decimal:
    """Return ``dec`` unchanged if it is >= 0, else raise ``ValueError``.

    Zero is allowed on purpose: a zero factor or rate is a well-defined,
    disabled line that contributes nothing, not an error. A negative value is
    never meaningful for a factor, quantity, rate, or percentage.
    """
    if dec < 0:
        raise ValueError(f"{field_name} cannot be negative (got {dec})")
    return dec


def _guard_finite(dec: Decimal, *, field_name: str) -> Decimal:
    """Reject a non-finite computed result, so overflow never leaks out."""
    if not dec.is_finite():
        raise ValueError(f"{field_name} overflowed to a non-finite value")
    return dec


def _normalise_currency(currency: str | None) -> str | None:
    """Normalise a currency code to trimmed upper-case, or ``None`` if absent.

    Currency is data, never assumed. An empty / whitespace string is treated
    as "no currency stated" rather than a distinct code.
    """
    if currency is None:
        return None
    text = str(currency).strip().upper()
    return text or None


# ── Component reading (accepts dicts or ComponentLine) ────────────────────────


@dataclass(frozen=True)
class ComponentLine:
    """A single priced component line, decoupled from the ORM.

    ``factor`` is the component factor (per one unit of the assembly),
    ``unit_rate`` is the price of one unit of the component, ``unit`` is the
    component's own unit of measure, and ``currency`` is the optional currency
    code the rate is expressed in. All numeric fields accept int / float /
    str / Decimal; coercion to Decimal happens inside the helpers.
    """

    factor: Any = 1
    unit_rate: Any = 0
    unit: str = ""
    currency: str | None = None
    description: str = ""


def _get(comp: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an object attribute, uniformly."""
    if isinstance(comp, Mapping):
        return comp.get(key, default)
    return getattr(comp, key, default)


def _read_rate(comp: Any) -> Any:
    """Read a component's unit rate, tolerating the module's field aliases.

    The module uses ``unit_cost`` on the ORM and ``unit_rate`` in several
    payloads; ``rate`` is also accepted. Returns ``None`` when no rate field is
    present so the caller can flag a missing rate cleanly.
    """
    for key in ("unit_rate", "unit_cost", "rate"):
        val = _get(comp, key, None)
        if val is not None:
            return val
    return None


# ── Pure rate helpers ─────────────────────────────────────────────────────────


def component_line_total(factor: Any, unit_rate: Any) -> Decimal:
    """Return one component's contribution: ``factor * unit_rate``, exact.

    A negative factor or rate is a clean input error. A zero factor or rate is
    a well-defined zero (a disabled or free line). A missing rate is an error.

    Raises:
        ValueError: On a missing, negative, non-numeric, or non-finite input.
    """
    f = _non_negative(_to_decimal(factor, field_name="factor"), field_name="factor")
    r = _non_negative(_to_decimal(unit_rate, field_name="unit_rate"), field_name="unit_rate")
    return _guard_finite(f * r, field_name="component line total")


def _normalise_lines(
    components: Iterable[Any],
    expected_currency: str | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Validate and normalise component lines into exact Decimal rows.

    Enforces a single currency across the whole set: if two components carry
    different currency codes (or one differs from ``expected_currency``), that
    is a clean ``ValueError`` rather than a meaningless mixed-currency sum.

    Returns:
        A tuple of ``(resolved_currency, rows)`` where each row is a dict with
        Decimal ``factor`` / ``unit_rate`` / ``line_total`` plus ``unit``,
        ``currency`` and ``description``.
    """
    currency = _normalise_currency(expected_currency)
    rows: list[dict[str, Any]] = []
    for idx, comp in enumerate(components):
        factor_raw = _get(comp, "factor", 1)
        rate_raw = _read_rate(comp)
        if rate_raw is None:
            raise ValueError(f"components[{idx}]: unit rate is required (missing value)")
        try:
            line_total = component_line_total(factor_raw, rate_raw)
        except ValueError as exc:
            raise ValueError(f"components[{idx}]: {exc}") from exc

        comp_ccy = _normalise_currency(_get(comp, "currency", None))
        if comp_ccy is not None:
            if currency is None:
                currency = comp_ccy
            elif comp_ccy != currency:
                raise ValueError(
                    f"cannot sum across currencies: {currency} and {comp_ccy} "
                    f"at components[{idx}] (convert to one currency first)"
                )

        rows.append(
            {
                "description": str(_get(comp, "description", "") or ""),
                "unit": str(_get(comp, "unit", "") or ""),
                "factor": _to_decimal(factor_raw, field_name="factor"),
                "unit_rate": _to_decimal(rate_raw, field_name="unit_rate"),
                "currency": comp_ccy,
                "line_total": line_total,
            }
        )
    # Backfill each row's currency with the single resolved currency so the
    # breakdown is self-describing even when only some lines stated a code.
    for row in rows:
        if row["currency"] is None:
            row["currency"] = currency
    return currency, rows


def composite_rate_from_components(
    components: Iterable[Any],
    *,
    expected_currency: str | None = None,
) -> Decimal:
    """Return the composite rate: the sum of every component's contribution.

    The composite rate is ``sum(factor * unit_rate)`` over all components, in a
    single currency. An empty component list is a well-defined ``Decimal("0")``
    (an assembly priced at zero until components are added), never an error.

    Args:
        components: Iterable of component dicts or ``ComponentLine`` objects.
        expected_currency: When given, every component with a stated currency
            must match it; otherwise the currency is inferred from the
            components and must be consistent across them.

    Raises:
        ValueError: On a missing / negative / non-numeric rate or factor, or on
            components that mix currency codes.
    """
    _currency, rows = _normalise_lines(components, expected_currency)
    total = Decimal("0")
    for row in rows:
        total += row["line_total"]
    return _guard_finite(total, field_name="composite rate")


def composite_rate_breakdown(
    components: Iterable[Any],
    *,
    expected_currency: str | None = None,
) -> list[dict[str, Any]]:
    """Return the per-component breakdown so a user can check the composite rate.

    Each row exposes the ``description``, ``unit``, ``factor``, ``unit_rate``,
    ``currency`` and the resulting ``line_total`` (all money as exact Decimal).
    The sum of the ``line_total`` values equals ``composite_rate_from_components``
    for the same input, which is what makes the composite rate explainable.
    """
    _currency, rows = _normalise_lines(components, expected_currency)
    return rows


def regional_adjusted_rate(
    base_rate: Any,
    regional_factor: Any = DEFAULT_REGIONAL_FACTOR,
) -> Decimal:
    """Return ``base_rate * regional_factor``, exact.

    The regional factor is data-driven; the documented worldwide default is
    ``1.0`` (``DEFAULT_REGIONAL_FACTOR``), which leaves the base rate unchanged.
    A negative base rate or factor is a clean input error.

    Raises:
        ValueError: On a missing / negative / non-numeric / non-finite input.
    """
    base = _non_negative(_to_decimal(base_rate, field_name="base_rate"), field_name="base_rate")
    factor = _non_negative(
        _to_decimal(regional_factor, field_name="regional_factor"),
        field_name="regional_factor",
    )
    return _guard_finite(base * factor, field_name="regional adjusted rate")


def apply_waste_uplift(rate: Any, waste_pct: Any = DEFAULT_WASTE_PCT) -> Decimal:
    """Return ``rate`` increased by a waste / overhead percentage, exact.

    ``waste_pct`` is a percentage (10 means +10 percent). The documented
    default is ``0`` (``DEFAULT_WASTE_PCT``), which returns the rate unchanged.
    A negative rate or percentage is a clean input error.

    Raises:
        ValueError: On a missing / negative / non-numeric / non-finite input.
    """
    base = _non_negative(_to_decimal(rate, field_name="rate"), field_name="rate")
    pct = _non_negative(_to_decimal(waste_pct, field_name="waste_pct"), field_name="waste_pct")
    factor = Decimal("1") + pct / Decimal("100")
    return _guard_finite(base * factor, field_name="rate with waste uplift")


def unit_rate_from_total(total: Any, quantity: Any) -> Decimal:
    """Return ``total / quantity``, guarding against division by zero.

    Useful when a lump-sum total must be spread over a quantity to get a per
    unit rate. A quantity of zero (or negative) is a clean input error rather
    than a division-by-zero crash.

    Raises:
        ValueError: If quantity is not strictly positive, or on non-finite
            inputs.
    """
    ttl = _non_negative(_to_decimal(total, field_name="total"), field_name="total")
    qty = _to_decimal(quantity, field_name="quantity")
    if qty <= 0:
        raise ValueError("quantity must be greater than zero to derive a unit rate")
    return _guard_finite(ttl / qty, field_name="unit rate")


def build_composite_rate(
    components: Iterable[Any],
    *,
    regional_factor: Any = DEFAULT_REGIONAL_FACTOR,
    waste_pct: Any = DEFAULT_WASTE_PCT,
    expected_currency: str | None = None,
) -> dict[str, Any]:
    """Build a fully explained composite rate for one unit of an assembly.

    This is the clear, worldwide-safe pipeline: add up the components into a
    subtotal, apply the regional factor (default 1.0, no adjustment), then add
    the waste / overhead uplift (default 0, no extra). Every step is exposed so
    a user, an auditor, or a validation rule can check the arithmetic.

    Returns:
        A dict with the resolved ``currency`` (may be ``None`` if no component
        stated one), the ``subtotal``, the ``regional_factor`` and
        ``regional_adjusted`` value, the ``waste_pct``, the final ``unit_rate``,
        and the per-component ``components`` breakdown. All money is Decimal.
    """
    currency, rows = _normalise_lines(components, expected_currency)
    subtotal = Decimal("0")
    for row in rows:
        subtotal += row["line_total"]
    subtotal = _guard_finite(subtotal, field_name="composite rate")

    regional = regional_adjusted_rate(subtotal, regional_factor)
    unit_rate = apply_waste_uplift(regional, waste_pct)

    return {
        "currency": currency,
        "subtotal": subtotal,
        "regional_factor": _to_decimal(regional_factor, field_name="regional_factor"),
        "regional_adjusted": regional,
        "waste_pct": _to_decimal(waste_pct, field_name="waste_pct"),
        "unit_rate": unit_rate,
        "components": rows,
    }
