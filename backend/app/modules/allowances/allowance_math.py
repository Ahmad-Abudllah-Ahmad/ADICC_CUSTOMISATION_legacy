# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure allowances / contingency register math (DB-free, float-free).

An allowance is money carried in the estimate but not yet measured: a
provisional sum, a prime-cost (PC) sum, or a design / construction contingency.
Each allowance holds a fixed amount, and scope firms up over time by drawing
down against it. This engine answers the two questions the register asks:

* how much is left on one allowance -- :func:`remaining` (held minus the sum of
  its drawdowns);
* what does the whole register total to -- :func:`roll_up_register`, which sums
  held, drawn and remaining per currency and, within each currency, by allowance
  type, so the estimate can carry the remaining figure forward.

Money discipline (identical to the CVR and value engines)
---------------------------------------------------------
Every figure is :class:`decimal.Decimal`, summed exactly and quantized to two
places half-up only at the boundary. Amounts in different currency codes are
NEVER summed together: the roll-up returns one :class:`CurrencyRollup` per
currency, so a register spanning two currencies yields two rows and the caller
never sees a blended total.

Over-draw is advisory, not fatal
--------------------------------
Drawing more than an allowance holds is a real situation (a provisional sum that
turned out too small): the engine reports it as an ``overdrawn`` flag and lets
``remaining`` go negative, rather than raising or clamping. The service treats it
as a warning for the estimator, never a hard error that blocks the entry.

No database, no ORM, no ``app.*`` imports -- stdlib plus :class:`decimal.Decimal`
only -- so it unit-tests on the local runner exactly like the CVR and value
engines. A thin service layer maps ORM rows onto :class:`AllowanceLine` and calls
in here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# Money quantum + the canonical allowance types. The type order is the order the
# register presents its sections in; it is exposed so a service or test can rely
# on it.
# --------------------------------------------------------------------------- #

#: Two-decimal-place quantum for money rounding (matches the CVR engine's q2).
TWOPLACES = Decimal("0.01")

_ZERO = Decimal("0")

#: A provisional sum: budgeted work not yet designed or priced.
ALLOWANCE_PROVISIONAL_SUM = "provisional_sum"
#: A prime-cost (PC) sum: a supply allowance for goods chosen later.
ALLOWANCE_PC_SUM = "pc_sum"
#: A design / construction contingency held against the unknown.
ALLOWANCE_CONTINGENCY = "contingency"

#: The allowance types in register-presentation order.
ALLOWANCE_TYPES: tuple[str, ...] = (
    ALLOWANCE_PROVISIONAL_SUM,
    ALLOWANCE_PC_SUM,
    ALLOWANCE_CONTINGENCY,
)

#: Rank of each type for stable ordering. Unknown types sort after known ones.
_TYPE_ORDER: dict[str, int] = {label: i for i, label in enumerate(ALLOWANCE_TYPES)}


