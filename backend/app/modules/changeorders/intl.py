# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, review-ready helpers for change orders.

These are pure functions with no database, network, or global state. They give
the change order module a small, well-documented vocabulary for the money and
status questions that come up on every construction project worldwide:

* what a change order is worth once its line items are priced and any markup /
  overhead-and-profit (OH&P) percentage is applied;
* how the priced change orders on a project group by their approval state;
* what those approved change orders do to the revised contract sum.

Design rules that keep the module correct for any country:

* Money is always ``Decimal``, never ``float``. Values round to 2 decimal
  places (HALF_UP) only at the presentation boundary, matching the rest of the
  module.
* No currency, tax rate, unit, or locale is hardcoded. Currency is carried
  alongside every amount and is never blended across different ISO codes: two
  amounts in different currencies are never summed without an explicit rate,
  which is out of scope for these helpers and raises a clean ``ValueError``.
* Every markup / OH&P / admin percentage is an explicit parameter with a
  documented default of zero, so a caller that says nothing gets the raw priced
  value and no silent uplift.
* Bad input surfaces as ``ValueError`` (a clean 400 for the API), never as a
  500, ``NaN``, or ``inf``. Division by zero, empty inputs, and mixed statuses
  are all handled with defined results.
* Outputs expose their components (net lines, markup, totals) so a reviewer or
  auditor can reconstruct every figure by hand.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Money rounds to 2 dp at the presentation boundary, matching service._round2.
_CENTS = Decimal("0.01")
# Percentages carry a little more scale so a fractional uplift is not lost.
_PCT_QUANT = Decimal("0.0001")
# Same guard rail the schema layer uses: reject absurd magnitudes long before
# they can overflow Decimal's default precision and surface as a 500.
_MONEY_MAX = Decimal("1e15")

# Valid change order lifecycle states, mirroring service.VALID_TRANSITIONS.
CHANGE_ORDER_STATUSES: tuple[str, ...] = (
    "draft",
    "submitted",
    "approved",
    "rejected",
    "executed",
)

# Plain-language labels for the workflow states. Kept here as neutral English
# source strings; the presentation layer localises them like any other label.
CHANGE_ORDER_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft (being prepared, not yet issued)",
    "submitted": "Submitted (issued and awaiting a decision)",
    "approved": "Approved (accepted and counted in the contract sum)",
    "rejected": "Rejected (declined, no effect on the contract sum)",
    "executed": "Executed (approved and carried out on site)",
}

# Per-step decision vocabulary of the approval chain, mirroring
# models.APPROVAL_DECISIONS.
APPROVAL_DECISION_LABELS: dict[str, str] = {
    "pending": "Waiting for this approver to decide",
    "approved": "This approver accepted the change order",
    "rejected": "This approver declined the change order",
}

# Reason categories, mirroring the schema pattern for reason_category.
REASON_CATEGORY_LABELS: dict[str, str] = {
    "client_request": "Requested by the client",
    "design_change": "Change in the design",
    "unforeseen": "Unforeseen site condition",
    "regulatory": "Required by a regulation or authority",
    "error": "Correction of an error or omission",
}

# Line change types, mirroring the schema pattern for change_type.
CHANGE_TYPE_LABELS: dict[str, str] = {
    "added": "New work added",
    "removed": "Work removed (a credit)",
    "modified": "Existing work changed",
}


# -- label helpers ------------------------------------------------------------


def status_label(status: str | None) -> str:
    """Return a plain-language label for a change order status code.

    Unknown or empty codes fall back to a readable form of the raw code so the
    caller never sees a blank cell.
    """
    key = (status or "").strip().lower()
    if key in CHANGE_ORDER_STATUS_LABELS:
        return CHANGE_ORDER_STATUS_LABELS[key]
    return key.replace("_", " ").capitalize() if key else "Unknown"


def approval_decision_label(decision: str | None) -> str:
    """Return a plain-language label for an approval-chain decision code."""
    key = (decision or "").strip().lower()
    if key in APPROVAL_DECISION_LABELS:
        return APPROVAL_DECISION_LABELS[key]
    return key.replace("_", " ").capitalize() if key else "Unknown"


