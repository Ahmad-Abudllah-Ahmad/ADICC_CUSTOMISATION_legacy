# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure change cycle-time telemetry.

Answers the project team's recurring question about open changes: what is
waiting on whom, and for how long. Given the current state of every change
record (a :class:`ChangeItem` - change order, variation notice / request /
order, or MoC entry) it builds a :class:`CycleTimeBoard`: one row per
responsible party (the "ball in court") with how many open changes sit with
them, how many are overdue, and how long they have been waiting, plus a
per-item aging list.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on
the local Python 3.11 runner exactly like the SLA and delegation engines. The
thin service layer gathers the rows from the change modules and feeds them in.

Scope note: this measures age since a change was opened and since its last
activity. Precise dwell-time per party (how long each successive holder kept
the ball) needs a recorded hand-off history, which is a later refinement; the
current board is built from present state plus the opened / last-activity
timestamps every record already carries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

#: Bucket label for an open change with no ball-in-court set.
UNASSIGNED = "unassigned"

# Stable kind tokens for the change-family record types the board spans.
KIND_CHANGE_ORDER = "change_order"
KIND_VARIATION_NOTICE = "variation_notice"
KIND_VARIATION_REQUEST = "variation_request"
KIND_VARIATION_ORDER = "variation_order"
KIND_MOC_ENTRY = "moc_entry"

#: Per-kind set of statuses that count as resolved (closed), compared
#: case-insensitively. A status not listed here is treated as still open, so
#: the board errs toward surfacing outstanding work rather than hiding it.
#: Derived from each module's own state machine: change orders end at
#: ``executed`` (and a ``rejected`` order is not awaiting anyone); a variation
#: request closes once decided or converted to an order; a variation order ends
#: at ``completed``; a notice closes once responded; a MoC ends at
#: ``implemented`` or ``declined``.
CLOSED_STATUSES: dict[str, frozenset[str]] = {
    KIND_CHANGE_ORDER: frozenset({"executed", "rejected", "cancelled", "withdrawn", "closed", "voided"}),
    KIND_VARIATION_NOTICE: frozenset({"responded", "closed", "cancelled", "withdrawn"}),
    KIND_VARIATION_REQUEST: frozenset({"approved", "rejected", "converted_to_vo", "cancelled", "withdrawn", "closed"}),
    KIND_VARIATION_ORDER: frozenset({"completed", "voided", "cancelled", "closed"}),
    KIND_MOC_ENTRY: frozenset({"implemented", "declined", "rejected", "cancelled", "closed"}),
}


def is_open_status(kind: str, status: str | None) -> bool:
    """True when a record of *kind* in *status* is still outstanding.

    Unknown kinds and unknown statuses default to open - a "waiting on whom"
    board should surface a record it cannot classify rather than silently drop
    it.
    """
    if status is None:
        return True
    closed = CLOSED_STATUSES.get(kind, frozenset())
    return status.strip().lower() not in closed


@dataclass(frozen=True)
class ChangeItem:
    """Present-state projection of one change record for the engine.

    ``response_due_date`` is the raw stored string (ISO-8601 date or datetime)
    and is parsed defensively inside the engine; an unparseable value is simply
    treated as "no due date". ``last_activity_at`` may be ``None`` when the
    record has never been updated since creation.
    """

    id: str
    kind: str
    code: str
    title: str
    status: str
    is_open: bool
    ball_in_court: str | None
    response_due_date: str | None
    opened_at: datetime
    last_activity_at: datetime | None = None


@dataclass(frozen=True)
class ItemAging:
    """Per-item aging row in the board."""

    id: str
    kind: str
    code: str
    title: str
    status: str
    party: str
    age_days: float
    stale_days: float | None
    response_due_date: str | None
    overdue: bool
    days_to_due: float | None


@dataclass(frozen=True)
class PartyLoad:
    """How much open change work sits with one responsible party."""

    party: str
    open_count: int
    overdue_count: int
    oldest_age_days: float
    total_age_days: float

    @property
    def avg_age_days(self) -> float:
        return round(self.total_age_days / self.open_count, 2) if self.open_count else 0.0


@dataclass(frozen=True)
class CycleTimeBoard:
    """The "waiting on whom" board for a project's open changes."""

    as_of: datetime
    total_open: int
    total_overdue: int
    unassigned_open: int
    parties: list[PartyLoad]
    items: list[ItemAging]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_due(value: str | None) -> datetime | None:
    """Parse a stored due-date string to aware UTC, or ``None`` if unusable.

    Accepts a date (``2026-07-01``) or a datetime (``2026-07-01T09:00:00+00:00``
    / trailing ``Z``). Never raises - a malformed value yields ``None``.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(text[:10])  # date-only fallback
        except ValueError:
            return None
    return _as_utc(parsed)


def _days_between(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds() / 86400.0, 2)


def is_overdue(response_due_date: str | None, now: datetime) -> bool:
    """True when *response_due_date* parses and is strictly before *now*."""
    due = parse_due(response_due_date)
    return due is not None and _as_utc(now) > due


def build_board(items: list[ChangeItem], now: datetime) -> CycleTimeBoard:
    """Aggregate open change items into a per-party board + aging list.

    Only ``is_open`` items count. Each is bucketed by its ball-in-court party
    (``UNASSIGNED`` when none). Parties are ordered by open count (then
    overdue, then name); items by overdue first, then oldest first.
    """
    now_utc = _as_utc(now) or now

    aging: list[ItemAging] = []
    for it in items:
        if not it.is_open:
            continue
        opened = _as_utc(it.opened_at) or now_utc
        last = _as_utc(it.last_activity_at)
        due = parse_due(it.response_due_date)
        overdue = due is not None and now_utc > due
        aging.append(
            ItemAging(
                id=it.id,
                kind=it.kind,
                code=it.code,
                title=it.title,
                status=it.status,
                party=it.ball_in_court or UNASSIGNED,
                age_days=_days_between(opened, now_utc),
                stale_days=_days_between(last, now_utc) if last is not None else None,
                response_due_date=it.response_due_date,
                overdue=overdue,
                days_to_due=_days_between(now_utc, due) if due is not None else None,
            )
        )

    # Aggregate per party.
    by_party: dict[str, list[ItemAging]] = {}
    for row in aging:
        by_party.setdefault(row.party, []).append(row)

    parties: list[PartyLoad] = []
    for party, rows in by_party.items():
        ages = [r.age_days for r in rows]
        parties.append(
            PartyLoad(
                party=party,
                open_count=len(rows),
                overdue_count=sum(1 for r in rows if r.overdue),
                oldest_age_days=max(ages) if ages else 0.0,
                total_age_days=round(sum(ages), 2),
            )
        )

    parties.sort(key=lambda p: (-p.open_count, -p.overdue_count, p.party))
    aging.sort(key=lambda r: (not r.overdue, -r.age_days, r.code))

    return CycleTimeBoard(
        as_of=now_utc,
        total_open=len(aging),
        total_overdue=sum(1 for r in aging if r.overdue),
        unassigned_open=sum(1 for r in aging if r.party == UNASSIGNED),
        parties=parties,
        items=aging,
    )


__all__ = [
    "CLOSED_STATUSES",
    "KIND_CHANGE_ORDER",
    "KIND_MOC_ENTRY",
    "KIND_VARIATION_NOTICE",
    "KIND_VARIATION_ORDER",
    "KIND_VARIATION_REQUEST",
    "UNASSIGNED",
    "ChangeItem",
    "CycleTimeBoard",
    "ItemAging",
    "PartyLoad",
    "build_board",
    "is_open_status",
    "is_overdue",
    "parse_due",
]
