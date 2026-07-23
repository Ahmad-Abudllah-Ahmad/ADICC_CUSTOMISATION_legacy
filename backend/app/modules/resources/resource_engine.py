# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure resource-depth engine for the schedule "Resource depth" slice (T3.1).

This module is deliberately **dependency-free** in the same spirit as
``app/modules/schedule/progress_math.py``: it imports nothing from the ORM, the
DB engine or FastAPI -- only the Python standard library plus the equally pure
CPM engine in :mod:`app.modules.schedule_advanced.cpm` (``TaskNetwork`` /
``Activity`` / ``compute_cpm``). That keeps the whole resource-management
algorithm a set of *pure* functions that can be unit-tested in isolation (and on
Python 3.11 locally, where importing ``resources/service.py`` would pull in
``app.database`` and require a live PostgreSQL cluster).

It implements the four capabilities described in
``docs/strategy/ADVANCED_SCHEDULING_PROJECT_CONTROLS_ROADMAP.md`` (the "T3.1 --
Resource depth" design):

1. **Time-phased resource histogram** -- :func:`resource_histogram` aggregates
   per-bucket demand (units + cost) against availability/capacity, generalising
   the per-bucket tally written twice in ``resources/service.py``
   (``portfolio_capacity`` / ``portfolio_leveling``) from "sum of
   ``allocation_percent``" to "demand units vs availability units". With no curve
   row it reproduces today's linear-overlap totals exactly (acceptance #1).
2. **Resource curves** -- :func:`curve_overlap_weight` spreads an assignment's
   units non-linearly across its span: ``flat`` (today's implicit behaviour),
   ``front_load``, ``back_load``, ``bell``. Every named curve integrates to 1.0
   over the assignment, so a curve only *redistributes* demand (acceptance #2).
3. **Multi-rate, effective-dated pricing** -- :func:`effective_rate` resolves the
   rate in force on a date from a rate table, falling back to a supplied default
   when none match; a zero rate is honoured, never coalesced away (acceptance #3).
4. **Smarter leveling** -- :func:`level_preview` runs a serial-greedy leveler
   that honours all four PDM link types (SS/FF/SF, not just FS), supports
   splittable activities, treats labor and non-labor uniformly via fractional
   ``units``, reports single-activity self-overloads as explicit ``unresolvable``
   findings (never spinning to the ceiling), and -- the headline differentiator
   -- always returns a preview delta plus an honest finish-date impact computed
   from a *copy* of the network, before any commit (acceptance #4-#8).

Determinism
-----------
No function reads the wall clock (no ``date.today`` / ``datetime.now``) and none
use randomness. Every input is passed explicitly, so results are fully
reproducible across runs and operating systems. The leveling priority rule is
the one already shipped in ``schedule_advanced/leveling.py``
(LS asc -> total_float asc -> id) and the diff contract is the same "return only
changed ES" one, so FS-only inputs produce byte-identical diffs to today.

Money discipline
----------------
The cost lane is :class:`Decimal` end-to-end; ``float`` is never mixed into money
math. Cost is quantised to cents (``0.01``) but always returned as ``Decimal`` so
the integrating schema can serialise Decimal-as-string. Demand *units* are plain
``float`` -- they model fractional crews / equipment counts and feed the curve
algebra (which is inherently floating point), matching the roadmap pseudocode
(``u = float(a.units) * w``).

Where the design contrasts behaviour with a commercial scheduling tool, that
tool is referred to as "the incumbent"; no product name appears in code.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.modules.schedule_advanced.cpm import (
    Activity,
    CPMResult,
    TaskNetwork,
    compute_cpm,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Recognised resource-spreading curve types; the first entry is the default.
CURVE_TYPES: tuple[str, ...] = ("flat", "front_load", "back_load", "bell")
DEFAULT_CURVE_TYPE: str = CURVE_TYPES[0]

#: Recognised rate types (free-form custom types are also accepted by the
#: resolver -- these are just the well-known ones the roadmap names).
RATE_TYPES: tuple[str, ...] = ("cost", "billing", "overtime")
DEFAULT_RATE_TYPE: str = RATE_TYPES[0]

#: Recognised unit kinds (labour vs non-labour). Treated uniformly by the
#: engine -- the kind is carried through for the UI / cost lane only.
UNIT_KINDS: tuple[str, ...] = ("labor", "equipment", "material", "other")
DEFAULT_UNIT_KIND: str = UNIT_KINDS[0]

#: Money quantum -- two decimal places, kept as ``Decimal``.
_MONEY_Q = Decimal("0.01")

_ZERO = Decimal("0")
_ONE = Decimal("1")

#: Tolerance (in units) for the curve-conservation invariant -- the sum of
#: curve-weighted demand across buckets must equal ``units x total-overlap`` to
#: within this. The named curves integrate analytically (exact CDF), so the only
#: error is floating-point; this leaves generous headroom. Exposed so tests can
#: assert against the same budget.
CURVE_CONSERVATION_TOL: float = 1e-9


# ---------------------------------------------------------------------------
# Decimal / numeric helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any, default: Decimal = _ZERO) -> Decimal:
    """Coerce an arbitrary numeric-ish input to :class:`Decimal`.

    ``None`` and unparseable values fall back to *default*. ``float`` is routed
    through ``str`` so binary-float noise never enters money math. ``bool`` is
    handled before ``int`` to avoid ``True == 1`` surprises in money fields.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
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


def _to_float(value: Any, default: float = 0.0) -> float:
    """Coerce a units-ish input to ``float`` (``None`` / garbage -> *default*)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def _parse_date(value: str | date | datetime) -> date:
    """Parse an ISO date / datetime (or pass a ``date``/``datetime``) to ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# Effective-dated multi-rate resolution (acceptance #3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateRow:
    """One effective-dated rate row (a pure view of ``oe_resources_rate``).

    :param rate: the rate value (``Decimal``); a *zero* rate is legitimate
        (donated kit / pro-bono crews) and is honoured, never coalesced away.
    :param rate_type: ``cost`` | ``billing`` | ``overtime`` | ``<custom>``.
    :param effective_from: inclusive lower bound (``YYYY-MM-DD`` or ``date``).
    :param effective_to: exclusive upper bound, or ``None`` for open-ended.
    :param currency: ISO currency of the rate (surfaced, never converted).
    """

    rate: Decimal = _ZERO
    rate_type: str = DEFAULT_RATE_TYPE
    effective_from: str | date | None = None
    effective_to: str | date | None = None
    currency: str = ""


def _coerce_rate_row(row: RateRow | Mapping[str, Any]) -> RateRow:
    """Normalise a rate row given as a dataclass *or* a plain mapping."""
    if isinstance(row, RateRow):
        return RateRow(
            rate=_to_decimal(row.rate),
            rate_type=str(row.rate_type or DEFAULT_RATE_TYPE),
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            currency=str(row.currency or ""),
        )
    return RateRow(
        rate=_to_decimal(row.get("rate")),
        rate_type=str(row.get("rate_type") or DEFAULT_RATE_TYPE),
        effective_from=row.get("effective_from"),
        effective_to=row.get("effective_to"),
        currency=str(row.get("currency") or ""),
    )


def effective_rate(
    rate_rows: Iterable[RateRow | Mapping[str, Any]],
    rate_type: str,
    on_date: str | date | datetime,
    default_rate: Any,
) -> Decimal:
    """Resolve the rate of ``rate_type`` in force on ``on_date``.

    Picks the row with the latest ``effective_from <= on_date`` among rows of the
    requested ``rate_type`` whose window still covers the date
    (``effective_to is None`` or ``on_date < effective_to`` -- the upper bound is
    exclusive). Rows of other rate types, rows that have not yet taken effect, and
    rows whose window has already closed are ignored.

    Falls back to ``default_rate`` (typically ``Resource.default_cost_rate``)
    when no row matches, so the default column stays the universal fallback. A
    matched **zero** rate is returned as ``Decimal('0')`` -- it is honoured, not
    treated as "missing" and coalesced to the default (acceptance #3). The result
    is always a :class:`Decimal` (never quantised here; the cost lane quantises
    once at the end so intermediate products keep full precision).
    """
    target = _parse_date(on_date)
    best: RateRow | None = None
    best_from: date | None = None
    for raw in rate_rows:
        row = _coerce_rate_row(raw)
        if row.rate_type != rate_type:
            continue
        if row.effective_from is None:
            continue
        eff_from = _parse_date(row.effective_from)
        if eff_from > target:
            continue
        if row.effective_to is not None and target >= _parse_date(row.effective_to):
            continue
        # Latest-effective wins; ties broken by keeping the first seen (stable).
        if best_from is None or eff_from > best_from:
            best = row
            best_from = eff_from
    if best is None:
        return _to_decimal(default_rate)
    return best.rate


# ---------------------------------------------------------------------------
# Resource curves (acceptance #2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Curve:
    """A spreading curve for one assignment (a pure view of the curve table).

    :param curve_type: ``flat`` | ``front_load`` | ``back_load`` | ``bell``.
        Unknown values degrade to ``flat`` (zero-behaviour-change default).
    :param manual_weights: optional explicit per-segment weights; when non-empty
        they are normalised to sum 1.0 and override ``curve_type``. An empty list
        means "use the named curve".
    """

    curve_type: str = DEFAULT_CURVE_TYPE
    manual_weights: tuple[float, ...] = ()


def _coerce_curve(curve: Curve | Mapping[str, Any] | None) -> Curve:
    """Normalise a curve given as a dataclass / mapping / ``None`` (-> flat)."""
    if curve is None:
        return Curve()
    if isinstance(curve, Curve):
        ctype = curve.curve_type or DEFAULT_CURVE_TYPE
        weights = tuple(_to_float(w) for w in curve.manual_weights)
    else:
        ctype = str(curve.get("curve_type") or DEFAULT_CURVE_TYPE)
        raw_weights = curve.get("manual_weights") or ()
        weights = tuple(_to_float(w) for w in raw_weights)
    if ctype not in CURVE_TYPES:
        ctype = DEFAULT_CURVE_TYPE
    return Curve(curve_type=ctype, manual_weights=weights)


def _curve_cdf(curve_type: str, t: float) -> float:
    """Cumulative area of a named curve's unit-integral density on ``[0, t]``.

    Each density integrates to 1.0 over ``[0, 1]``, so the fraction of an
    assignment falling in ``[lo, hi]`` is the *exact* difference
    ``_curve_cdf(type, hi) - _curve_cdf(type, lo)`` (no discretisation error,
    which is what keeps curve conservation exact even for the bell's mid-span
    kink). The densities are:

    * ``flat``       -> ``1``            => CDF ``t``.
    * ``front_load`` -> ``2 * (1 - t)``  => CDF ``2t - t^2`` (linear ramp down).
    * ``back_load``  -> ``2 * t``        => CDF ``t^2`` (linear ramp up).
    * ``bell``       -> a symmetric triangular hump peaking at the midpoint
      (``4t`` for ``t <= 0.5`` then ``4(1 - t)``; integral 1.0, and simpler /
      more deterministic than a truncated Gaussian) => CDF ``2 t^2`` for
      ``t <= 0.5`` and ``1 - 2 (1 - t)^2`` thereafter.

    ``t`` is clamped to ``[0, 1]``.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if curve_type == "front_load":
        return 2.0 * t - t * t
    if curve_type == "back_load":
        return t * t
    if curve_type == "bell":
        if t <= 0.5:
            return 2.0 * t * t
        return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)
    return t  # flat


def _manual_weight_fraction(weights: Sequence[float], lo: float, hi: float) -> float:
    """Fraction of normalised ``weights`` covering the sub-interval ``[lo, hi]``.

    The weights tile ``[0, 1]`` in equal-width segments (segment ``i`` spans
    ``[i/n, (i+1)/n]``). Negative weights are floored at 0; an all-zero or empty
    set yields ``0`` (the caller treats that as "no curve information"). The
    overlap of ``[lo, hi]`` with each segment is taken proportionally.
    """
    clean = [max(0.0, w) for w in weights]
    total = math.fsum(clean)
    n = len(clean)
    if n == 0 or total <= 0.0 or hi <= lo:
        return 0.0
    seg = 1.0 / n
    acc = 0.0
    for i, w in enumerate(clean):
        s_lo = i * seg
        s_hi = (i + 1) * seg
        ov = min(hi, s_hi) - max(lo, s_lo)
        if ov > 0.0:
            acc += (w / total) * (ov / seg)
    return acc


def curve_overlap_weight(
    curve: Curve | Mapping[str, Any] | None,
    assignment_start: str | date | datetime,
    assignment_end: str | date | datetime,
    overlap_start: str | date | datetime,
    overlap_end: str | date | datetime,
) -> float:
    """Fraction of an assignment's curve falling in ``[overlap_start, overlap_end]``.

    For ``flat`` (and the no-curve default) this is the plain *time-overlap
    fraction* -- ``overlap_duration / assignment_duration`` -- so the histogram
    reproduces today's linear-overlap numbers exactly when no curve row exists
    (acceptance #1, zero-behaviour change). For ``front_load`` / ``back_load`` /
    ``bell`` it is the integral of that curve's unit-area density over the
    normalised overlap window, so summing the weight across a partition of the
    assignment yields 1.0 -- the curve only *redistributes* demand (acceptance
    #2). ``manual_weights`` (when present) override the named curve.

    Time is measured in seconds so partial-day buckets are honoured. A zero-length
    assignment, or an overlap clamped outside the assignment, contributes ``0``.
    """
    a_start = _to_epoch(assignment_start)
    a_end = _to_epoch(assignment_end)
    span = a_end - a_start
    if span <= 0.0:
        return 0.0

    # Clamp the overlap window to the assignment, then normalise to [0, 1].
    o_start = max(a_start, _to_epoch(overlap_start))
    o_end = min(a_end, _to_epoch(overlap_end))
    if o_end <= o_start:
        return 0.0
    lo = (o_start - a_start) / span
    hi = (o_end - a_start) / span

    c = _coerce_curve(curve)
    if c.manual_weights:
        frac = _manual_weight_fraction(c.manual_weights, lo, hi)
        if frac > 0.0:
            return frac
        # All-zero manual weights -> fall back to the named curve / flat.

    if c.curve_type == "flat":
        return hi - lo

    # Exact analytic integral of the named density over [lo, hi] via its closed-
    # form CDF -- no discretisation error, so curve conservation holds exactly
    # for every named curve (including the bell's mid-span kink).
    return _curve_cdf(c.curve_type, hi) - _curve_cdf(c.curve_type, lo)


def _to_epoch(value: str | date | datetime | int | float) -> float:
    """Seconds-since-epoch for a date / datetime / ISO string (date -> midnight).

    ``datetime`` MUST be tested before ``date`` (it is a subclass). A bare
    ``int`` / ``float`` is taken to already be epoch seconds (so an epoch produced
    by this helper round-trips safely). Naive datetimes are read as-is (the engine
    compares like-with-like; callers pass a consistent tz convention). This is
    only ever used for *ratios* of durations, so the absolute epoch and any
    timezone offset cancel out.
    """
    if isinstance(value, bool):  # guard: bool is an int subclass
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp() if value.tzinfo else _naive_epoch(value)
    if isinstance(value, date):
        return date_to_ordinal_seconds(value)
    parsed = str(value)
    try:
        dt = datetime.fromisoformat(parsed)
        return dt.timestamp() if dt.tzinfo else _naive_epoch(dt)
    except ValueError:
        return date_to_ordinal_seconds(_parse_date(parsed))


_EPOCH_NAIVE = datetime(1970, 1, 1)
_SECONDS_PER_DAY = 86400.0


def _naive_epoch(dt: datetime) -> float:
    """Seconds between a naive datetime and 1970-01-01 (offset-free, for ratios)."""
    return (dt - _EPOCH_NAIVE).total_seconds()


def date_to_ordinal_seconds(d: date) -> float:
    """Seconds from 1970-01-01 to midnight of ``d`` (offset-free, for ratios)."""
    return (d.toordinal() - date(1970, 1, 1).toordinal()) * _SECONDS_PER_DAY


# ---------------------------------------------------------------------------
# Time-phased resource histogram (acceptance #1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistogramAssignment:
    """A pure, ORM-free view of one assignment for the histogram.

    :param assignment_id: opaque id echoed back in the ``bookings`` list.
    :param project_id: opaque project id (or ``None`` for unassigned).
    :param start: assignment start (``YYYY-MM-DD`` / ``date`` / ``datetime``).
    :param end: assignment end (exclusive).
    :param units: demand in resource-native units (crew=3, excavator=1). Float so
        fractional allocations work; defaults to 1.0.
    :param cost_rate: the assignment's frozen snapshot rate, used as the cost-lane
        fallback when no effective-dated rate row matches a bucket.
    :param curve: optional spreading curve (``None`` -> flat).
    :param unit_kind: labour vs non-labour tag (carried through, not branched on).
    """

    assignment_id: Any
    project_id: Any = None
    start: str | date | datetime = ""
    end: str | date | datetime = ""
    units: float = 1.0
    cost_rate: Decimal = _ZERO
    curve: Curve | None = None
    unit_kind: str = DEFAULT_UNIT_KIND


@dataclass(frozen=True)
class HistogramCell:
    """One bucket of a resource histogram.

    :param bucket_index: 0-based index into the supplied bucket list.
    :param demand_units: curve-weighted demand summed over contributing
        assignments (``float``).
    :param demand_cost: cost-lane total for the bucket (``Decimal``, cents).
    :param available: available units in the bucket, or ``None`` when the
        resource has no declared ceiling (capacity unknown).
    :param capacity_unknown: ``True`` when the resource has no declared capacity.
    :param over_allocated: ``True`` only when capacity is *known* and demand
        exceeds it -- ``capacity_unknown`` cells are never over-allocated.
    :param bookings: per-assignment contribution detail in the bucket.
    """

    bucket_index: int
    demand_units: float
    demand_cost: Decimal
    available: float | None
    capacity_unknown: bool
    over_allocated: bool
    bookings: list[dict[str, Any]] = field(default_factory=list)


def _coerce_hist_assignment(a: HistogramAssignment | Mapping[str, Any]) -> HistogramAssignment:
    """Normalise a histogram assignment given as a dataclass *or* a mapping."""
    if isinstance(a, HistogramAssignment):
        return HistogramAssignment(
            assignment_id=a.assignment_id,
            project_id=a.project_id,
            start=a.start,
            end=a.end,
            units=_to_float(a.units, 1.0),
            cost_rate=_to_decimal(a.cost_rate),
            curve=a.curve,
            unit_kind=str(a.unit_kind or DEFAULT_UNIT_KIND),
        )
    return HistogramAssignment(
        assignment_id=a.get("assignment_id"),
        project_id=a.get("project_id"),
        start=a.get("start", ""),
        end=a.get("end", ""),
        units=_to_float(a.get("units"), 1.0),
        cost_rate=_to_decimal(a.get("cost_rate")),
        curve=a.get("curve"),
        unit_kind=str(a.get("unit_kind") or DEFAULT_UNIT_KIND),
    )


def _hours_in_bucket(b_start: float, b_end: float, hours_per_day: float) -> float:
    """Working hours represented by a bucket of ``[b_start, b_end)`` epoch seconds."""
    days = max(0.0, (b_end - b_start) / _SECONDS_PER_DAY)
    return days * hours_per_day


def resource_histogram(
    assignments: Iterable[HistogramAssignment | Mapping[str, Any]],
    buckets: Sequence[tuple[int, Any, Any, Any]],
    *,
    capacity_units: float | None,
    rate_rows: Iterable[RateRow | Mapping[str, Any]] = (),
    blocked_bucket_indices: Iterable[int] = (),
    hours_per_day: float = 8.0,
    rate_type: str = DEFAULT_RATE_TYPE,
) -> list[HistogramCell]:
    """Aggregate a resource's demand vs availability/cost across ``buckets``.

    This is the pure kernel the roadmap factors out of ``portfolio_capacity`` /
    ``portfolio_leveling``, generalised from "sum of allocation_percent" to
    "demand units vs availability units" and given the two missing lanes
    (availability + curve-weighted demand + a cost lane).

    For each bucket and each overlapping assignment, demand is
    ``units x curve_overlap_weight(curve, a_start, a_end, overlap)`` -- with no
    curve row that weight is the plain time-overlap fraction, so the per-bucket
    *unit* totals reproduce today's linear-overlap numbers (acceptance #1). The
    cost lane multiplies that demand by the bucket's working hours and the
    effective-dated rate in force at the bucket start (falling back to the
    assignment's frozen ``cost_rate``), and is returned as a quantised
    :class:`Decimal`.

    Over-allocation honours "never fabricate a ceiling": when ``capacity_units``
    is ``None`` the cell is ``capacity_unknown`` and *never* ``over_allocated``.
    ``blocked_bucket_indices`` lists buckets fully blocked by an
    unavailable/holiday/sick window -- their ``available`` drops to ``0`` (only
    meaningful when capacity is known).

    Args:
        buckets: ``(index, start, end, label)`` tuples (label unused here); start
            / end may be ``date`` / ``datetime`` / ISO strings.
        capacity_units: the resource's ceiling in native units, or ``None``.
        rate_rows: effective-dated rate rows for the cost lane.
        blocked_bucket_indices: bucket indices with no availability.
        hours_per_day: working hours per day for the cost lane.
        rate_type: which rate type drives the cost lane (default ``cost``).
    """
    coerced = [_coerce_hist_assignment(a) for a in assignments]
    blocked = set(blocked_bucket_indices)
    capacity_unknown = capacity_units is None
    cells: list[HistogramCell] = []

    for bucket in buckets:
        bi, b_start_raw, b_end_raw = bucket[0], bucket[1], bucket[2]
        b_start = _to_epoch(b_start_raw)
        b_end = _to_epoch(b_end_raw)
        demand_units = 0.0
        demand_cost = _ZERO
        bookings: list[dict[str, Any]] = []
        bucket_hours = _hours_in_bucket(b_start, b_end, hours_per_day)

        for a in coerced:
            a_start = _to_epoch(a.start)
            a_end = _to_epoch(a.end)
            # Half-open overlap test, identical in spirit to _intervals_overlap.
            if not (a_start < b_end and b_start < a_end):
                continue
            # Pass the bucket window as the overlap; curve_overlap_weight clamps it
            # to [a_start, a_end] itself, so the curve fraction is exact and we
            # never re-encode an epoch float as a date.
            weight = curve_overlap_weight(a.curve, a.start, a.end, b_start_raw, b_end_raw)
            u = a.units * weight
            if u == 0.0:
                continue
            demand_units += u
            rate = effective_rate(rate_rows, rate_type, _bucket_date(b_start_raw), a.cost_rate)
            demand_cost += _to_decimal(u) * _to_decimal(bucket_hours) * rate
            bookings.append(
                {
                    "assignment_id": a.assignment_id,
                    "project_id": a.project_id,
                    "units": u,
                    "unit_kind": a.unit_kind,
                }
            )

        if capacity_unknown:
            available: float | None = None
            over = False
        else:
            available = 0.0 if bi in blocked else float(capacity_units)  # type: ignore[arg-type]
            over = demand_units > float(capacity_units)  # type: ignore[arg-type]

        cells.append(
            HistogramCell(
                bucket_index=bi,
                demand_units=demand_units,
                demand_cost=quantize_money(demand_cost),
                available=available,
                capacity_unknown=capacity_unknown,
                over_allocated=over,
                bookings=bookings,
            )
        )
    return cells


def _bucket_date(value: Any) -> date:
    """Best-effort date of a bucket start for rate resolution."""
    try:
        return _parse_date(value)
    except (ValueError, TypeError):
        if isinstance(value, datetime):
            return value.date()
        return date(1970, 1, 1)


# ---------------------------------------------------------------------------
# Smarter leveling (acceptance #4, #5, #6, #8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Unresolvable:
    """A single-activity self-overload that leveling cannot clear by shifting.

    Raised when an activity's own demand for a resource exceeds that resource's
    ceiling: no amount of moving the activity in time will fit it, so the engine
    reports it explicitly rather than spinning forward to the search ceiling.

    :param activity_id: the offending activity.
    :param resource: the resource code whose ceiling is exceeded.
    :param required: units the activity alone demands of the resource.
    :param limit: the resource ceiling.
    """

    activity_id: Any
    resource: str
    required: float
    limit: float


@dataclass(frozen=True)
class Shift:
    """One activity whose early start moved under leveling.

    :param activity_id: the shifted activity.
    :param base_es: early start before leveling (work-day index).
    :param new_es: early start after leveling (work-day index).
    :param delta: ``new_es - base_es`` (always ``>= 0`` -- leveling never pulls
        an activity earlier).
    """

    activity_id: Any
    base_es: int
    new_es: int
    delta: int


@dataclass(frozen=True)
class LevelingPreview:
    """The read-only result of :func:`level_preview` (preview == apply intent).

    :param shifts: activities whose ES moved (only changed activities, mirroring
        the existing diff contract).
    :param segments: ``{activity_id: [(start, finish), ...]}`` for splittable
        activities placed in multiple day-runs; whole (non-split) activities are
        absent.
    :param finish_delta_days: leveled project finish minus base project finish
        (``>= 0``); the honest finish-date impact shown before any commit.
    :param base_finish_workday: project finish (max EF) before leveling.
    :param leveled_finish_workday: project finish (max EF) after leveling.
    :param unresolvable: single-activity self-overloads (see :class:`Unresolvable`).
    :param peak_before: per-resource peak concurrent demand before leveling.
    :param peak_after: per-resource peak concurrent demand after leveling.
    """

    shifts: list[Shift]
    segments: dict[Any, list[tuple[int, int]]]
    finish_delta_days: int
    base_finish_workday: int
    leveled_finish_workday: int
    unresolvable: list[Unresolvable]
    peak_before: dict[str, float]
    peak_after: dict[str, float]


def _earliest_legal_start(
    network: TaskNetwork,
    aid: Any,
    dur: int,
    original_es: int,
    schedule: dict[Any, tuple[int, int]],
) -> int:
    """Earliest start honouring ALL four PDM link types from placed predecessors.

    Mirrors the CPM forward-pass algebra in
    :func:`schedule_advanced.cpm.compute_cpm` translated to an ES lower bound, so
    leveled starts can never violate a constraint the scheduler the app trusts
    would enforce (acceptance #4). FS is unchanged from the existing FS-only
    leveler, so FS-only inputs reproduce today's bound exactly:

        FS: earliest = max(earliest, p_finish + lag)
        SS: earliest = max(earliest, p_start  + lag)
        FF: earliest = max(earliest, p_finish + lag - dur)
        SF: earliest = max(earliest, p_start  + lag - dur)
    """
    earliest = original_es
    for p_id, dep_type, lag in network.predecessors(aid):
        if p_id not in schedule:
            continue
        p_start, p_finish = schedule[p_id]
        lag = int(lag)
        if dep_type == "SS":
            earliest = max(earliest, p_start + lag)
        elif dep_type == "FF":
            earliest = max(earliest, p_finish + lag - dur)
        elif dep_type == "SF":
            earliest = max(earliest, p_start + lag - dur)
        else:  # FS (default) -- unchanged
            earliest = max(earliest, p_finish + lag)
    return earliest


class _DemandTimeline:
    """Incremental per-resource demand timeline for fast placement.

    ``timeline[resource][day] -> running_units``. Updated once when an activity is
    locked, so each placement check is O(duration x resources_of_activity) rather
    than O(duration x all_activities) -- the fix for the "slow leveler" rescan.
    Units are fractional (labour and non-labour on one axis).
    """

    __slots__ = ("_t", "_peak")

    def __init__(self) -> None:
        self._t: dict[str, dict[int, float]] = {}
        self._peak: dict[str, float] = {}

    def fits(self, start: int, finish: int, demand: Mapping[str, float], limits: Mapping[str, float | None]) -> bool:
        """True iff adding ``demand`` over ``[start, finish)`` respects every limit."""
        for resource, req in demand.items():
            if req <= 0.0:
                continue
            limit = limits.get(resource)
            if limit is None:
                continue  # no ceiling -> always fits
            lane = self._t.get(resource)
            if lane is None:
                if req > limit:
                    return False
                continue
            for day in range(start, finish):
                if lane.get(day, 0.0) + req > limit + _PLACE_EPS:
                    return False
        return True

    def add(self, start: int, finish: int, demand: Mapping[str, float]) -> None:
        """Lock ``demand`` over ``[start, finish)`` into the timeline."""
        for resource, req in demand.items():
            if req <= 0.0:
                continue
            lane = self._t.setdefault(resource, {})
            for day in range(start, finish):
                lane[day] = lane.get(day, 0.0) + req
                if lane[day] > self._peak.get(resource, 0.0):
                    self._peak[resource] = lane[day]

    def peaks(self) -> dict[str, float]:
        """Per-resource peak concurrent demand seen so far."""
        return dict(self._peak)


#: Floating-point slack so a demand that equals its limit is not rejected by
#: accumulated binary-float error (e.g. 0.1*3 vs 0.3).
_PLACE_EPS: float = 1e-9


def _activity_units(a: Activity) -> dict[str, float]:
    """Per-resource demand for an activity as floats (from ``required_resources``).

    ``required_resources`` is the ``{code: count}`` map the CPM engine already
    carries; widening the values to ``float`` is what lets a 3-person crew and a
    single excavator (or any fractional allocation) sit on the same axis -- the
    mixed labour/non-labour handling the incumbent lacks.
    """
    return {code: float(req) for code, req in a.required_resources.items()}


def _peak_demand(
    schedule: dict[Any, tuple[int, int]],
    activities: dict[Any, Activity],
    segments: Mapping[Any, list[tuple[int, int]]] | None = None,
) -> dict[str, float]:
    """Per-resource peak concurrent demand over a placed schedule (pure).

    Honours split ``segments`` when given (a split activity only consumes its
    resources during its placed runs, not across the gaps).
    """
    segments = segments or {}
    day_demand: dict[str, dict[int, float]] = {}
    for aid, (start, finish) in schedule.items():
        runs = segments.get(aid) or [(start, finish)]
        units = _activity_units(activities[aid])
        for run_start, run_finish in runs:
            for day in range(run_start, run_finish):
                for resource, req in units.items():
                    if req <= 0.0:
                        continue
                    lane = day_demand.setdefault(resource, {})
                    lane[day] = lane.get(day, 0.0) + req
    return {res: max(lane.values()) for res, lane in day_demand.items() if lane}


def _place_contiguous(
    earliest: int,
    dur: int,
    demand: Mapping[str, float],
    limits: Mapping[str, float | None],
    timeline: _DemandTimeline,
    ceiling: int,
) -> int:
    """Walk forward from ``earliest`` to the first start where ``demand`` fits."""
    start = earliest
    while start <= ceiling and not timeline.fits(start, start + dur, demand, limits):
        start += 1
    return start


def _place_split(
    earliest: int,
    dur: int,
    demand: Mapping[str, float],
    limits: Mapping[str, float | None],
    timeline: _DemandTimeline,
    ceiling: int,
) -> list[tuple[int, int]] | None:
    """Place a splittable activity in feasible single-day runs summing to ``dur``.

    Walks day by day from ``earliest``; a day is usable when the activity's demand
    fits there. Consecutive usable days are merged into runs; the activity needs
    ``dur`` working days total. Returns the list of ``(start, finish)`` runs, or
    ``None`` when ``dur`` days cannot be found before ``ceiling``.
    """
    runs: list[tuple[int, int]] = []
    placed = 0
    day = earliest
    run_start: int | None = None
    while placed < dur and day <= ceiling:
        if timeline.fits(day, day + 1, demand, limits):
            if run_start is None:
                run_start = day
            placed += 1
            day += 1
        else:
            if run_start is not None:
                runs.append((run_start, day))
                run_start = None
            day += 1
    if run_start is not None:
        runs.append((run_start, day))
    if placed < dur:
        return None
    return runs


def level_by_resource_units(
    network: TaskNetwork,
    cpm_result: dict[Any, CPMResult],
    resource_limits: Mapping[str, float | None],
    *,
    splittable: set[Any] | None = None,
) -> tuple[dict[Any, int], dict[Any, list[tuple[int, int]]], list[Unresolvable]]:
    """Serial-greedy leveling honouring SS/FF/SF, splitting, and fractional units.

    The structural successor to ``schedule_advanced.leveling.level_by_resource_max``
    (which this module cannot edit in place): same priority rule
    (LS asc -> total_float asc -> id) and same "return only changed ES" diff
    contract, extended per the roadmap with

    * **all four PDM link types** via :func:`_earliest_legal_start` (acceptance #4;
      FS-only inputs yield byte-identical diffs to today),
    * **fast incremental placement** via :class:`_DemandTimeline` (no per-day x
      per-activity rescan),
    * **fractional / mixed units** (labour crew + equipment on one axis;
      acceptance #9),
    * **splittable activities** placed in day-runs summing to their duration
      (acceptance #5), and
    * **single-activity self-overloads** returned as explicit
      :class:`Unresolvable` findings instead of spinning to the ceiling
      (acceptance #6) -- such activities are still placed at their earliest legal
      start so leveling completes for everyone else.

    Returns ``(diff, segments, unresolvable)`` where ``diff`` maps changed
    activity ids to their new ES, ``segments`` maps split activity ids to their
    placed runs, and ``unresolvable`` lists the self-overloads. Never mutates the
    network or the CPM result.
    """
    splittable = splittable or set()
    if not cpm_result:
        return {}, {}, []

    activities: dict[Any, Activity] = {a.id: a for a in network.activities}
    original_es: dict[Any, int] = {aid: r.es for aid, r in cpm_result.items()}

    # Up-front self-overload detection (acceptance #6): an activity whose own
    # demand exceeds a ceiling can never fit, regardless of placement.
    unresolvable: list[Unresolvable] = []
    for aid in sorted(activities, key=str):
        for resource, req in _activity_units(activities[aid]).items():
            if req <= 0.0:
                continue
            limit = resource_limits.get(resource)
            if limit is not None and req > limit + _PLACE_EPS:
                unresolvable.append(Unresolvable(activity_id=aid, resource=resource, required=req, limit=float(limit)))
    self_overloaded = {u.activity_id for u in unresolvable}

    if not resource_limits:
        return {}, {}, unresolvable

    # Stable priority order -- identical to the shipped leveler.
    priority: list[Any] = sorted(
        cpm_result.keys(),
        key=lambda aid: (cpm_result[aid].ls, cpm_result[aid].total_float, str(aid)),
    )

    total_dur = sum(max(0, int(x.duration)) for x in activities.values())
    timeline = _DemandTimeline()
    schedule: dict[Any, tuple[int, int]] = {}
    segments: dict[Any, list[tuple[int, int]]] = {}

    for aid in priority:
        a = activities.get(aid)
        if a is None:
            continue
        dur = max(0, int(a.duration))
        demand = _activity_units(a)
        earliest = _earliest_legal_start(network, aid, dur, original_es[aid], schedule)

        if dur == 0 or not demand:
            schedule[aid] = (earliest, earliest + dur)
            timeline.add(earliest, earliest + dur, demand)
            continue

        ceiling = earliest + total_dur + 1

        # A self-overloaded activity can never satisfy its own ceiling; placing it
        # at its earliest legal start (rather than walking to the search ceiling)
        # keeps the rest of the run meaningful and the finish honest.
        if aid in self_overloaded:
            schedule[aid] = (earliest, earliest + dur)
            timeline.add(earliest, earliest + dur, demand)
            continue

        if aid in splittable:
            runs = _place_split(earliest, dur, demand, resource_limits, timeline, ceiling)
            if runs is not None and len(runs) > 1:
                start = runs[0][0]
                finish = runs[-1][1]
                schedule[aid] = (start, finish)
                segments[aid] = runs
                for r_start, r_finish in runs:
                    timeline.add(r_start, r_finish, demand)
                continue
            # Splittable but fit contiguously (or could not split) -> fall through.

        start = _place_contiguous(earliest, dur, demand, resource_limits, timeline, ceiling)
        schedule[aid] = (start, start + dur)
        timeline.add(start, start + dur, demand)

    diff: dict[Any, int] = {}
    for aid, (new_start, _finish) in schedule.items():
        if new_start != original_es[aid]:
            diff[aid] = new_start
    return diff, segments, unresolvable


def _shifted_network(
    network: TaskNetwork,
    diff: Mapping[Any, int],
    base_es: Mapping[Any, int],
) -> TaskNetwork:
    """Build a COPY of ``network`` that pins each leveled start.

    Re-seeding the leveled ES as a zero-lag constraint from a virtual start would
    also work; instead we pin via an extra FS predecessor from a synthetic origin
    so the recomputed forward pass honours the lock without mutating durations or
    the original activities. The original network is never mutated.

    For each activity we add a self-anchoring constraint: a milestone ``__origin__``
    at day 0 plus an FS edge with lag = leveled ES, which forces ``ES >= leveled``
    while the real predecessor logic still applies its own (>=) bounds -- so the
    recomputed finish reflects both leveling and logic (acceptance #8).
    """
    origin = "__origin__"
    new_activities: list[Activity] = [Activity(id=origin, duration=0)]
    for a in network.activities:
        pinned = diff.get(a.id, base_es.get(a.id))
        preds = list(a.predecessors)
        if pinned is not None and pinned > 0:
            preds = [*preds, (origin, "FS", int(pinned))]
        new_activities.append(
            Activity(
                id=a.id,
                duration=a.duration,
                predecessors=preds,
                required_resources=dict(a.required_resources),
            )
        )
    return TaskNetwork(new_activities)


def _max_ef(results: Mapping[Any, CPMResult], exclude: set[Any] | None = None) -> int:
    """Project finish = max EF over results, ignoring ``exclude`` (synthetic) ids."""
    exclude = exclude or set()
    efs = [r.ef for aid, r in results.items() if aid not in exclude]
    return max(efs) if efs else 0


def level_preview(
    network: TaskNetwork,
    resource_limits: Mapping[str, float | None],
    *,
    splittable: set[Any] | None = None,
) -> LevelingPreview:
    """Read-only leveling preview with an honest finish-date impact (acceptance #7/#8).

    Computes everything from a *copy* of the network and never mutates the inputs,
    so the same payload can drive both the preview endpoint and the apply
    endpoint -- what the planner approves is exactly what gets written. Steps:

    1. Run base CPM -> ``base_finish`` (max EF) and per-resource ``peak_before``.
    2. Level (SS/FF/SF, split, fractional units, self-overload findings).
    3. Rebuild a pinned copy of the network and re-run CPM -> ``leveled_finish``;
       ``finish_delta_days = leveled_finish - base_finish`` (clamped ``>= 0``).
    4. Compute ``peak_after`` from the leveled schedule (honouring split runs).

    The result is labelled by its data, not its prose: ``finish_delta_days`` is
    the real post-level critical-chain slip, surfaced *before* any commit -- where
    the incumbent extends the finish opaquely.
    """
    splittable = splittable or set()
    base = compute_cpm(network)
    if not base:
        return LevelingPreview(
            shifts=[],
            segments={},
            finish_delta_days=0,
            base_finish_workday=0,
            leveled_finish_workday=0,
            unresolvable=[],
            peak_before={},
            peak_after={},
        )

    base_es = {aid: r.es for aid, r in base.items()}
    base_finish = _max_ef(base)
    activities: dict[Any, Activity] = {a.id: a for a in network.activities}
    base_schedule = {aid: (r.es, r.ef) for aid, r in base.items()}
    peak_before = _peak_demand(base_schedule, activities)

    diff, segments, unresolvable = level_by_resource_units(network, base, resource_limits, splittable=splittable)

    shifts = [
        Shift(activity_id=aid, base_es=base_es[aid], new_es=new_es, delta=new_es - base_es[aid])
        for aid, new_es in sorted(diff.items(), key=lambda kv: str(kv[0]))
    ]

    # Honest finish: re-run CPM over a copy that pins the leveled starts.
    pinned = _shifted_network(network, diff, base_es)
    leveled = compute_cpm(pinned)
    leveled_finish = _max_ef(leveled, exclude={"__origin__"})
    finish_delta = max(0, leveled_finish - base_finish)

    # peak_after from the leveled schedule (use pinned ES, honour split runs).
    leveled_schedule: dict[Any, tuple[int, int]] = {}
    for aid in activities:
        es = diff.get(aid, base_es.get(aid, 0))
        leveled_schedule[aid] = (es, es + max(0, int(activities[aid].duration)))
    peak_after = _peak_demand(leveled_schedule, activities, segments)

    return LevelingPreview(
        shifts=shifts,
        segments=segments,
        finish_delta_days=finish_delta,
        base_finish_workday=base_finish,
        leveled_finish_workday=leveled_finish,
        unresolvable=unresolvable,
        peak_before=peak_before,
        peak_after=peak_after,
    )


__all__ = [
    "CURVE_CONSERVATION_TOL",
    "CURVE_TYPES",
    "DEFAULT_CURVE_TYPE",
    "DEFAULT_RATE_TYPE",
    "DEFAULT_UNIT_KIND",
    "RATE_TYPES",
    "UNIT_KINDS",
    "Activity",
    "Curve",
    "HistogramAssignment",
    "HistogramCell",
    "LevelingPreview",
    "RateRow",
    "Shift",
    "TaskNetwork",
    "Unresolvable",
    "compute_cpm",
    "curve_overlap_weight",
    "date_to_ordinal_seconds",
    "effective_rate",
    "level_by_resource_units",
    "level_preview",
    "quantize_money",
    "resource_histogram",
]
