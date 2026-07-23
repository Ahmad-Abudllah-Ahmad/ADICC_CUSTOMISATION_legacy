# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure computation core for the temporary-works governance register.

Temporary works (falsework, propping, excavation support, facade retention,
crane bases, ...) are safety-critical: they carry construction loads while the
permanent works are incomplete, and a failure kills people. Governance follows a
strict gated lifecycle - a design brief, an independent design check whose rigour
scales with a category (0 to 3), a Temporary Works Coordinator (TWC) permit to
load, an inspection before use, and finally a permit to strike / dismantle.

This module turns a flat list of register items (each with a status, a design
check category and a set of permits) into the answers a TWC needs: whether an
item is cleared to load, cleared to strike, how far design clearance has
progressed across the register, which items are overdue to load or strike, and -
the single most important safety signal - whether any item is bearing load with
no valid permit to load (a compliance breach).

Everything here is a plain value object plus a set of functions. It is
``Decimal``-exact for the one percentage it reports and carries no ORM, database,
FastAPI or Pydantic dependency, exactly like
:mod:`app.modules.site_prep.readiness`, so the whole safety core is trivially
constructed and asserted from plain values. The DB loaders that build
:class:`RegisterItem` lists live in :mod:`app.modules.temporary_works.service`.

Guard convention: the design-clearance percentage is guarded and returns ``None``
(never raises, never a silent zero) when there are no items - an empty register
reads "undefined" rather than "0 percent cleared".

Fail-safe convention: every gate answers "cleared" only on positive evidence (a
valid permit that is live and in date). Missing data, an unknown status or an
expired permit all read as "not cleared" / "breach", never as "cleared".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

# The one percentage this module reports is quantised to 2 dp, matching the
# platform-wide convention.
_PCT_Q = Decimal("0.01")
_HUNDRED = Decimal("100")


class TWType(StrEnum):
    """The kind of temporary works an item represents."""

    FALSEWORK = "falsework"  # temporary support to in-situ concrete / structure
    FORMWORK = "formwork"  # moulds that shape wet concrete
    PROPPING = "propping"  # back-propping / re-propping of slabs and beams
    EXCAVATION_SUPPORT = "excavation_support"  # shoring, trench boxes, sheet piles
    SCAFFOLD = "scaffold"  # access and working-platform scaffolds
    FACADE_RETENTION = "facade_retention"  # retained facades during demolition
    CRANE_BASE = "crane_base"  # tower / mobile crane foundations and mats
    EDGE_PROTECTION = "edge_protection"  # guardrails, nets, barriers
    DEWATERING = "dewatering"  # well points, sumps, ground-water control
    HOARDING = "hoarding"  # site perimeter hoarding and gantries
    OTHER = "other"  # anything not covered above


class ItemStatus(StrEnum):
    """Lifecycle status of a single temporary-works item.

    The main flow runs identified -> design_brief -> design_submitted ->
    design_checked -> approved_to_load -> loaded -> in_use ->
    approved_to_strike -> struck -> removed. ``on_hold`` is a side status a
    paused item can carry at any point and has no position in the main flow.
    """

    IDENTIFIED = "identified"
    DESIGN_BRIEF = "design_brief"
    DESIGN_SUBMITTED = "design_submitted"
    DESIGN_CHECKED = "design_checked"
    APPROVED_TO_LOAD = "approved_to_load"
    LOADED = "loaded"
    IN_USE = "in_use"
    APPROVED_TO_STRIKE = "approved_to_strike"
    STRUCK = "struck"
    REMOVED = "removed"
    ON_HOLD = "on_hold"


class PermitType(StrEnum):
    """The kind of permit a Temporary Works Coordinator issues against an item."""

    PERMIT_TO_LOAD = "permit_to_load"
    PERMIT_TO_STRIKE = "permit_to_strike"
    PERMIT_TO_DISMANTLE = "permit_to_dismantle"


class PermitStatus(StrEnum):
    """Lifecycle status of a single permit."""

    DRAFT = "draft"
    ISSUED = "issued"
    ACTIVE = "active"
    EXPIRED = "expired"
    CLOSED = "closed"


