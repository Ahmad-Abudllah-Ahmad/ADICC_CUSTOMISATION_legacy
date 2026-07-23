# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Approval-SLA breach + escalation computation core.

Pure standard-library engine - no app.* imports, no SQLAlchemy. The
service layer feeds primitive values pulled off the ORM rows (the
``Step.sla_hours`` integer, the ``Instance.started_at`` timestamp, the
ordered escalation chain) and gets back a verdict it can persist, surface
in the UI, or turn into a reminder notification.

Design notes
------------

* Every datetime is normalised to UTC. Naive datetimes are *assumed*
  UTC rather than rejected, so a mix of naive and timezone-aware inputs
  never raises - a breach calculation must not blow up a request just
  because one timestamp lost its tzinfo somewhere upstream.
* The module is deliberately free of I/O. ``build_reminder_message``
  formats a string; it does not send anything.
* Ordinals follow the approval_routes convention: steps are numbered
  ``1..N`` and an instance's ``current_step_ordinal`` points at the live
  step. ``next_escalation_target`` therefore treats the chain as a plain
  ordered list and returns the entry that follows the current ordinal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Traffic-light verdict for an approval step against its SLA.

    Members
    -------
    OK
        Either no SLA is configured, or the deadline is comfortably in
        the future (more than ``due_soon_hours`` away).
    DUE_SOON
        The deadline has not passed yet but is within the
        ``due_soon_hours`` warning window.
    BREACHED
        ``now`` is at or past the computed due time.
    """

    OK = "OK"
    DUE_SOON = "DUE_SOON"
    BREACHED = "BREACHED"


def _as_utc(value: datetime) -> datetime:
    """Return ``value`` as a timezone-aware UTC datetime.

    A naive datetime is interpreted as already being UTC (tzinfo is
    attached, the wall-clock value is left unchanged). An aware datetime
    is converted into UTC. This is the single choke point that lets the
    rest of the module subtract two datetimes without ever risking a
    ``TypeError`` from mixing naive and aware values.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def compute_due_at(started_at: datetime, sla_hours: float | None) -> datetime | None:
    """Return the UTC deadline for a step, or ``None`` when no SLA applies.

    Parameters
    ----------
    started_at:
        When the step (or instance) became active. Naive values are
        treated as UTC.
    sla_hours:
        The allowed duration in hours, e.g. ``Step.sla_hours``. ``None``
        means the step has no SLA, so there is no deadline and the
        function returns ``None``.

    Returns
    -------
    datetime | None
        ``started_at + sla_hours`` as a timezone-aware UTC datetime, or
        ``None`` when ``sla_hours`` is ``None``.
    """
    if sla_hours is None:
        return None
    return _as_utc(started_at) + timedelta(hours=float(sla_hours))


@dataclass(frozen=True)
class BreachStatus:
    """Immutable verdict describing a step's standing against its SLA.

    Attributes
    ----------
    is_breached:
        ``True`` when ``now`` is at or past ``due_at``.
    hours_overdue:
        Hours elapsed since ``due_at`` (``>= 0``). ``0.0`` when not
        breached.
    hours_remaining:
        Hours left until ``due_at`` (``>= 0``) when still within the SLA,
        ``None`` once breached or when there is no SLA.
    due_at:
        The computed UTC deadline, or ``None`` when no SLA applies.
    severity:
        The :class:`Severity` traffic-light verdict.
    """

    is_breached: bool
    hours_overdue: float
    hours_remaining: float | None
    due_at: datetime | None
    severity: Severity


def breach_status(
    started_at: datetime,
    sla_hours: float | None,
    now: datetime,
    due_soon_hours: float = 24.0,
) -> BreachStatus:
    """Evaluate a step against its SLA at instant ``now``.

    Rules
    -----
    * ``sla_hours is None`` -> :attr:`Severity.OK`, ``due_at`` ``None``,
      not breached, no remaining time. The step simply has no clock.
    * Otherwise ``due_at = started_at + sla_hours``:

        - ``now >= due_at`` -> :attr:`Severity.BREACHED`,
          ``hours_overdue = (now - due_at)`` in hours,
          ``hours_remaining`` is ``None``.
        - ``0 < remaining <= due_soon_hours`` -> :attr:`Severity.DUE_SOON`.
        - ``remaining > due_soon_hours`` -> :attr:`Severity.OK`.

    All datetimes are normalised to UTC first, so passing a naive value
    for any of ``started_at`` / ``now`` is safe and never raises.

    Parameters
    ----------
    started_at:
        When the step became active.
    sla_hours:
        Allowed duration in hours, or ``None`` for no SLA.
    now:
        The instant to evaluate against (usually the current time).
    due_soon_hours:
        Width of the warning window before the deadline, in hours.
        Defaults to 24.0.

    Returns
    -------
    BreachStatus
        The frozen verdict.
    """
    due_at = compute_due_at(started_at, sla_hours)
    if due_at is None:
        return BreachStatus(
            is_breached=False,
            hours_overdue=0.0,
            hours_remaining=None,
            due_at=None,
            severity=Severity.OK,
        )

    now_utc = _as_utc(now)
    delta_hours = (now_utc - due_at).total_seconds() / 3600.0

    if delta_hours >= 0.0:
        # At or past the deadline.
        return BreachStatus(
            is_breached=True,
            hours_overdue=delta_hours,
            hours_remaining=None,
            due_at=due_at,
            severity=Severity.BREACHED,
        )

    remaining = -delta_hours
    severity = Severity.DUE_SOON if remaining <= due_soon_hours else Severity.OK
    return BreachStatus(
        is_breached=False,
        hours_overdue=0.0,
        hours_remaining=remaining,
        due_at=due_at,
        severity=severity,
    )


