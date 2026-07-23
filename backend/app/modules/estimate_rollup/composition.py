# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure estimate-rollup composition math (DB-free, float-free).

This module composes a project's full estimate headline number out of the three
figures that are tracked in separate estimating modules today and never roll up
on their own:

* the **BOQ base** - the measured works total the BOQ module already computes
  (its direct cost plus any BOQ-level markups), already converted to the project
  base currency;
* the **preliminaries** (general conditions) - a register that is priced and
  rolled up on its own and is added *on top* of the measured works;
* the **allowances / contingency** register - money carried in the estimate but
  not yet measured (provisional sums, prime-cost sums, design / construction
  contingency), also added on top.

  estimate_total = boq_base + preliminaries + allowances

Double-counting decisions (the whole point of this slice)
---------------------------------------------------------
* **BOQ base is taken as-is and nothing here re-derives it.** The BOQ grand
  total already contains its direct cost and its own markups; preliminaries and
  allowances are separate registers, so adding them on top cannot double-count
  what the BOQ already holds. (If a user modelled preliminaries or a contingency
  *as a BOQ markup* instead of using the dedicated module, that is a modelling
  duplication this read-side rollup cannot detect and does not try to.)
* **Allowances contribute their REMAINING amount, not the held amount.** An
  allowance firms up over time by drawing down against it; a drawdown is scope
  that has moved into the measured works. The allowances engine documents
  ``remaining`` (held minus drawn) as "the figure the estimate carries forward",
  so using remaining is exactly the anti-double-count choice: the drawn portion
  is assumed to already live in the BOQ. See
  :mod:`app.modules.allowances.allowance_math`.
* **Provisional / prime-cost sums are additive here** because in this platform
  they are held only in the allowances register, never materialised as BOQ
  positions. Nothing syncs an allowance into a BOQ line, so the register total is
  genuinely on top of the measured works.

Every figure is :class:`decimal.Decimal`, summed exactly and quantized to two
places half-up only at the boundary - never a float. Amounts already reduced to
the project base currency arrive here; the only currency work this module does is
the small :func:`_convert_to_base` used when folding the per-currency allowances
register, which mirrors the BOQ module's FX convention (``rate`` = base units per
one unit of the foreign currency; a missing rate leaves the amount in its own
units rather than silently converting at 1:1, so a forgotten rate degrades
visibly instead of dropping money).

No database, no ORM, no FastAPI - stdlib plus the two sibling *pure* engines
(:mod:`allowances.allowance_math`, :mod:`preliminaries.prelim_math`) - so the
whole composition unit-tests on a bare interpreter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.modules.allowances.allowance_math import (
    ALLOWANCE_CONTINGENCY,
    ALLOWANCE_PC_SUM,
    ALLOWANCE_PROVISIONAL_SUM,
    RegisterSummary,
)
from app.modules.preliminaries.prelim_math import PrelimRollup

# Money quantum - two decimal places, half-up (the accounting default shared by
# the BOQ, preliminaries and allowances engines).
_CENTS = Decimal("0.01")
_ZERO = Decimal("0")

# Stable machine keys for the component lines. A UI keys / translates off these,
# so the human ``label`` on each line is only a sensible English default.
LINE_BOQ_BASE = "boq_base"
LINE_PRELIMINARIES = "preliminaries"
LINE_ALLOWANCES = "allowances"
LINE_CONTINGENCY = "contingency"


