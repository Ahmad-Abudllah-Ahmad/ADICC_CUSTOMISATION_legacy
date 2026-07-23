# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure computation core for pre-construction mobilisation readiness.

Before construction can start on site, the site must be mobilised: access
established, welfare and accommodation in place, temporary utilities connected,
the perimeter secured, temporary works signed off, environmental controls up,
laydown organised, statutory permits obtained and the workforce inducted. This
module turns a flat list of readiness items (each with a category, a status and
an optional "gate" flag marking a hard prerequisite to commence) into the numbers
a site manager needs: how ready each category is, whether every commencement gate
is satisfied, which items are blocked or overdue, and whether the mobilisation is
on track for the planned start date.

Everything here is a plain value object plus a set of functions. It is
``Decimal``-exact for the readiness percentages and carries no ORM, database,
FastAPI or Pydantic dependency, exactly like
:mod:`app.modules.site_inventory.ledger`, so the whole core is trivially
constructed and asserted from plain values. The DB loaders that build
:class:`ReadinessItem` lists live in :mod:`app.modules.site_prep.service`.

Guard convention: every division is guarded and returns ``None`` (never raises,
never a silent zero) when the denominator is zero - a category with no applicable
items reads "undefined" rather than "0 percent ready".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

# Percentages are quantised to 2 dp, matching the platform-wide convention.
_PCT_Q = Decimal("0.01")
_HUNDRED = Decimal("100")


class Category(StrEnum):
    """The mobilisation categories a readiness item can belong to."""

    ACCESS = "access"  # site access, roads, gates, crossings
    ACCOMMODATION_WELFARE = "accommodation_welfare"  # offices, canteen, toilets, drying room
    TEMPORARY_UTILITIES = "temporary_utilities"  # temp power, water, comms, drainage
    SECURITY_HOARDING = "security_hoarding"  # perimeter, hoarding, gates, CCTV
    TEMPORARY_WORKS = "temporary_works"  # scaffolding, props, temp support, designs
    ENVIRONMENTAL_CONTROLS = "environmental_controls"  # dust, noise, spill, protected species
    LOGISTICS_LAYDOWN = "logistics_laydown"  # laydown areas, storage, crane / hoist setup
    PERMITS_CONSENTS = "permits_consents"  # statutory permits, licences, consents
    INDUCTIONS_TRAINING = "inductions_training"  # inductions, compet/training, briefings
    OTHER = "other"  # anything not covered above


class ItemStatus(StrEnum):
    """Lifecycle status of a single readiness item."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY = "ready"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


# Canonical ordered tuples, exposed so schemas, the service and tests share one
# source of truth for the allowed vocabularies without importing the enums.
ALL_CATEGORIES: tuple[str, ...] = tuple(c.value for c in Category)
ALL_STATUSES: tuple[str, ...] = tuple(s.value for s in ItemStatus)

# A readiness item counts towards "ready" only in READY; it is excluded from the
# applicable base when NOT_APPLICABLE; a commencement gate is satisfied when it is
# READY or NOT_APPLICABLE (a gate that does not apply cannot block the start).
_SATISFIED_STATUSES: frozenset[str] = frozenset(
    {ItemStatus.READY.value, ItemStatus.NOT_APPLICABLE.value},
)


def safe_percent(numerator: int, denominator: int) -> Decimal | None:
    """Percentage ``numerator / denominator * 100`` quantised to 2 dp.

    The single guarded-division primitive every readiness percentage is built
    on: returns ``None`` when ``denominator`` is zero so "undefined" is
    represented uniformly and never as a raised ``ZeroDivisionError`` or a
    misleading ``0``.
    """
    if denominator == 0:
        return None
    ratio = Decimal(numerator) / Decimal(denominator) * _HUNDRED
    return ratio.quantize(_PCT_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ReadinessItem:
    """One mobilisation readiness item, as consumed by the pure functions here.

    A DB-free projection of a persisted ``SitePrepItem`` row. ``category`` and
    ``status`` are the canonical string values (see :class:`Category` /
    :class:`ItemStatus`); an unknown value never raises here, it simply fails to
    match a bucket, so a stray row can never poison a whole-project rollup.
    """

    category: str
    status: str
    is_gate: bool = False
    due_date: date | None = None
    title: str = ""
    item_id: str | None = None
    completed_date: date | None = None

    @property
    def is_applicable(self) -> bool:
        """True when the item counts towards the readiness base (not N/A)."""
        return self.status != ItemStatus.NOT_APPLICABLE.value

    @property
    def is_ready(self) -> bool:
        """True when the item is fully ready."""
        return self.status == ItemStatus.READY.value

    @property
    def is_blocked(self) -> bool:
        """True when the item is blocked."""
        return self.status == ItemStatus.BLOCKED.value

    @property
    def is_gate_satisfied(self) -> bool:
        """True when this item does not stand in the way of commencing.

        A non-gate item is always "satisfied" for gate purposes; a gate item is
        satisfied only when it is READY or NOT_APPLICABLE.
        """
        if not self.is_gate:
            return True
        return self.status in _SATISFIED_STATUSES

    def is_overdue(self, as_of: date) -> bool:
        """True when the item is past its due date and not yet resolved.

        Resolved means READY or NOT_APPLICABLE; a due date strictly before
        ``as_of`` on any other status is overdue. An item with no due date is
        never overdue.
        """
        if self.due_date is None:
            return False
        if self.status in _SATISFIED_STATUSES:
            return False
        return self.due_date < as_of

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready reference to this item (dates as ISO strings)."""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "is_gate": self.is_gate,
            "due_date": self.due_date.isoformat() if self.due_date is not None else None,
        }