def to_decimal(value: object, default: Decimal = _ZERO) -> Decimal:
    """Coerce *value* to :class:`Decimal`, returning *default* on any bad input.

    Accepts a ``Decimal`` untouched and promotes strings / ints / floats through
    :class:`str` so a binary float never pollutes the value. ``None`` and any
    unparseable input collapse to *default* (zero) rather than raising, so a
    stray blank in the register can never crash the roll-up.
    """
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding."""
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def total_drawn(drawdowns: Iterable[object]) -> Decimal:
    """Sum an allowance's *drawdowns* exactly, quantized to two places.

    Each item is coerced with :func:`to_decimal`, so an iterable of Decimals,
    numeric strings or drawdown amounts all work. An empty iterable totals to
    ``0.00``.
    """
    running = _ZERO
    for amount in drawdowns:
        running += to_decimal(amount)
    return quantize_money(running)


def remaining(held: object, drawdowns: Iterable[object]) -> Decimal:
    """Return what is left on one allowance: *held* minus the sum of *drawdowns*.

    Both sides are summed exactly before the single half-up quantize, so money
    rounding never drifts. The result MAY be negative: an allowance drawn beyond
    what it holds reports a negative remaining (an over-draw), which the caller
    surfaces as an advisory flag rather than clamping to zero.
    """
    held_dec = to_decimal(held)
    drawn = _ZERO
    for amount in drawdowns:
        drawn += to_decimal(amount)
    return quantize_money(held_dec - drawn)


def is_overdrawn(held: object, drawn: object) -> bool:
    """True when the amount *drawn* exceeds the amount *held* (advisory only)."""
    return to_decimal(drawn) > to_decimal(held)


# --------------------------------------------------------------------------- #
# Input value object. The service maps one ORM allowance (plus its drawdown
# amounts) onto this; the engine never imports the ORM.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AllowanceLine:
    """One allowance and its drawdowns, ready for the register roll-up.

    ``allowance_type`` is one of :data:`ALLOWANCE_TYPES` (an unknown value still
    rolls up, sorted after the known types). ``currency`` is the ISO 4217 code
    the ``held`` amount is denominated in; it scopes the roll-up so amounts in
    different currencies are never summed together. ``held`` is the amount
    carried, and ``drawdowns`` are the individual amounts drawn against it (empty
    when nothing has been spent yet). All money is :class:`Decimal`.
    """

    allowance_type: str
    currency: str
    held: Decimal
    drawdowns: tuple[Decimal, ...] = ()


# --------------------------------------------------------------------------- #
# Output value objects.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TypeRollup:
    """The held / drawn / remaining position of one allowance type in one currency.

    ``remaining`` is ``held - drawn`` and may be negative when the type is
    over-drawn; ``overdrawn`` records that condition as an advisory flag.
    ``count`` is how many allowances of this type back the figures.
    """

    allowance_type: str
    held: Decimal
    drawn: Decimal
    remaining: Decimal
    count: int
    overdrawn: bool


@dataclass(frozen=True)
class CurrencyRollup:
    """The whole register's position in a single currency (never blended).

    ``held`` / ``drawn`` / ``remaining`` are the currency totals; ``remaining``
    is the figure the estimate carries forward. ``by_type`` breaks the same
    totals down by allowance type in :data:`ALLOWANCE_TYPES` order. ``overdrawn``
    is true when the currency's total drawn exceeds its total held.
    """

    currency: str
    held: Decimal
    drawn: Decimal
    remaining: Decimal
    count: int
    overdrawn: bool
    by_type: tuple[TypeRollup, ...]


@dataclass(frozen=True)
class RegisterSummary:
    """The composed allowances register: one :class:`CurrencyRollup` per currency.

    ``by_currency`` is ordered by descending held then currency code, so the
    heaviest allowance pot leads and ties are stable. ``primary_currency`` is the
    currency carrying the most held (``""`` when the register is empty).
    ``allowance_count`` is the total number of allowances across every currency.
    """

    by_currency: tuple[CurrencyRollup, ...]
    primary_currency: str
    allowance_count: int


# --------------------------------------------------------------------------- #
# Internal accumulators (mutable; Decimal sums stay exact until the boundary).
# --------------------------------------------------------------------------- #


@dataclass
class _TypeAcc:
    """Held / drawn accumulator for one allowance type."""

    count: int = 0
    held: Decimal = field(default_factory=lambda: Decimal("0"))
    drawn: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class _CurrencyAcc:
    """Held / drawn accumulator for one currency, split by allowance type."""

    count: int = 0
    held: Decimal = field(default_factory=lambda: Decimal("0"))
    drawn: Decimal = field(default_factory=lambda: Decimal("0"))
    by_type: dict[str, _TypeAcc] = field(default_factory=dict)


def _type_sort_key(allowance_type: str) -> tuple[int, str]:
    """Sort key placing known types in canonical order, unknowns last by name."""
    return (_TYPE_ORDER.get(allowance_type, len(ALLOWANCE_TYPES)), allowance_type)


def roll_up_register(lines: Sequence[AllowanceLine]) -> RegisterSummary:
    """Roll a set of allowances up into a per-currency, per-type register summary.

    Sums held and each allowance's drawn (the exact sum of its drawdowns) into
    per-currency and per-type accumulators, then quantizes at the boundary so
    money rounding never drifts. Currencies are NEVER blended: each currency gets
    its own :class:`CurrencyRollup`. Within a currency the types are ordered by
    :data:`ALLOWANCE_TYPES`; the currencies are ordered by descending held then
    code. Over-draw (drawn beyond held) is reported via the ``overdrawn`` flag and
    left in the negative ``remaining``, never clamped. Pure and deterministic:
    identical input always yields an identical summary. An empty input yields an
    empty summary (no currencies, ``""`` primary, zero count).
    """
    currencies: dict[str, _CurrencyAcc] = defaultdict(_CurrencyAcc)

    for line in lines:
        held = to_decimal(line.held)
        drawn = _ZERO
        for amount in line.drawdowns:
            drawn += to_decimal(amount)

        acc = currencies[line.currency]
        acc.count += 1
        acc.held += held
        acc.drawn += drawn

        type_acc = acc.by_type.get(line.allowance_type)
        if type_acc is None:
            type_acc = _TypeAcc()
            acc.by_type[line.allowance_type] = type_acc
        type_acc.count += 1
        type_acc.held += held
        type_acc.drawn += drawn

    rows: list[CurrencyRollup] = []
    for currency, acc in currencies.items():
        by_type = tuple(
            TypeRollup(
                allowance_type=allowance_type,
                held=quantize_money(type_acc.held),
                drawn=quantize_money(type_acc.drawn),
                remaining=quantize_money(type_acc.held - type_acc.drawn),
                count=type_acc.count,
                overdrawn=type_acc.drawn > type_acc.held,
            )
            for allowance_type, type_acc in sorted(
                acc.by_type.items(),
                key=lambda item: _type_sort_key(item[0]),
            )
        )
        rows.append(
            CurrencyRollup(
                currency=currency,
                held=quantize_money(acc.held),
                drawn=quantize_money(acc.drawn),
                remaining=quantize_money(acc.held - acc.drawn),
                count=acc.count,
                overdrawn=acc.drawn > acc.held,
                by_type=by_type,
            )
        )

    # Heaviest pot first; ties broken by currency code for a stable order. The
    # sort key uses the exact-summed held via the already-quantized row value.
    rows.sort(key=lambda r: (-r.held, r.currency))
    primary_currency = rows[0].currency if rows else ""
    allowance_count = sum(r.count for r in rows)

    return RegisterSummary(
        by_currency=tuple(rows),
        primary_currency=primary_currency,
        allowance_count=allowance_count,
    )


__all__ = [
    "TWOPLACES",
    "ALLOWANCE_PROVISIONAL_SUM",
    "ALLOWANCE_PC_SUM",
    "ALLOWANCE_CONTINGENCY",
    "ALLOWANCE_TYPES",
    "to_decimal",
    "quantize_money",
    "total_drawn",
    "remaining",
    "is_overdrawn",
    "AllowanceLine",
    "TypeRollup",
    "CurrencyRollup",
    "RegisterSummary",
    "roll_up_register",
]
