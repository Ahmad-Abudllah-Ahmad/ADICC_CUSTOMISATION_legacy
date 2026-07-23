# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Approval-SLA escalation-depth decision core (roadmap item #17).

Pure standard-library engine - no app.* imports, no SQLAlchemy, no
FastAPI at import time. It runs on Python 3.11.

Where :mod:`sla_engine` answers "is this step breached, and by how
much?", this module answers the follow-on operational question: given a
breached step and a per-target-kind escalation policy, *should we
escalate right now, and to whom next?*

The SLA monitor pulls a small policy descriptor (the target kind, its
SLA window, the grace period before escalation kicks in, and the ordered
chain of approver identifiers) plus the live state of the held step (how
long it has been sitting, who holds it now, who it has already been
escalated to) and feeds both into :func:`decide_escalation`. It gets
back a frozen verdict it can persist, surface in the UI, or turn into a
notification - the engine itself performs no I/O.

Design notes
------------

* Everything is deterministic and side-effect free. The same inputs
  always produce the same :class:`EscalationDecision`.
* The chain is a plain ordered tuple of opaque identifiers (a role name,
  a user id, a small descriptor string). The engine never interprets an
  entry beyond string equality, so callers are free to choose the id
  scheme. This mirrors ``sla_engine.next_escalation_target`` which also
  treats the chain as an ordered list of opaque targets; here the
  "next" entry is the first one not yet used (rather than the entry that
  follows a 1-based ordinal) because escalation tracks *consumed*
  targets explicitly via :attr:`EscalationState.already_escalated_to`.
* The entry currently holding the step is skipped: there is no point
  escalating an approval to the person who is already sitting on it.
* Severity here is expressed as plain lower-case strings (on_time,
  late, breached, critical) rather than the :class:`sla_engine.Severity`
  enum, so the verdict serialises directly to JSON without an enum
  conversion and adds a finer "critical" band on top of "breached".
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Reasons returned on EscalationDecision.reason - small closed set so
# callers can branch on them without parsing free text.
REASON_WITHIN_WINDOW = "within_window"
REASON_ESCALATE = "escalate"
REASON_CHAIN_EXHAUSTED = "chain_exhausted"

# Severity band labels, ordered from best to worst.
SEVERITY_ON_TIME = "on_time"
SEVERITY_LATE = "late"
SEVERITY_BREACHED = "breached"
SEVERITY_CRITICAL = "critical"


@dataclass(frozen=True)
class EscalationPolicy:
    """Per-target-kind rule set for escalating a stalled approval step.

    Attributes
    ----------
    target_kind:
        Opaque label for the class of approval this policy governs (for
        example ``"cost_approval"`` or ``"safety_signoff"``). The engine
        does not interpret it; it is carried for the caller's bookkeeping.
    sla_hours:
        The allowed duration of the step in hours. Used only for the
        severity helpers (:func:`hours_overdue` / :func:`classify_severity`);
        the escalate/hold decision is driven by ``escalate_after_hours``.
    escalate_after_hours:
        Grace period in hours. While the step has been held for fewer
        hours than this, no escalation happens. Often larger than
        ``sla_hours`` so a step is given some slack past its deadline
        before the chain is walked, but the engine does not require any
        particular relationship between the two.
    chain:
        Ordered tuple of approver identifiers to escalate to, in turn.
        The first entry not already consumed (and not equal to the
        current holder) is the next target.
    """

    target_kind: str
    sla_hours: int
    escalate_after_hours: int
    chain: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EscalationState:
    """Live standing of a single held approval step.

    Attributes
    ----------
    hours_since_assigned:
        How long, in hours, the step has been sitting with its current
        holder (or since it became active). Compared against the policy's
        ``escalate_after_hours`` and ``sla_hours``.
    current_holder:
        Identifier of whoever holds the approval right now. A chain entry
        equal to this value is skipped so the step is never "escalated"
        to the person already holding it.
    already_escalated_to:
        Ordered tuple of chain entries that have already received the
        escalation. Determines the next unused target and the escalation
        ``level``.
    """

    hours_since_assigned: float
    current_holder: str
    already_escalated_to: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EscalationDecision:
    """Immutable verdict for one escalation evaluation.

    Attributes
    ----------
    should_escalate:
        ``True`` when the step is past its grace period and an unused,
        eligible chain entry exists to escalate to.
    next_target:
        The chain entry to escalate to now, or ``None`` when no
        escalation is due (still within the window, or the chain is
        exhausted).
    level:
        1-based escalation level this decision represents. It is
        ``len(already_escalated_to) + 1`` for a real escalation (the
        first escalation is level 1, the second level 2, and so on) and
        ``0`` when no escalation is due.
    reason:
        One of :data:`REASON_WITHIN_WINDOW`, :data:`REASON_ESCALATE`,
        :data:`REASON_CHAIN_EXHAUSTED`.
    """

    should_escalate: bool
    next_target: str | None
    level: int
    reason: str


