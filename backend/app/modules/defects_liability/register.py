# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure computation core for the defects-liability / DLP register.

When a building or a section of works is handed over, the contractor and its
subcontractors do not walk away: for a defined period - the defects liability
period (DLP), also called the rectification or maintenance period - they stay
liable to make good defects that appear, and many elements carry a workmanship or
manufacturer warranty on top. Part of the contract price (the retention) is held
back until that period ends clean. So the two questions the post-handover team
lives by are: which entries are running down towards their DLP end, and which have
finished their DLP with nothing left outstanding, so the final retention can be
released.

This module turns a flat list of warranty / DLP entries (each with a status, a
type, a responsible subcontractor, the key dates and the defect notices raised
against it) into those answers: how the register splits by status and by type;
which entries are expiring within a horizon or already expired; how many defects
are open and which are overdue; a per-subcontractor health view; a single overall
health score; and - the valuable signal - the list of entries whose DLP has ended
with no outstanding defects and are therefore clear for the final retention money.

Everything here is a plain value object plus a set of functions. It is
``Decimal``-exact for every percentage it reports and carries no ORM, database,
FastAPI or Pydantic dependency, exactly like
:mod:`app.modules.interface_management.register` and
:mod:`app.modules.temporary_works.register`, so the whole core is trivially
constructed and asserted from plain values. The DB loaders that build
:class:`WarrantyRow` lists live in
:mod:`app.modules.defects_liability.service`.

Guard convention: every percentage is guarded and returns ``None`` (never raises,
never a silent zero) when the base is zero - an empty register reads "undefined"
rather than "0 percent healthy".

Vocabulary convention: an unknown status, type or severity value never raises
here; it simply fails to match a bucket or an outstanding-state check, so a stray
row can never poison a whole-register rollup or make an entry look ready for
retention release.

Boundary convention: overdue and expired both use a strict "<" against ``as_of``,
so a due date or DLP end date falling exactly on ``as_of`` is not yet overdue and
not yet expired; the retention-release check uses "<=", so a DLP that ends exactly
on ``as_of`` is already eligible for release once nothing is outstanding.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

# Every percentage this module reports is quantised to 2 dp, matching the
# platform-wide convention.
_PCT_Q = Decimal("0.01")
_HUNDRED = Decimal("100")


class WarrantyType(StrEnum):
    """The kind of cover a warranty / DLP entry represents."""

    WORKMANSHIP = "workmanship"  # the trade's own quality of installation
    MANUFACTURER = "manufacturer"  # a product / material manufacturer's guarantee
    LATENT_DEFECT = "latent_defect"  # cover for defects not apparent at handover
    EXTENDED = "extended"  # a purchased extension beyond the standard period
    OTHER = "other"  # anything not covered above


class WarrantyStatus(StrEnum):
    """Lifecycle status of a single warranty / DLP entry.

    The main flow runs in_dlp -> expiring -> expired -> closed as the period runs
    down and is finally signed off. ``on_hold`` is a side state a paused entry can
    carry at any point (for example while a dispute is resolved) and has no fixed
    position in the main flow.
    """

    IN_DLP = "in_dlp"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    CLOSED = "closed"
    ON_HOLD = "on_hold"


class DefectStatus(StrEnum):
    """Lifecycle status of a single defect notice raised during the DLP.

    The main flow runs open -> rectifying -> rectified -> closed. ``rejected`` is
    a terminal state for a notice the responsible party disputes and that is not
    upheld. Only ``open`` and ``rectifying`` count as outstanding; the other three
    are settled and never hold back a retention release.
    """

    OPEN = "open"
    RECTIFYING = "rectifying"
    RECTIFIED = "rectified"
    REJECTED = "rejected"
    CLOSED = "closed"


class DefectSeverity(StrEnum):
    """How serious a single defect is."""

    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


