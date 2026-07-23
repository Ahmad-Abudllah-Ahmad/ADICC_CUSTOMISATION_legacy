# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure back-charge / cost-recovery math.

A back-charge is a cost the project intends to recover from the party held
responsible for causing it - for example rework arising from a subcontractor's
defect, or extra cost from a supplier's delay. Given the current state of every
back-charge record (a :class:`BackChargeItem`) this engine computes the
chargeable amount for each item, what remains outstanding, and rolls the items
up two ways: per responsible party (split by currency) and per currency. The
result is a :class:`RecoveryLedger` that tells the commercial team how much is
recoverable, how much has been recovered, and what is still outstanding against
whom.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on
the local Python 3.11 runner exactly like the other pure engines. A thin
service layer (written separately) gathers the records and feeds them in.

Money is always :class:`decimal.Decimal`, quantized to two places with
half-up rounding. Amounts denominated in different currency codes are never
summed together; every rollup that carries money is scoped to a single
currency, and a party holding back-charges in two currencies yields two party
rows.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

# Status strings for a back-charge record's commercial state.
STATUS_PROPOSED = "proposed"
STATUS_AGREED = "agreed"
STATUS_DISPUTED = "disputed"
STATUS_RECOVERED = "recovered"
STATUS_WAIVED = "waived"

#: Statuses for a back-charge that is still live and may yet be recovered.
OPEN_STATUSES = frozenset({STATUS_PROPOSED, STATUS_AGREED, STATUS_DISPUTED})

#: Statuses for a back-charge that is settled, whether collected or written off.
CLOSED_STATUSES = frozenset({STATUS_RECOVERED, STATUS_WAIVED})

#: Bucket label for a back-charge with no responsible party recorded.
UNASSIGNED = "unassigned"

#: Two-decimal-place quantum for money rounding.
TWOPLACES = Decimal("0.01")