def _no_escalation(reason: str) -> EscalationDecision:
    """Build the canonical "do not escalate" verdict for ``reason``."""
    return EscalationDecision(
        should_escalate=False,
        next_target=None,
        level=0,
        reason=reason,
    )


def decide_escalation(policy: EscalationPolicy, state: EscalationState) -> EscalationDecision:
    """Decide whether to escalate a held step now, and to whom.

    Rules
    -----
    1. If ``state.hours_since_assigned < policy.escalate_after_hours`` the
       step is still within its grace period: ``should_escalate`` is
       ``False``, ``next_target`` is ``None``, ``level`` is ``0`` and
       ``reason`` is :data:`REASON_WITHIN_WINDOW`. The boundary is
       inclusive of the threshold - at exactly ``escalate_after_hours``
       the step is considered past the window and escalation is
       evaluated.
    2. Otherwise the chain is walked in order and the first entry that is
       neither already in ``state.already_escalated_to`` nor equal to
       ``state.current_holder`` becomes ``next_target``;
       ``should_escalate`` is ``True``, ``reason`` is
       :data:`REASON_ESCALATE` and ``level`` is
       ``len(state.already_escalated_to) + 1``.
    3. If every chain entry is already consumed or skipped (including the
       empty-chain case) there is nobody left to escalate to:
       ``should_escalate`` is ``False``, ``next_target`` is ``None``,
       ``level`` is ``0`` and ``reason`` is
       :data:`REASON_CHAIN_EXHAUSTED`.

    The function is pure and deterministic.

    Parameters
    ----------
    policy:
        The escalation rule set for the step's target kind.
    state:
        The live standing of the held step.

    Returns
    -------
    EscalationDecision
        The frozen verdict.
    """
    if state.hours_since_assigned < policy.escalate_after_hours:
        return _no_escalation(REASON_WITHIN_WINDOW)

    used = set(state.already_escalated_to)
    for entry in policy.chain:
        if entry in used:
            continue
        if entry == state.current_holder:
            continue
        return EscalationDecision(
            should_escalate=True,
            next_target=entry,
            level=len(state.already_escalated_to) + 1,
            reason=REASON_ESCALATE,
        )

    return _no_escalation(REASON_CHAIN_EXHAUSTED)


def hours_overdue(policy: EscalationPolicy, state: EscalationState) -> float:
    """Return hours the step is past its SLA, clamped at zero.

    Computed as ``max(0.0, hours_since_assigned - sla_hours)``. A step
    that has not yet reached its SLA window returns ``0.0`` rather than a
    negative number, so the value is always a non-negative "how late are
    we" magnitude.

    Parameters
    ----------
    policy:
        Supplies ``sla_hours``.
    state:
        Supplies ``hours_since_assigned``.

    Returns
    -------
    float
        Hours overdue (``>= 0.0``).
    """
    return max(0.0, float(state.hours_since_assigned) - float(policy.sla_hours))


def classify_severity(policy: EscalationPolicy, state: EscalationState) -> str:
    """Classify how badly a step is overrunning its SLA.

    The band is chosen from the ratio of :func:`hours_overdue` to the
    policy's ``sla_hours``:

    * ratio ``== 0``           -> :data:`SEVERITY_ON_TIME`
      (the step has not passed its SLA deadline at all).
    * ``0 < ratio <= 0.5``     -> :data:`SEVERITY_LATE`
      (overdue by up to half the SLA window).
    * ``0.5 < ratio <= 1.0``   -> :data:`SEVERITY_BREACHED`
      (overdue by up to a full SLA window).
    * ``ratio > 1.0``          -> :data:`SEVERITY_CRITICAL`
      (overdue by more than the whole SLA window again).

    Boundaries are inclusive at the top of each band (``<=``), matching
    the half-open intuition that, for example, being overdue by exactly
    half the window is still merely "late".

    A non-positive ``sla_hours`` cannot form a meaningful ratio (it would
    divide by zero or by a negative). In that degenerate case the verdict
    falls back to a simple absolute test: any overdue time at all is
    treated as :data:`SEVERITY_CRITICAL`, otherwise :data:`SEVERITY_ON_TIME`.

    Parameters
    ----------
    policy:
        Supplies ``sla_hours``.
    state:
        Supplies ``hours_since_assigned`` (via :func:`hours_overdue`).

    Returns
    -------
    str
        One of :data:`SEVERITY_ON_TIME`, :data:`SEVERITY_LATE`,
        :data:`SEVERITY_BREACHED`, :data:`SEVERITY_CRITICAL`.
    """
    overdue = hours_overdue(policy, state)
    if overdue <= 0.0:
        return SEVERITY_ON_TIME

    sla = float(policy.sla_hours)
    if sla <= 0.0:
        # No meaningful window to scale against - any overrun is critical.
        return SEVERITY_CRITICAL

    ratio = overdue / sla
    if ratio <= 0.5:
        return SEVERITY_LATE
    if ratio <= 1.0:
        return SEVERITY_BREACHED
    return SEVERITY_CRITICAL
