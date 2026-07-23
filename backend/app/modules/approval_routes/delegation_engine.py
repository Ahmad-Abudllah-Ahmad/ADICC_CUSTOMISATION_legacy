# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure delegation / out-of-office resolution for approval routing.

When an approver is away their pending sign-offs stall the whole chain. A
delegation lets a user hand their approvals to a stand-in for a window of
time, optionally scoped to a single project. This module owns the *rules* for
turning a set of delegation records into "who may actually decide right now" -
with no database, no ORM and no ``app.*`` imports, so it unit-tests under
Python 3.11 exactly like :mod:`app.modules.approval_routes.sla_engine`.

The impure glue (querying delegation rows, writing the per-instance assignee
override, sending the hand-off notification) lives in the service layer.

Resolution semantics
---------------------
A chain ``A -> B -> C`` means A is out (delegating to B) and B is also out
(delegating to C). The person actually present is C, so:

* :func:`resolve_delegate` walks the chain to its terminal user.
* :func:`eligible_deciders` returns ``{base, terminal}`` - the original
  approver may always still act if they are in fact around, and the terminal
  stand-in may act on their behalf. Intermediate "also-out" users are not
  eligible, which is the whole point of chaining.

Every walk is guarded against cycles (``A -> B -> A``) and capped at
``max_hops`` so a pathological data set can never spin.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

# A walk never follows more than this many delegation links. Real out-of-office
# chains are one or two deep; the cap is a backstop against bad data, never a
# limit a legitimate configuration would reach.
DEFAULT_MAX_HOPS = 5


@dataclass(frozen=True)
class DelegationView:
    """Immutable projection of one delegation record for the pure engine.

    ``project_id is None`` means the delegation applies to every project (a
    blanket "I am on leave" hand-off); a concrete id scopes it to that project
    only. ``starts_at`` / ``ends_at`` are an optional active window; ``None``
    means open-ended on that side.
    """

    delegator_id: uuid.UUID
    delegate_id: uuid.UUID
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    project_id: uuid.UUID | None = None


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalise a datetime to timezone-aware UTC (mirrors sla_engine)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def is_active_at(
    delegation: DelegationView,
    now: datetime,
    *,
    project_id: uuid.UUID | None = None,
) -> bool:
    """Whether *delegation* is in force at *now* for the given project.

    A project-scoped delegation applies only when *project_id* matches it; a
    blanket delegation (``delegation.project_id is None``) applies everywhere.
    When the caller cannot supply a project (``project_id is None``) a
    project-scoped delegation is treated as not applicable - we never widen a
    project-scoped hand-off into a blanket one by accident.
    """
    if not delegation.is_active:
        return False
    moment = _as_utc(now)
    starts = _as_utc(delegation.starts_at)
    ends = _as_utc(delegation.ends_at)
    if starts is not None and moment is not None and moment < starts:
        return False
    if ends is not None and moment is not None and moment > ends:
        return False
    if delegation.project_id is not None and delegation.project_id != project_id:
        return False
    return True


def _active_delegate_map(
    delegations: list[DelegationView],
    now: datetime,
    project_id: uuid.UUID | None,
) -> dict[uuid.UUID, uuid.UUID]:
    """Build ``delegator -> delegate`` over the currently-active delegations.

    When a delegator has both a project-scoped and a blanket delegation active
    at once, the project-scoped one wins (it is the more specific intent).
    """
    active = [d for d in delegations if is_active_at(d, now, project_id=project_id)]
    # Sort so project-scoped rows come first; the later ``setdefault`` then
    # keeps the most specific delegation per delegator.
    active.sort(key=lambda d: d.project_id is None)
    chosen: dict[uuid.UUID, uuid.UUID] = {}
    for d in active:
        chosen.setdefault(d.delegator_id, d.delegate_id)
    return chosen


def resolve_delegate(
    base_user_id: uuid.UUID,
    delegations: list[DelegationView],
    *,
    now: datetime,
    project_id: uuid.UUID | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> uuid.UUID:
    """Walk the active delegation chain from *base_user_id* to its terminal user.

    Returns *base_user_id* itself when there is no active delegation for it.
    Cycle-safe and hop-capped: a loop or an over-long chain stops at the last
    safe user rather than raising.
    """
    by_delegator = _active_delegate_map(delegations, now, project_id)
    current = base_user_id
    visited = {current}
    hops = 0
    while current in by_delegator and hops < max_hops:
        nxt = by_delegator[current]
        if nxt in visited:
            break  # cycle - stop at the last safe user
        visited.add(nxt)
        current = nxt
        hops += 1
    return current


def eligible_deciders(
    base_user_id: uuid.UUID,
    delegations: list[DelegationView],
    *,
    now: datetime,
    project_id: uuid.UUID | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> set[uuid.UUID]:
    """Set of users allowed to decide on behalf of *base_user_id* right now.

    Always includes *base_user_id* (they may still act if present) plus the
    terminal stand-in resolved through any active delegation chain.
    """
    terminal = resolve_delegate(
        base_user_id,
        delegations,
        now=now,
        project_id=project_id,
        max_hops=max_hops,
    )
    return {base_user_id, terminal}


__all__ = [
    "DEFAULT_MAX_HOPS",
    "DelegationView",
    "eligible_deciders",
    "is_active_at",
    "resolve_delegate",
]