# Canonical ordered tuples, exposed so schemas, the service and tests share one
# source of truth for the allowed vocabularies without importing the enums.
ALL_WARRANTY_TYPES: tuple[str, ...] = tuple(t.value for t in WarrantyType)
ALL_WARRANTY_STATUSES: tuple[str, ...] = tuple(s.value for s in WarrantyStatus)
ALL_DEFECT_STATUSES: tuple[str, ...] = tuple(s.value for s in DefectStatus)
ALL_DEFECT_SEVERITIES: tuple[str, ...] = tuple(s.value for s in DefectSeverity)

# The bucket label used for warranties whose warranty type or responsible
# subcontractor is not set. Shared across both groupings so an "unassigned"
# bucket always means the same thing.
UNASSIGNED = "unassigned"

# A defect is outstanding (still holding back a retention release) only while it
# is open or being rectified. Rectified, rejected and closed are all settled.
_OUTSTANDING_DEFECT_STATUSES: frozenset[str] = frozenset(
    {DefectStatus.OPEN.value, DefectStatus.RECTIFYING.value},
)

# A closed warranty is signed off and is never reported as expiring, whatever its
# DLP end date says. Every other status can still be expiring within the horizon.
_EXPIRING_EXCLUDED_STATUSES: frozenset[str] = frozenset({WarrantyStatus.CLOSED.value})

# A closed warranty is signed off and is never reported as expired either; an
# entry only expires while it is still live.
_EXPIRED_EXCLUDED_STATUSES: frozenset[str] = frozenset({WarrantyStatus.CLOSED.value})


