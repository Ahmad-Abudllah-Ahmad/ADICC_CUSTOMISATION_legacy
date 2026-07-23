# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure recovery-total breakdown, provability and plain-language helpers.

A back-charge recovers a cost from the party responsible for causing it. In
practice the amount actually invoiced to that party is rarely the bare cost: a
contract often lets the recovering party add an administration or markup
percentage to cover its own handling, and it must subtract any credits already
given back (a credit note, a prior part-payment, an agreed offset). This module
builds that recovery total transparently, as

    recovery_total = base_cost + admin_fee - credits

and exposes every component (:class:`RecoveryBreakdown`) so the figure stands up
to dispute rather than arriving as one opaque number. ``admin_fee`` is itself
``base_cost * admin_pct``, so the whole total decomposes to primitives a
reviewer can re-add by hand.

It also ties a recovery back to its evidence: :func:`sum_recovery_lines` totals
the documented cost lines behind a back-charge (a labour sheet, a materials
invoice, a plant hire note) and :func:`lines_reconcile_to` proves that those
lines add up to the base cost that was claimed, so a recovered amount is always
traceable to the lines that justify it.

Finally it turns the module's status and traceability codes into plain language
that says what a state means and what to do next
(:func:`describe_status`, :func:`describe_band`), and states a back-charge in
one clear sentence (:func:`state_recovery`): what is being recovered, from whom,
and on what basis.

International by construction: no currency, tax rate, unit or locale is
hardcoded. The admin/markup percentage is a parameter with a documented default
of zero (:data:`DEFAULT_ADMIN_PCT`, so nothing is added unless a contract says
so), applicable in any country. Money is :class:`decimal.Decimal` throughout,
quantized to two places with half-up rounding, and amounts in different currency
codes are never summed together.

No database, no ORM - stdlib plus the module's own pure status / band vocabulary
(:mod:`app.modules.cost_recovery.back_charge` and
:mod:`app.modules.cost_recovery.recovery_analytics`, both stdlib-only) - so it
unit-tests on the local runner exactly like the other pure engines.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.cost_recovery.back_charge import (
    STATUS_AGREED,
    STATUS_DISPUTED,
    STATUS_PROPOSED,
    STATUS_RECOVERED,
    STATUS_WAIVED,
)
from app.modules.cost_recovery.recovery_analytics import (
    BAND_MODERATE,
    BAND_STRONG,
    BAND_WEAK,
    STATUS_ABSORBED,
    normalise_band,
)

#: Two-decimal-place quantum for money rounding (matches back_charge.TWOPLACES).
TWOPLACES = Decimal("0.01")

_ZERO = Decimal("0")

