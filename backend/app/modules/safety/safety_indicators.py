# DDC-CWICR-OE: DataDrivenConstruction / OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Leading vs lagging safety indicators rollup (pure, DB-free).

A safety programme is judged on two families of numbers:

* Lagging indicators measure harm that already happened - recordable
  incidents, lost-time incidents, days lost, and the OSHA/ILO style
  frequency rates (TRIR, LTIFR, severity rate). They tell you how bad the
  past period was.
* Leading indicators measure the proactive work that prevents harm -
  near-misses reported, safety observations raised and closed out, and the
  corrective actions opened against findings and their close rate. They tell
  you whether the team is actively working the problem before someone gets
  hurt.

This module rolls a project's already-stored safety rows into both families
side by side so a report or dashboard can show "how much prevention work are
we doing" next to "how much harm are we still seeing".

Everything here is a pure function or an immutable value object. There is no
database access, no I/O and no framework dependency, so the rollup is trivial
to unit test and safe to reuse from services, exports or reports.

Design guarantees:

* Every division is guarded. A rate whose denominator (hours worked, or the
  corrective-action count) is zero or absent is returned as ``None``, never as
  NaN, infinity, a falsely-precise zero, or a crash.
* Frequency rates are computed with Decimal (never float) and quantized to two
  decimals; the corrective-action close rate is a Decimal ratio in [0, 1]
  quantized to four decimals. This keeps the money-adjacent rate numbers exact
  and reproducible.
* A near-miss is a leading signal (no one was hurt): it is surfaced under
  ``near_misses_reported`` while still being included in the raw
  ``total_incidents`` count, and it never enters a lagging frequency-rate
  numerator.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# ---------------------------------------------------------------------------
# Standard hours bases (the multiplier in the frequency-rate formula), matching
# app/modules/safety/intl.py and the existing get_stats math:
#   rate = incident_count * base_hours / hours_worked
# TRIR is per 200,000 hours (about 100 full-time workers over one year); LTIFR
# and the severity rate are per 1,000,000 hours.
# ---------------------------------------------------------------------------
TRIR_BASE_HOURS = Decimal("200000")
LTIFR_BASE_HOURS = Decimal("1000000")
SEVERITY_RATE_BASE_HOURS = Decimal("1000000")

# Rates round to two decimals; the close-rate ratio to four.
_RATE_QUANT = Decimal("0.01")
_RATIO_QUANT = Decimal("0.0001")

# Status vocabularies, mirrored from the safety schemas so the rollup stays in
# step with what the API actually accepts.
#   CorrectiveActionEntry.status: open | in_progress | completed
#   SafetyObservation.status:     open | in_progress | closed
_OPEN_CA_STATUSES = frozenset({"open", "in_progress"})
_CLOSED_CA_STATUSES = frozenset({"completed", "closed", "verified"})
_OPEN_OBS_STATUSES = frozenset({"open", "in_progress"})
_CLOSED_OBS_STATUSES = frozenset({"closed"})

# Canonical near-miss code shared by incident_type and observation_type.
_NEAR_MISS = "near_miss"


# ---------------------------------------------------------------------------
# Inputs - one immutable value object per stored row, already reduced to the
# handful of fields the rollup needs. The service builds these from ORM rows.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IncidentInput:
    """One safety incident reduced to the fields the rollup needs.

    Attributes:
        recordable: True when the incident is OSHA-300 recordable.
        lost_time: True when the incident caused at least one lost day.
        days_lost: Whole days lost (the severity-rate numerator).
        man_hours: Exposure hours attributed to this incident, or zero when
            none were recorded. Summed into the frequency-rate denominator.
        incident_type: Canonical incident type, e.g. ``"injury"`` or
            ``"near_miss"``.
        on_date: The incident date, or ``None`` when it could not be parsed.
        corrective_action_statuses: Status of each corrective action attached
            to this incident (e.g. ``("open", "completed")``).
    """

    recordable: bool = False
    lost_time: bool = False
    days_lost: int = 0
    man_hours: Decimal = Decimal("0")
    incident_type: str = ""
    on_date: date | None = None
    corrective_action_statuses: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ObservationInput:
    """One safety observation reduced to the fields the rollup needs.

    Attributes:
        status: Observation status, e.g. ``"open"`` or ``"closed"``.
        observation_type: Canonical observation type, e.g. ``"unsafe_act"`` or
            ``"near_miss"``.
        on_date: The observation date, or ``None`` when it is unknown.
    """

    status: str = "open"
    observation_type: str = ""
    on_date: date | None = None


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LaggingIndicators:
    """Harm that already happened over the period.

    ``trir``/``ltifr``/``severity_rate`` are ``None`` when no exposure hours
    were recorded (an unknown denominator is "not enough data", never a
    falsely-precise zero).
    """

    total_incidents: int
    recordable_incidents: int
    lost_time_incidents: int
    total_days_lost: int
    total_hours_worked: Decimal
    trir: Decimal | None
    ltifr: Decimal | None
    severity_rate: Decimal | None


@dataclass(frozen=True)
class LeadingIndicators:
    """Proactive prevention work done over the period.

    ``corrective_action_close_rate`` is a Decimal ratio in [0, 1], or ``None``
    when there are no corrective actions to measure a close rate against.
    """

    near_misses_reported: int
    observations_total: int
    observations_open: int
    observations_closed: int
    corrective_actions_total: int
    corrective_actions_open: int
    corrective_actions_closed: int
    corrective_action_close_rate: Decimal | None


