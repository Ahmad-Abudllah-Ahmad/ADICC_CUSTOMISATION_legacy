# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Pure interference risk matrix - correlate open clashes with the schedule.

A static clash report tells a coordinator *what* collides. It never tells
them *when* the two colliding trades are actually booked to be on site at
the same time while the clash is still open. That is the moment a paper
clash turns into a field interference: two crews arrive, the beam is still
through the duct, and someone stops work.

This module is the testable core of that correlation. It is deliberately
free of any database, ORM or I/O so it can be unit-tested with plain
values. The owning service (``clash.service``) is responsible for
resolving each clash to its affected BOQ positions, mapping those
positions to schedule activities and reading the planned date windows,
then handing this function a list of :class:`ClashScheduleFacts`.

For each open clash the function answers:

* do the two trades' planned work windows overlap in time,
* how many days of overlap (or, when disjoint, the gap between them),
* how soon the shared window starts relative to a reference ``today``,
* a risk score combining severity x cost impact x window proximity,
* a status: ``imminent`` / ``upcoming`` / ``no-overlap`` /
  ``no-schedule-data``.

Money stays in :class:`~decimal.Decimal` the whole way through; the cost
impact is echoed back byte-exact and the risk score is computed with
Decimal arithmetic so the ranking never picks up binary-float drift.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# ── Vocabulary ──────────────────────────────────────────────────────────────

#: Clash lifecycle states that still carry an interference risk. Covers both
#: the per-row ``ClashResult`` open set (``new``/``active``/``reviewed``) and
#: the smart-issue lifecycle open set (``new``/``persisted``); a resolved,
#: approved, ignored or archived clash no longer warns anyone. Passed as a
#: default so callers may narrow it, but never has to be imported from the DB
#: layer - keeping this module standalone and DB-free.
OPEN_STATUSES: frozenset[str] = frozenset({"new", "active", "reviewed", "persisted"})

#: Severity to numeric weight, worst carries the most weight. Matches the
#: clash module's ``CLASH_SEVERITIES`` ordering (critical is worst) but is
#: kept local so the pure core never reaches into the schema layer.
SEVERITY_WEIGHTS: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}

#: Weight for an unrecognised / missing severity label. One (the ``low``
#: weight) so a mislabelled clash never inflates its own ranking.
DEFAULT_SEVERITY_WEIGHT = 1

#: Default horizon: an overlap whose shared window opens within this many days
#: of ``today`` (or is already in progress / past) counts as ``imminent``;
#: further out is ``upcoming``. Thirty days is a common look-ahead window.
DEFAULT_IMMINENT_WITHIN_DAYS = 30

# Status labels (hyphenated, matching the task's vocabulary).
STATUS_IMMINENT = "imminent"
STATUS_UPCOMING = "upcoming"
STATUS_NO_OVERLAP = "no-overlap"
STATUS_NO_SCHEDULE_DATA = "no-schedule-data"

#: Proximity assigned when one or both trades have no linked schedule window.
#: Non-zero so the clash still surfaces (we cannot prove it is safe), but low
#: so a clash we *can* time-correlate always outranks a blind one at equal
#: severity and cost.
_NO_DATA_PROXIMITY = Decimal("0.15")

#: Multiplier applied to a disjoint (no time overlap) clash's proximity, so a
#: clash whose trades never share the site ranks below an equivalent one whose
#: trades do. The nearer the two windows sit, the closer to this ceiling.
_NO_OVERLAP_PENALTY = Decimal("0.25")

#: Decimal quantum for the emitted risk score. The internal product stays
#: exact; this only tidies the surfaced value.
_SCORE_QUANTUM = Decimal("0.0001")
_PROXIMITY_QUANTUM = Decimal("0.000001")


# ── Inputs / outputs ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClashScheduleFacts:
    """Everything the correlation needs about a single clash.

    ``activity_windows_a`` / ``activity_windows_b`` are the planned date
    windows of the schedule activities linked (via the affected BOQ
    positions) to trade A and trade B respectively. Each window is a
    ``(start, end)`` pair; start and end may be a :class:`datetime.date`,
    a :class:`datetime.datetime` or an ISO date/datetime string - they are
    normalised internally, and any window with an unparseable or missing
    endpoint is dropped.
    """

    clash_id: str
    severity: str
    cost_impact: Decimal
    trade_a: str
    trade_b: str
    activity_windows_a: Sequence[Sequence[Any]] = field(default_factory=tuple)
    activity_windows_b: Sequence[Sequence[Any]] = field(default_factory=tuple)
    status: str = "new"