def next_escalation_target(current_ordinal: int, escalation_chain: list) -> Any | None:
    """Return the chain entry that follows ``current_ordinal``.

    The escalation chain is a plain ordered list - each element is
    whatever the caller put there (a user id, a role name, a small
    descriptor object). Following the approval_routes 1-based ordinal
    convention, the entry "after" ``current_ordinal`` lives at list index
    ``current_ordinal`` (the element at index ``current_ordinal - 1`` is
    the current one).

    Parameters
    ----------
    current_ordinal:
        The 1-based ordinal of the step currently holding the approval.
    escalation_chain:
        Ordered list of escalation targets.

    Returns
    -------
    object | None
        The next target, or ``None`` when ``current_ordinal`` is already
        at (or past) the end of the chain, when the chain is empty, or
        when ``current_ordinal`` is below 1. Pure list indexing - never
        raises ``IndexError``.
    """
    if not escalation_chain:
        return None
    next_index = current_ordinal  # element at current_ordinal-1 is current
    if next_index < 1 or next_index >= len(escalation_chain):
        return None
    return escalation_chain[next_index]


def build_reminder_message(step_label: str, status: BreachStatus, now: datetime) -> str:
    """Build a concise ASCII reminder line for a step's SLA standing.

    Examples
    --------
    Overdue::

        Approval step 'Cost review' is overdue by 5.0 h (was due 2026-01-01 12:00 UTC).

    Due soon::

        Approval step 'Cost review' is due in 3.0 h (due 2026-01-01 12:00 UTC).

    No SLA / comfortably on track::

        Approval step 'Cost review' has no SLA deadline.
        Approval step 'Cost review' is on track (due 2026-01-01 12:00 UTC).

    Parameters
    ----------
    step_label:
        Human label for the step (used verbatim inside single quotes).
    status:
        The :class:`BreachStatus` produced by :func:`breach_status`.
    now:
        The reference instant. Accepted for a stable call signature and
        future-proofing; the wording is driven by ``status``. Naive
        values are tolerated.

    Returns
    -------
    str
        A single ASCII line. No I/O is performed.
    """
    # Touch ``now`` so a naive value is still tolerated and the parameter
    # has a defined meaning, even though the phrasing comes from status.
    _ = _as_utc(now)

    prefix = "Approval step '" + step_label + "'"

    if status.due_at is None:
        return prefix + " has no SLA deadline."

    due_text = status.due_at.strftime("%Y-%m-%d %H:%M") + " UTC"

    if status.is_breached:
        return f"{prefix} is overdue by {status.hours_overdue:.1f} h (was due {due_text})."

    if status.severity is Severity.DUE_SOON:
        remaining = status.hours_remaining if status.hours_remaining is not None else 0.0
        return f"{prefix} is due in {remaining:.1f} h (due {due_text})."

    return f"{prefix} is on track (due {due_text})."


def current_step_baseline(
    instance_started_at: datetime,
    prior_step_decided_at: list[datetime | None] | None = None,
) -> datetime:
    """Best-effort start time of the step that currently holds an instance.

    The approval_routes schema records no per-step start timestamp, so the
    moment the current step became active is reconstructed:

    * For the first step there are no prior decisions, so the step started
      when the instance did (``instance_started_at``).
    * For a later step, the step became active when the previous step closed,
      i.e. at the latest decision recorded against that previous step. The
      caller passes those decision timestamps in ``prior_step_decided_at`` and
      the most recent one is used.

    ``None`` entries (undecided rows) are ignored. When no usable prior
    decision is supplied the instance start is returned, which is correct for
    step 1 and a safe, conservative fallback otherwise: it can only make a step
    look older, never younger, so a real breach is never hidden.

    All datetimes are normalised to UTC; the return value is timezone-aware.
    """
    candidates = [_as_utc(d) for d in (prior_step_decided_at or []) if d is not None]
    if candidates:
        return max(candidates)
    return _as_utc(instance_started_at)