def reason_category_label(reason: str | None) -> str:
    """Return a plain-language label for a reason_category code."""
    key = (reason or "").strip().lower()
    if key in REASON_CATEGORY_LABELS:
        return REASON_CATEGORY_LABELS[key]
    return key.replace("_", " ").capitalize() if key else "Unspecified"


def change_type_label(change_type: str | None) -> str:
    """Return a plain-language label for a line change_type code."""
    key = (change_type or "").strip().lower()
    if key in CHANGE_TYPE_LABELS:
        return CHANGE_TYPE_LABELS[key]
    return key.replace("_", " ").capitalize() if key else "Change"


# -- one-line concept explainers ----------------------------------------------


def explain_priced_value() -> str:
    """One line: how a change order's priced value is built."""
    return (
        "The priced value is the sum of each line's cost delta "
        "(new quantity times new rate minus original quantity times original rate), "
        "plus any markup or overhead-and-profit percentage applied on top."
    )


def explain_contract_impact() -> str:
    """One line: how a change order affects the contract sum."""
    return (
        "Only approved change orders change the contract sum. "
        "The revised contract sum is the original contract sum plus the total of "
        "approved change orders, all in the same currency."
    )


def explain_approval_state(status: str | None) -> str:
    """One line: what a given approval state means for the money and the work."""
    key = (status or "").strip().lower()
    return status_label(key)