@dataclass(frozen=True)
class CategoryReadiness:
    """Readiness rollup for one category (or the whole project when overall)."""

    category: str
    total: int
    applicable: int
    ready: int
    counts: dict[str, int]
    readiness_percent: Decimal | None  # None when applicable == 0 (guarded)
    gate_total: int
    gate_ready: bool
    blocked: int
    overdue: int

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view (percentage as ``float | None``)."""
        return {
            "category": self.category,
            "total": self.total,
            "applicable": self.applicable,
            "ready": self.ready,
            "counts": dict(self.counts),
            "readiness_percent": (float(self.readiness_percent) if self.readiness_percent is not None else None),
            "gate_total": self.gate_total,
            "gate_ready": self.gate_ready,
            "blocked": self.blocked,
            "overdue": self.overdue,
        }


@dataclass(frozen=True)
class ReadinessReport:
    """Whole-project mobilisation readiness: overall, per category, and gates."""

    as_of: date
    target_start_date: date | None
    days_to_target: int | None
    overall: CategoryReadiness
    categories: list[CategoryReadiness]
    gate_ready: bool
    on_track: bool
    blocked_items: list[ReadinessItem] = field(default_factory=list)
    overdue_items: list[ReadinessItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of the whole readiness report."""
        return {
            "as_of": self.as_of.isoformat(),
            "target_start_date": (self.target_start_date.isoformat() if self.target_start_date is not None else None),
            "days_to_target": self.days_to_target,
            "gate_ready": self.gate_ready,
            "on_track": self.on_track,
            "total_items": self.overall.total,
            "applicable_items": self.overall.applicable,
            "ready_items": self.overall.ready,
            "readiness_percent": self.overall.to_dict()["readiness_percent"],
            "overall": self.overall.to_dict(),
            "categories": [c.to_dict() for c in self.categories],
            "blocked_items": [i.to_dict() for i in self.blocked_items],
            "overdue_items": [i.to_dict() for i in self.overdue_items],
        }


def status_counts(items: Iterable[ReadinessItem]) -> dict[str, int]:
    """Count items by status, zero-filling every known status in canonical order."""
    counts: dict[str, int] = dict.fromkeys(ALL_STATUSES, 0)
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
        else:  # defensive: an unknown status still shows up so nothing is lost
            counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def applicable_count(items: Iterable[ReadinessItem]) -> int:
    """Number of items that count towards readiness (everything but N/A)."""
    return sum(1 for item in items if item.is_applicable)


def ready_count(items: Iterable[ReadinessItem]) -> int:
    """Number of items that are fully ready."""
    return sum(1 for item in items if item.is_ready)


def readiness_percent(items: Iterable[ReadinessItem]) -> Decimal | None:
    """Ready items as a percentage of the applicable base, guarded to ``None``.

    ``ready / applicable * 100`` quantised to 2 dp, or ``None`` when nothing is
    applicable (empty input or every item marked not-applicable).
    """
    materialised = list(items)
    return safe_percent(ready_count(materialised), applicable_count(materialised))


def gate_items(items: Iterable[ReadinessItem]) -> list[ReadinessItem]:
    """Only the items flagged as commencement gates."""
    return [item for item in items if item.is_gate]


def gate_ready(items: Iterable[ReadinessItem]) -> bool:
    """True when every commencement gate is satisfied (READY or N/A).

    Vacuously true when there are no gate items - nothing hard-blocks the start.
    """
    return all(item.is_gate_satisfied for item in items if item.is_gate)


