# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure proactive change watch.

Answers the question the project team only ever asks too late: which open change
items are quietly going wrong right now. The cycle-time board already says what
is overdue and waiting on whom; this engine goes a step further and classifies
each change against a small set of failure modes so a watchlist (or a daily
digest) can surface the ones drifting toward trouble before anyone chases them.

Given the present state of every change record (a :class:`WatchItem`) it builds a
:class:`WatchSummary`: one :class:`WatchResult` per item carrying its
classification, the human-stable reasons behind it, and the idle / overdue day
math, plus a per-class count and the items ordered worst-first.

Each item is tested against three failure modes, every one driven by documented
threshold constants:

* **stalled** - the change is open, past its due date (``now > due_at``), and has
  gone idle beyond :data:`STALE_IDLE_DAYS` (measured from its last movement,
  falling back to when it was opened). It is late and nobody is touching it.
* **incomplete** - the change's completeness score is below
  :data:`INCOMPLETE_THRESHOLD`. It is not yet fit to circulate / decide, mirroring
  the clarifier's completeness fraction.
* **lost** - the change is open, has gone idle beyond :data:`LOST_IDLE_DAYS`, and
  has no owner assigned. Nobody holds it and nobody is moving it; it is at risk
  of being forgotten entirely.

An item can satisfy several modes at once. Its single ``classification`` is the
most severe matched mode (``lost`` > ``stalled`` > ``incomplete`` > ``ok``), but
``reasons`` lists every matched mode so a UI can explain the full picture. A
change in a closed status (see :data:`CLOSED_STATUSES`) is never flagged - it is
resolved, not drifting - and is classified ``ok`` with no reasons.

No database, no ORM, no ``app.*`` imports - stdlib plus datetime only - so it
unit-tests on the local Python 3.11 runner exactly like the cycle-time,
ownership-chain and clarifier engines it draws its ideas from. It takes "now" as
a parameter and reads no clock, so identical inputs always yield an identical
result.

Units: ``idle_days`` and ``overdue_days`` are float day counts (seconds / 86400,
rounded to two decimals, clamped at zero) to match the cycle-time board's age
figures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# --------------------------------------------------------------------------- #
# Classifications, worst-first. ``classification`` on a result is always one of
# these tokens; ``CLASS_RANK`` fixes their severity order for selection and for
# the worst-first ordering of the summary.
# --------------------------------------------------------------------------- #

#: The change is open, overdue, and idle beyond the stall threshold.
CLASS_STALLED = "stalled"

#: The change's completeness score is below the incomplete threshold.
CLASS_INCOMPLETE = "incomplete"

#: The change is open, long idle, and has no owner - at risk of being dropped.
CLASS_LOST = "lost"

#: Nothing is wrong - the change is not drifting (or it is already closed).
CLASS_OK = "ok"

#: Severity rank per classification (higher == worse). Used both to pick the
#: single classification when several modes match and to order the summary
#: worst-first. ``ok`` is the floor.
CLASS_RANK: dict[str, int] = {
    CLASS_OK: 0,
    CLASS_INCOMPLETE: 1,
    CLASS_STALLED: 2,
    CLASS_LOST: 3,
}

#: Every classification key, in worst-first order. ``WatchSummary.counts``
#: always carries every one of these (zero when none), so a UI never has to
#: guard for a missing key.
ALL_CLASSES: tuple[str, ...] = (CLASS_LOST, CLASS_STALLED, CLASS_INCOMPLETE, CLASS_OK)

# --------------------------------------------------------------------------- #
# Threshold constants. Documented and exported so a UI / service can describe
# the watch rules without re-deriving the cut points.
# --------------------------------------------------------------------------- #

#: Days of inactivity past which an open, overdue change counts as *stalled*.
#: A change can be a little overdue and still be in active hand-off; only once it
#: has also gone untouched for this long is it flagged as stalled. Idle time is
#: measured from the last movement, falling back to when it was opened.
STALE_IDLE_DAYS = 7.0

#: Days of inactivity past which an open, unowned change counts as *lost*.
#: Deliberately longer than :data:`STALE_IDLE_DAYS`: losing track of a change
#: entirely is a higher bar than it merely stalling, and only an item with no
#: owner can reach it.
LOST_IDLE_DAYS = 21.0

#: Completeness score (a fraction in ``[0, 1]``, mirroring the clarifier's
#: completeness) below which a change is flagged *incomplete* - not yet carrying
#: the key pieces (cost / schedule / clause / responsible party) it needs to be
#: fit to circulate. The boundary is inclusive-open: a score exactly at the
#: threshold is considered complete enough and is not flagged.
INCOMPLETE_THRESHOLD = 0.5

