# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Critical Path Method (CPM) calculation engine.

Forward pass -> early dates. Backward pass -> late dates. Float -> critical path.
Calendar-aware (skips weekends/holidays via work_calendar).

This module is stateless and operates on plain dicts, making it easy to test
independently of the ORM and database layer.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# Default work calendar: Mon-Fri, no holidays
_DEFAULT_CALENDAR: dict = {
    "work_days": {0, 1, 2, 3, 4},
    "exceptions": [],
}


def _parse_work_days(calendar: dict | None) -> set[int]:
    """Extract working day indices (0=Mon .. 6=Sun) from a calendar dict.

    Values outside 0..6 and non-numeric junk are dropped, and an empty result
    falls back to the Monday-Friday default. This guarantees at least one
    reachable working weekday, so the day-stepping loops in ``_add_working_days``
    / ``_sub_working_days`` always terminate: a malformed calendar such as
    ``work_days=[7]`` (a common "Sunday = ISO 7" mistake) can never spin them
    forever into an ``OverflowError``.
    """
    if not calendar:
        return _DEFAULT_CALENDAR["work_days"]
    raw = calendar.get("work_days")
    if raw is None:
        return _DEFAULT_CALENDAR["work_days"]
    valid: set[int] = set()
    for d in raw:
        try:
            n = int(d)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 6:
            valid.add(n)
    return valid or _DEFAULT_CALENDAR["work_days"]


def _parse_exceptions(calendar: dict | None) -> set[date]:
    """Extract exception dates (holidays) from a calendar dict."""
    if not calendar:
        return set()
    exceptions = calendar.get("exceptions", [])
    result: set[date] = set()
    for exc in exceptions:
        if isinstance(exc, str):
            try:
                result.add(date.fromisoformat(exc))
            except ValueError:
                pass
        elif isinstance(exc, date):
            result.add(exc)
    return result


def _add_working_days(
    start: int,
    duration: int,
    work_days: set[int],
    exceptions: set[date],
    project_start: date,
) -> int:
    """Add *duration* working days to *start* (day-offset from project_start).

    Returns the day-offset of the finish date.
    """
    if duration <= 0:
        return start

    current_date = project_start + timedelta(days=start)
    added = 0
    while added < duration:
        current_date += timedelta(days=1)
        if current_date.weekday() in work_days and current_date not in exceptions:
            added += 1
    return (current_date - project_start).days


def _sub_working_days(
    end: int,
    duration: int,
    work_days: set[int],
    exceptions: set[date],
    project_start: date,
) -> int:
    """Subtract *duration* working days from *end* (day-offset).

    Returns the day-offset of the start date.
    """
    if duration <= 0:
        return end

    current_date = project_start + timedelta(days=end)
    subtracted = 0
    while subtracted < duration:
        current_date -= timedelta(days=1)
        if current_date.weekday() in work_days and current_date not in exceptions:
            subtracted += 1
    return (current_date - project_start).days


def _working_days_between(
    start: int,
    end: int,
    work_days: set[int],
    exceptions: set[date],
    project_start: date,
) -> int:
    """Count working days between two day-offsets (exclusive of start, inclusive of end)."""
    if end <= start:
        return 0
    count = 0
    current = project_start + timedelta(days=start)
    target = project_start + timedelta(days=end)
    while current < target:
        current += timedelta(days=1)
        if current.weekday() in work_days and current not in exceptions:
            count += 1
    return count


def _snap_to_working_day(
    offset: int,
    work_days: set[int],
    exceptions: set[date],
    project_start: date,
) -> int:
    """Advance a day-offset to the first working day at or after it.

    A "start no earlier than" floor that lands on a weekend or holiday would
    give an activity an early_start on a non-working day, which is asymmetric
    with the working-day backward pass (``_sub_working_days``) and produces a
    spurious negative total_float and a false ``is_critical``. Snapping the
    floor forward keeps early_start on a working day. An offset already on a
    working day is returned unchanged.
    """
    # A calendar with no working weekday at all (malformed input, e.g. an
    # out-of-range work_days list) would spin forever, so fall back to the
    # offset unchanged. With at least one working weekday the loop always
    # terminates: exceptions is finite, so a working weekday eventually lands
    # outside it.
    if not work_days & {0, 1, 2, 3, 4, 5, 6}:
        return offset
    current = project_start + timedelta(days=offset)
    while current.weekday() not in work_days or current in exceptions:
        current += timedelta(days=1)
    return (current - project_start).days