def explain_time_extension(days: int | None) -> str:
    """One line: what a schedule impact in days means for the programme."""
    try:
        n = int(days or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return "No time extension: this change order does not move the completion date."
    unit = "day" if n == 1 else "days"
    return f"Time extension of {n} {unit}: the completion date moves later by this many calendar {unit}."


# -- money + currency primitives ----------------------------------------------


def parse_money(value: object, field_name: str = "amount") -> Decimal:
    """Parse an incoming money value into an exact, finite ``Decimal``.

    Accepts ``Decimal``, ``int``, or a decimal string. Routes everything through
    ``str()`` so a binary float such as ``0.1`` cannot enter the math as
    ``0.1000000000000000055``. Rejects ``None``, ``NaN``, ``Infinity``, garbage,
    and absurd magnitudes with a clean ``ValueError`` so a bad value can never
    poison a rollup or surface as a 500.
    """
    if value is None:
        raise ValueError(f"{field_name} is required and cannot be empty")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value for {field_name}: {value!r}") from exc
    if not d.is_finite():
        raise ValueError(f"{field_name} must be a finite number (no NaN or Infinity), got {value!r}")
    if abs(d) >= _MONEY_MAX:
        raise ValueError(f"{field_name} is outside the supported range, got {value!r}")
    return d


def parse_non_negative_money(value: object, field_name: str = "amount") -> Decimal:
    """Parse a money value that must not be negative (quantities, rates)."""
    d = parse_money(value, field_name)
    if d < 0:
        raise ValueError(f"{field_name} must be non-negative, got {value!r}")
    return d


def round_money(value: Decimal) -> Decimal:
    """Round a money ``Decimal`` to 2 dp (HALF_UP) at the presentation boundary."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def normalize_currency(code: str | None) -> str:
    """Normalise a currency code to a trimmed upper-case string.

    An empty or missing code becomes ``""`` (unspecified), never a hardcoded
    default such as a Eurozone code.
    """
    return (code or "").strip().upper()


def _money_str(value: Decimal) -> str:
    """Canonical decimal string form of a rounded money value."""
    return format(round_money(value), "f")


def _field(obj: object, name: str, default: object = None) -> object:
    """Read ``name`` from a mapping key or an object attribute."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


# -- line pricing -------------------------------------------------------------


@dataclass(frozen=True)
class LinePrice:
    """Priced view of one change order line, with every component exposed.

    ``cost_delta`` is signed: a positive value adds cost, a negative value is a
    credit (for example work removed).
    """

    original_amount: Decimal
    new_amount: Decimal
    cost_delta: Decimal

    def to_dict(self) -> dict[str, str]:
        """Wire-friendly form with canonical decimal strings."""
        return {
            "original_amount": _money_str(self.original_amount),
            "new_amount": _money_str(self.new_amount),
            "cost_delta": _money_str(self.cost_delta),
        }


def price_line(
    original_quantity: object,
    new_quantity: object,
    original_rate: object,
    new_rate: object,
) -> LinePrice:
    """Price a single line from its quantities and rates.

    The cost delta is ``new_quantity * new_rate - original_quantity *
    original_rate``, matching the service's item math exactly. Quantities and
    rates must be non-negative and finite; the resulting delta may be negative
    (a credit). Rounding happens only in ``to_dict`` / at the persistence
    boundary, so intermediate math stays exact.
    """
    oq = parse_non_negative_money(original_quantity, "original_quantity")
    nq = parse_non_negative_money(new_quantity, "new_quantity")
    orr = parse_non_negative_money(original_rate, "original_rate")
    nr = parse_non_negative_money(new_rate, "new_rate")
    original_amount = oq * orr
    new_amount = nq * nr
    return LinePrice(
        original_amount=original_amount,
        new_amount=new_amount,
        cost_delta=new_amount - original_amount,
    )


def line_cost_delta(line: object) -> Decimal:
    """Return the signed cost delta of one line, exact and un-rounded.

    Accepts either an object/mapping carrying ``original_quantity``,
    ``new_quantity``, ``original_rate``, ``new_rate`` (the delta is recomputed
    from them) or one carrying a precomputed ``cost_delta`` (used as-is). When
    both are present the quantities and rates win, because they are the source
    of truth for the figure.
    """
    has_components = all(
        _field(line, name, None) is not None
        for name in ("original_quantity", "new_quantity", "original_rate", "new_rate")
    )
    if has_components:
        return price_line(
            _field(line, "original_quantity", "0"),
            _field(line, "new_quantity", "0"),
            _field(line, "original_rate", "0"),
            _field(line, "new_rate", "0"),
        ).cost_delta
    raw = _field(line, "cost_delta", None)
    if raw is None:
        raise ValueError(
            "line must carry either quantity/rate fields or a cost_delta value",
        )
    return parse_money(raw, "cost_delta")


# -- change order priced total (lines + markup) -------------------------------


@dataclass(frozen=True)
class ChangeOrderPrice:
    """Priced total of a change order, with the markup broken out.

    Components (all in ``currency``):
        net_lines_total  - sum of every line's signed cost delta;
        markup_pct       - the markup / OH&P percentage that was applied;
        markup_amount    - net_lines_total times markup_pct / 100;
        priced_total     - net_lines_total plus markup_amount.
    """

    currency: str
    line_count: int
    net_lines_total: Decimal
    markup_pct: Decimal
    markup_amount: Decimal
    priced_total: Decimal

    def to_dict(self) -> dict[str, object]:
        """Wire-friendly form with canonical decimal strings."""
        return {
            "currency": self.currency,
            "line_count": self.line_count,
            "net_lines_total": _money_str(self.net_lines_total),
            "markup_pct": format(self.markup_pct.quantize(_PCT_QUANT).normalize(), "f"),
            "markup_amount": _money_str(self.markup_amount),
            "priced_total": _money_str(self.priced_total),
            "explanation": explain_priced_value(),
        }


def _parse_pct(value: object, field_name: str) -> Decimal:
    """Parse a percentage: finite, and no steeper than a full 100% credit."""
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid percentage for {field_name}: {value!r}") from exc
    if not d.is_finite():
        raise ValueError(f"{field_name} must be a finite number, got {value!r}")
    if d < Decimal("-100"):
        raise ValueError(f"{field_name} cannot discount more than 100 percent, got {value!r}")
    if d > Decimal("1000"):
        raise ValueError(f"{field_name} is unrealistically large, got {value!r}")
    return d


def price_change_order(
    lines: Iterable[object],
    *,
    markup_pct: object = Decimal("0"),
    currency: str | None = None,
) -> ChangeOrderPrice:
    """Price a whole change order from its lines, then apply a markup / OH&P.

    Args:
        lines: an iterable of line objects or mappings. Each line is priced via
            ``line_cost_delta`` (quantity/rate fields, or a precomputed
            ``cost_delta``).
        markup_pct: the markup / overhead-and-profit percentage to apply on top
            of the net line total. Defaults to zero, so with no argument the
            priced total equals the net line total and nothing is silently
            added. A negative value (down to -100) expresses a discount.
        currency: the ISO currency code the lines are priced in, carried through
            to the result. Never inferred from a hardcoded default.

    An empty ``lines`` iterable is valid and yields a zero-valued price rather
    than an error, so a brand-new change order prices cleanly.

    Returns:
        A :class:`ChangeOrderPrice` with the net line total, the markup
        percentage and amount, and the final priced total all exposed.
    """
    pct = _parse_pct(markup_pct, "markup_pct")
    net = Decimal("0")
    count = 0
    for line in lines:
        net += line_cost_delta(line)
        count += 1
    markup_amount = net * pct / Decimal("100")
    return ChangeOrderPrice(
        currency=normalize_currency(currency),
        line_count=count,
        net_lines_total=net,
        markup_pct=pct,
        markup_amount=markup_amount,
        priced_total=net + markup_amount,
    )


# -- totals grouped by approval status ----------------------------------------


@dataclass(frozen=True)
class StatusTotal:
    """One approval-status bucket: how many change orders and their total value."""

    status: str
    label: str
    count: int
    total_cost_impact: Decimal

    def to_dict(self) -> dict[str, object]:
        """Wire-friendly form with a canonical decimal string total."""
        return {
            "status": self.status,
            "label": self.label,
            "count": self.count,
            "total_cost_impact": _money_str(self.total_cost_impact),
        }


def _single_currency(orders: Sequence[object], currency: str | None) -> str:
    """Resolve the one currency the orders share, or raise on a real mix.

    Empty / unspecified currency codes are treated as "the base currency" and do
    not count as a conflict. Two different non-empty ISO codes never sum
    together, so this raises a clean ``ValueError`` instead of blending them.
    """
    seen: set[str] = set()
    for order in orders:
        code = normalize_currency(_field(order, "currency", ""))
        if code:
            seen.add(code)
    if currency is not None:
        want = normalize_currency(currency)
        extra = {c for c in seen if c != want}
        if extra:
            raise ValueError(
                f"Cannot total change orders across currencies: expected {want or 'base'}, "
                f"also saw {sorted(extra)}. Convert with an explicit rate first.",
            )
        return want
    if len(seen) > 1:
        raise ValueError(
            f"Cannot total change orders across currencies: saw {sorted(seen)}. Convert with an explicit rate first.",
        )
    return next(iter(seen), "")


def totals_by_approval_status(
    orders: Iterable[object],
    *,
    currency: str | None = None,
) -> dict[str, StatusTotal]:
    """Group change orders by approval status and total each bucket's value.

    Each order must expose ``status``, ``cost_impact``, and (optionally)
    ``currency``. All orders must share one currency: a genuine mix of ISO codes
    raises ``ValueError`` rather than blending money. The result maps every
    status seen to a :class:`StatusTotal`; an empty input yields an empty dict.
    Buckets stay ordered by the canonical lifecycle so dashboards render
    predictably.
    """
    order_list = list(orders)
    resolved_currency = _single_currency(order_list, currency)

    counts: dict[str, int] = {}
    sums: dict[str, Decimal] = {}
    for order in order_list:
        status = (str(_field(order, "status", "")) or "").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
        sums[status] = sums.get(status, Decimal("0")) + parse_money(_field(order, "cost_impact", "0"), "cost_impact")

    ordered_keys = [s for s in CHANGE_ORDER_STATUSES if s in counts]
    ordered_keys += [s for s in counts if s not in CHANGE_ORDER_STATUSES]

    out: dict[str, StatusTotal] = {}
    for status in ordered_keys:
        out[status] = StatusTotal(
            status=status,
            label=status_label(status),
            count=counts[status],
            total_cost_impact=sums[status],
        )
    # ``resolved_currency`` is intentionally not stored per bucket: every bucket
    # shares it, and callers that need it already passed or can read it back
    # from the orders. Kept as a local so the currency guard still runs.
    _ = resolved_currency
    return out


# -- effect on the contract sum -----------------------------------------------


@dataclass(frozen=True)
class ContractSumEffect:
    """How the approved change orders move the contract sum, fully itemised."""

    currency: str
    original_contract_sum: Decimal
    approved_change_total: Decimal
    revised_contract_sum: Decimal
    approved_count: int
    considered_count: int
    pct_change: Decimal
    pct_defined: bool

    def to_dict(self) -> dict[str, object]:
        """Wire-friendly form with canonical decimal strings."""
        return {
            "currency": self.currency,
            "original_contract_sum": _money_str(self.original_contract_sum),
            "approved_change_total": _money_str(self.approved_change_total),
            "revised_contract_sum": _money_str(self.revised_contract_sum),
            "approved_count": self.approved_count,
            "considered_count": self.considered_count,
            "pct_change": (format(self.pct_change.quantize(_PCT_QUANT).normalize(), "f") if self.pct_defined else None),
            "explanation": explain_contract_impact(),
        }


def contract_sum_effect(
    original_contract_sum: object,
    orders: Iterable[object],
    *,
    currency: str | None = None,
    counted_status: str = "approved",
) -> ContractSumEffect:
    """Compute the effect of change orders on a contract sum.

    Only change orders in ``counted_status`` (``"approved"`` by default) move the
    contract sum: a submitted or rejected order is counted for context but adds
    nothing. The revised contract sum is the original plus the total of the
    counted orders, all in one currency.

    Args:
        original_contract_sum: the contract value before any change orders. Must
            be non-negative and finite.
        orders: an iterable exposing ``status``, ``cost_impact``, and optionally
            ``currency``. A genuine mix of currencies raises ``ValueError``.
        currency: the ISO currency both the contract sum and the orders are in.
        counted_status: the single status whose orders change the sum. Must be a
            known lifecycle state.

    The percentage change guards against a zero original contract sum: when the
    original is zero the ratio is undefined, so ``pct_defined`` is ``False`` and
    ``pct_change`` is zero rather than a division-by-zero crash.
    """
    counted = (counted_status or "").strip().lower()
    if counted not in CHANGE_ORDER_STATUSES:
        raise ValueError(
            f"counted_status must be one of {CHANGE_ORDER_STATUSES}, got {counted_status!r}",
        )

    original = parse_non_negative_money(original_contract_sum, "original_contract_sum")
    order_list = list(orders)
    resolved_currency = _single_currency(order_list, currency)

    approved_total = Decimal("0")
    approved_count = 0
    for order in order_list:
        status = (str(_field(order, "status", "")) or "").strip().lower()
        if status == counted:
            approved_total += parse_money(_field(order, "cost_impact", "0"), "cost_impact")
            approved_count += 1

    revised = original + approved_total
    if original == 0:
        pct = Decimal("0")
        pct_defined = False
    else:
        pct = approved_total / original * Decimal("100")
        pct_defined = True

    return ContractSumEffect(
        currency=resolved_currency,
        original_contract_sum=original,
        approved_change_total=approved_total,
        revised_contract_sum=revised,
        approved_count=approved_count,
        considered_count=len(order_list),
        pct_change=pct,
        pct_defined=pct_defined,
    )


__all__ = [
    "APPROVAL_DECISION_LABELS",
    "CHANGE_ORDER_STATUSES",
    "CHANGE_ORDER_STATUS_LABELS",
    "CHANGE_TYPE_LABELS",
    "REASON_CATEGORY_LABELS",
    "ChangeOrderPrice",
    "ContractSumEffect",
    "LinePrice",
    "StatusTotal",
    "approval_decision_label",
    "change_type_label",
    "contract_sum_effect",
    "explain_approval_state",
    "explain_contract_impact",
    "explain_priced_value",
    "explain_time_extension",
    "line_cost_delta",
    "normalize_currency",
    "parse_money",
    "parse_non_negative_money",
    "price_change_order",
    "price_line",
    "reason_category_label",
    "round_money",
    "status_label",
    "totals_by_approval_status",
]
