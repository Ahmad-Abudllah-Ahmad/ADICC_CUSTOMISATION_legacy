# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure apportioned back-charge math.

Responsibility for a back-charge is usually split across several parties - a
defect might be 60% the subcontractor's fault and 40% the designer's. The
single ``responsible_party`` on a :class:`~app.modules.cost_recovery.back_charge.BackChargeItem`
mis-models that normal case, so this engine takes a chargeable amount and a set
of party shares and splits the money across them.

The split obeys the same money discipline as the rest of the cost-recovery
engine: every per-party amount is :class:`decimal.Decimal` quantized to two
places with half-up rounding, and the apportioned amounts always sum back to
the original chargeable amount EXACTLY - the residual cent left by rounding is
absorbed by the largest share so nothing is lost or invented. Amounts in
different currency codes are never summed together; the per-party rollup is
scoped to a single currency and a party holding apportioned charges in two
currencies yields two rows, exactly as ``build_ledger`` does.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on
the local Python 3.11 runner like the other pure engines. A thin service layer
(written separately) gathers the records and feeds them in. The shares this
engine consumes are plain :class:`PartyShare` value objects, not ORM rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

# Re-use the same money primitives as the back-charge engine so apportioned
# amounts round identically to the per-item amounts they are derived from. These
# are duplicated as module-level constants (not imported) to keep this engine a
# self-contained pure module, but the values match back_charge.TWOPLACES exactly.

#: Two-decimal-place quantum for money rounding (matches back_charge.TWOPLACES).
TWOPLACES = Decimal("0.01")

#: Default tolerance for the "shares must sum to 1" check. Shares are stored to
#: four decimal places (NUMERIC(6,4)) so a handful of rows can drift by a few
#: ten-thousandths from an exact 1; anything larger is a data error, not noise.
DEFAULT_SHARE_TOLERANCE = Decimal("0.0001")

#: The unit total every share set must reconcile to: 100%.
WHOLE = Decimal("1")

