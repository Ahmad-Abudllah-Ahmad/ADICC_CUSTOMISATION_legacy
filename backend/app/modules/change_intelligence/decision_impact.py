# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure decision-time impact preview for a candidate change.

At the approval decision point a reviewer needs one number that the change
board does not give them: not "what will this change cost", but "what does
approving this change ADD on top of everything already committed". This engine
answers exactly that. It takes the set of changes that are already committed
(those whose status is in :data:`COMMITTED_STATUSES`) plus the one candidate
change being decided, and produces a before / after position per change-kind
and per currency: the currently committed cost and days, the candidate's signed
delta, and the resulting position if the candidate is approved.

Money discipline matches the rest of the change-intelligence and cost-recovery
engines. Every cost figure is a signed :class:`~decimal.Decimal` quantized to
two places with half-up rounding, and amounts in different currency codes are
NEVER summed together: a candidate priced in EUR against committed work in USD
yields two separate rows and two separate currency totals. Schedule impacts are
signed whole-or-fractional day counts summed as :class:`~decimal.Decimal`
(acceleration may be negative) and are likewise currency-scoped so the
before / after table reads as one coherent row per (kind, currency).

The committed-status vocabulary mirrors the change-intelligence service layer
(``_CO_APPROVED_STATUSES``), where a change order counts as committed once it is
``approved`` or ``executed``. It is duplicated here as the documented
:data:`COMMITTED_STATUSES` constant so this stays a self-contained pure module:
no database, no ORM, no ``app.*`` imports - stdlib plus ``Decimal`` only - and
it unit-tests on the local Python 3.11 runner exactly like the sibling engines.
A thin service layer gathers the committed change rows and the candidate and
feeds them in; this engine reads no clock and no I/O, so identical inputs always
produce an identical result.

Only committed items count toward the "current committed" baseline. A candidate
is the prospective change under decision and is always treated as a delta on top
of that baseline regardless of its own status - so a reviewer sees the same
preview whether the candidate is still a draft, pending, or has just been
provisionally marked. Statuses are compared case-insensitively after trimming
surrounding whitespace, matching how the service layer normalises them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- #
# Committed-status vocabulary.
#
# Mirrors app.modules.change_intelligence.service._CO_APPROVED_STATUSES: a change
# is "committed" - part of the baseline the candidate is measured against - once
# it has been approved or executed. Duplicated (not imported) so this module
# pulls in nothing heavy; the values match the service layer exactly. Compared
# case-insensitively after trimming, so callers can pass raw stored statuses.
# --------------------------------------------------------------------------- #

#: Change statuses that count as committed (part of the current baseline).
COMMITTED_STATUSES: frozenset[str] = frozenset({"approved", "executed"})