@dataclass(frozen=True)
class ClashRiskRecord:
    """The interference verdict for one clash.

    ``risk_score`` and ``cost_impact`` are :class:`~decimal.Decimal`;
    ``cost_impact`` is echoed exactly as supplied. ``days_until_overlap`` is
    signed - negative when the shared window has already opened - and is
    ``None`` when the trades never overlap or the schedule link is missing.
    ``gap_days`` is the number of days between the two windows when they are
    disjoint (``None`` otherwise).
    """

    clash_id: str
    severity: str
    trade_a: str
    trade_b: str
    cost_impact: Decimal
    status: str
    overlaps: bool
    overlap_days: int
    days_until_overlap: int | None
    gap_days: int | None
    window_a: tuple[date, date] | None
    window_b: tuple[date, date] | None
    risk_score: Decimal
    explanation: str


# ── Helpers ─────────────────────────────────────────────────────────────────


def _coerce_date(value: Any) -> date | None:
    """Best-effort coercion of a date-like value to a :class:`date`.

    Accepts ``date``, ``datetime`` and ISO date/datetime strings. A
    datetime (or datetime string) is narrowed to its date. Anything empty
    or unparseable returns ``None`` so the caller can drop the window
    instead of raising on one bad schedule row.
    """
    if value is None:
        return None
    # datetime is a subclass of date - test it first.
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        head = text.replace("T", " ").split(" ", 1)[0]
        for candidate in (text, head):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None
    return None


def _normalise_windows(raw: Sequence[Sequence[Any]] | None) -> list[tuple[date, date]]:
    """Coerce a sequence of ``(start, end)`` pairs into clean date windows.

    Windows with a missing or unparseable endpoint are dropped; a window
    whose start falls after its end is swapped (defensive against a
    backwards schedule row) so downstream overlap maths always sees
    ``start <= end``.
    """
    out: list[tuple[date, date]] = []
    if not raw:
        return out
    for item in raw:
        if item is None:
            continue
        try:
            start_raw, end_raw = item[0], item[1]
        except (TypeError, KeyError, IndexError, ValueError):
            continue
        start = _coerce_date(start_raw)
        end = _coerce_date(end_raw)
        if start is None or end is None:
            continue
        if start > end:
            start, end = end, start
        out.append((start, end))
    return out


def _envelope(windows: list[tuple[date, date]]) -> tuple[date, date] | None:
    """Earliest start to latest end across ``windows`` (for display)."""
    if not windows:
        return None
    return (min(w[0] for w in windows), max(w[1] for w in windows))


def _best_pair(
    windows_a: list[tuple[date, date]],
    windows_b: list[tuple[date, date]],
) -> tuple[int, date, date]:
    """Return the most-overlapping (or least-gapped) A/B window pair.

    The measure is ``(min(end_a, end_b) - max(start_a, start_b)).days``:
    positive means the two windows overlap by that many days, zero means
    they touch on a shared boundary day, negative means they are disjoint
    by that many days. We keep the maximum such value across every pair, so
    a trade with two activity windows correlates on its closest approach.
    Returns ``(delta_days, shared_start, shared_end)`` where the two dates
    are the bounds of the best pair's intersection (meaningful only when
    ``delta_days >= 0``). Both window lists must be non-empty (the caller
    guarantees it), so the first pair primes the running best.
    """
    prime_start = max(windows_a[0][0], windows_b[0][0])
    prime_end = min(windows_a[0][1], windows_b[0][1])
    best: tuple[int, date, date] = ((prime_end - prime_start).days, prime_start, prime_end)
    for start_a, end_a in windows_a:
        for start_b, end_b in windows_b:
            shared_start = max(start_a, start_b)
            shared_end = min(end_a, end_b)
            delta = (shared_end - shared_start).days
            if delta > best[0]:
                best = (delta, shared_start, shared_end)
    return best


def _severity_weight(severity: str | None) -> int:
    """Numeric weight for a severity label (unknown -> lowest)."""
    return SEVERITY_WEIGHTS.get((severity or "").strip().lower(), DEFAULT_SEVERITY_WEIGHT)


def _as_decimal(value: Any) -> Decimal:
    """Coerce a cost value to Decimal without losing exactness.

    A ``Decimal`` passes straight through (byte-exact echo); ints and
    strings convert exactly; a float is stringified first so we never bake
    binary-float noise into the money. Bad input degrades to ``0``.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return Decimal("0")


def _proximity_overlap(days_until: int, horizon: int) -> Decimal:
    """Proximity weight for an overlapping clash.

    ``horizon / (horizon + max(0, days_until))``: 1.0 when the shared
    window is open now or already past, decaying towards zero the further
    the overlap sits in the future. Always in ``(0, 1]``.
    """
    effective = max(0, days_until)
    return (Decimal(horizon) / Decimal(horizon + effective)).quantize(_PROXIMITY_QUANTUM, rounding=ROUND_HALF_UP)


def _proximity_gap(gap_days: int, horizon: int) -> Decimal:
    """Proximity weight for a disjoint clash - penalised, nearer ranks higher."""
    prox = _NO_OVERLAP_PENALTY * (Decimal(horizon) / Decimal(horizon + gap_days))
    return prox.quantize(_PROXIMITY_QUANTUM, rounding=ROUND_HALF_UP)


def _pluralise(count: int, noun: str) -> str:
    """``1 day`` / ``2 days`` - plain English, no cleverness."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