def blocking_gate_items(items: Iterable[ReadinessItem]) -> list[ReadinessItem]:
    """Gate items that are NOT yet satisfied - the hard blockers to commencing."""
    return [item for item in items if item.is_gate and not item.is_gate_satisfied]


def blocked_items(items: Iterable[ReadinessItem]) -> list[ReadinessItem]:
    """Items whose status is BLOCKED."""
    return [item for item in items if item.is_blocked]


def overdue_items(items: Iterable[ReadinessItem], as_of: date) -> list[ReadinessItem]:
    """Items past their due date and not yet resolved as of ``as_of``."""
    return [item for item in items if item.is_overdue(as_of)]


def days_to_target(target_start_date: date | None, as_of: date) -> int | None:
    """Whole days from ``as_of`` to the planned start, or ``None`` when unset.

    Positive means the start is still ahead; zero is the start day itself;
    negative means the planned start has already passed.
    """
    if target_start_date is None:
        return None
    return (target_start_date - as_of).days


def on_track(
    items: Iterable[ReadinessItem],
    target_start_date: date | None,
    as_of: date,
) -> bool:
    """True when the mobilisation is on track.

    On track means either every commencement gate is already satisfied, or there
    is still positive lead time before the planned start
    (``days_to_target > 0``). With no target date and gates unsatisfied the
    honest answer is "not on track", since there is neither slack nor a cleared
    gate to rely on.
    """
    materialised = list(items)
    if gate_ready(materialised):
        return True
    remaining = days_to_target(target_start_date, as_of)
    return remaining is not None and remaining > 0


def _category_readiness(
    items: list[ReadinessItem],
    label: str,
    as_of: date,
) -> CategoryReadiness:
    """Build a :class:`CategoryReadiness` for an already-filtered item list."""
    ready = ready_count(items)
    applicable = applicable_count(items)
    gates = [item for item in items if item.is_gate]
    return CategoryReadiness(
        category=label,
        total=len(items),
        applicable=applicable,
        ready=ready,
        counts=status_counts(items),
        readiness_percent=safe_percent(ready, applicable),
        gate_total=len(gates),
        gate_ready=all(item.is_gate_satisfied for item in gates),
        blocked=sum(1 for item in items if item.is_blocked),
        overdue=sum(1 for item in items if item.is_overdue(as_of)),
    )


def category_readiness(
    items: Iterable[ReadinessItem],
    category: str,
    as_of: date,
) -> CategoryReadiness:
    """Readiness rollup for a single category."""
    return _category_readiness([i for i in items if i.category == category], category, as_of)


def overall_readiness(items: Iterable[ReadinessItem], as_of: date) -> CategoryReadiness:
    """Readiness rollup across every item, labelled ``overall``."""
    return _category_readiness(list(items), "overall", as_of)


def _ordered_present_categories(items: list[ReadinessItem]) -> list[str]:
    """Present categories: canonical order first, then any extras sorted.

    Guarantees every category that appears in ``items`` gets a breakdown (so the
    per-category totals always sum to the overall total) while keeping a stable,
    canonical ordering for the common case.
    """
    present = {item.category for item in items}
    canonical = [c for c in ALL_CATEGORIES if c in present]
    extras = sorted(present - set(ALL_CATEGORIES))
    return canonical + extras


def build_report(
    items: Iterable[ReadinessItem],
    *,
    target_start_date: date | None,
    as_of: date,
) -> ReadinessReport:
    """Assemble the full mobilisation readiness report.

    Computes the overall rollup, a per-category breakdown for every category
    present, the commencement-gate status, the on-track flag against the planned
    start, and the blocked / overdue item lists - all from a single pass over the
    provided items.
    """
    materialised = list(items)
    overall = overall_readiness(materialised, as_of)
    categories = [
        _category_readiness([i for i in materialised if i.category == label], label, as_of)
        for label in _ordered_present_categories(materialised)
    ]
    remaining = days_to_target(target_start_date, as_of)
    gate_ok = overall.gate_ready
    is_on_track = gate_ok or (remaining is not None and remaining > 0)
    return ReadinessReport(
        as_of=as_of,
        target_start_date=target_start_date,
        days_to_target=remaining,
        overall=overall,
        categories=categories,
        gate_ready=gate_ok,
        on_track=is_on_track,
        blocked_items=blocked_items(materialised),
        overdue_items=overdue_items(materialised, as_of),
    )