#: Statuses (compared case-insensitively, whitespace-trimmed) that count as
#: resolved / closed. A change in one of these is never flagged - it is done,
#: not drifting. Mirrors the union of the per-kind closed sets the cycle-time
#: board uses, kept as one flat set here because the watch rules do not vary by
#: kind. An empty / ``None`` status is treated as open (surface it rather than
#: hide it).
CLOSED_STATUSES: frozenset[str] = frozenset(
    {
        "executed",
        "rejected",
        "cancelled",
        "withdrawn",
        "closed",
        "voided",
        "responded",
        "approved",
        "converted_to_vo",
        "completed",
        "implemented",
        "declined",
        "resolved",
        "done",
    }
)

# --------------------------------------------------------------------------- #
# Stable reason tokens. ``reasons`` on a result holds a subset of these, one per
# matched failure mode, in worst-first order.
# --------------------------------------------------------------------------- #

REASON_STALLED = "stalled_overdue_and_idle"
REASON_INCOMPLETE = "incomplete_below_threshold"
REASON_LOST = "lost_idle_and_unowned"


@dataclass(frozen=True)
class WatchItem:
    """Present-state projection of one change record for the watch engine.

    Attributes
    ----------
    change_id:
        Stable identifier of the change record (used for tie-break ordering).
    kind:
        Change-family kind token (mirrors
        :mod:`app.modules.change_intelligence.cycle_time` ``KIND_*``); carried
        through for display and not used in the maths.
    status:
        The record's current status. Compared case-insensitively against
        :data:`CLOSED_STATUSES`; ``None`` / empty is treated as open.
    opened_at:
        When the change was opened. Used as the idle-time baseline when
        ``last_movement_at`` is ``None``.
    last_movement_at:
        When the change last moved (last activity / status change / hand-off).
        ``None`` when it has not moved since it was opened, in which case idle
        time is measured from ``opened_at``.
    due_at:
        The response / decision due instant, if any. A change is "overdue" when
        ``now`` is strictly after this. ``None`` means no due date, so the change
        can never be overdue (and therefore never *stalled*).
    completeness_score:
        Fraction in ``[0, 1]`` of the key pieces the change already carries
        (mirrors the clarifier's completeness). Below
        :data:`INCOMPLETE_THRESHOLD` flags the change *incomplete*.
    has_owner:
        Whether the change has a responsible party / ball-in-court assigned. An
        open, long-idle change with no owner is flagged *lost*.
    """

    change_id: str
    kind: str
    status: str | None
    opened_at: datetime
    last_movement_at: datetime | None
    due_at: datetime | None
    completeness_score: float
    has_owner: bool


@dataclass(frozen=True)
class WatchResult:
    """The watch classification of one change.

    Attributes
    ----------
    change_id / kind:
        Carried through from the input for display + stable ordering.
    classification:
        The single most severe matched failure mode, one of :data:`CLASS_LOST`
        / :data:`CLASS_STALLED` / :data:`CLASS_INCOMPLETE` / :data:`CLASS_OK`.
    reasons:
        Every matched failure-mode reason token, worst-first. Empty for an
        ``ok`` (or closed) change.
    idle_days:
        Days since the change last moved (from ``last_movement_at``, falling
        back to ``opened_at``), clamped at zero.
    overdue_days:
        Days the change is past ``due_at`` (zero when not overdue or no due
        date), clamped at zero.
    """

    change_id: str
    kind: str
    classification: str
    reasons: tuple[str, ...]
    idle_days: float
    overdue_days: float


@dataclass(frozen=True)
class WatchSummary:
    """Portfolio roll-up over a set of classified change items.

    Attributes
    ----------
    item_count:
        Number of changes assessed.
    counts:
        Count of items in each classification, keyed by the :data:`CLASS_*`
        tokens. Every class key is always present (zero when none).
    items:
        The per-item results, ordered worst-first (most severe classification
        first; ties broken by most idle, then most overdue, then ``change_id``).
    """

    item_count: int
    counts: dict[str, int]
    items: tuple[WatchResult, ...] = field(default_factory=tuple)


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to aware UTC; ``None`` passes through.

    A naive datetime is assumed to already be UTC (the store persists UTC), so
    it is stamped rather than shifted.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _days_between(start: datetime, end: datetime) -> float:
    """Whole-and-fractional day count between two aware datetimes.

    Clamped at zero so an ``end`` before ``start`` never yields a negative
    figure. Rounded to two decimals to match the cycle-time board.
    """
    seconds = (end - start).total_seconds()
    if seconds < 0:
        seconds = 0.0
    return round(seconds / 86400.0, 2)


