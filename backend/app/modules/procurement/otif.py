# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Supplier delivery-performance (OTIF) computation - pure and dependency-free.

OTIF is On-Time-In-Full. Given one record per confirmed goods receipt, this
module computes, per supplier and rolled up across the whole project:

    on-time rate  - receipts received on or before the promised date
    in-full rate  - receipts whose received quantity is >= the ordered quantity
    OTIF rate     - receipts that are BOTH on-time AND in-full
    avg days late - mean lateness measured over only the late receipts
    counts        - the totals used as the (guarded) denominators

The module imports nothing beyond dataclasses, decimal and date, so the whole
calculation is unit-testable without a database, a session or FastAPI. Every
rate is guarded: a zero denominator yields None (never 0.0, never a crash) so a
caller can tell "no data yet" apart from a genuine "measured 0 percent".

Sourcing and the unscheduled rule
---------------------------------
The promised date is the parent purchase order delivery_date; the received date
is the goods-receipt receipt_date; the ordered and received quantities are
summed per receipt from its line items. A receipt whose purchase order carries
no promised date is "unscheduled": on-time cannot be judged for it, so it is
left out of the on-time and OTIF denominators (yet still counted for in-full and
in the receipt total). This mirrors the existing supplier scorecard rule
(unscheduled receipts excluded from the on-time denominator) so the two views
never contradict each other.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# Rates are reported as 0.0-1.0 Decimals quantised to four places; average days
# late is a duration, quantised to two places. Both are rendered as strings by
# the caller so rate/quantity values never leak onto the wire as floats.
_RATE_QUANTUM = Decimal("0.0001")
_DAYS_QUANTUM = Decimal("0.01")


def _ratio(numerator: int, denominator: int, quantum: Decimal) -> Decimal | None:
    """Return numerator / denominator quantised, or None when denominator is 0.

    The guard is the whole point of the helper: a caller must be able to tell a
    genuine zero rate apart from an undefined one (no receipts to measure yet).
    """
    if denominator <= 0:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(quantum, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ReceiptRecord:
    """One confirmed goods receipt reduced to the fields OTIF needs.

    Fields:
        supplier_id: grouping key (a vendor contact id, or None when the PO has
            no vendor assigned); receipts group by this value.
        received_date: when the goods were received (goods-receipt receipt_date).
        promised_date: the promised delivery date (PO delivery_date), or None
            when the PO is unscheduled.
        ordered_qty: total ordered quantity for this receipt (sum of its items).
        received_qty: total received quantity for this receipt (sum of its items).
        supplier_name: optional display label, carried through untouched.
    """

    supplier_id: str | None
    received_date: date
    promised_date: date | None = None
    ordered_qty: Decimal = Decimal("0")
    received_qty: Decimal = Decimal("0")
    supplier_name: str | None = None


@dataclass
class DeliveryPerformance:
    """OTIF counts and guarded rates for one supplier or the whole project."""

    supplier_id: str | None = None
    supplier_name: str | None = None
    total_receipts: int = 0
    scheduled_receipts: int = 0
    unscheduled_receipts: int = 0
    on_time_count: int = 0
    late_count: int = 0
    in_full_count: int = 0
    otif_count: int = 0
    total_days_late: int = 0

    @property
    def on_time_rate(self) -> Decimal | None:
        """On-time receipts over SCHEDULED receipts (unscheduled excluded)."""
        return _ratio(self.on_time_count, self.scheduled_receipts, _RATE_QUANTUM)

    @property
    def in_full_rate(self) -> Decimal | None:
        """In-full receipts over ALL receipts (in-full is always evaluable)."""
        return _ratio(self.in_full_count, self.total_receipts, _RATE_QUANTUM)

    @property
    def otif_rate(self) -> Decimal | None:
        """On-time-and-in-full receipts over SCHEDULED receipts."""
        return _ratio(self.otif_count, self.scheduled_receipts, _RATE_QUANTUM)

    @property
    def avg_days_late(self) -> Decimal | None:
        """Mean lateness across only the late receipts (None when none late)."""
        return _ratio(self.total_days_late, self.late_count, _DAYS_QUANTUM)


@dataclass
class ProjectDeliveryPerformance:
    """Project-wide OTIF rollup plus a per-supplier breakdown."""

    overall: DeliveryPerformance
    suppliers: list[DeliveryPerformance] = field(default_factory=list)


def _accumulate(
    acc: DeliveryPerformance,
    *,
    scheduled: bool,
    on_time: bool,
    late: bool,
    in_full: bool,
    otif: bool,
    days_late: int,
) -> None:
    """Fold one classified receipt into an accumulator (a supplier or overall)."""
    acc.total_receipts += 1
    if scheduled:
        acc.scheduled_receipts += 1
    else:
        acc.unscheduled_receipts += 1
    if on_time:
        acc.on_time_count += 1
    if late:
        acc.late_count += 1
        acc.total_days_late += days_late
    if in_full:
        acc.in_full_count += 1
    if otif:
        acc.otif_count += 1


def compute_project_delivery_performance(
    receipts: Iterable[ReceiptRecord],
) -> ProjectDeliveryPerformance:
    """Compute the per-supplier and project-wide OTIF view.

    Pure and deterministic: the same receipts always yield the same result, with
    suppliers ordered by id (the unnamed/None group last) so output is stable
    across calls. Guarded rates mean an empty input returns an all-zero overall
    with every rate None, never a division error.
    """
    overall = DeliveryPerformance(supplier_id=None, supplier_name=None)
    by_supplier: dict[str | None, DeliveryPerformance] = {}

    for r in receipts:
        scheduled = r.promised_date is not None
        # Short-circuit protects the date comparison when promised_date is None.
        on_time = scheduled and r.received_date <= r.promised_date
        late = scheduled and not on_time
        days_late = (r.received_date - r.promised_date).days if late else 0
        in_full = r.received_qty >= r.ordered_qty
        otif = on_time and in_full

        group = by_supplier.get(r.supplier_id)
        if group is None:
            group = DeliveryPerformance(supplier_id=r.supplier_id, supplier_name=r.supplier_name)
            by_supplier[r.supplier_id] = group
        elif group.supplier_name is None and r.supplier_name is not None:
            group.supplier_name = r.supplier_name

        for acc in (overall, group):
            _accumulate(
                acc,
                scheduled=scheduled,
                on_time=on_time,
                late=late,
                in_full=in_full,
                otif=otif,
                days_late=days_late,
            )

    suppliers = [by_supplier[key] for key in sorted(by_supplier, key=lambda s: (s is None, s or ""))]
    return ProjectDeliveryPerformance(overall=overall, suppliers=suppliers)