# Canonical ordered tuples, exposed so schemas, the service and tests share one
# source of truth for the allowed vocabularies without importing the enums. The
# design check category is a plain tuple (BS-5975-style categories 0-3) because
# a digit-named enum member is awkward and buys nothing here.
ALL_TW_TYPES: tuple[str, ...] = tuple(t.value for t in TWType)
ALL_ITEM_STATUSES: tuple[str, ...] = tuple(s.value for s in ItemStatus)
ALL_PERMIT_TYPES: tuple[str, ...] = tuple(t.value for t in PermitType)
ALL_PERMIT_STATUSES: tuple[str, ...] = tuple(s.value for s in PermitStatus)
ALL_DESIGN_CHECK_CATEGORIES: tuple[str, ...] = ("0", "1", "2", "3")

# The bucket label used for items whose design check category is not set yet.
UNASSIGNED_CATEGORY = "unassigned"

# A permit only counts as "valid" (in force) when it is issued or active; a
# draft is not yet in force, and an expired or closed permit is spent.
_LIVE_PERMIT_STATUSES: frozenset[str] = frozenset(
    {PermitStatus.ISSUED.value, PermitStatus.ACTIVE.value},
)

# Design clearance is reached at design_checked and holds for every later status
# in the main flow. ``on_hold`` is deliberately excluded - a paused item makes no
# claim about whether its check is complete.
_DESIGN_CLEARED_STATUSES: frozenset[str] = frozenset(
    {
        ItemStatus.DESIGN_CHECKED.value,
        ItemStatus.APPROVED_TO_LOAD.value,
        ItemStatus.LOADED.value,
        ItemStatus.IN_USE.value,
        ItemStatus.APPROVED_TO_STRIKE.value,
        ItemStatus.STRUCK.value,
        ItemStatus.REMOVED.value,
    },
)

# An item is no longer "waiting to load" once it has been approved to load or has
# moved past that point, so those statuses are never counted as overdue-to-load.
_LOAD_SETTLED_STATUSES: frozenset[str] = frozenset(
    {
        ItemStatus.APPROVED_TO_LOAD.value,
        ItemStatus.LOADED.value,
        ItemStatus.IN_USE.value,
        ItemStatus.APPROVED_TO_STRIKE.value,
        ItemStatus.STRUCK.value,
        ItemStatus.REMOVED.value,
    },
)

# An item is no longer "waiting to strike" once it has been struck or removed.
_STRIKE_SETTLED_STATUSES: frozenset[str] = frozenset(
    {ItemStatus.STRUCK.value, ItemStatus.REMOVED.value},
)

# The statuses that mean the item is actually bearing load. An item in one of
# these with no valid permit to load is the register's red-flag safety breach.
_LOAD_BEARING_STATUSES: frozenset[str] = frozenset(
    {ItemStatus.LOADED.value, ItemStatus.IN_USE.value},
)