# ── Core ────────────────────────────────────────────────────────────────────


def is_open_status(status: str | None, open_statuses: Iterable[str] = OPEN_STATUSES) -> bool:
    """True when ``status`` is one of the open (still-warning) states."""
    return (status or "").strip().lower() in {s.lower() for s in open_statuses}


def assess_clash(
    facts: ClashScheduleFacts,
    *,
    today: date,
    imminent_within_days: int = DEFAULT_IMMINENT_WITHIN_DAYS,
) -> ClashRiskRecord:
    """Compute the interference verdict for one clash (status-agnostic).

    This does not filter on ``facts.status`` - it evaluates whatever it is
    given, which keeps it trivially unit-testable on a single clash. Use
    :func:`build_interference_risk_matrix` for the open-only, ranked list.
    """
    horizon = max(1, int(imminent_within_days))
    weight = _severity_weight(facts.severity)
    cost = _as_decimal(facts.cost_impact)

    windows_a = _normalise_windows(facts.activity_windows_a)
    windows_b = _normalise_windows(facts.activity_windows_b)
    env_a = _envelope(windows_a)
    env_b = _envelope(windows_b)

    overlap_days = 0
    days_until: int | None = None
    gap_days: int | None = None

    if not windows_a or not windows_b:
        status = STATUS_NO_SCHEDULE_DATA
        overlaps = False
        proximity = _NO_DATA_PROXIMITY
        missing = []
        if not windows_a:
            missing.append(facts.trade_a or "trade A")
        if not windows_b:
            missing.append(facts.trade_b or "trade B")
        explanation = f"No linked schedule window for {' and '.join(missing)}; cannot time the interference."
    else:
        delta, shared_start, shared_end = _best_pair(windows_a, windows_b)
        if delta >= 0:
            overlaps = True
            overlap_days = delta
            days_until = (shared_start - today).days
            proximity = _proximity_overlap(days_until, horizon)
            if days_until <= horizon:
                status = STATUS_IMMINENT
            else:
                status = STATUS_UPCOMING
            span = _pluralise(overlap_days, "day")
            if days_until < 0:
                when = f"shared window opened {_pluralise(-days_until, 'day')} ago and is still open"
            elif days_until == 0:
                when = "shared window opens today"
            else:
                when = f"shared window opens in {_pluralise(days_until, 'day')}"
            explanation = f"{facts.trade_a} and {facts.trade_b} overlap by {span}; {when}."
        else:
            overlaps = False
            gap_days = -delta
            proximity = _proximity_gap(gap_days, horizon)
            status = STATUS_NO_OVERLAP
            explanation = (
                f"{facts.trade_a} and {facts.trade_b} are scheduled {_pluralise(gap_days, 'day')} "
                "apart; no time overlap."
            )

    risk_score = (Decimal(weight) * cost * proximity).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)

    return ClashRiskRecord(
        clash_id=facts.clash_id,
        severity=facts.severity,
        trade_a=facts.trade_a,
        trade_b=facts.trade_b,
        cost_impact=cost,
        status=status,
        overlaps=overlaps,
        overlap_days=overlap_days,
        days_until_overlap=days_until,
        gap_days=gap_days,
        window_a=env_a,
        window_b=env_b,
        risk_score=risk_score,
        explanation=explanation,
    )


def build_interference_risk_matrix(
    facts: Iterable[ClashScheduleFacts],
    *,
    today: date,
    imminent_within_days: int = DEFAULT_IMMINENT_WITHIN_DAYS,
    open_statuses: Iterable[str] = OPEN_STATUSES,
) -> list[ClashRiskRecord]:
    """Rank every *open* clash by interference risk, highest first.

    Closed / resolved / ignored clashes are excluded (they no longer warn
    anyone). The remaining records are ordered by risk score descending,
    then by exact cost impact descending, then by ``clash_id`` ascending so
    the order is fully deterministic across runs and backends.
    """
    open_set = {s.lower() for s in open_statuses}
    records = [
        assess_clash(item, today=today, imminent_within_days=imminent_within_days)
        for item in facts
        if is_open_status(item.status, open_set)
    ]
    records.sort(key=lambda r: (-r.risk_score, -r.cost_impact, r.clash_id))
    return records
