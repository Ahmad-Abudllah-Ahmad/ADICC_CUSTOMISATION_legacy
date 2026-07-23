# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure cross-source commitment / action register.

A project accumulates open commitments in many places at once: action items
minuted in meetings, mitigation actions on the risk register, change orders
awaiting the party that holds the ball, and RFIs / submittals with a response
date. Each module shows its own slice, but nobody owes-list is consolidated,
so an owner cannot see everything that is on them and a manager cannot see who
is the most loaded or the most overdue. This engine folds all of those into one
owner-ranked, overdue-first register.

Given every open :class:`RegisterItem` (already gathered from its source module
by the thin service layer), :func:`build_register` produces a
:class:`CommitmentRegister`: one unified row per commitment (its source, owner,
title, due date, whether it is overdue and how old it is), ordered overdue-first
then by soonest due date, plus summary counts (total open, overdue, a per-owner
load ranking, and a per-source tally).

Whether a raw record still counts as an open commitment is decided here too, per
source, via :func:`is_open_commitment`, so the same "surface it unless it is
explicitly done" rule the cycle-time board uses applies across every source and
stays unit-testable.

No database, no ORM, no ``app.*`` imports beyond the sibling pure date parser -
stdlib only - so it unit-tests on the local Python 3.11 runner exactly like the
cycle-time and coordination engines. The engine never reads the wall clock
itself; the caller passes the current moment in as ``now``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.modules.change_intelligence.cycle_time import parse_due

#: Bucket label for an open commitment with no owner set.
UNASSIGNED = "unassigned"

# Stable source tokens for the modules a commitment can originate from. These
# are surfaced verbatim to the client so a row can be traced back to its module.
SOURCE_MEETING_ACTION = "meeting_action"
SOURCE_RISK_ACTION = "risk_action"
SOURCE_CHANGE_ORDER = "change_order"
SOURCE_RFI = "rfi"
SOURCE_SUBMITTAL = "submittal"

#: Per-source set of statuses that mean the commitment is settled (done) and is
#: no longer owed by anyone. Compared case-insensitively. A status not listed
#: here is treated as still open, so the register errs toward surfacing an
#: outstanding action rather than hiding it (the cycle-time board's rule).
#:
#: * meeting / risk actions carry their own tiny status vocabulary
#:   (open / in_progress / completed / cancelled);
#: * a change order mirrors the cycle-time board's closed set for change orders;
#: * an RFI is done once closed / cancelled / withdrawn;
#: * a submittal is done once the reviewer has decided it (approved / rejected)
#:   or it is closed - a ``revise_and_resubmit`` bounces back to the submitter
#:   and therefore stays an open commitment.
DONE_STATUSES: dict[str, frozenset[str]] = {
    SOURCE_MEETING_ACTION: frozenset({"completed", "complete", "done", "closed", "cancelled", "canceled"}),
    SOURCE_RISK_ACTION: frozenset({"completed", "complete", "done", "closed", "cancelled", "canceled", "resolved"}),
    SOURCE_CHANGE_ORDER: frozenset({"executed", "rejected", "cancelled", "canceled", "withdrawn", "closed", "voided"}),
    SOURCE_RFI: frozenset({"closed", "cancelled", "canceled", "void", "voided", "withdrawn", "superseded"}),
    SOURCE_SUBMITTAL: frozenset(
        {
            "closed",
            "cancelled",
            "canceled",
            "void",
            "voided",
            "withdrawn",
            "superseded",
            "approved",
            "approved_as_noted",
            "rejected",
        }
    ),
}


def is_open_commitment(source: str, status: str | None) -> bool:
    """True when a *source* record in *status* is still an open commitment.

    An unknown source or an unknown status both default to open - a consolidated
    owe-list should surface a record it cannot classify rather than silently drop
    it.
    """
    if status is None:
        return True
    done = DONE_STATUSES.get(source, frozenset())
    return status.strip().lower() not in done


@dataclass(frozen=True)
class RegisterItem:
    """One raw commitment as gathered from its source module.

    ``owner`` is the party that owes the action (a name, role label or user id);
    a blank owner buckets under :data:`UNASSIGNED`. ``due_date`` is the raw
    stored string (ISO-8601 date or datetime) parsed defensively here; a blank
    or unparseable value is treated as "no due date". ``opened_at`` is when the
    commitment first arose (its own or its parent record's creation time) and
    may be ``None`` when the source carries no timestamp.
    """

    source: str
    ref_id: str
    code: str
    title: str
    owner: str
    status: str | None
    due_date: str | None = None
    opened_at: datetime | None = None