def is_closed_status(status: str | None) -> bool:
    """True when *status* is a resolved / closed status.

    Compared case-insensitively and whitespace-trimmed against
    :data:`CLOSED_STATUSES`. ``None`` / empty is treated as open (not closed).
    """
    if not status:
        return False
    return status.strip().lower() in CLOSED_STATUSES


def _idle_days(item: WatchItem, now_utc: datetime) -> float:
    """Days the change has been idle, from last movement else opened-at."""
    last = _as_utc(item.last_movement_at)
    baseline = last if last is not None else (_as_utc(item.opened_at) or now_utc)
    return _days_between(baseline, now_utc)


def _overdue_days(item: WatchItem, now_utc: datetime) -> float:
    """Days the change is past its due date; zero when not overdue / no due."""
    due = _as_utc(item.due_at)
    if due is None or now_utc <= due:
        return 0.0
    return _days_between(due, now_utc)


def classify(item: WatchItem, *, now: datetime) -> WatchResult:
    """Classify one change item against the watch failure modes.

    Computes idle and overdue day math, evaluates the stalled / incomplete /
    lost rules (a closed-status change matches none), records every matched
    reason worst-first, and sets ``classification`` to the most severe matched
    mode (or :data:`CLASS_OK`). Pure and deterministic: identical input and
    ``now`` always yield an identical result.

    Rules (every threshold a documented constant):

    * **stalled** - open AND ``now > due_at`` AND ``idle_days >
      STALE_IDLE_DAYS``.
    * **incomplete** - ``completeness_score < INCOMPLETE_THRESHOLD``.
    * **lost** - open AND ``idle_days > LOST_IDLE_DAYS`` AND not ``has_owner``.

    A change in a closed status (:func:`is_closed_status`) is never flagged and
    is classified ``ok`` with no reasons (its idle / overdue math is still
    reported for display).
    """
    now_utc = _as_utc(now) or now
    idle = _idle_days(item, now_utc)
    overdue = _overdue_days(item, now_utc)

    closed = is_closed_status(item.status)

    stalled = (not closed) and overdue > 0.0 and idle > STALE_IDLE_DAYS
    incomplete = (not closed) and item.completeness_score < INCOMPLETE_THRESHOLD
    lost = (not closed) and idle > LOST_IDLE_DAYS and not item.has_owner

    # Collect matched reasons worst-first (lost, stalled, incomplete) so the
    # reasons tuple reads in the same severity order as the classification.
    reasons: list[str] = []
    if lost:
        reasons.append(REASON_LOST)
    if stalled:
        reasons.append(REASON_STALLED)
    if incomplete:
        reasons.append(REASON_INCOMPLETE)

    # Single classification = the most severe matched mode (or ok).
    if lost:
        classification = CLASS_LOST
    elif stalled:
        classification = CLASS_STALLED
    elif incomplete:
        classification = CLASS_INCOMPLETE
    else:
        classification = CLASS_OK

    return WatchResult(
        change_id=item.change_id,
        kind=item.kind,
        classification=classification,
        reasons=tuple(reasons),
        idle_days=idle,
        overdue_days=overdue,
    )


def build_watch(items: list[WatchItem], *, now: datetime) -> WatchSummary:
    """Classify every change item and roll them into a :class:`WatchSummary`.

    Each item is classified via :func:`classify`; the results are counted per
    classification (every :data:`CLASS_*` key present, zero when none) and
    ordered worst-first: most severe classification (by :data:`CLASS_RANK`)
    first, ties broken by most idle, then most overdue, then ``change_id`` for a
    fully deterministic order. Empty input yields a zeroed summary with no items.
    """
    results = [classify(it, now=now) for it in items]

    counts: dict[str, int] = dict.fromkeys(ALL_CLASSES, 0)
    for r in results:
        counts[r.classification] = counts.get(r.classification, 0) + 1

    ordered = tuple(
        sorted(
            results,
            key=lambda r: (
                -CLASS_RANK.get(r.classification, 0),
                -r.idle_days,
                -r.overdue_days,
                r.change_id,
            ),
        )
    )

    return WatchSummary(
        item_count=len(results),
        counts=counts,
        items=ordered,
    )


__all__ = [
    "ALL_CLASSES",
    "CLASS_INCOMPLETE",
    "CLASS_LOST",
    "CLASS_OK",
    "CLASS_RANK",
    "CLASS_STALLED",
    "CLOSED_STATUSES",
    "INCOMPLETE_THRESHOLD",
    "LOST_IDLE_DAYS",
    "REASON_INCOMPLETE",
    "REASON_LOST",
    "REASON_STALLED",
    "STALE_IDLE_DAYS",
    "WatchItem",
    "WatchResult",
    "WatchSummary",
    "build_watch",
    "classify",
    "is_closed_status",
]