def _q(amount: Decimal) -> Decimal:
    """Quantize a money amount to two decimal places, half-up."""
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _to_decimal(value: object, default: Decimal = _ZERO) -> Decimal:
    """Coerce an arbitrary value to a finite Decimal, degrading to ``default``."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else default
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default
    return parsed if parsed.is_finite() else default


def _convert_to_base(
    amount: Decimal,
    code: str,
    fx_map: dict[str, str] | None,
    base_currency: str,
) -> Decimal:
    """Convert one amount from currency ``code`` into the project base currency.

    Mirrors ``app.modules.boq.service._position_total_in_base`` so a multi-currency
    project composes the same way the BOQ rollup does: an amount in a non-base
    currency contributes ``amount * fx_rates_map[code]`` (base units per one unit
    of the foreign currency). A missing / non-positive rate leaves the amount in
    its own units - never zeroed and never converted at 1:1 - so a forgotten FX
    rate degrades visibly rather than silently dropping or inflating money.

    Args:
        amount: The amount to convert (Decimal, exact).
        code: The ISO currency the amount is denominated in.
        fx_map: ``{currency_code: rate_string}`` for the project.
        base_currency: The project base currency code.

    Returns:
        The amount expressed in the base currency (exact, not yet quantized).
    """
    ccy = (code or "").strip().upper()
    base = (base_currency or "").strip().upper()
    if ccy and ccy != base and fx_map:
        rate = fx_map.get(ccy)
        if rate:
            converted = _to_decimal(rate)
            if converted > 0:
                return amount * converted
    return amount


@dataclass(frozen=True)
class PreliminariesBreakdown:
    """The preliminaries contribution to the estimate, in the base currency.

    Attributes:
        total: The preliminaries grand total (adds to the estimate).
        fixed_total: The one-off (mobilisation / set-up / clean) portion.
        time_related_total: The duration-priced (site staff / standing plant)
            portion. ``fixed_total + time_related_total == total``.
        item_count: How many preliminaries lines were rolled up.
    """

    total: Decimal
    fixed_total: Decimal
    time_related_total: Decimal
    item_count: int


@dataclass(frozen=True)
class AllowancesBreakdown:
    """The allowances contribution to the estimate, in the base currency.

    Every figure is the REMAINING amount (held minus drawdowns), reduced to the
    project base currency. Contingency is broken out so it can be shown as its
    own line even though it is part of ``total``.

    Attributes:
        total: Remaining across every allowance type (adds to the estimate).
        provisional_sum_total: Remaining provisional sums.
        pc_sum_total: Remaining prime-cost sums.
        contingency_total: Remaining contingency (called out separately).
        provisional_and_pc_count: How many provisional / prime-cost (and any
            unknown-type) allowances back the non-contingency figure.
        contingency_count: How many contingency allowances back the figure.
        allowance_count: Total allowances across every currency and type.
        unconverted_currencies: Foreign currencies with no FX rate to the base;
            their amounts were summed in their own units (advisory, so a missing
            rate is visible rather than silent).
    """

    total: Decimal
    provisional_sum_total: Decimal
    pc_sum_total: Decimal
    contingency_total: Decimal
    provisional_and_pc_count: int
    contingency_count: int
    allowance_count: int
    unconverted_currencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RollupLine:
    """One component line of the composition, so a UI can render the sum.

    Attributes:
        key: Stable machine key (``boq_base`` / ``preliminaries`` / ``allowances``
            / ``contingency``); the i18n anchor for the label.
        label: Human-facing English default label.
        amount: The line's contribution (2 dp Decimal). The shown lines always
            sum exactly to :attr:`EstimateRollup.estimate_total`.
    """

    key: str
    label: str
    amount: Decimal


@dataclass(frozen=True)
class EstimateRollup:
    """The composed estimate headline number and its breakdown.

    Attributes:
        base_currency: The project base currency every amount is expressed in
            (``""`` when the project has no currency set).
        boq_base: The measured-works total (BOQ direct cost + BOQ markups).
        preliminaries: The preliminaries contribution.
        allowances: The allowances / contingency contribution.
        estimate_total: ``boq_base + preliminaries.total + allowances.total``.
        lines: The component lines, in display order, that sum to
            ``estimate_total``.
    """

    base_currency: str
    boq_base: Decimal
    preliminaries: PreliminariesBreakdown
    allowances: AllowancesBreakdown
    estimate_total: Decimal
    lines: tuple[RollupLine, ...] = field(default_factory=tuple)


def prelim_breakdown_from_rollup(rollup: PrelimRollup) -> PreliminariesBreakdown:
    """Project a :class:`PrelimRollup` onto the composition's breakdown.

    The preliminaries register has no currency column, so its lines are priced in
    the project base currency by convention (the estimate's own currency); no FX
    conversion is applied here.

    Args:
        rollup: The output of ``preliminaries.prelim_math.rollup_by_category``.

    Returns:
        The base-currency :class:`PreliminariesBreakdown`.
    """
    return PreliminariesBreakdown(
        total=_q(rollup.grand_total),
        fixed_total=_q(rollup.fixed_total),
        time_related_total=_q(rollup.time_related_total),
        item_count=rollup.item_count,
    )


def fold_allowances_to_base(
    register: RegisterSummary,
    fx_map: dict[str, str] | None,
    base_currency: str,
) -> AllowancesBreakdown:
    """Fold the per-currency allowances register into base-currency totals.

    Takes the register roll-up (held / drawn / remaining per currency and per
    type, produced by ``allowances.allowance_math.roll_up_register``) and reduces
    the REMAINING figures to the project base currency, bucketed by allowance
    type. Remaining - not held - is used deliberately (see the module docstring):
    the drawn portion is assumed to have firmed up into the measured works, so
    only the un-drawn remainder is still carried on top of the BOQ.

    Remaining may be negative when an allowance is over-drawn; that is preserved
    (advisory, never clamped), so an over-draw honestly reduces the carried
    figure rather than being hidden.

    Args:
        register: The allowances register summary (per currency, per type).
        fx_map: ``{currency_code: rate_string}`` for the project.
        base_currency: The project base currency code.

    Returns:
        The base-currency :class:`AllowancesBreakdown`.
    """
    base = (base_currency or "").strip().upper()

    total = _ZERO
    provisional = _ZERO
    pc = _ZERO
    contingency = _ZERO
    provisional_and_pc_count = 0
    contingency_count = 0
    unconverted: set[str] = set()

    for currency_row in register.by_currency:
        code = (currency_row.currency or "").strip().upper()
        # Flag a foreign currency that has no usable rate to the base: its
        # amounts fall through _convert_to_base unchanged (own units), which we
        # surface rather than pretend it converted.
        if code and code != base:
            rate = (fx_map or {}).get(code)
            if not rate or _to_decimal(rate) <= 0:
                unconverted.add(code)

        for type_row in currency_row.by_type:
            amount = _convert_to_base(type_row.remaining, code, fx_map, base)
            total += amount
            if type_row.allowance_type == ALLOWANCE_CONTINGENCY:
                contingency += amount
                contingency_count += type_row.count
            elif type_row.allowance_type == ALLOWANCE_PC_SUM:
                pc += amount
                provisional_and_pc_count += type_row.count
            elif type_row.allowance_type == ALLOWANCE_PROVISIONAL_SUM:
                provisional += amount
                provisional_and_pc_count += type_row.count
            else:
                # An unknown type is money carried but not measured, and it is
                # not a contingency, so it joins the provisional / PC bucket.
                provisional += amount
                provisional_and_pc_count += type_row.count

    return AllowancesBreakdown(
        total=_q(total),
        provisional_sum_total=_q(provisional),
        pc_sum_total=_q(pc),
        contingency_total=_q(contingency),
        provisional_and_pc_count=provisional_and_pc_count,
        contingency_count=contingency_count,
        allowance_count=register.allowance_count,
        unconverted_currencies=tuple(sorted(unconverted)),
    )


def compose_estimate_rollup(
    base_currency: str,
    boq_base: Decimal,
    preliminaries: PreliminariesBreakdown,
    allowances: AllowancesBreakdown,
) -> EstimateRollup:
    """Compose the estimate total from its three base-currency parts.

    ``estimate_total = boq_base + preliminaries.total + allowances.total`` - the
    deliberate sum (see the module docstring for the double-counting decisions).
    A component with no data contributes zero, so a project with only a BOQ
    returns the BOQ base as the total and a bare project returns zeros; this
    function never raises.

    The component ``lines`` are non-overlapping and always sum exactly to
    ``estimate_total``: contingency is split out of the allowances line so it can
    be shown on its own, and the two allowance lines together equal
    ``allowances.total``. A line is only emitted when its component is present
    (the BOQ base line is always emitted as the anchor), and an omitted component
    is always zero, so the invariant holds either way.

    Args:
        base_currency: The project base currency all parts are expressed in.
        boq_base: The measured-works total (already in the base currency).
        preliminaries: The preliminaries breakdown.
        allowances: The allowances breakdown.

    Returns:
        The composed :class:`EstimateRollup`.
    """
    base = (base_currency or "").strip().upper()
    boq_base_q = _q(boq_base)
    estimate_total = _q(boq_base_q + preliminaries.total + allowances.total)

    lines: list[RollupLine] = [RollupLine(LINE_BOQ_BASE, "BOQ base", boq_base_q)]
    if preliminaries.item_count > 0:
        lines.append(RollupLine(LINE_PRELIMINARIES, "Preliminaries", preliminaries.total))
    # Derive the two allowance lines from the together-rounded ``allowances.total``
    # so the emitted lines always reconcile to it (and thus to ``estimate_total``).
    # Contingency is shown at its own rounded value; the provisional / PC line takes
    # the remainder, absorbing any sub-cent FX-conversion residual so that
    # ``sum(lines) == estimate_total`` holds in every currency scenario. Rounding
    # each type separately (the earlier approach) could drift a cent apart from
    # ``allowances.total`` once foreign-currency remainders were converted to base.
    if allowances.provisional_and_pc_count > 0:
        provisional_and_pc = _q(allowances.total - allowances.contingency_total)
        lines.append(RollupLine(LINE_ALLOWANCES, "Provisional and prime-cost sums", provisional_and_pc))
    if allowances.contingency_count > 0:
        lines.append(RollupLine(LINE_CONTINGENCY, "Contingency", allowances.contingency_total))

    return EstimateRollup(
        base_currency=base,
        boq_base=boq_base_q,
        preliminaries=preliminaries,
        allowances=allowances,
        estimate_total=estimate_total,
        lines=tuple(lines),
    )


__all__ = [
    "LINE_ALLOWANCES",
    "LINE_BOQ_BASE",
    "LINE_CONTINGENCY",
    "LINE_PRELIMINARIES",
    "AllowancesBreakdown",
    "EstimateRollup",
    "PreliminariesBreakdown",
    "RollupLine",
    "compose_estimate_rollup",
    "fold_allowances_to_base",
    "prelim_breakdown_from_rollup",
]