@dataclass(frozen=True)
class Commitment:
    """One open commitment in the unified register."""

    source: str
    ref_id: str
    code: str
    title: str
    owner: str
    due_date: str | None
    overdue: bool
    days_overdue: float
    age_days: float | None


@dataclass(frozen=True)
class OwnerLoad:
    """How many open commitments sit with one owner, and how many are overdue."""

    owner: str
    open_count: int
    overdue_count: int


@dataclass(frozen=True)
class CommitmentRegister:
    """The consolidated open-commitment register for a project."""

    generated_at: str
    total_open: int
    overdue_count: int
    by_owner: list[OwnerLoad]
    by_source: dict[str, int]
    items: list[Commitment]


def _as_utc(value: datetime | None) -> datetime | None:
    """Coerce a naive or aware datetime to aware UTC, passing ``None`` through."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _days_between(start: datetime, end: datetime) -> float:
    """Whole-and-fractional days from *start* to *end*, rounded to 2 places."""
    return round((end - start).total_seconds() / 86400.0, 2)


def build_register(items: list[RegisterItem], now: datetime) -> CommitmentRegister:
    """Fold *items* into an owner-ranked, overdue-first commitment register.

    Only items that :func:`is_open_commitment` classifies as still open are
    kept. Each open item is measured for overdue-ness against its due date and
    for age against its opened timestamp. Rows are ordered overdue-first (most
    overdue first), then by soonest due date, then no-date, with owner and
    ``ref_id`` breaking ties so ordering is stable and deterministic. The
    per-owner load ranking is ordered by open count (then overdue, then name).
    """
    now_utc = _as_utc(now) or now

    ranked: list[tuple[tuple[bool, float, float, str, str], Commitment]] = []
    by_source: dict[str, int] = {}
    for it in items:
        if not is_open_commitment(it.source, it.status):
            continue

        due = parse_due(it.due_date)
        overdue = due is not None and now_utc > due
        days_overdue = _days_between(due, now_utc) if overdue else 0.0
        opened = _as_utc(it.opened_at)
        age_days = _days_between(opened, now_utc) if opened is not None else None
        owner = (it.owner or "").strip() or UNASSIGNED

        by_source[it.source] = by_source.get(it.source, 0) + 1

        # Sort key: overdue first (False < True so negate), most overdue first
        # (negate days), then soonest due first (unparseable/no-date sorts last
        # via +inf), then owner and ref for a stable order.
        due_epoch = due.timestamp() if due is not None else float("inf")
        sort_key = (not overdue, -days_overdue, due_epoch, owner, it.ref_id)
        ranked.append(
            (
                sort_key,
                Commitment(
                    source=it.source,
                    ref_id=it.ref_id,
                    code=it.code,
                    title=it.title,
                    owner=owner,
                    due_date=it.due_date,
                    overdue=overdue,
                    days_overdue=days_overdue,
                    age_days=age_days,
                ),
            )
        )

    ranked.sort(key=lambda pair: pair[0])
    commitments = [row for _key, row in ranked]

    # Per-owner load.
    owner_open: dict[str, int] = {}
    owner_overdue: dict[str, int] = {}
    for row in commitments:
        owner_open[row.owner] = owner_open.get(row.owner, 0) + 1
        if row.overdue:
            owner_overdue[row.owner] = owner_overdue.get(row.owner, 0) + 1
    by_owner = [
        OwnerLoad(owner=owner, open_count=count, overdue_count=owner_overdue.get(owner, 0))
        for owner, count in owner_open.items()
    ]
    by_owner.sort(key=lambda o: (-o.open_count, -o.overdue_count, o.owner))

    return CommitmentRegister(
        generated_at=now_utc.isoformat(),
        total_open=len(commitments),
        overdue_count=sum(1 for row in commitments if row.overdue),
        by_owner=by_owner,
        by_source=dict(sorted(by_source.items())),
        items=commitments,
    )


__all__ = [
    "DONE_STATUSES",
    "SOURCE_CHANGE_ORDER",
    "SOURCE_MEETING_ACTION",
    "SOURCE_RFI",
    "SOURCE_RISK_ACTION",
    "SOURCE_SUBMITTAL",
    "UNASSIGNED",
    "Commitment",
    "CommitmentRegister",
    "OwnerLoad",
    "RegisterItem",
    "build_register",
    "is_open_commitment",
]
