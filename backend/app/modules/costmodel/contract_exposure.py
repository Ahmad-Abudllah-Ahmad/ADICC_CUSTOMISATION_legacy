# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contract-exposure helpers for the 5D Cost Model.

Pure, database-free functions that turn budget-vs-committed figures into a
contract-exposure view. For each cost group they report how much of the budget
has already been committed to contracts (subcontracts, purchase orders, awarded
values), how much budget is still free to commit, the commitment ratio, and
whether the group is overcommitted (committed above budget). The per-group rows
roll up into a single project-level summary.

Design goals (kept deliberately clear and simple for a worldwide user):

- International by default. No hardcoded currency; money stays Decimal-exact end
  to end and is never coerced through binary float.
- Defensive. Every division is guarded: a zero, negative or absent budget yields
  a commitment ratio of None (undefined) rather than a crash, an infinity or a
  fabricated zero.
- Explainable. Committed equal to budget is fully committed but NOT
  overcommitted; only committed strictly above budget flags an overcommit.

These functions touch no session, no I/O and no global state, so they are safe
to call from the service layer or a test in isolation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_ZERO = Decimal("0")

# Commitment ratio precision. The ratio is a unitless committed/budget fraction
# (0.5 means half the budget is committed); six places is ample for a percentage
# read-out and keeps the value deterministic for tests.
_RATIO_PLACES = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    """Parse a money value to a finite Decimal, returning 0 on junk or non-finite.

    Accepts the Decimal-as-string figures the repository emits, plain numbers or
    an existing Decimal. Unparseable, NaN or infinite inputs collapse to 0 so a
    single dirty row can never poison the whole exposure view.

    Args:
        value: The raw value (Decimal, int, float, numeric string or None).

    Returns:
        A finite Decimal (0 when the input is missing or not a finite number).
    """
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value if value.is_finite() else _ZERO
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO
    return parsed if parsed.is_finite() else _ZERO


def commitment_ratio(committed: Decimal, budgeted: Decimal) -> Decimal | None:
    """Return committed / budgeted as an exact Decimal, or None when undefined.

    This is the single guarded division the whole module relies on - callers
    never divide by a budget themselves. The ratio is undefined (``None``) when
    ``budgeted`` is zero or negative: there is no positive baseline to measure
    commitment against, so a share cannot be expressed.

    Args:
        committed: The committed amount.
        budgeted: The budgeted amount (the denominator).

    Returns:
        The committed/budgeted ratio quantized to six places, or None when the
        budget is zero or negative.
    """
    if budgeted <= _ZERO:
        return None
    return (committed / budgeted).quantize(_RATIO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class GroupExposure:
    """Contract exposure for one cost group (committed vs budget)."""

    group: str
    budgeted: Decimal
    committed: Decimal
    remaining_to_commit: Decimal
    commitment_ratio: Decimal | None
    overcommitted: bool


@dataclass(frozen=True)
class ContractExposure:
    """Project-wide contract exposure rolled up from the per-group rows.

    The project ``overcommitted`` flag reflects the totals (total committed
    strictly above total budget), while ``overcommitted_group_count`` reports how
    many individual groups breach their own budget, so a project can be within
    budget overall yet still surface line-level overruns.
    """

    groups: list[GroupExposure] = field(default_factory=list)
    total_budgeted: Decimal = _ZERO
    total_committed: Decimal = _ZERO
    total_remaining_to_commit: Decimal = _ZERO
    total_commitment_ratio: Decimal | None = None
    overcommitted: bool = False
    overcommitted_group_count: int = 0


def compute_group_exposure(group: str, budgeted: object, committed: object) -> GroupExposure:
    """Build the contract-exposure row for a single cost group.

    Money is parsed defensively to Decimal (see :func:`_to_decimal`). Remaining
    to commit is ``budgeted - committed`` (it goes negative when overcommitted,
    which is the honest signal). The commitment ratio is guarded via
    :func:`commitment_ratio`. A group is overcommitted only when committed is
    strictly greater than budgeted - committed exactly equal to budgeted is fully
    committed but not an overrun.

    Args:
        group: The group label (for example a cost category).
        budgeted: The budgeted amount (Decimal-as-string or number).
        committed: The committed amount (Decimal-as-string or number).

    Returns:
        A :class:`GroupExposure` for the group.
    """
    budget_dec = _to_decimal(budgeted)
    committed_dec = _to_decimal(committed)
    return GroupExposure(
        group=group,
        budgeted=budget_dec,
        committed=committed_dec,
        remaining_to_commit=budget_dec - committed_dec,
        commitment_ratio=commitment_ratio(committed_dec, budget_dec),
        overcommitted=committed_dec > budget_dec,
    )


def compute_contract_exposure(groups: Iterable[tuple[str, object, object]]) -> ContractExposure:
    """Compute the full contract-exposure view from grouped budget/committed figures.

    Args:
        groups: An iterable of ``(group_label, budgeted, committed)`` triples, one
            per cost group. Order is preserved in the output rows.

    Returns:
        A :class:`ContractExposure` carrying the per-group rows and the
        project-level rollup. An empty input yields an empty, all-zero exposure
        with a ``None`` ratio.
    """
    rows = [compute_group_exposure(label, budgeted, committed) for label, budgeted, committed in groups]

    total_budgeted = sum((r.budgeted for r in rows), _ZERO)
    total_committed = sum((r.committed for r in rows), _ZERO)
    overcommitted_group_count = sum(1 for r in rows if r.overcommitted)

    return ContractExposure(
        groups=rows,
        total_budgeted=total_budgeted,
        total_committed=total_committed,
        total_remaining_to_commit=total_budgeted - total_committed,
        total_commitment_ratio=commitment_ratio(total_committed, total_budgeted),
        overcommitted=total_committed > total_budgeted,
        overcommitted_group_count=overcommitted_group_count,
    )