#: Bucket label for a share with no responsible party recorded (mirrors
#: back_charge.UNASSIGNED so rollups bucket blank parties the same way).
UNASSIGNED = "unassigned"


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding.

    Identical behaviour to ``back_charge.quantize_money`` - kept local so this
    module imports nothing from the rest of the app.
    """
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_party(party: str) -> str:
    """Map a blank / whitespace party to :data:`UNASSIGNED`."""
    cleaned = (party or "").strip()
    return cleaned if cleaned else UNASSIGNED


@dataclass(frozen=True)
class PartyShare:
    """One party's share of responsibility for a back-charge.

    ``share_pct`` is a FRACTION in the inclusive range [0, 1] (0.6 means 60%),
    NOT a whole-number percentage. Within a single back-charge the shares are
    expected to sum to :data:`WHOLE` (1.0); :func:`distribute_chargeable`
    enforces that. ``party`` is the responsible party's name; a blank value is
    resolved to :data:`UNASSIGNED` at distribution time.
    """

    party: str
    share_pct: Decimal


@dataclass(frozen=True)
class ApportionedAmount:
    """The money assigned to one party by a split, in one currency."""

    party: str
    currency: str
    amount: Decimal


@dataclass(frozen=True)
class PartyApportionment:
    """Apportionment rollup for one responsible party in one currency."""

    party: str
    currency: str
    item_count: int
    amount_total: Decimal


def _normalise_shares(shares: Sequence[PartyShare]) -> list[PartyShare]:
    """Resolve blank parties and merge duplicate parties by summing shares.

    Two rows naming the same party are combined into one share so the split and
    the rollup agree on how many distinct parties there are. Order of first
    appearance is preserved so the result is deterministic.
    """
    order: list[str] = []
    summed: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for s in shares:
        party = _resolve_party(s.party)
        if party not in summed:
            order.append(party)
        summed[party] += s.share_pct
    return [PartyShare(party=p, share_pct=summed[p]) for p in order]


def validate_shares(
    shares: Sequence[PartyShare],
    *,
    tolerance: Decimal = DEFAULT_SHARE_TOLERANCE,
) -> None:
    """Raise :class:`ValueError` unless *shares* are a valid apportionment.

    A valid set is non-empty, has no negative share, and sums to :data:`WHOLE`
    (1.0) within *tolerance*. Raising rather than silently normalising is
    deliberate: a share set that does not add up to 100% almost always means the
    caller forgot a party or fat-fingered a percentage, and silently rescaling
    would hide a money-allocation error. Duplicate parties are summed before the
    check, so two 0.5 rows for the same party are treated as a single 1.0 share.
    """
    if not shares:
        raise ValueError("apportionment requires at least one party share")

    merged = _normalise_shares(shares)
    total = Decimal("0")
    for s in merged:
        if s.share_pct < Decimal("0"):
            raise ValueError(f"apportionment share for {s.party!r} is negative: {s.share_pct}")
        total += s.share_pct

    if abs(total - WHOLE) > tolerance:
        raise ValueError(f"apportionment shares must sum to 1.0 (100%); got {total} (tolerance {tolerance})")


def distribute_chargeable(
    chargeable_amount: Decimal,
    shares: Sequence[PartyShare],
    *,
    quantum: Decimal = TWOPLACES,
    tolerance: Decimal = DEFAULT_SHARE_TOLERANCE,
) -> list[tuple[str, Decimal]]:
    """Split *chargeable_amount* across *shares*, reconciling to the cent.

    Each party gets ``chargeable_amount * share_pct`` rounded half-up to
    *quantum* (two places by default). Half-up rounding of the individual shares
    can leave a residual of a cent or two versus the original total; that
    residual is added to the party with the LARGEST share so the returned
    amounts sum to *chargeable_amount* EXACTLY (after quantizing the input to the
    same quantum). This mirrors the "half-up quantize + remainder-to-largest"
    convention used across the cost-recovery engine.

    Shares are validated first (see :func:`validate_shares`) and a
    :class:`ValueError` is raised if they do not sum to 1.0 within *tolerance*.
    Duplicate parties are merged. The result preserves the parties' first-
    appearance order. Returns a list of ``(party, amount)`` tuples; the party
    names are resolved (blank -> :data:`UNASSIGNED`).

    A zero or negative *chargeable_amount* is split proportionally just the same
    (the remainder logic still reconciles the rounded parts to the total), which
    lets callers run reversals and credit notes through the same path.
    """
    validate_shares(shares, tolerance=tolerance)
    merged = _normalise_shares(shares)

    target = chargeable_amount.quantize(quantum, rounding=ROUND_HALF_UP)

    # Raw per-party amounts, quantized. Track the running sum so we can hand the
    # rounding residual to the largest share at the end.
    amounts: list[Decimal] = []
    running = Decimal("0")
    for s in merged:
        part = (chargeable_amount * s.share_pct).quantize(quantum, rounding=ROUND_HALF_UP)
        amounts.append(part)
        running += part

    residual = target - running
    if residual != Decimal("0"):
        # Index of the largest share; first-appearance order breaks ties so the
        # choice is deterministic regardless of input ordering.
        largest = 0
        for i in range(1, len(merged)):
            if merged[i].share_pct > merged[largest].share_pct:
                largest = i
        amounts[largest] = amounts[largest] + residual

    return [(merged[i].party, amounts[i]) for i in range(len(merged))]


def single_party_share(
    responsible_party: str,
    chargeable_pct: Decimal,
) -> list[PartyShare]:
    """Back-compat helper: one responsible party at 100% of the chargeable.

    Callers that have no apportionment carry a single ``responsible_party`` and
    a ``chargeable_pct`` that already scaled the gross down to the chargeable
    amount. Once the chargeable amount is computed, the WHOLE of it belongs to
    that one party, so this returns a single share of 1.0 - feeding it through
    :func:`distribute_chargeable` yields exactly the pre-apportionment behaviour
    (one party, the entire chargeable amount, no residual).

    ``chargeable_pct`` is accepted for signature symmetry with the per-item path
    and is intentionally NOT used to scale the share: the gross-to-chargeable
    scaling happens before distribution (in ``BackChargeItem.chargeable_amount``),
    and the share here describes how that already-chargeable amount divides
    across parties. With one party that division is the whole.
    """
    del chargeable_pct  # documented no-op; see docstring
    return [PartyShare(party=responsible_party, share_pct=WHOLE)]


def rollup_apportioned(
    items: Iterable[ApportionedAmount],
) -> tuple[PartyApportionment, ...]:
    """Group apportioned amounts per ``(party, currency)`` without blending.

    Mirrors ``build_ledger``'s grouping: a single party with apportioned charges
    in two currencies yields two rows, and money is never summed across currency
    codes. Rows are ordered by descending amount total, then party, then
    currency, so the heaviest exposure sorts first. Party names are resolved
    (blank -> :data:`UNASSIGNED`).
    """
    totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    counts: dict[tuple[str, str], int] = defaultdict(int)

    for it in items:
        key = (_resolve_party(it.party), it.currency)
        totals[key] += it.amount
        counts[key] += 1

    rows = tuple(
        PartyApportionment(
            party=party,
            currency=currency,
            item_count=counts[(party, currency)],
            amount_total=quantize_money(totals[(party, currency)]),
        )
        for (party, currency) in counts
    )
    return tuple(sorted(rows, key=lambda r: (-r.amount_total, r.party, r.currency)))


__all__ = [
    "DEFAULT_SHARE_TOLERANCE",
    "TWOPLACES",
    "UNASSIGNED",
    "WHOLE",
    "ApportionedAmount",
    "PartyApportionment",
    "PartyShare",
    "distribute_chargeable",
    "quantize_money",
    "rollup_apportioned",
    "single_party_share",
    "validate_shares",
]
