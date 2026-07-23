# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Pure progress / percent-complete math for the schedule "Progress rigor" slice.

This module is deliberately **dependency-free**: it imports nothing from the ORM,
the DB engine, FastAPI or the rest of the app -- only the Python standard
library. That keeps the per-type progress engine a set of *pure* functions that
can be unit-tested in isolation (and on Python 3.11 locally, where importing
``schedule/service.py`` would otherwise pull in ``app.database`` and require a
live PostgreSQL cluster).

It implements the algorithm described in
``docs/strategy/ADVANCED_SCHEDULING_PROJECT_CONTROLS_ROADMAP.md`` (the "Progress
rigor" / T3.2 design): three percent-complete *types*, weighted step roll-up,
suspend/resume remaining-duration freeze, deterministic EVM-distortion warnings,
and time-phased planned value. The real ORM->calendar adapter and the service
dispatcher that persist these results are built separately by the integrator;
this file only provides the math they call.

Terms used here are standard project-controls vocabulary (CPM, total float,
earned value, PV / EV / AC / BAC, data date, S-curve). Where the design contrasts
behaviour with a commercial scheduling tool, that tool is referred to as "the
incumbent" / "the industry-standard suite" -- no product name appears in code.

Percent-complete types
----------------------
* ``duration`` -- remaining duration is *auto-computed* from the driver percent;
  ``RD = round(OD * (1 - pct/100))``. The percent is the source of truth.
* ``units``    -- percent is *derived* from installed / budgeted quantity;
  ``pct = clamp(100 * installed / budgeted)``. Falls back to a supplied percent
  (with a warning) when ``budgeted <= 0``.
* ``physical`` -- percent and remaining duration legitimately *diverge*. Percent
  is the weighted step roll-up if steps exist, else a manually supplied percent;
  remaining duration is taken from an explicit value, else auto-computed.

Calendar / working-day arithmetic
---------------------------------
Working-day math lives in :class:`WorkCalendar`. The inclusivity convention
mirrors ``app/core/cpm.py``'s ``_working_days_between`` so this engine and the
CPM passes agree:

    :meth:`WorkCalendar.working_days_between` is **exclusive of the start date,
    inclusive of the end date** -- it counts working days strictly after
    ``start`` up to and including ``end``.

Money discipline
----------------
Monetary values (cost, planned value, earned value, BAC) are :class:`Decimal`
end-to-end; ``float`` is never mixed into money math. Money is quantised to cents
(``0.01``) but always returned as ``Decimal``. Percentages are ``Decimal``,
remaining-duration and day counts are ``int``.

Determinism
-----------
No function reads the wall clock (no ``date.today`` / ``datetime.now``) and none
use randomness. The ``data_date`` and every other input are passed explicitly so
results are fully reproducible.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Recognised percent-complete types; the first entry is the default.
PERCENT_COMPLETE_TYPES: tuple[str, ...] = ("physical", "duration", "units")
DEFAULT_PERCENT_COMPLETE_TYPE: str = PERCENT_COMPLETE_TYPES[0]

#: Money quantum -- two decimal places, kept as ``Decimal``.
_MONEY_Q = Decimal("0.01")
#: Percent quantum -- three decimal places (enough for the milestone 99.999 cap).
_PCT_Q = Decimal("0.001")

#: A milestone step that is not yet 100% caps the parent strictly below complete.
_MILESTONE_CAP = Decimal("99.999")

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_ONE = Decimal("1")

#: Status strings (kept identical to the ones the service status machine uses).
STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_SUSPENDED = "suspended"


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    """Coerce an arbitrary numeric-ish input to :class:`Decimal`.

    ``None`` and unparseable values fall back to *default*. ``float`` is routed
    through ``str`` so we do not inherit binary-float noise into money math.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # avoid True == 1 surprises in money fields
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


def quantize_money(value: Any) -> Decimal:
    """Quantise a money value to cents, returned as :class:`Decimal`."""
    return _to_decimal(value).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


def quantize_pct(value: Any) -> Decimal:
    """Quantise a percent to three decimals, returned as :class:`Decimal`."""
    return _to_decimal(value).quantize(_PCT_Q, rounding=ROUND_HALF_UP)


def clamp_pct(value: Any) -> Decimal:
    """Clamp a percent into ``[0, 100]`` and quantise it to three decimals.

    Accepts ``Decimal`` / ``int`` / ``float`` / numeric strings; ``None`` and
    garbage clamp to ``0``.
    """
    dec = _to_decimal(value)
    if dec < _ZERO:
        dec = _ZERO
    elif dec > _HUNDRED:
        dec = _HUNDRED
    return quantize_pct(dec)


def _decimal_round_half_up(value: Decimal) -> int:
    """Round a Decimal to the nearest integer, halves away from zero."""
    return int(value.quantize(_ONE, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Working-day calendar (pure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkCalendar:
    """A pure working-day calendar.

    :param work_weekdays: weekday indices that are working days, ``0=Mon`` ..
        ``6=Sun``. Defaults to Monday-Friday.
    :param holidays: ISO ``YYYY-MM-DD`` date strings that are *not* working days
        even when they fall on a working weekday.

    The default instance (:data:`DEFAULT_CALENDAR`) is Mon-Fri with no holidays.
    """

    work_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})
    holidays: frozenset[str] = frozenset()

    def is_working_day(self, iso: str) -> bool:
        """Return ``True`` when *iso* (``YYYY-MM-DD``) is a working day."""
        d = _parse_date(iso)
        return self._is_working(d)

    def _is_working(self, d: date) -> bool:
        return d.weekday() in self.work_weekdays and d.isoformat() not in self.holidays

    def working_days_between(self, start_iso: str, end_iso: str) -> int:
        """Count working days in ``(start, end]`` -- exclusive start, inclusive end.

        Mirrors ``app/core/cpm.py``'s ``_working_days_between``: it counts working
        days strictly *after* ``start`` up to and including ``end``. Returns ``0``
        when ``end <= start`` (so an empty or inverted span contributes nothing).

        Example: with the default Mon-Fri calendar, the count from a Monday to the
        Friday of the same week is ``4`` (Tue, Wed, Thu, Fri).
        """
        start = _parse_date(start_iso)
        end = _parse_date(end_iso)
        if end <= start:
            return 0
        count = 0
        current = start
        while current < end:
            current += timedelta(days=1)
            if self._is_working(current):
                count += 1
        return count

    def add_working_days(self, start_iso: str, n: int) -> str:
        """Return the ISO date *n* working days after *start* (counting forward).

        Counting starts the day *after* ``start`` (consistent with
        :meth:`working_days_between`). ``n <= 0`` returns ``start`` unchanged, so
        ``add_working_days(d, working_days_between(a, d))`` round-trips a finish
        offset. For ``n > 0`` the result is always a working day.
        """
        d = _parse_date(start_iso)
        if n <= 0:
            return d.isoformat()
        added = 0
        current = d
        while added < n:
            current += timedelta(days=1)
            if self._is_working(current):
                added += 1
        return current.isoformat()


#: Default calendar: Monday-Friday, no holidays.
DEFAULT_CALENDAR = WorkCalendar()


def _parse_date(iso: str | date) -> date:
    """Parse an ISO ``YYYY-MM-DD`` (or longer ISO) string into a ``date``.

    Accepts an existing ``date`` for convenience. Raises ``ValueError`` on
    anything unparseable -- callers pass validated dates, and a silent default
    would corrupt working-day math.
    """
    if isinstance(iso, date):
        return iso
    return date.fromisoformat(str(iso)[:10])


def _max_iso(a: str, b: str) -> str:
    """Return the later of two ISO date strings."""
    return a if _parse_date(a) >= _parse_date(b) else b


def _min_iso(a: str, b: str) -> str:
    """Return the earlier of two ISO date strings."""
    return a if _parse_date(a) <= _parse_date(b) else b


# ---------------------------------------------------------------------------
# Step roll-up (physical %)
# ---------------------------------------------------------------------------


@dataclass
class ProgressStep:
    """One weighted step of a physical-progress activity.

    :param weight: relative weight in the roll-up (``Decimal``); ``0`` means the
        step does not bias the weighted average.
    :param percent_complete: the step's own 0..100 progress.
    :param is_milestone: when ``True`` and the step is below 100%, the rolled-up
        parent percent is capped strictly below complete (:data:`_MILESTONE_CAP`).
    """

    weight: Decimal = _ZERO
    percent_complete: Decimal = _ZERO
    is_milestone: bool = False


def _coerce_step(step: ProgressStep | Mapping[str, Any]) -> ProgressStep:
    """Normalise a step given as a dataclass *or* a plain mapping."""
    if isinstance(step, ProgressStep):
        return ProgressStep(
            weight=_to_decimal(step.weight),
            percent_complete=_to_decimal(step.percent_complete),
            is_milestone=bool(step.is_milestone),
        )
    return ProgressStep(
        weight=_to_decimal(step.get("weight")),
        percent_complete=_to_decimal(step.get("percent_complete")),
        is_milestone=bool(step.get("is_milestone", False)),
    )


def step_rollup(steps: Sequence[ProgressStep | Mapping[str, Any]]) -> Decimal:
    """Weighted-average roll-up of step percents into a parent percent.

    Rules (from the roadmap pseudocode):

    * No steps -> ``0`` (the caller substitutes the activity's own percent).
    * Total weight ``== 0`` -> the *plain mean* of the step percents (the caller
      is expected to surface an ``all_steps_zero_weight`` warning).
    * Otherwise -> ``sum(weight * pct) / sum(weight)``.
    * If any *milestone* step is below 100%, the result is capped at
      :data:`_MILESTONE_CAP` (so an activity with an open milestone never reads
      100% even when the weighted mean would).
    * The result is clamped to ``[0, 100]`` and quantised to three decimals.
    """
    coerced = [_coerce_step(s) for s in steps]
    if not coerced:
        return _ZERO

    total_weight = sum((s.weight for s in coerced), _ZERO)
    if total_weight == _ZERO:
        rolled = sum((s.percent_complete for s in coerced), _ZERO) / Decimal(len(coerced))
    else:
        weighted = sum((s.weight * s.percent_complete for s in coerced), _ZERO)
        rolled = weighted / total_weight

    if any(s.is_milestone and s.percent_complete < _HUNDRED for s in coerced):
        if rolled > _MILESTONE_CAP:
            rolled = _MILESTONE_CAP

    return clamp_pct(rolled)


def steps_total_weight(steps: Sequence[ProgressStep | Mapping[str, Any]]) -> Decimal:
    """Sum of step weights (used by the caller to decide the zero-weight warning)."""
    return sum((_coerce_step(s).weight for s in steps), _ZERO)


# ---------------------------------------------------------------------------
# Status machine
# ---------------------------------------------------------------------------


def status_from(
    percent_complete: Any,
    *,
    suspended: bool = False,
    predecessors_complete: bool = True,
) -> str:
    """Resolve an activity's status from its percent and flags.

    * ``suspended`` is *sticky*: a suspended activity reports ``suspended``
      regardless of percent (the caller clears the flag on resume).
    * ``completed`` only at ``>= 100`` **and** only when predecessors are
      complete (the real predecessor guard lives in the service and raises 409;
      here we simply refuse to *label* an activity complete while a predecessor
      is open, so the math never reports a state the guard would reject).
    * ``> 0`` -> ``in_progress``; otherwise ``not_started``.
    """
    if suspended:
        return STATUS_SUSPENDED
    pct = clamp_pct(percent_complete)
    if pct >= _HUNDRED:
        return STATUS_COMPLETED if predecessors_complete else STATUS_IN_PROGRESS
    if pct > _ZERO:
        return STATUS_IN_PROGRESS
    return STATUS_NOT_STARTED


# ---------------------------------------------------------------------------
# EVM-distortion warnings (deterministic, no AI)
# ---------------------------------------------------------------------------

# Stable warning keys (consumed by the UI and tests). Kept as constants so the
# exact strings the roadmap names cannot drift.
WARN_UNITS_WITHOUT_BUDGETED = "units_type_without_budgeted_units"
WARN_DURATION_ON_NONLINEAR_COST = "duration_type_on_nonlinear_cost"
WARN_PHYSICAL_MANUAL_SUBJECTIVE = "physical_manual_pct_is_subjective"
WARN_ALL_STEPS_ZERO_WEIGHT = "all_steps_zero_weight"


def evm_distortion_warnings(
    *,
    pct_type: str,
    budgeted_units: Any = None,
    has_steps: bool = False,
    cost_planned: Any = None,
    steps_total_weight: Any = None,
    cost_is_nonlinear: bool = False,
) -> list[str]:
    """Deterministic EVM-distortion warnings for a percent-complete configuration.

    Returns a list of the stable warning keys from the roadmap:

    * ``units_type_without_budgeted_units`` -- a ``units`` activity with no
      positive budgeted quantity (percent cannot be derived from quantity).
    * ``duration_type_on_nonlinear_cost`` -- a ``duration`` activity whose cost is
      front- or back-loaded (earning by time then misstates EV).
    * ``physical_manual_pct_is_subjective`` -- a cost-loaded ``physical`` activity
      driven by a manual percent with no steps to substantiate it.
    * ``all_steps_zero_weight`` -- the activity has steps but their weights sum to
      zero (the roll-up silently degrades to a plain mean).

    Order is deterministic (the order the checks are written).
    """
    warnings: list[str] = []

    if pct_type == "units" and _to_decimal(budgeted_units) <= _ZERO:
        warnings.append(WARN_UNITS_WITHOUT_BUDGETED)

    if pct_type == "duration" and cost_is_nonlinear:
        warnings.append(WARN_DURATION_ON_NONLINEAR_COST)

    if pct_type == "physical" and not has_steps and _to_decimal(cost_planned) > _ZERO:
        warnings.append(WARN_PHYSICAL_MANUAL_SUBJECTIVE)

    if has_steps and _to_decimal(steps_total_weight) == _ZERO:
        warnings.append(WARN_ALL_STEPS_ZERO_WEIGHT)

    return warnings


# ---------------------------------------------------------------------------
# Unified per-type progress computation
# ---------------------------------------------------------------------------


@dataclass
class ProgressResult:
    """Result of :func:`compute_progress`.

    :param percent_complete: resolved 0..100 percent (``Decimal``).
    :param remaining_duration: remaining working days (``int``).
    :param forecast_finish_iso: forecast finish date (``YYYY-MM-DD``).
    :param warnings: deterministic warning keys raised while computing.
    :param status: resolved status string (see the status machine).
    """

    percent_complete: Decimal
    remaining_duration: int
    forecast_finish_iso: str
    warnings: list[str] = field(default_factory=list)
    status: str = STATUS_NOT_STARTED


def original_duration(calendar: WorkCalendar, start_iso: str, end_iso: str) -> int:
    """Original planned working-day duration ``OD`` between start and end."""
    return calendar.working_days_between(start_iso, end_iso)


def remaining_from_pct(original_dur: int, percent_complete: Any) -> int:
    """``RD = round(OD * (1 - pct/100))`` -- auto-computed remaining duration.

    Uses Decimal half-up rounding so a 10-day span at 40% gives exactly ``6``
    (and never the float-rounding-down ``5`` you would get from ``int(...)``).
    """
    pct = clamp_pct(percent_complete)
    remaining_fraction = (_HUNDRED - pct) / _HUNDRED
    rd = _decimal_round_half_up(Decimal(original_dur) * remaining_fraction)
    return max(rd, 0)


def forecast_finish(
    calendar: WorkCalendar,
    start_iso: str,
    data_date_iso: str,
    remaining_duration: int,
) -> str:
    """Forecast finish = ``add_working_days(max(start, data_date), RD)``.

    Work cannot remain in the past, so the remaining duration is laid out from
    the later of the activity start and the data date.
    """
    anchor = _max_iso(start_iso, data_date_iso)
    return calendar.add_working_days(anchor, remaining_duration)


def compute_progress(
    *,
    pct_type: str = DEFAULT_PERCENT_COMPLETE_TYPE,
    calendar: WorkCalendar | None = None,
    start_iso: str,
    end_iso: str,
    data_date_iso: str,
    percent_in: Any = None,
    installed_units: Any = None,
    budgeted_units: Any = None,
    explicit_remaining: int | None = None,
    steps: Sequence[ProgressStep | Mapping[str, Any]] | None = None,
    suspended: bool = False,
    predecessors_complete: bool = True,
) -> ProgressResult:
    """Resolve percent / remaining-duration / forecast-finish for one activity.

    Dispatches on *pct_type* exactly as the roadmap pseudocode prescribes:

    * ``duration`` -- ``pct = clamp(percent_in)``; ``RD = round(OD*(1-pct/100))``
      (the percent is the driver, remaining duration is always derived).
    * ``units``    -- ``pct = clamp(100*installed/budgeted)`` when ``budgeted>0``,
      otherwise fall back to ``percent_in`` and raise
      ``units_type_without_budgeted_units``; ``RD = round(OD*(1-pct/100))``.
    * ``physical`` -- ``pct = step_rollup(steps)`` when steps exist, else
      ``clamp(percent_in)``; ``RD = explicit_remaining`` when given, else
      ``round(OD*(1-pct/100))`` (the only type where percent and RD may diverge).

    Unknown *pct_type* values are treated as ``physical`` (the safe default).
    ``forecast_finish_iso`` and ``status`` are always populated. A suspended
    activity keeps the remaining duration it is given (the caller freezes it) and
    is laid out from the data date so resuming shifts the finish by exactly the
    elapsed gap.
    """
    cal = calendar or DEFAULT_CALENDAR
    if pct_type not in PERCENT_COMPLETE_TYPES:
        pct_type = DEFAULT_PERCENT_COMPLETE_TYPE

    warnings: list[str] = []
    od = original_duration(cal, start_iso, end_iso)

    if pct_type == "units":
        budgeted = _to_decimal(budgeted_units)
        if budgeted > _ZERO:
            pct = clamp_pct(_HUNDRED * _to_decimal(installed_units) / budgeted)
        else:
            warnings.append(WARN_UNITS_WITHOUT_BUDGETED)
            pct = clamp_pct(percent_in)
        remaining = remaining_from_pct(od, pct)

    elif pct_type == "physical":
        if steps:
            pct = step_rollup(steps)
            if steps_total_weight(steps) == _ZERO:
                warnings.append(WARN_ALL_STEPS_ZERO_WEIGHT)
        else:
            pct = clamp_pct(percent_in)
        if explicit_remaining is not None:
            remaining = max(int(explicit_remaining), 0)
        else:
            remaining = remaining_from_pct(od, pct)

    else:  # "duration"
        pct = clamp_pct(percent_in)
        remaining = remaining_from_pct(od, pct)

    finish = forecast_finish(cal, start_iso, data_date_iso, remaining)
    status = status_from(
        pct,
        suspended=suspended,
        predecessors_complete=predecessors_complete,
    )

    return ProgressResult(
        percent_complete=pct,
        remaining_duration=remaining,
        forecast_finish_iso=finish,
        warnings=warnings,
        status=status,
    )


# ---------------------------------------------------------------------------
# Time-phased planned value (PV) and earned value (EV)
# ---------------------------------------------------------------------------


@dataclass
class PVActivity:
    """Minimal baseline-cost view of an activity for the PV / EV roll-up.

    Decoupled from the ORM so the roll-up stays pure.

    :param baseline_start_iso: baseline (planned) start, ``YYYY-MM-DD``.
    :param baseline_end_iso: baseline (planned) end, ``YYYY-MM-DD``.
    :param cost_planned: budgeted cost (``Decimal``); the activity's BAC share.
    :param percent_complete: the activity's *already-resolved* percent, used by
        :func:`earned_value` (method-aware -- the caller resolves it per type).
    """

    baseline_start_iso: str | None
    baseline_end_iso: str | None
    cost_planned: Decimal = _ZERO
    percent_complete: Decimal = _ZERO


def _coerce_pv_activity(act: PVActivity | Mapping[str, Any]) -> PVActivity:
    """Normalise a PV activity given as a dataclass *or* a plain mapping."""
    if isinstance(act, PVActivity):
        return PVActivity(
            baseline_start_iso=act.baseline_start_iso,
            baseline_end_iso=act.baseline_end_iso,
            cost_planned=_to_decimal(act.cost_planned),
            percent_complete=_to_decimal(act.percent_complete),
        )
    return PVActivity(
        baseline_start_iso=act.get("baseline_start_iso"),
        baseline_end_iso=act.get("baseline_end_iso"),
        cost_planned=_to_decimal(act.get("cost_planned")),
        percent_complete=_to_decimal(act.get("percent_complete")),
    )


def planned_percent_for(
    activity: PVActivity | Mapping[str, Any],
    data_date_iso: str,
    calendar: WorkCalendar,
) -> Decimal:
    """Time-phased *planned* fraction (0..1) of one activity at the data date.

    ``planned_pct = elapsed_working_days(start, min(data_date, end)) /
    total_working_days(start, end)``, clamped to ``[0, 1]``.

    Because :meth:`WorkCalendar.working_days_between` is exclusive of the start,
    the fraction is:

    * ``0`` on or before the baseline start (nothing has elapsed),
    * ``1`` on or after the baseline end (the whole span has elapsed),
    * strictly between ``0`` and ``1`` inside the window.

    Returns ``0`` for an activity with missing dates or a zero-length span (it
    contributes no PV rather than crashing).
    """
    act = _coerce_pv_activity(activity)
    if not act.baseline_start_iso or not act.baseline_end_iso:
        return _ZERO

    total_wd = calendar.working_days_between(act.baseline_start_iso, act.baseline_end_iso)
    if total_wd <= 0:
        return _ZERO

    as_of = _min_iso(data_date_iso, act.baseline_end_iso)
    elapsed_wd = calendar.working_days_between(act.baseline_start_iso, as_of)

    fraction = Decimal(elapsed_wd) / Decimal(total_wd)
    if fraction < _ZERO:
        return _ZERO
    if fraction > _ONE:
        return _ONE
    return fraction


def planned_value_at(
    activities: Iterable[PVActivity | Mapping[str, Any]],
    data_date_iso: str,
    calendar_for: Any,
) -> Decimal:
    """Time-phased planned value (PV / BCWS) of a set of activities at the data date.

    ``PV = sum(cost_planned * planned_percent_for(activity, data_date))`` using a
    *per-activity* calendar supplied by ``calendar_for(activity) -> WorkCalendar``
    (so each activity honours its own working week / holidays, exactly as the
    integrator's ORM adapter will). Result is quantised to cents but stays a
    :class:`Decimal`.
    """
    total = _ZERO
    for raw in activities:
        cal = calendar_for(raw)
        fraction = planned_percent_for(raw, data_date_iso, cal)
        total += _coerce_pv_activity(raw).cost_planned * fraction
    return quantize_money(total)


def earned_value(
    activities: Iterable[PVActivity | Mapping[str, Any]],
    *,
    method_aware: bool = True,
) -> Decimal:
    """Earned value (EV / BCWP) = ``sum(cost_planned * percent_complete/100)``.

    Each activity carries its *already-resolved* ``percent_complete`` -- the
    caller resolves it per percent-complete type (``duration`` earns by time,
    ``units`` by installed quantity, ``physical`` / stepped by the rolled-up
    percent). That is exactly the method-aware EV the roadmap calls for; it keeps
    this function simple and pure while still being method-aware *upstream*.

    ``method_aware`` is accepted for interface symmetry with the service layer.
    When ``False`` the computation is identical (the per-activity percent is
    already resolved), so the flag documents intent without changing the math.
    Result is quantised to cents but stays a :class:`Decimal`.
    """
    total = _ZERO
    for raw in activities:
        act = _coerce_pv_activity(raw)
        total += act.cost_planned * (clamp_pct(act.percent_complete) / _HUNDRED)
    return quantize_money(total)


def budget_at_completion(activities: Iterable[PVActivity | Mapping[str, Any]]) -> Decimal:
    """BAC = ``sum(cost_planned)`` over the activities, quantised to cents."""
    total = _ZERO
    for raw in activities:
        total += _coerce_pv_activity(raw).cost_planned
    return quantize_money(total)


__all__ = [
    "DEFAULT_CALENDAR",
    "DEFAULT_PERCENT_COMPLETE_TYPE",
    "PERCENT_COMPLETE_TYPES",
    "STATUS_COMPLETED",
    "STATUS_IN_PROGRESS",
    "STATUS_NOT_STARTED",
    "STATUS_SUSPENDED",
    "WARN_ALL_STEPS_ZERO_WEIGHT",
    "WARN_DURATION_ON_NONLINEAR_COST",
    "WARN_PHYSICAL_MANUAL_SUBJECTIVE",
    "WARN_UNITS_WITHOUT_BUDGETED",
    "PVActivity",
    "ProgressResult",
    "ProgressStep",
    "WorkCalendar",
    "budget_at_completion",
    "clamp_pct",
    "compute_progress",
    "earned_value",
    "evm_distortion_warnings",
    "forecast_finish",
    "original_duration",
    "planned_percent_for",
    "planned_value_at",
    "quantize_money",
    "quantize_pct",
    "remaining_from_pct",
    "status_from",
    "step_rollup",
    "steps_total_weight",
]