#: Default administration / markup percentage added to the base cost. Zero on
#: purpose: no country or contract is assumed, so nothing is added unless a
#: caller passes a percentage. A caller supplies the contractual figure (for
#: example Decimal("0.15") for 15%); the same math then serves any jurisdiction.
DEFAULT_ADMIN_PCT = Decimal("0")


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding.

    Identical behaviour to ``back_charge.quantize_money`` - kept local so this
    module imports no money helper from elsewhere in the app.
    """
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _require_finite(value: Decimal, name: str) -> None:
    """Raise :class:`ValueError` unless *value* is a finite Decimal.

    A NaN or infinite input would otherwise propagate into a total and surface
    as a nonsensical figure or a comparison that never settles. Rejecting it at
    the boundary keeps every returned amount a real, finite number.
    """
    if not value.is_finite():
        raise ValueError(f"{name} must be a finite amount; got {value}")


@dataclass(frozen=True)
class RecoveryLine:
    """One documented cost line behind a back-charge, in a single currency.

    A back-charge is justified by real cost evidence - a labour timesheet, a
    materials invoice, a plant hire note. Each :class:`RecoveryLine` is one such
    item: ``ref`` identifies the source document, ``description`` says what it
    is, ``amount`` is its cost (expected non-negative) and ``currency`` is the
    ISO code it is denominated in (blank when the caller tracks currency at the
    back-charge level). Summing the lines gives the base cost, which is what
    makes a recovered amount traceable to its evidence.
    """

    ref: str
    description: str
    amount: Decimal
    currency: str = ""


@dataclass(frozen=True)
class RecoveryBreakdown:
    """The recovery total decomposed into the parts a reviewer can re-add.

    ``recovery_total`` equals ``base_cost + admin_fee - credits_total``, floored
    at zero (credits exceeding cost plus fee mean the charge is fully credited,
    a well-defined zero rather than a negative recovery). ``admin_fee`` is
    ``base_cost * admin_pct`` quantized. Every field is a two-place Decimal in
    the one ``currency``; nothing here mixes currency codes. ``line_count`` is
    how many evidence lines the base cost was built from (0 when the base cost
    was supplied directly rather than derived from lines).
    """

    currency: str
    line_count: int
    base_cost: Decimal
    admin_pct: Decimal
    admin_fee: Decimal
    credits_total: Decimal
    recovery_total: Decimal


def sum_recovery_lines(lines: Iterable[RecoveryLine]) -> tuple[str, Decimal]:
    """Total the evidence lines behind a back-charge, in a single currency.

    Returns ``(currency, total)`` where *currency* is the common ISO code of the
    lines (blank when no line carried one) and *total* is the quantized sum. The
    total is the base cost a recovery is built on, so this is the anchor for
    provability: a recovered amount can always be traced back to these lines.

    Raises :class:`ValueError` on an empty line list (there is nothing to
    recover), on any negative line amount (a cost line is not a credit; model a
    credit with the ``credits`` argument of :func:`build_recovery_breakdown`
    instead), and on lines that mix currency codes (a recovery total is always
    single-currency). Blank currencies are permitted and do not conflict with a
    named one.
    """
    lines = list(lines)
    if not lines:
        raise ValueError("recovery has no evidence lines to total")

    currency = ""
    total = _ZERO
    for index, line in enumerate(lines):
        _require_finite(line.amount, f"evidence line {line.ref or index} amount")
        if line.amount < _ZERO:
            raise ValueError(
                f"evidence line {line.ref or index} has a negative amount: {line.amount}",
            )
        line_currency = (line.currency or "").strip()
        if line_currency:
            if currency and line_currency != currency:
                raise ValueError(
                    "evidence lines mix currency codes; a recovery total is single-currency",
                )
            currency = currency or line_currency
        total += line.amount

    return currency, quantize_money(total)


def build_recovery_breakdown(
    base_cost: Decimal,
    *,
    admin_pct: Decimal = DEFAULT_ADMIN_PCT,
    credits: Decimal = _ZERO,
    currency: str = "",
    line_count: int = 0,
) -> RecoveryBreakdown:
    """Build a transparent recovery total from a base cost, fee and credits.

    The total is ``base_cost + admin_fee - credits`` where
    ``admin_fee = base_cost * admin_pct``. Every component is returned on the
    :class:`RecoveryBreakdown` so the figure can be re-derived by hand and
    defended in a dispute.

    All three money inputs must be finite and non-negative; a negative base
    cost, admin percentage or credit is a data error and raises
    :class:`ValueError` with a plain message rather than producing a misleading
    total. ``admin_pct`` is a fraction (0.15 means 15%) and defaults to
    :data:`DEFAULT_ADMIN_PCT` (zero), so with no contractual fee the recovery
    total is simply the base cost net of credits. When credits exceed the cost
    plus fee the recovery total is floored at zero (fully credited), a defined
    value rather than a negative amount.
    """
    _require_finite(base_cost, "base cost")
    _require_finite(admin_pct, "admin percentage")
    _require_finite(credits, "credits")
    if base_cost < _ZERO:
        raise ValueError(f"base cost cannot be negative: {base_cost}")
    if admin_pct < _ZERO:
        raise ValueError(f"admin percentage cannot be negative: {admin_pct}")
    if credits < _ZERO:
        raise ValueError(f"credits cannot be negative: {credits}")

    base_q = quantize_money(base_cost)
    admin_fee = quantize_money(base_cost * admin_pct)
    credits_q = quantize_money(credits)

    total = base_q + admin_fee - credits_q
    if total < _ZERO:
        total = _ZERO

    return RecoveryBreakdown(
        currency=(currency or "").strip(),
        line_count=line_count,
        base_cost=base_q,
        admin_pct=admin_pct,
        admin_fee=admin_fee,
        credits_total=credits_q,
        recovery_total=quantize_money(total),
    )


def build_recovery_breakdown_from_lines(
    lines: Iterable[RecoveryLine],
    *,
    admin_pct: Decimal = DEFAULT_ADMIN_PCT,
    credits: Decimal = _ZERO,
) -> RecoveryBreakdown:
    """Build a recovery breakdown whose base cost is the sum of evidence lines.

    Convenience over :func:`sum_recovery_lines` + :func:`build_recovery_breakdown`
    that keeps the recovery total tied to the documented lines: the base cost is
    exactly what the evidence adds up to, the currency is carried from the lines,
    and ``line_count`` records how many lines back it. Every guard of the two
    underlying functions applies (empty list, negative amount, mixed currency,
    negative fee or credit).
    """
    lines = list(lines)
    currency, base_cost = sum_recovery_lines(lines)
    return build_recovery_breakdown(
        base_cost,
        admin_pct=admin_pct,
        credits=credits,
        currency=currency,
        line_count=len(lines),
    )


def lines_reconcile_to(
    base_cost: Decimal,
    lines: Iterable[RecoveryLine],
    *,
    tolerance: Decimal = TWOPLACES,
) -> bool:
    """Return whether *lines* sum to *base_cost* within *tolerance*.

    This is the provability check: it proves that a claimed base cost is backed
    by evidence lines that actually add up to it, so a recovered amount is not
    asserted but grounded. Returns ``True`` when the absolute difference is
    within *tolerance* (one cent by default). An empty line list never
    reconciles to a non-zero base cost. Propagates the currency / negative-line
    guards of :func:`sum_recovery_lines`.
    """
    lines = list(lines)
    if not lines:
        return quantize_money(base_cost) == _ZERO
    _, total = sum_recovery_lines(lines)
    return abs(total - quantize_money(base_cost)) <= tolerance


def cap_recovered(recovered: Decimal, recovery_total: Decimal) -> Decimal:
    """Clamp a recovered amount into ``[0, recovery_total]``, quantized.

    A recovered amount below zero is meaningless and a recovered amount above
    the recovery total is an over-recovery: neither should feed a rollup
    unclamped. This returns the defined, safe value (never a negative, never
    more than was recoverable) for callers that want a clean number. Callers
    that must reject an over-recovery as an error should use
    :func:`ensure_not_over_recovered` instead.
    """
    _require_finite(recovered, "recovered amount")
    _require_finite(recovery_total, "recovery total")
    ceiling = recovery_total if recovery_total > _ZERO else _ZERO
    if recovered < _ZERO:
        return quantize_money(_ZERO)
    if recovered > ceiling:
        return quantize_money(ceiling)
    return quantize_money(recovered)


def is_over_recovered(recovered: Decimal, recovery_total: Decimal) -> bool:
    """Return whether *recovered* exceeds *recovery_total* (an over-recovery)."""
    _require_finite(recovered, "recovered amount")
    _require_finite(recovery_total, "recovery total")
    return recovered > recovery_total


def ensure_not_over_recovered(recovered: Decimal, recovery_total: Decimal) -> Decimal:
    """Return *recovered* unchanged, or raise if it exceeds *recovery_total*.

    The strict counterpart to :func:`cap_recovered`, for callers that want an
    over-recovery surfaced as a clean input error rather than silently clamped.
    Raises :class:`ValueError` when more has been recovered than was ever
    recoverable, or when either input is negative or non-finite.
    """
    _require_finite(recovered, "recovered amount")
    _require_finite(recovery_total, "recovery total")
    if recovered < _ZERO:
        raise ValueError(f"recovered amount cannot be negative: {recovered}")
    if recovery_total < _ZERO:
        raise ValueError(f"recovery total cannot be negative: {recovery_total}")
    if recovered > recovery_total:
        raise ValueError(
            f"recovered {recovered} exceeds the recoverable total {recovery_total}",
        )
    return quantize_money(recovered)


def remaining_to_recover(recovery_total: Decimal, recovered: Decimal) -> Decimal:
    """Still-recoverable amount: recovery total minus recovered, floored at 0.

    An over-recovery (recovered beyond the total) yields zero rather than a
    negative remainder, mirroring ``BackChargeItem.outstanding``.
    """
    _require_finite(recovery_total, "recovery total")
    _require_finite(recovered, "recovered amount")
    remaining = quantize_money(recovery_total) - quantize_money(recovered)
    if remaining < _ZERO:
        remaining = _ZERO
    return quantize_money(remaining)


# --------------------------------------------------------------------------- #
# Plain-language helpers: turn status / band codes into a sentence that says
# what the state means and what to do next, in clear, country-neutral English.
# --------------------------------------------------------------------------- #

_STATUS_DESCRIPTIONS: dict[str, str] = {
    STATUS_PROPOSED: (
        "Proposed: recorded but not yet agreed with the party. "
        "Next, share the basis and evidence and seek their agreement."
    ),
    STATUS_AGREED: ("Agreed: the party has accepted the charge. Next, invoice it and record what is recovered."),
    STATUS_DISPUTED: ("Disputed: the party contests the charge. Next, add evidence or negotiate a settlement."),
    STATUS_RECOVERED: ("Recovered: the charge has been collected in full. No further action is needed."),
    STATUS_WAIVED: ("Waived: the charge was written off and will not be pursued. No further action is needed."),
    STATUS_ABSORBED: (
        "Absorbed: the project accepted the cost itself instead of recovering it. No further action is needed."
    ),
}


def describe_status(status: str) -> str:
    """Return a plain-language description of a back-charge *status*.

    Each recognised status maps to one sentence saying what the state means and
    what to do next, so a user never has to decode a bare code word. An
    unrecognised status returns a message naming the valid statuses instead of
    failing, so the helper is always safe to call on stored data.
    """
    cleaned = (status or "").strip().lower()
    described = _STATUS_DESCRIPTIONS.get(cleaned)
    if described is not None:
        return described
    valid = ", ".join(sorted(_STATUS_DESCRIPTIONS))
    shown = status if status else "(blank)"
    return f"Unknown status {shown!r}. Set it to one of: {valid}."


_BAND_DESCRIPTIONS: dict[str, str] = {
    BAND_STRONG: (
        "Strong evidence: the responsible owner is clearly traceable, "
        "so this charge should stand up if it is challenged."
    ),
    BAND_MODERATE: (
        "Moderate evidence: the owner is only partly traceable. Strengthen the record before relying on recovery."
    ),
    BAND_WEAK: (
        "Weak evidence: the owner is hard to trace, so recovery is at risk. Add a timely notice or supporting records."
    ),
}


def describe_band(band: str) -> str:
    """Return a plain-language description of a traceability *band*.

    The band is normalised first (a blank or unrecognised value is treated as
    the most conservative ``weak``, matching the recovery-analytics engine), so
    this always returns one of the three evidence-strength sentences and never
    fails on junk input.
    """
    return _BAND_DESCRIPTIONS[normalise_band(band)]


def state_recovery(
    *,
    amount: Decimal | str,
    currency: str,
    party: str,
    description: str,
    basis: str = "",
) -> str:
    """State a back-charge in one clear sentence: what, from whom, on what basis.

    Produces a line a reviewer can read at a glance, for example
    ``"Recovering 1150.00 EUR from Subcontractor A for rework of a defective
    slab, on the basis of contract clause 12.3."`` A blank party reads as
    "an unassigned party" and a blank description as "an unspecified cost", so
    the sentence is always well formed. The currency is appended only when
    given, so no currency is ever invented.
    """
    who = (party or "").strip() or "an unassigned party"
    what = (description or "").strip() or "an unspecified cost"
    currency = (currency or "").strip()
    money = f"{amount} {currency}".strip() if currency else str(amount).strip()
    sentence = f"Recovering {money} from {who} for {what}"
    grounded = (basis or "").strip()
    if grounded:
        sentence = f"{sentence}, on the basis of {grounded}"
    return f"{sentence}."


__all__ = [
    "DEFAULT_ADMIN_PCT",
    "TWOPLACES",
    "RecoveryBreakdown",
    "RecoveryLine",
    "build_recovery_breakdown",
    "build_recovery_breakdown_from_lines",
    "cap_recovered",
    "describe_band",
    "describe_status",
    "ensure_not_over_recovered",
    "is_over_recovered",
    "lines_reconcile_to",
    "quantize_money",
    "remaining_to_recover",
    "state_recovery",
    "sum_recovery_lines",
]