def safe_percent(numerator: int, denominator: int) -> Decimal | None:
    """Percentage ``numerator / denominator * 100`` quantised to 2 dp.

    The single guarded-division primitive the design-clearance percentage is
    built on: returns ``None`` when ``denominator`` is zero so "undefined" is
    represented uniformly and never as a raised ``ZeroDivisionError`` or a
    misleading ``0``.

    Args:
        numerator: Count of items satisfying the condition.
        denominator: Size of the base being measured against.

    Returns:
        The 2-dp ``Decimal`` percentage, or ``None`` when ``denominator`` is 0.
    """
    if denominator == 0:
        return None
    ratio = Decimal(numerator) / Decimal(denominator) * _HUNDRED
    return ratio.quantize(_PCT_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class RegisterPermit:
    """One permit on a temporary-works item, as consumed by the pure functions.

    A DB-free projection of a persisted permit row. ``permit_type`` and
    ``status`` are the canonical string values (see :class:`PermitType` /
    :class:`PermitStatus`); an unknown value never raises here, it simply fails
    to satisfy a gate, so a stray row can never make an item look cleared.
    """

    permit_type: str
    status: str
    valid_from: date | None = None
    valid_to: date | None = None
    prereq_design_check_accepted: bool = False
    prereq_inspection_passed: bool = False

    def is_live(self) -> bool:
        """True when the permit status is issued or active (in force)."""
        return self.status in _LIVE_PERMIT_STATUSES

    def is_in_window(self, as_of: date) -> bool:
        """True when ``as_of`` falls within the permit validity window.

        An open-ended bound (``None``) never closes the window on that side, so a
        permit with no ``valid_from`` is valid up to ``valid_to`` and a permit
        with no ``valid_to`` is valid from ``valid_from`` onwards. The window is
        inclusive at both ends.
        """
        if self.valid_from is not None and as_of < self.valid_from:
            return False
        return not (self.valid_to is not None and as_of > self.valid_to)

    def is_valid(self, as_of: date) -> bool:
        """True when the permit is both live and in its validity window."""
        return self.is_live() and self.is_in_window(as_of)


@dataclass(frozen=True)
class RegisterItem:
    """One temporary-works item, as consumed by the pure functions here.

    A DB-free projection of a persisted item row plus the permits attached to it.
    ``tw_type``, ``design_check_category`` and ``status`` are the canonical
    string values; an unknown value never raises here, it simply fails to match a
    bucket or a gate, so a stray row can never poison a whole-register rollup or
    make an item look cleared to load.
    """

    id: str | None = None
    reference: str = ""
    title: str = ""
    tw_type: str = "other"
    design_check_category: str | None = None
    status: str = "identified"
    required_load_date: date | None = None
    required_strike_date: date | None = None
    permits: list[RegisterPermit] = field(default_factory=list)

    @property
    def is_design_cleared(self) -> bool:
        """True when the item has reached the independent-design-check stage."""
        return self.status in _DESIGN_CLEARED_STATUSES

    @property
    def is_load_bearing(self) -> bool:
        """True when the item is actually carrying load (loaded or in use)."""
        return self.status in _LOAD_BEARING_STATUSES

    def to_ref(self) -> dict[str, Any]:
        """JSON-ready reference to this item (dates as ISO strings)."""
        return {
            "item_id": self.id,
            "reference": self.reference,
            "title": self.title,
            "tw_type": self.tw_type,
            "status": self.status,
            "required_load_date": (
                self.required_load_date.isoformat() if self.required_load_date is not None else None
            ),
            "required_strike_date": (
                self.required_strike_date.isoformat() if self.required_strike_date is not None else None
            ),
        }


@dataclass(frozen=True)
class ItemGateStatus:
    """Per-item load / strike clearance, the heart of the load-status view."""

    item_id: str | None
    reference: str
    cleared_to_load: bool
    cleared_to_strike: bool

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of the item's two gate flags."""
        return {
            "item_id": self.item_id,
            "reference": self.reference,
            "cleared_to_load": self.cleared_to_load,
            "cleared_to_strike": self.cleared_to_strike,
        }


@dataclass(frozen=True)
class TemporaryWorksRegister:
    """Whole-project temporary-works rollup: counts, clearance, breaches, gates."""

    as_of: date
    total: int
    status_counts: dict[str, int]
    category_counts: dict[str, int]
    design_clearance_pct: Decimal | None  # None when total == 0 (guarded)
    is_compliant: bool
    overdue_to_load: list[RegisterItem] = field(default_factory=list)
    overdue_to_strike: list[RegisterItem] = field(default_factory=list)
    compliance_breaches: list[dict[str, Any]] = field(default_factory=list)
    gate_statuses: list[ItemGateStatus] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of the whole register.

        ``design_clearance_pct`` is left as a ``Decimal`` (or ``None``); the
        response schema serialises it to a plain decimal string so no float
        rounding is introduced at the API edge.
        """
        return {
            "as_of": self.as_of.isoformat(),
            "total": self.total,
            "status_counts": dict(self.status_counts),
            "category_counts": dict(self.category_counts),
            "design_clearance_pct": self.design_clearance_pct,
            "is_compliant": self.is_compliant,
            "overdue_to_load": [i.to_ref() for i in self.overdue_to_load],
            "overdue_to_strike": [i.to_ref() for i in self.overdue_to_strike],
            "compliance_breaches": [dict(b) for b in self.compliance_breaches],
            "gate_statuses": [g.to_dict() for g in self.gate_statuses],
        }


# -- Permit / gate logic -----------------------------------------------------


def valid_permit(item: RegisterItem, permit_type: str, as_of: date) -> bool:
    """True when ``item`` has a live, in-date permit of ``permit_type``.

    "Valid" means a permit whose status is issued or active and whose validity
    window contains ``as_of``. A draft, expired or closed permit does not count,
    and neither does one whose window has not opened or has already closed.
    """
    return any(p.permit_type == permit_type and p.is_valid(as_of) for p in item.permits)


def design_check_accepted(item: RegisterItem, as_of: date) -> bool:
    """True when a valid permit to load records both safety prerequisites.

    The permit-to-load is the TWC's record that the independent design check has
    been accepted and the inspection-before-use has passed. This returns True
    only when such a permit exists, is valid as of ``as_of``, and carries both
    ``prereq_design_check_accepted`` and ``prereq_inspection_passed`` set.
    """
    return any(
        p.permit_type == PermitType.PERMIT_TO_LOAD.value
        and p.is_valid(as_of)
        and p.prereq_design_check_accepted
        and p.prereq_inspection_passed
        for p in item.permits
    )


def load_gate(item: RegisterItem, as_of: date) -> bool:
    """True when ``item`` is cleared to bear load as of ``as_of``.

    Fail-safe: the item is cleared only when the design check has been accepted
    and the inspection passed on a valid permit to load (see
    :func:`design_check_accepted`) AND a valid permit to load holds (see
    :func:`valid_permit`). Either condition missing leaves the gate shut.
    """
    return design_check_accepted(item, as_of) and valid_permit(
        item,
        PermitType.PERMIT_TO_LOAD.value,
        as_of,
    )


def strike_gate(item: RegisterItem, as_of: date) -> bool:
    """True when ``item`` is cleared to be struck / dismantled as of ``as_of``.

    Cleared only when a valid permit to strike holds; without it, striking the
    temporary works is not authorised.
    """
    return valid_permit(item, PermitType.PERMIT_TO_STRIKE.value, as_of)


def item_gate_status(item: RegisterItem, as_of: date) -> ItemGateStatus:
    """Both gate flags for a single item, packaged for the load-status view."""
    return ItemGateStatus(
        item_id=item.id,
        reference=item.reference,
        cleared_to_load=load_gate(item, as_of),
        cleared_to_strike=strike_gate(item, as_of),
    )


# -- Overdue detection -------------------------------------------------------


def is_overdue_to_load(item: RegisterItem, as_of: date) -> bool:
    """True when the item is past its required load date and not yet loaded.

    An item with no required load date is never overdue. Once it has been
    approved to load or has moved past that point, it is no longer waiting to
    load and is never overdue. A required load date strictly before ``as_of`` on
    any other status is overdue; the required date falling exactly on ``as_of``
    is not.
    """
    if item.required_load_date is None:
        return False
    if item.status in _LOAD_SETTLED_STATUSES:
        return False
    return item.required_load_date < as_of


def is_overdue_to_strike(item: RegisterItem, as_of: date) -> bool:
    """True when the item is past its required strike date and not yet struck.

    An item with no required strike date is never overdue. Once it has been
    struck or removed it is never overdue. A required strike date strictly before
    ``as_of`` on any other status is overdue; the required date falling exactly
    on ``as_of`` is not.
    """
    if item.required_strike_date is None:
        return False
    if item.status in _STRIKE_SETTLED_STATUSES:
        return False
    return item.required_strike_date < as_of


def overdue_to_load_items(items: Iterable[RegisterItem], as_of: date) -> list[RegisterItem]:
    """Items past their required load date and not yet loaded."""
    return [item for item in items if is_overdue_to_load(item, as_of)]


def overdue_to_strike_items(items: Iterable[RegisterItem], as_of: date) -> list[RegisterItem]:
    """Items past their required strike date and not yet struck."""
    return [item for item in items if is_overdue_to_strike(item, as_of)]


# -- Compliance breaches (the safety red flag) -------------------------------


def compliance_breaches(items: Iterable[RegisterItem], as_of: date) -> list[dict[str, Any]]:
    """Items bearing load with no valid permit to load - the safety red flag.

    An item whose status is ``loaded`` or ``in_use`` must be backed by a valid
    permit to load at all times. If it is not (no permit, or a draft / expired /
    closed / out-of-window permit), that is a live compliance breach: temporary
    works are carrying load without a coordinator's authorisation in force.

    Returns:
        One dict per breaching item with ``item_id``, ``reference``, ``title``
        and a plain-language ``reason``. An empty list means no breaches.
    """
    breaches: list[dict[str, Any]] = []
    for item in items:
        if item.is_load_bearing and not valid_permit(item, PermitType.PERMIT_TO_LOAD.value, as_of):
            breaches.append(
                {
                    "item_id": item.id,
                    "reference": item.reference,
                    "title": item.title,
                    "reason": (
                        f"Status '{item.status}' means the temporary works are bearing load, "
                        f"but no valid permit to load is in force as of {as_of.isoformat()}."
                    ),
                },
            )
    return breaches


# -- Counts and clearance ----------------------------------------------------


def status_counts(items: Iterable[RegisterItem]) -> dict[str, int]:
    """Count items by status, zero-filling every known status in canonical order."""
    counts: dict[str, int] = dict.fromkeys(ALL_ITEM_STATUSES, 0)
    for item in items:
        if item.status in counts:
            counts[item.status] += 1
        else:  # defensive: an unknown status still shows up so nothing is lost
            counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def category_counts(items: Iterable[RegisterItem]) -> dict[str, int]:
    """Count items by design-check category, zero-filling 0-3 and unassigned.

    An item with no category set is counted under :data:`UNASSIGNED_CATEGORY`; an
    out-of-vocabulary category value is still counted (defensively) rather than
    dropped, so the per-category counts always sum to the total.
    """
    counts: dict[str, int] = dict.fromkeys(ALL_DESIGN_CHECK_CATEGORIES, 0)
    counts[UNASSIGNED_CATEGORY] = 0
    for item in items:
        key = item.design_check_category if item.design_check_category is not None else UNASSIGNED_CATEGORY
        if key in counts:
            counts[key] += 1
        else:  # defensive: an unknown category still shows up so nothing is lost
            counts[key] = counts.get(key, 0) + 1
    return counts


def design_cleared_count(items: Iterable[RegisterItem]) -> int:
    """Number of items that have reached the design-checked stage or later."""
    return sum(1 for item in items if item.is_design_cleared)


def design_clearance_pct(items: Iterable[RegisterItem]) -> Decimal | None:
    """Design-cleared items as a percentage of all items, guarded to ``None``.

    ``design_cleared / total * 100`` quantised to 2 dp, or ``None`` when the
    register is empty. Every temporary work is subject to a design check, so the
    base is the whole register rather than a filtered subset.
    """
    materialised = list(items)
    return safe_percent(design_cleared_count(materialised), len(materialised))


def is_compliant(items: Iterable[RegisterItem], as_of: date) -> bool:
    """True when no item is bearing load without a valid permit to load."""
    return not compliance_breaches(items, as_of)


# -- Report assembly ---------------------------------------------------------


def build_report(items: Iterable[RegisterItem], as_of: date) -> TemporaryWorksRegister:
    """Assemble the full temporary-works register rollup in a single pass.

    Computes the per-status and per-category counts, the design-clearance
    percentage, the overdue-to-load and overdue-to-strike lists, the per-item
    load / strike gate statuses, and - the critical safety output - the list of
    compliance breaches (items bearing load with no valid permit to load) plus
    the overall ``is_compliant`` flag.

    Args:
        items: The register items with their permits.
        as_of: The date the gates and overdue checks are evaluated against.

    Returns:
        A :class:`TemporaryWorksRegister` value object.
    """
    materialised = list(items)
    breaches = compliance_breaches(materialised, as_of)
    return TemporaryWorksRegister(
        as_of=as_of,
        total=len(materialised),
        status_counts=status_counts(materialised),
        category_counts=category_counts(materialised),
        design_clearance_pct=safe_percent(design_cleared_count(materialised), len(materialised)),
        is_compliant=not breaches,
        overdue_to_load=overdue_to_load_items(materialised, as_of),
        overdue_to_strike=overdue_to_strike_items(materialised, as_of),
        compliance_breaches=breaches,
        gate_statuses=[item_gate_status(item, as_of) for item in materialised],
    )