def clamp_pct(pct: Decimal) -> Decimal:
    """Clamp a chargeable percentage into the inclusive range [0, 1].

    A chargeable percentage is the share of the gross cost the project judges
    recoverable from the responsible party. Values outside the unit range are
    nonsensical for a proportion, so they are clamped rather than trusted.
    """
    if pct < Decimal("0"):
        return Decimal("0")
    if pct > Decimal("1"):
        return Decimal("1")
    return pct


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding."""
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_party(responsible_party: str) -> str:
    """Map a blank / whitespace responsible party to :data:`UNASSIGNED`."""
    party = (responsible_party or "").strip()
    return party if party else UNASSIGNED


@dataclass(frozen=True)
class BackChargeItem:
    """Present-state projection of one back-charge record for the engine.

    ``gross_amount`` is the full cost incurred; ``chargeable_pct`` is the share
    of it (0 to 1) the project judges recoverable from ``responsible_party``;
    ``recovered_amount`` is how much has actually been collected so far. A
    blank ``responsible_party`` is resolved to :data:`UNASSIGNED` at grouping
    time (the item itself is left untouched).
    """

    ref_id: str
    responsible_party: str
    description: str
    basis: str
    gross_amount: Decimal
    chargeable_pct: Decimal
    currency: str
    status: str
    recovered_amount: Decimal = Decimal("0")

    @property
    def is_open(self) -> bool:
        """True when the back-charge is not yet settled (recovered / waived)."""
        return self.status not in CLOSED_STATUSES

    @property
    def chargeable_amount(self) -> Decimal:
        """Gross cost times the clamped chargeable percentage, quantized."""
        return quantize_money(self.gross_amount * clamp_pct(self.chargeable_pct))

    @property
    def outstanding(self) -> Decimal:
        """Still-recoverable amount: chargeable minus recovered, floored at 0.

        A closed (recovered or waived) item has nothing outstanding regardless
        of the recorded amounts. An over-recovery (recovered exceeding the
        chargeable amount) clamps to zero rather than going negative.
        """
        if not self.is_open:
            return quantize_money(Decimal("0"))
        remaining = self.chargeable_amount - self.recovered_amount
        if remaining < Decimal("0"):
            remaining = Decimal("0")
        return quantize_money(remaining)


@dataclass(frozen=True)
class PartyRecovery:
    """Back-charge rollup for one responsible party in one currency."""

    party: str
    currency: str
    item_count: int
    open_count: int
    gross_total: Decimal
    chargeable_total: Decimal
    recovered_total: Decimal
    outstanding_total: Decimal


@dataclass(frozen=True)
class CurrencyRecovery:
    """Back-charge rollup for one currency across all parties."""

    currency: str
    item_count: int
    chargeable_total: Decimal
    recovered_total: Decimal
    outstanding_total: Decimal


@dataclass(frozen=True)
class RecoveryLedger:
    """The project's back-charge position: per-party and per-currency rollups.

    ``primary_currency`` is the currency carrying the greatest chargeable
    total (ties broken alphabetically), and ``primary_outstanding`` is that
    currency's outstanding total - a single headline figure that never mixes
    currencies. Empty input yields an empty currency and a zero headline.
    """

    item_count: int
    open_count: int
    primary_currency: str
    primary_outstanding: Decimal
    by_party: tuple[PartyRecovery, ...] = field(default_factory=tuple)
    by_currency: tuple[CurrencyRecovery, ...] = field(default_factory=tuple)


def build_ledger(items: Iterable[BackChargeItem]) -> RecoveryLedger:
    """Roll a set of back-charge items into a :class:`RecoveryLedger`.

    Per-party rows are grouped by ``(resolved_party, currency)`` so a single
    party holding back-charges in two currencies yields two rows and money is
    never summed across currency codes. Per-currency rows group by currency
    alone. ``open_count`` counts items whose :attr:`BackChargeItem.is_open` is
    true. Party rows are ordered by descending outstanding total, then party,
    then currency; currency rows by descending chargeable total, then currency.
    """
    items = list(items)

    # Accumulators keyed by group. Decimal sums stay exact; quantize at the end.
    party_gross: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    party_chargeable: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    party_recovered: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    party_outstanding: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    party_items: dict[tuple[str, str], int] = defaultdict(int)
    party_open: dict[tuple[str, str], int] = defaultdict(int)

    cur_chargeable: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    cur_recovered: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    cur_outstanding: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    cur_items: dict[str, int] = defaultdict(int)

    open_count = 0

    for it in items:
        party = _resolve_party(it.responsible_party)
        currency = it.currency
        key = (party, currency)

        chargeable = it.chargeable_amount
        # Recovered is only meaningful up to the chargeable amount; mirror the
        # outstanding clamp so per-party recovered never exceeds chargeable.
        recovered = it.recovered_amount
        if recovered < Decimal("0"):
            recovered = Decimal("0")
        if recovered > chargeable:
            recovered = chargeable
        outstanding = it.outstanding
        is_open = it.is_open
        if is_open:
            open_count += 1

        party_gross[key] += it.gross_amount
        party_chargeable[key] += chargeable
        party_recovered[key] += recovered
        party_outstanding[key] += outstanding
        party_items[key] += 1
        if is_open:
            party_open[key] += 1

        cur_chargeable[currency] += chargeable
        cur_recovered[currency] += recovered
        cur_outstanding[currency] += outstanding
        cur_items[currency] += 1

    by_party = tuple(
        PartyRecovery(
            party=party,
            currency=currency,
            item_count=party_items[(party, currency)],
            open_count=party_open[(party, currency)],
            gross_total=quantize_money(party_gross[(party, currency)]),
            chargeable_total=quantize_money(party_chargeable[(party, currency)]),
            recovered_total=quantize_money(party_recovered[(party, currency)]),
            outstanding_total=quantize_money(party_outstanding[(party, currency)]),
        )
        for (party, currency) in party_items
    )

    by_currency = tuple(
        CurrencyRecovery(
            currency=currency,
            item_count=cur_items[currency],
            chargeable_total=quantize_money(cur_chargeable[currency]),
            recovered_total=quantize_money(cur_recovered[currency]),
            outstanding_total=quantize_money(cur_outstanding[currency]),
        )
        for currency in cur_items
    )

    by_party = tuple(sorted(by_party, key=lambda r: (-r.outstanding_total, r.party, r.currency)))
    by_currency = tuple(sorted(by_currency, key=lambda r: (-r.chargeable_total, r.currency)))

    # Headline currency: greatest chargeable total, alphabetical tie-break.
    if by_currency:
        primary = min(by_currency, key=lambda r: (-r.chargeable_total, r.currency))
        primary_currency = primary.currency
        primary_outstanding = primary.outstanding_total
    else:
        primary_currency = ""
        primary_outstanding = quantize_money(Decimal("0"))

    return RecoveryLedger(
        item_count=len(items),
        open_count=open_count,
        primary_currency=primary_currency,
        primary_outstanding=primary_outstanding,
        by_party=by_party,
        by_currency=by_currency,
    )


__all__ = [
    "CLOSED_STATUSES",
    "OPEN_STATUSES",
    "STATUS_AGREED",
    "STATUS_DISPUTED",
    "STATUS_PROPOSED",
    "STATUS_RECOVERED",
    "STATUS_WAIVED",
    "TWOPLACES",
    "UNASSIGNED",
    "BackChargeItem",
    "CurrencyRecovery",
    "PartyRecovery",
    "RecoveryLedger",
    "build_ledger",
    "clamp_pct",
    "quantize_money",
]
