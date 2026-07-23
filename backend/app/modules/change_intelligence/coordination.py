# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure action-coordination co-pilot.

Across approvals and the change family, every open item is owed by some party
(the "ball in court") and may carry a response due date. Faced with a long
list of such items, a user needs to know what to act on first. This engine
ranks the open items so the most pressing surfaces at the top, and pairs each
one with a recommended action and a short plain-language reason.

Given every open :class:`ActionItem`, :func:`build_plan` produces a
:class:`CoordinationPlan`: one :class:`CoordinationStep` per item, ordered so
that overdue items come first (most overdue first), then items due soon
(soonest first), then upcoming items (soonest first), then items with no due
date. Each step names its urgency, the days remaining until the due date (or
``None``), a recommended action, and a reason; the plan also carries the total
and the overdue / due-soon counts.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on
the local Python 3.11 runner exactly like the cycle-time and impact engines.
The engine is deterministic: it never reads the wall clock itself; the caller
passes the current moment in as ``now``. A thin service layer gathers the open
items from the approval and change modules and feeds them in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

#: How many days ahead still counts as "due soon" rather than merely upcoming.
DUE_SOON_DAYS = 2

# Urgency buckets, surfaced verbatim to the client.
URGENCY_OVERDUE = "overdue"
URGENCY_DUE_SOON = "due_soon"
URGENCY_UPCOMING = "upcoming"
URGENCY_NO_DATE = "no_date"

# Recommended actions, one per urgency bucket.
ACTION_ESCALATE = "escalate"
ACTION_NUDGE = "nudge"
ACTION_REVIEW = "review"
ACTION_AWAIT = "await"

# Rank bands. Lower sorts first. Each band reserves room for a within-band
# offset (days-based) so the bands never interleave regardless of date spread.
_BAND_OVERDUE = 0
_BAND_DUE_SOON = 1_000_000
_BAND_UPCOMING = 2_000_000
_BAND_NO_DATE = 3_000_000


@dataclass(frozen=True)
class ActionItem:
    """One open item awaiting attention.

    ``due_date`` is the raw stored string (ISO-8601 date or datetime) and is
    parsed defensively inside the engine; a blank or unparseable value is
    treated as "no due date". ``age_days`` is optional context (how long the
    item has been open) and does not affect ranking.
    """

    ref_id: str
    kind: str
    title: str
    ball_in_court: str
    status: str
    due_date: str | None = None
    age_days: int | None = None


@dataclass(frozen=True)
class CoordinationStep:
    """One ranked item in the coordination plan.

    ``days_to_due`` is the signed whole-day count from ``now`` to the due date
    (negative when overdue), or ``None`` when the item has no parseable date.
    ``rank_score`` is the sort key; lower surfaces first.
    """

    ref_id: str
    kind: str
    title: str
    ball_in_court: str
    urgency: str
    days_to_due: int | None
    recommended_action: str
    reason: str
    rank_score: int


@dataclass(frozen=True)
class CoordinationPlan:
    """The ordered "what to act on first" plan for a set of open items."""

    generated_at: str
    total: int
    overdue_count: int
    due_soon_count: int
    steps: tuple[CoordinationStep, ...]