#: Two-decimal-place quantum for money rounding (mirrors the sibling engines).
TWOPLACES = Decimal("0.01")


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding.

    Identical behaviour to the cost-recovery and dispute-risk engines - kept
    local so this module imports nothing from the rest of the app.
    """
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def is_committed(status: str) -> bool:
    """Whether a change *status* counts as committed.

    The status is trimmed and lower-cased before the membership test, so the
    raw stored value (which may carry surrounding whitespace or mixed case) is
    accepted directly. A blank or unrecognised status is not committed.
    """
    return (status or "").strip().lower() in COMMITTED_STATUSES


@dataclass(frozen=True)
class ChangeImpact:
    """One change's cost and schedule impact, in a single currency.

    ``cost_impact`` is a signed :class:`~decimal.Decimal`: positive when the
    change adds cost, negative for a credit. ``schedule_impact_days`` is a
    signed :class:`~decimal.Decimal` day count (acceleration may be negative).
    ``currency`` is the ISO code the cost is expressed in; an empty string is
    its own bucket rather than an error, so an unpriced change is still
    surfaced. ``status`` is the raw change-status string; an item counts toward
    the committed baseline only when it is in :data:`COMMITTED_STATUSES` (see
    :func:`is_committed`). ``kind`` is the change-family kind token used to
    group the before / after rows.
    """

    kind: str
    currency: str
    cost_impact: Decimal
    schedule_impact_days: Decimal
    status: str


@dataclass(frozen=True)
class DecisionImpactRow:
    """Before / after position for one (kind, currency) at the decision point.

    All money figures are signed :class:`~decimal.Decimal` quantized to two
    places; day figures are signed :class:`~decimal.Decimal`. The ``resulting_``
    fields are ``current_committed_*`` plus ``candidate_*_delta``, i.e. the
    position if the candidate under decision is approved. When no committed work
    exists for this (kind, currency) the committed columns are zero and the
    resulting position equals the candidate delta; when there is committed work
    but no candidate delta the candidate columns are zero and the resulting
    position equals the current committed position.
    """

    kind: str
    currency: str
    current_committed_cost: Decimal
    candidate_cost_delta: Decimal
    resulting_cost: Decimal
    current_committed_days: Decimal
    candidate_days_delta: Decimal
    resulting_days: Decimal


@dataclass(frozen=True)
class CurrencyTotal:
    """All-kinds rollup of a decision-impact preview for a single currency.

    Sums the committed, candidate-delta and resulting positions across every
    kind that shares this currency. Money is never blended across currencies,
    so there is exactly one of these per distinct currency in the preview.
    """

    currency: str
    current_committed_cost: Decimal
    candidate_cost_delta: Decimal
    resulting_cost: Decimal
    current_committed_days: Decimal
    candidate_days_delta: Decimal
    resulting_days: Decimal


@dataclass(frozen=True)
class DecisionImpact:
    """The full decision-time preview: per (kind, currency) rows plus rollups.

    ``rows`` are ordered deterministically by ``(kind, currency)``.
    ``totals_by_currency`` is the all-kinds rollup per currency, ordered by
    ``currency``. With no committed work and a candidate carrying no cost or
    days the preview still surfaces the candidate's (kind, currency) as a row of
    zeros, so the reviewer always sees the line they are deciding on.
    """

    rows: tuple[DecisionImpactRow, ...]
    totals_by_currency: tuple[CurrencyTotal, ...]


# Internal accumulator key: a change is positioned within its (kind, currency)
# cell so currencies never blend and each kind reads as its own before / after
# row. A mutable triple [committed_cost, candidate_cost, ...] would be terser
# but a small dataclass keeps the summation readable and typo-proof.
@dataclass
class _Cell:
    committed_cost: Decimal = Decimal("0")
    candidate_cost: Decimal = Decimal("0")
    committed_days: Decimal = Decimal("0")
    candidate_days: Decimal = Decimal("0")


def _accumulate(
    committed: list[ChangeImpact],
    candidates: list[ChangeImpact],
) -> dict[tuple[str, str], _Cell]:
    """Fold committed items and candidate items into per-(kind, currency) cells.

    Committed items add to the committed columns only when their status is in
    :data:`COMMITTED_STATUSES`; a non-committed status passed in the committed
    list is ignored for the baseline (it is not part of what is already
    committed). Candidate items always add to the candidate-delta columns
    regardless of their own status - they are the prospective change being
    decided. Both sides are bucketed by (kind, currency) so nothing blends.
    """
    cells: dict[tuple[str, str], _Cell] = {}

    def cell_for(kind: str, currency: str) -> _Cell:
        key = (kind, currency)
        cell = cells.get(key)
        if cell is None:
            cell = _Cell()
            cells[key] = cell
        return cell

    for item in committed:
        if not is_committed(item.status):
            continue
        cell = cell_for(item.kind, item.currency)
        cell.committed_cost += item.cost_impact
        cell.committed_days += item.schedule_impact_days

    for item in candidates:
        cell = cell_for(item.kind, item.currency)
        cell.candidate_cost += item.cost_impact
        cell.candidate_days += item.schedule_impact_days

    return cells


def _build(cells: dict[tuple[str, str], _Cell]) -> DecisionImpact:
    """Turn accumulated cells into ordered rows and per-currency rollups."""
    rows: list[DecisionImpactRow] = []
    for kind, currency in sorted(cells):
        cell = cells[(kind, currency)]
        committed_cost = quantize_money(cell.committed_cost)
        candidate_cost = quantize_money(cell.candidate_cost)
        committed_days = cell.committed_days
        candidate_days = cell.candidate_days
        rows.append(
            DecisionImpactRow(
                kind=kind,
                currency=currency,
                current_committed_cost=committed_cost,
                candidate_cost_delta=candidate_cost,
                resulting_cost=quantize_money(committed_cost + candidate_cost),
                current_committed_days=committed_days,
                candidate_days_delta=candidate_days,
                resulting_days=committed_days + candidate_days,
            )
        )

    # Per-currency rollup over all kinds. Decimal sums stay exact; quantize the
    # money at the end. Days are summed as Decimal and left unrounded.
    cur_committed_cost: dict[str, Decimal] = {}
    cur_candidate_cost: dict[str, Decimal] = {}
    cur_committed_days: dict[str, Decimal] = {}
    cur_candidate_days: dict[str, Decimal] = {}
    for (kind, currency), cell in cells.items():
        cur_committed_cost[currency] = cur_committed_cost.get(currency, Decimal("0")) + cell.committed_cost
        cur_candidate_cost[currency] = cur_candidate_cost.get(currency, Decimal("0")) + cell.candidate_cost
        cur_committed_days[currency] = cur_committed_days.get(currency, Decimal("0")) + cell.committed_days
        cur_candidate_days[currency] = cur_candidate_days.get(currency, Decimal("0")) + cell.candidate_days

    totals: list[CurrencyTotal] = []
    for currency in sorted(cur_committed_cost):
        committed_cost = quantize_money(cur_committed_cost[currency])
        candidate_cost = quantize_money(cur_candidate_cost[currency])
        committed_days = cur_committed_days[currency]
        candidate_days = cur_candidate_days[currency]
        totals.append(
            CurrencyTotal(
                currency=currency,
                current_committed_cost=committed_cost,
                candidate_cost_delta=candidate_cost,
                resulting_cost=quantize_money(committed_cost + candidate_cost),
                current_committed_days=committed_days,
                candidate_days_delta=candidate_days,
                resulting_days=committed_days + candidate_days,
            )
        )

    return DecisionImpact(rows=tuple(rows), totals_by_currency=tuple(totals))


def project_with_pending(
    committed: list[ChangeImpact],
    candidate: ChangeImpact,
) -> DecisionImpact:
    """Preview the position if *candidate* is approved on top of *committed*.

    Only items in *committed* whose status is in :data:`COMMITTED_STATUSES`
    count toward the current-committed baseline; any non-committed item in that
    list is ignored (it is not yet part of what is committed). The *candidate*
    is the single prospective change being decided and is always applied as a
    signed delta on its own (kind, currency), regardless of its status. The
    result has one :class:`DecisionImpactRow` per (kind, currency) ordered by
    ``(kind, currency)`` and one :class:`CurrencyTotal` per currency.
    """
    return _build(_accumulate(committed, [candidate]))


def project_with_pending_many(
    committed: list[ChangeImpact],
    candidates: list[ChangeImpact],
) -> DecisionImpact:
    """Preview the position if every change in *candidates* is approved together.

    Like :func:`project_with_pending` but for a batch decision: the candidate
    deltas are summed per (kind, currency), so two candidates of the same kind
    and currency collapse into one row whose ``candidate_cost_delta`` /
    ``candidate_days_delta`` is their combined signed delta. The committed
    baseline is filtered by :data:`COMMITTED_STATUSES` exactly as in the single
    case. An empty *candidates* list yields a preview of the committed baseline
    alone (every candidate column zero); empty on both sides yields an empty
    preview.
    """
    return _build(_accumulate(committed, candidates))


__all__ = [
    "COMMITTED_STATUSES",
    "TWOPLACES",
    "ChangeImpact",
    "DecisionImpactRow",
    "CurrencyTotal",
    "DecisionImpact",
    "quantize_money",
    "is_committed",
    "project_with_pending",
    "project_with_pending_many",
]