def offset_to_iso(offset: int, project_start: date) -> str:
    """Project a CPM day-offset back onto an ISO calendar date.

    The forward/backward pass emit integer offsets measured in elapsed
    calendar days from the project origin. Rescheduling turns one back into a
    ``YYYY-MM-DD`` string: ``project_start + offset days``. Kept here (next to
    the engine that produces the offsets) so callers project dates the same
    way the engine measured them.

    Args:
        offset: Day-offset from the CPM origin (may be zero; never negative
            in practice - the forward pass floors early_start at zero).
        project_start: The calendar date the offsets are measured from.

    Returns:
        The ISO date string ``(project_start + offset)``.
    """
    return (project_start + timedelta(days=int(offset))).isoformat()


async def calculate_cpm(
    activities: list[dict],
    relationships: list[dict],
    calendar: dict | None = None,
    project_start_date: str | None = None,
) -> list[dict]:
    """Run CPM on a set of activities and relationships.

    Each activity dict must have:
        - id: str (UUID as string)
        - duration: int (working days)
        - name: str (optional, for logging)
        - start_offset: int (optional) - earliest the activity may start, as a
          calendar-day offset from the project origin. Acts as a "start no
          earlier than" floor and defaults to 0. A root (no predecessor) passes
          its own manual start here so its successors are scheduled after it,
          not at the project origin.
        - calendar: dict (optional) - a per-activity work calendar
          ({"work_days": [...], "exceptions": [...]}) so this activity's
          duration is measured on its own work week (e.g. a six-day trade).
          Omitted -> the activity uses the schedule-wide ``calendar`` argument.

    Each relationship dict must have:
        - predecessor_id: str
        - successor_id: str
        - type: str (FS, FF, SS, SF)
        - lag: int (days, can be negative)

    Calendar dict (optional):
        - work_days: list[int] - weekday indices (0=Mon, 6=Sun)
        - exceptions: list[str] - ISO date strings for holidays

    Returns a list of activity dicts with computed CPM fields:
        - early_start, early_finish, late_start, late_finish: int (day offsets)
        - total_float, free_float: int
        - is_critical: bool
    """
    if not activities:
        return []

    work_days = _parse_work_days(calendar)
    exceptions = _parse_exceptions(calendar)

    # Parse project start date
    if project_start_date:
        try:
            p_start = date.fromisoformat(project_start_date)
        except (ValueError, TypeError):
            p_start = date.today()
    else:
        p_start = date.today()

    # Build lookup structures
    act_map: dict[str, dict] = {}
    for act in activities:
        aid = str(act["id"])
        # Per-activity work calendar. When an activity carries its own
        # ``calendar`` ({"work_days": [...], "exceptions": [...]}) its duration
        # is measured on that work week (e.g. a six-day trade, or a crew with
        # its own holidays); otherwise it uses the schedule-wide default. Both
        # its early_start and late_start are derived with the SAME calendar, so
        # the working-day forward/backward passes stay symmetric.
        act_cal = act.get("calendar")
        act_map[aid] = {
            "id": aid,
            "duration": max(int(act.get("duration", 0)), 0),
            "name": act.get("name", ""),
            # "Start no earlier than" floor as a calendar-day offset from the
            # project origin. 0 (default) lets predecessors alone drive the
            # date; a root passes its own manual start here so its successors
            # anchor after it, not at the origin.
            "start_offset": max(int(act.get("start_offset", 0) or 0), 0),
            "work_days": _parse_work_days(act_cal) if act_cal else work_days,
            "exceptions": _parse_exceptions(act_cal) if act_cal else exceptions,
            "early_start": 0,
            "early_finish": 0,
            "late_start": 0,
            "late_finish": 0,
            "total_float": 0,
            "free_float": 0,
            "is_critical": False,
        }

    # Build adjacency: successors of each activity, and predecessors of each activity
    successors: dict[str, list[dict]] = defaultdict(list)
    predecessors: dict[str, list[dict]] = defaultdict(list)

    for rel in relationships:
        pred_id = str(rel.get("predecessor_id", ""))
        succ_id = str(rel.get("successor_id", ""))
        rel_type = str(rel.get("type", rel.get("relationship_type", "FS"))).upper()
        lag = int(rel.get("lag", rel.get("lag_days", 0)))

        if pred_id not in act_map or succ_id not in act_map:
            continue

        link = {"pred": pred_id, "succ": succ_id, "type": rel_type, "lag": lag}
        successors[pred_id].append(link)
        predecessors[succ_id].append(link)

    # ── Topological sort (Kahn's algorithm) ──────────────────────────────
    in_degree: dict[str, int] = dict.fromkeys(act_map, 0)
    for aid in act_map:
        in_degree[aid] = len(predecessors[aid])

    queue: list[str] = [aid for aid, deg in in_degree.items() if deg == 0]
    topo_order: list[str] = []

    while queue:
        # Process in stable order
        queue.sort()
        current = queue.pop(0)
        topo_order.append(current)
        for link in successors[current]:
            succ_id = link["succ"]
            in_degree[succ_id] -= 1
            if in_degree[succ_id] == 0:
                queue.append(succ_id)

    # If not all activities were sorted, there's a cycle - process remaining
    if len(topo_order) < len(act_map):
        remaining = [aid for aid in act_map if aid not in set(topo_order)]
        logger.warning("CPM: detected cycle involving %d activities", len(remaining))
        topo_order.extend(remaining)

    # ── Forward Pass ─────────────────────────────────────────────────────
    for aid in topo_order:
        act = act_map[aid]
        # "Start no earlier than" floor: a root's own manual start (a nonzero
        # offset), else 0 for a network-driven successor.
        es = act["start_offset"]

        for link in predecessors[aid]:
            pred = act_map[link["pred"]]
            rel_type = link["type"]
            lag = link["lag"]

            if rel_type == "FS":
                candidate = pred["early_finish"] + lag
            elif rel_type == "SS":
                candidate = pred["early_start"] + lag
            elif rel_type == "FF":
                candidate = pred["early_finish"] + lag - act["duration"]
            elif rel_type == "SF":
                candidate = pred["early_start"] + lag - act["duration"]
            else:
                candidate = pred["early_finish"] + lag  # Default to FS

            es = max(es, candidate)

        # Snap the resolved early_start onto THIS activity's own working calendar.
        # An early_start on a day the activity does not work is asymmetric with
        # the working-day backward pass and yields a spurious negative float and
        # a false is_critical. This covers a root starting on its own non-working
        # day (a weekend/holiday, or the whole schedule starting on a non-working
        # origin) AND a predecessor on a different calendar finishing on a day
        # this activity does not work (e.g. a six-day trade feeding a five-day
        # follow-on). Snapping a value already on a working day - every
        # same-calendar case - is a no-op, so existing schedules are unchanged.
        act["early_start"] = max(_snap_to_working_day(es, act["work_days"], act["exceptions"], p_start), 0)
        act["early_finish"] = _add_working_days(
            act["early_start"], act["duration"], act["work_days"], act["exceptions"], p_start
        )

    # ── Project duration ─────────────────────────────────────────────────
    project_finish = max((act_map[aid]["early_finish"] for aid in act_map), default=0)

    # ── Backward Pass ────────────────────────────────────────────────────
    # Initialize late finish to project duration
    for aid in act_map:
        act_map[aid]["late_finish"] = project_finish

    for aid in reversed(topo_order):
        act = act_map[aid]
        lf = project_finish  # latest finish

        for link in successors[aid]:
            succ = act_map[link["succ"]]
            rel_type = link["type"]
            lag = link["lag"]

            if rel_type == "FS":
                candidate = succ["late_start"] - lag
            elif rel_type == "SS":
                candidate = succ["late_start"] - lag + act["duration"]
            elif rel_type == "FF":
                candidate = succ["late_finish"] - lag
            elif rel_type == "SF":
                candidate = succ["late_finish"] - lag + act["duration"]
            else:
                candidate = succ["late_start"] - lag  # Default to FS

            lf = min(lf, candidate)

        act["late_finish"] = lf
        act["late_start"] = _sub_working_days(
            act["late_finish"], act["duration"], act["work_days"], act["exceptions"], p_start
        )

    # ── Float calculation ────────────────────────────────────────────────
    for aid in act_map:
        act = act_map[aid]
        act["total_float"] = act["late_start"] - act["early_start"]

        # Free float: min(ES of successors - EF of this) across all FS successors
        min_ff = None
        for link in successors[aid]:
            succ = act_map[link["succ"]]
            rel_type = link["type"]
            lag = link["lag"]

            if rel_type == "FS":
                ff = succ["early_start"] - act["early_finish"] - lag
            elif rel_type == "SS":
                ff = succ["early_start"] - act["early_start"] - lag
            elif rel_type == "FF":
                ff = succ["early_finish"] - act["early_finish"] - lag
            elif rel_type == "SF":
                ff = succ["early_finish"] - act["early_start"] - lag
            else:
                ff = succ["early_start"] - act["early_finish"] - lag

            if min_ff is None or ff < min_ff:
                min_ff = ff

        act["free_float"] = max(min_ff or 0, 0)

        # Mark critical: total float == 0 (or very close to zero)
        act["is_critical"] = act["total_float"] <= 0

    # Return results as list
    return list(act_map.values())