@dataclass(frozen=True)
class SafetyIndicators:
    """Leading and lagging indicators side by side for a period."""

    period_start: date | None
    period_end: date | None
    leading: LeadingIndicators
    lagging: LaggingIndicators


# ---------------------------------------------------------------------------
# Guarded rate helpers
# ---------------------------------------------------------------------------
def frequency_rate(count: int, hours_worked: Decimal, base_hours: Decimal) -> Decimal | None:
    """Compute an OSHA/ILO style frequency rate, guarded against zero hours.

    The formula is ``count * base_hours / hours_worked``, quantized to two
    decimals with round-half-up.

    Args:
        count: Non-negative numerator (recordable/lost-time incidents or days).
        hours_worked: Exposure hours (the denominator).
        base_hours: The multiplier (200,000 for TRIR, 1,000,000 for LTIFR).

    Returns:
        The rate as a Decimal, or ``None`` when ``hours_worked`` is zero or
        negative (no exposure data) so the caller never divides by zero.
    """
    if hours_worked <= 0:
        return None
    value = Decimal(count) * base_hours / hours_worked
    return value.quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)


def close_rate(closed: int, total: int) -> Decimal | None:
    """Fraction of items closed, guarded against a zero denominator.

    Args:
        closed: Count of closed/completed items.
        total: Count of all items.

    Returns:
        ``closed / total`` as a Decimal ratio in [0, 1] quantized to four
        decimals, or ``None`` when ``total`` is zero (nothing to measure).
    """
    if total <= 0:
        return None
    return (Decimal(closed) / Decimal(total)).quantize(_RATIO_QUANT, rounding=ROUND_HALF_UP)


def _in_period(on_date: date | None, period_start: date | None, period_end: date | None) -> bool:
    """Return True when ``on_date`` falls in the inclusive window.

    When neither bound is set, every record is in period (including undated
    ones). When either bound is set, an undated record is excluded rather than
    attributed to a period it may not belong to.
    """
    if period_start is None and period_end is None:
        return True
    if on_date is None:
        return False
    if period_start is not None and on_date < period_start:
        return False
    return not (period_end is not None and on_date > period_end)


# ---------------------------------------------------------------------------
# Rollup
# ---------------------------------------------------------------------------
def compute_safety_indicators(
    incidents: Sequence[IncidentInput],
    observations: Sequence[ObservationInput],
    *,
    period_start: date | None = None,
    period_end: date | None = None,
) -> SafetyIndicators:
    """Roll incidents and observations into leading and lagging indicators.

    Incidents and observations outside ``[period_start, period_end]`` (both
    optional, inclusive) are excluded before aggregation, and corrective
    actions are taken from the surviving in-period incidents so they inherit
    their parent incident's period.

    Args:
        incidents: The project's incidents as :class:`IncidentInput` records.
        observations: The project's observations as :class:`ObservationInput`.
        period_start: Optional inclusive lower date bound.
        period_end: Optional inclusive upper date bound (the "as of" cutoff).

    Returns:
        A :class:`SafetyIndicators` with every rate guarded against a zero or
        absent denominator.
    """
    inc = [i for i in incidents if _in_period(i.on_date, period_start, period_end)]
    obs = [o for o in observations if _in_period(o.on_date, period_start, period_end)]

    # Lagging - harm that already happened.
    total_incidents = len(inc)
    recordable_incidents = sum(1 for i in inc if i.recordable)
    lost_time_incidents = sum(1 for i in inc if i.lost_time)
    total_days_lost = sum(i.days_lost for i in inc)
    total_hours_worked = sum((i.man_hours for i in inc), Decimal("0"))

    lagging = LaggingIndicators(
        total_incidents=total_incidents,
        recordable_incidents=recordable_incidents,
        lost_time_incidents=lost_time_incidents,
        total_days_lost=total_days_lost,
        total_hours_worked=total_hours_worked,
        trir=frequency_rate(recordable_incidents, total_hours_worked, TRIR_BASE_HOURS),
        ltifr=frequency_rate(lost_time_incidents, total_hours_worked, LTIFR_BASE_HOURS),
        severity_rate=frequency_rate(total_days_lost, total_hours_worked, SEVERITY_RATE_BASE_HOURS),
    )

    # Leading - proactive prevention work.
    ca_statuses: list[str] = [s for i in inc for s in i.corrective_action_statuses]
    ca_total = len(ca_statuses)
    ca_open = sum(1 for s in ca_statuses if s in _OPEN_CA_STATUSES)
    ca_closed = sum(1 for s in ca_statuses if s in _CLOSED_CA_STATUSES)

    near_miss_incidents = sum(1 for i in inc if i.incident_type == _NEAR_MISS)
    near_miss_observations = sum(1 for o in obs if o.observation_type == _NEAR_MISS)

    leading = LeadingIndicators(
        near_misses_reported=near_miss_incidents + near_miss_observations,
        observations_total=len(obs),
        observations_open=sum(1 for o in obs if o.status in _OPEN_OBS_STATUSES),
        observations_closed=sum(1 for o in obs if o.status in _CLOSED_OBS_STATUSES),
        corrective_actions_total=ca_total,
        corrective_actions_open=ca_open,
        corrective_actions_closed=ca_closed,
        corrective_action_close_rate=close_rate(ca_closed, ca_total),
    )

    return SafetyIndicators(
        period_start=period_start,
        period_end=period_end,
        leading=leading,
        lagging=lagging,
    )


def iter_corrective_action_statuses(incidents: Iterable[IncidentInput]) -> list[str]:
    """Flatten every corrective-action status across incidents (helper for reports)."""
    return [s for i in incidents for s in i.corrective_action_statuses]