def safe_percent(numerator: int, denominator: int) -> Decimal | None:
    """Percentage ``numerator / denominator * 100`` quantised to 2 dp.

    The single guarded-division primitive every percentage in this module is
    built on: returns ``None`` when ``denominator`` is zero so "undefined" is
    represented uniformly and never as a raised ``ZeroDivisionError`` or a
    misleading ``0``.

    Args:
        numerator: Count of warranties satisfying the condition.
        denominator: Size of the base being measured against.

    Returns:
        The 2-dp ``Decimal`` percentage, or ``None`` when ``denominator`` is 0.
    """
    if denominator == 0:
        return None
    ratio = Decimal(numerator) / Decimal(denominator) * _HUNDRED
    return ratio.quantize(_PCT_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DefectRow:
    """One defect notice on a warranty, as consumed by the pure functions.

    A DB-free projection of a persisted defect row. ``status`` and ``severity``
    are the canonical string values (see :class:`DefectStatus` /
    :class:`DefectSeverity`); an unknown value never raises here, it simply fails
    to count as outstanding, so a stray row can never hold back a retention
    release or inflate the open-defect load.
    """

    status: str = "open"
    severity: str | None = None
    due_date: date | None = None

    @property
    def is_outstanding(self) -> bool:
        """True while the defect is still open or being rectified."""
        return self.status in _OUTSTANDING_DEFECT_STATUSES

    def is_overdue(self, as_of: date) -> bool:
        """True when the defect is outstanding and past its due date.

        A defect with no due date is never overdue. A settled defect (rectified,
        rejected, closed) is never overdue. Otherwise a due date strictly before
        ``as_of`` is overdue; the due date falling exactly on ``as_of`` is not.
        """
        if self.due_date is None:
            return False
        if not self.is_outstanding:
            return False
        return self.due_date < as_of


@dataclass(frozen=True)
class WarrantyRow:
    """One warranty / DLP entry, as consumed by the pure functions here.

    A DB-free projection of a persisted warranty row plus the defects raised
    against it. ``status`` and ``warranty_type`` are the canonical string values;
    an unknown value never raises here, it simply fails to match a bucket or a
    state check, so a stray row can never poison a rollup or make an entry look
    ready for retention release.
    """

    id: str | None = None
    reference: str = ""
    title: str = ""
    status: str = "in_dlp"
    subcontractor_name: str | None = None
    work_package: str | None = None
    warranty_type: str | None = None
    dlp_end_date: date | None = None
    warranty_end_date: date | None = None
    defects: list[DefectRow] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        """True when the entry has been signed off (status closed)."""
        return self.status == WarrantyStatus.CLOSED.value

    def to_ref(self, as_of: date) -> dict[str, Any]:
        """JSON-ready reference to this warranty (dates as ISO strings)."""
        return {
            "warranty_id": self.id,
            "reference": self.reference,
            "title": self.title,
            "status": self.status,
            "subcontractor_name": self.subcontractor_name,
            "work_package": self.work_package,
            "warranty_type": self.warranty_type,
            "dlp_end_date": (self.dlp_end_date.isoformat() if self.dlp_end_date is not None else None),
            "warranty_end_date": (self.warranty_end_date.isoformat() if self.warranty_end_date is not None else None),
            "open_defect_count": open_defect_count(self),
            "retention_release_ready": retention_release_ready(self, as_of),
        }


@dataclass(frozen=True)
class SubcontractorDlpHealth:
    """Post-handover health rollup for one subcontractor (or one grouping label)."""

    subcontractor: str
    total: int
    open_defects: int
    overdue_defects: int
    health_score: Decimal | None  # None when total == 0 (guarded)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of one subcontractor's DLP health.

        ``health_score`` stays a ``Decimal`` (or ``None``); the response schema
        serialises it to a plain decimal string so no float rounding is
        introduced at the API edge.
        """
        return {
            "subcontractor": self.subcontractor,
            "total": self.total,
            "open_defects": self.open_defects,
            "overdue_defects": self.overdue_defects,
            "health_score": self.health_score,
        }


@dataclass(frozen=True)
class DlpRegister:
    """Whole-project DLP rollup: counts, expiry, defect load, health, readiness."""

    as_of: date
    horizon_days: int
    total: int
    per_status: dict[str, int]
    per_warranty_type: dict[str, int]
    total_open_defects: int
    overall_health_score: Decimal | None  # None when total == 0 (guarded)
    is_clean: bool
    expiring: list[WarrantyRow] = field(default_factory=list)
    expired: list[WarrantyRow] = field(default_factory=list)
    overdue_defects: list[dict[str, Any]] = field(default_factory=list)
    retention_release_ready: list[WarrantyRow] = field(default_factory=list)
    subcontractors: list[SubcontractorDlpHealth] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready view of the whole register.

        ``overall_health_score`` is left as a ``Decimal`` (or ``None``); the
        response schema serialises it to a plain decimal string so no float
        rounding is introduced at the API edge.
        """
        return {
            "as_of": self.as_of.isoformat(),
            "horizon_days": self.horizon_days,
            "total": self.total,
            "per_status": dict(self.per_status),
            "per_warranty_type": dict(self.per_warranty_type),
            "total_open_defects": self.total_open_defects,
            "overall_health_score": self.overall_health_score,
            "is_clean": self.is_clean,
            "expiring": [w.to_ref(self.as_of) for w in self.expiring],
            "expired": [w.to_ref(self.as_of) for w in self.expired],
            "overdue_defects": [dict(d) for d in self.overdue_defects],
            "retention_release_ready": [w.to_ref(self.as_of) for w in self.retention_release_ready],
            "subcontractors": [s.to_dict() for s in self.subcontractors],
        }


# -- Per-warranty predicates -------------------------------------------------


def is_expiring(warranty: WarrantyRow, as_of: date, horizon_days: int) -> bool:
    """True when the entry's DLP ends within the horizon and is not yet closed.

    The window is ``[as_of, as_of + horizon_days]`` inclusive at both ends, so a
    DLP that ends exactly today or exactly on the last day of the horizon both
    count as expiring. An entry with no DLP end date is never expiring, an already
    expired entry (DLP end strictly before ``as_of``) is not expiring (it is
    expired), and a closed entry is never expiring whatever its date says.
    """
    if warranty.dlp_end_date is None:
        return False
    if warranty.status in _EXPIRING_EXCLUDED_STATUSES:
        return False
    horizon_end = as_of + timedelta(days=horizon_days)
    return as_of <= warranty.dlp_end_date <= horizon_end


def is_expired(warranty: WarrantyRow, as_of: date) -> bool:
    """True when the entry's DLP has passed and it is not yet closed.

    An entry with no DLP end date is never expired. A closed entry is never
    expired (it is signed off). Otherwise a DLP end date strictly before ``as_of``
    is expired; the DLP end date falling exactly on ``as_of`` is not yet expired
    (but is already eligible for retention release, see
    :func:`retention_release_ready`).
    """
    if warranty.dlp_end_date is None:
        return False
    if warranty.status in _EXPIRED_EXCLUDED_STATUSES:
        return False
    return warranty.dlp_end_date < as_of


def open_defect_count(warranty: WarrantyRow) -> int:
    """Number of outstanding defects on the entry (open or rectifying)."""
    return sum(1 for defect in warranty.defects if defect.is_outstanding)


def overdue_defect_count(warranty: WarrantyRow, as_of: date) -> int:
    """Number of outstanding defects on the entry past their due date."""
    return sum(1 for defect in warranty.defects if defect.is_overdue(as_of))


def has_open_or_overdue(warranty: WarrantyRow, as_of: date) -> bool:
    """True when the entry carries at least one open or overdue defect.

    The unhealthy predicate the per-subcontractor and overall health scores are
    built on. An overdue defect is by definition also outstanding, so this is
    driven by the outstanding defects; the "or overdue" is kept explicit so the
    intent survives any future change to what counts as outstanding.
    """
    return open_defect_count(warranty) > 0 or overdue_defect_count(warranty, as_of) > 0


def retention_release_ready(warranty: WarrantyRow, as_of: date) -> bool:
    """True when the entry's DLP has ended with no outstanding defects.

    The key money signal: a warranty whose defects liability period has run out
    (DLP end date on or before ``as_of``) with nothing open or being rectified is
    clear for the final retention to be released. An entry with no DLP end date is
    never ready (the period is undefined), an entry whose DLP end date is still in
    the future is not ready, and an entry with any open or rectifying defect is
    not ready however far its DLP has run. An entry that never had a defect
    raised is ready as soon as its DLP has ended.

    Note this is a readiness signal derived from dates and defect state; it does
    not consider whether the retention was actually released (that is the separate
    ``retention_release_date`` field on the persisted row).
    """
    if warranty.dlp_end_date is None:
        return False
    if warranty.dlp_end_date > as_of:
        return False
    return open_defect_count(warranty) == 0


# -- Collections -------------------------------------------------------------


def expiring_warranties(
    warranties: Iterable[WarrantyRow],
    as_of: date,
    horizon_days: int,
) -> list[WarrantyRow]:
    """Entries whose DLP ends within the horizon and are not closed, in input order."""
    return [w for w in warranties if is_expiring(w, as_of, horizon_days)]


def expired_warranties(warranties: Iterable[WarrantyRow], as_of: date) -> list[WarrantyRow]:
    """Entries whose DLP has passed and are not closed, in input order."""
    return [w for w in warranties if is_expired(w, as_of)]


def retention_release_ready_warranties(
    warranties: Iterable[WarrantyRow],
    as_of: date,
) -> list[WarrantyRow]:
    """Entries clear for final retention release (DLP ended, nothing outstanding)."""
    return [w for w in warranties if retention_release_ready(w, as_of)]


def overdue_defects(warranties: Iterable[WarrantyRow], as_of: date) -> list[dict[str, Any]]:
    """Every outstanding defect past its due date, flattened across all entries.

    Returns one dict per overdue defect carrying the owning warranty's identity
    (``warranty_id``, ``warranty_reference``, ``title``) and the defect's own
    ``severity``, ``status`` and ISO ``due_date``, so the post-handover team can
    chase each one back to its entry without a second lookup. An empty list means
    nothing is overdue.
    """
    out: list[dict[str, Any]] = []
    for warranty in warranties:
        for defect in warranty.defects:
            if defect.is_overdue(as_of):
                out.append(
                    {
                        "warranty_id": warranty.id,
                        "warranty_reference": warranty.reference,
                        "title": warranty.title,
                        "severity": defect.severity,
                        "status": defect.status,
                        "due_date": (defect.due_date.isoformat() if defect.due_date is not None else None),
                    },
                )
    return out


def total_open_defects(warranties: Iterable[WarrantyRow]) -> int:
    """Total number of outstanding defects across every entry."""
    return sum(open_defect_count(warranty) for warranty in warranties)


# -- Counts ------------------------------------------------------------------


def status_counts(warranties: Iterable[WarrantyRow]) -> dict[str, int]:
    """Count entries by status, zero-filling every known status in canonical order."""
    counts: dict[str, int] = dict.fromkeys(ALL_WARRANTY_STATUSES, 0)
    for warranty in warranties:
        if warranty.status in counts:
            counts[warranty.status] += 1
        else:  # defensive: an unknown status still shows up so nothing is lost
            counts[warranty.status] = counts.get(warranty.status, 0) + 1
    return counts


def warranty_type_counts(warranties: Iterable[WarrantyRow]) -> dict[str, int]:
    """Count entries by warranty type, zero-filling every type plus unassigned.

    An entry with no warranty type set is counted under :data:`UNASSIGNED`; an
    out-of-vocabulary type value is still counted (defensively) rather than
    dropped, so the per-type counts always sum to the total.
    """
    counts: dict[str, int] = dict.fromkeys(ALL_WARRANTY_TYPES, 0)
    counts[UNASSIGNED] = 0
    for warranty in warranties:
        key = warranty.warranty_type if warranty.warranty_type is not None else UNASSIGNED
        if key in counts:
            counts[key] += 1
        else:  # defensive: an unknown type still shows up so nothing is lost
            counts[key] = counts.get(key, 0) + 1
    return counts


# -- Health ------------------------------------------------------------------


def overall_health_score(warranties: Iterable[WarrantyRow], as_of: date) -> Decimal | None:
    """Share of entries carrying no open or overdue defect, guarded to ``None``.

    ``(total - entries_with_open_or_overdue) / total * 100`` quantised to 2 dp, or
    ``None`` when the register is empty. A register where nothing is outstanding
    scores 100; one where every entry carries an open defect scores 0. Expiry is
    deliberately not folded into this score - it measures defect cleanliness, the
    thing that actually holds a retention back.
    """
    materialised = list(warranties)
    total = len(materialised)
    unhealthy = sum(1 for warranty in materialised if has_open_or_overdue(warranty, as_of))
    return safe_percent(total - unhealthy, total)


def is_clean(warranties: Iterable[WarrantyRow], as_of: date) -> bool:
    """True when nothing is outstanding and nothing has expired unclosed.

    The honest single-flag summary of the register: an open defect anywhere, or a
    live entry whose DLP has run out without being closed, both mean the register
    needs attention. Vacuously true for an empty register - there is nothing to be
    unclean.
    """
    materialised = list(warranties)
    if total_open_defects(materialised) > 0:
        return False
    return not any(is_expired(warranty, as_of) for warranty in materialised)


# -- Per-subcontractor health ------------------------------------------------


def _subcontractor_key(warranty: WarrantyRow) -> str:
    """The grouping label for an entry: its responsible subcontractor or unassigned.

    A ``None`` or blank (whitespace-only) ``subcontractor_name`` groups under
    :data:`UNASSIGNED` so every entry lands in exactly one bucket and the
    per-subcontractor totals always sum to the register total.
    """
    name = warranty.subcontractor_name
    if name is None:
        return UNASSIGNED
    stripped = name.strip()
    return stripped if stripped else UNASSIGNED


def _ordered_subcontractors(warranties: list[WarrantyRow]) -> list[str]:
    """Present subcontractor labels: named ones sorted, then unassigned last.

    Subcontractor names are free text with no canonical order, so named ones are
    sorted alphabetically for a stable, testable output; the ``unassigned``
    bucket, when present, is always appended last.
    """
    keys = {_subcontractor_key(warranty) for warranty in warranties}
    ordered = sorted(key for key in keys if key != UNASSIGNED)
    if UNASSIGNED in keys:
        ordered.append(UNASSIGNED)
    return ordered


def _subcontractor_health(
    warranties: list[WarrantyRow],
    label: str,
    as_of: date,
) -> SubcontractorDlpHealth:
    """Build a :class:`SubcontractorDlpHealth` for an already-filtered entry list.

    ``open_defects`` sums the outstanding defects across the subcontractor's
    entries, ``overdue_defects`` counts the overdue ones, and ``health_score`` is
    the share of the subcontractor's entries carrying neither an open nor an
    overdue defect, guarded to ``None`` for an empty group.
    """
    total = len(warranties)
    unhealthy = sum(1 for warranty in warranties if has_open_or_overdue(warranty, as_of))
    return SubcontractorDlpHealth(
        subcontractor=label,
        total=total,
        open_defects=sum(open_defect_count(warranty) for warranty in warranties),
        overdue_defects=sum(overdue_defect_count(warranty, as_of) for warranty in warranties),
        health_score=safe_percent(total - unhealthy, total),
    )


def subcontractor_health(warranties: Iterable[WarrantyRow], as_of: date) -> list[SubcontractorDlpHealth]:
    """Per-subcontractor DLP health, one entry per responsible subcontractor present."""
    materialised = list(warranties)
    return [
        _subcontractor_health(
            [warranty for warranty in materialised if _subcontractor_key(warranty) == label],
            label,
            as_of,
        )
        for label in _ordered_subcontractors(materialised)
    ]


# -- Report assembly ---------------------------------------------------------


def build_report(
    warranties: Iterable[WarrantyRow],
    as_of: date,
    horizon_days: int = 30,
) -> DlpRegister:
    """Assemble the full defects-liability register rollup in a single pass.

    Computes the per-status and per-warranty-type counts, the expiring and expired
    lists, the total open defect load and the overdue-defect list, the
    per-subcontractor health view, the single overall health score, the ``is_clean``
    flag (nothing outstanding and nothing expired unclosed), and - the valuable
    output - the retention-release-ready list (entries whose DLP has ended with no
    outstanding defects, clear for the final retention money).

    Args:
        warranties: The register entries with their defects.
        as_of: The date the expiry, overdue and readiness checks are evaluated
            against.
        horizon_days: How many days ahead an entry counts as "expiring". Defaults
            to 30. A non-positive horizon simply yields an empty expiring list.

    Returns:
        A :class:`DlpRegister` value object.
    """
    materialised = list(warranties)
    return DlpRegister(
        as_of=as_of,
        horizon_days=horizon_days,
        total=len(materialised),
        per_status=status_counts(materialised),
        per_warranty_type=warranty_type_counts(materialised),
        total_open_defects=total_open_defects(materialised),
        overall_health_score=overall_health_score(materialised, as_of),
        is_clean=is_clean(materialised, as_of),
        expiring=expiring_warranties(materialised, as_of, horizon_days),
        expired=expired_warranties(materialised, as_of),
        overdue_defects=overdue_defects(materialised, as_of),
        retention_release_ready=retention_release_ready_warranties(materialised, as_of),
        subcontractors=subcontractor_health(materialised, as_of),
    )