def parse_date(value: str | None) -> date | None:
    """Parse a stored date string to a :class:`~datetime.date`, best-effort.

    Accepts a date (``2026-07-01``) or a full datetime (``2026-07-01T09:00:00``,
    optionally with offset or trailing ``Z``). Returns ``None`` for a blank or
    unparseable value and never raises.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])  # date-only fallback
        except ValueError:
            return None


def days_between(start: date, end: date) -> int:
    """Whole days from *start* to *end* (negative when *end* precedes *start*)."""
    return (end - start).days


def classify(due_date: str | None, now: date) -> tuple[str, int | None]:
    """Bucket *due_date* relative to *now*.

    Returns ``(urgency, days_to_due)``. With no parseable date the result is
    ``(URGENCY_NO_DATE, None)``. Otherwise ``days_to_due`` is the signed day
    count from *now* to the due date: negative is overdue, ``0`` through
    :data:`DUE_SOON_DAYS` inclusive is due soon, and anything further out is
    upcoming.
    """
    due = parse_date(due_date)
    if due is None:
        return URGENCY_NO_DATE, None
    days_to_due = days_between(now, due)
    if days_to_due < 0:
        return URGENCY_OVERDUE, days_to_due
    if days_to_due <= DUE_SOON_DAYS:
        return URGENCY_DUE_SOON, days_to_due
    return URGENCY_UPCOMING, days_to_due


def recommend(urgency: str) -> tuple[str, str]:
    """Map an urgency to its recommended action and a short reason sentence."""
    if urgency == URGENCY_OVERDUE:
        return ACTION_ESCALATE, "This item is past its response due date - escalate to the owner."
    if urgency == URGENCY_DUE_SOON:
        return ACTION_NUDGE, "This item is due within the next couple of days - nudge the owner."
    if urgency == URGENCY_UPCOMING:
        return ACTION_REVIEW, "This item has a due date further out - review it and plan ahead."
    return ACTION_AWAIT, "This item has no response due date - await the owner or set a date."


def _normalize_now(now: datetime | date) -> date:
    """Reduce a datetime or date to a plain date for deterministic comparison."""
    if isinstance(now, datetime):
        return now.date()
    return now


def _rank_score(urgency: str, days_to_due: int | None) -> int:
    """Sort key: overdue band first (most overdue first), then due-soon and
    upcoming (soonest first), then no-date. Lower sorts first.
    """
    if urgency == URGENCY_OVERDUE:
        # days_to_due is negative; more negative (more overdue) must sort first,
        # so add it directly: -10 days yields a lower score than -1 day.
        return _BAND_OVERDUE + (days_to_due or 0)
    if urgency == URGENCY_DUE_SOON:
        # 0..DUE_SOON_DAYS; sooner (smaller) sorts first.
        return _BAND_DUE_SOON + (days_to_due or 0)
    if urgency == URGENCY_UPCOMING:
        # Positive and possibly large; sooner (smaller) sorts first.
        return _BAND_UPCOMING + (days_to_due or 0)
    return _BAND_NO_DATE


def build_plan(items: Iterable[ActionItem], now: datetime | date) -> CoordinationPlan:
    """Rank *items* into a :class:`CoordinationPlan` as of *now*.

    *now* may be a :class:`~datetime.datetime` or a :class:`~datetime.date`; it
    is reduced to a date for all comparisons. Each item is classified and given
    a recommended action, then steps are sorted by ``(rank_score, ref_id)`` so
    ordering is stable and deterministic.
    """
    as_of = _normalize_now(now)

    steps: list[CoordinationStep] = []
    for item in items:
        urgency, days_to_due = classify(item.due_date, as_of)
        action, reason = recommend(urgency)
        steps.append(
            CoordinationStep(
                ref_id=item.ref_id,
                kind=item.kind,
                title=item.title,
                ball_in_court=item.ball_in_court,
                urgency=urgency,
                days_to_due=days_to_due,
                recommended_action=action,
                reason=reason,
                rank_score=_rank_score(urgency, days_to_due),
            )
        )

    steps.sort(key=lambda s: (s.rank_score, s.ref_id))

    overdue_count = sum(1 for s in steps if s.urgency == URGENCY_OVERDUE)
    due_soon_count = sum(1 for s in steps if s.urgency == URGENCY_DUE_SOON)

    return CoordinationPlan(
        generated_at=as_of.isoformat(),
        total=len(steps),
        overdue_count=overdue_count,
        due_soon_count=due_soon_count,
        steps=tuple(steps),
    )


__all__ = [
    "ACTION_AWAIT",
    "ACTION_ESCALATE",
    "ACTION_NUDGE",
    "ACTION_REVIEW",
    "DUE_SOON_DAYS",
    "URGENCY_DUE_SOON",
    "URGENCY_NO_DATE",
    "URGENCY_OVERDUE",
    "URGENCY_UPCOMING",
    "ActionItem",
    "CoordinationPlan",
    "CoordinationStep",
    "build_plan",
    "classify",
    "days_between",
    "parse_date",
    "recommend",
]
