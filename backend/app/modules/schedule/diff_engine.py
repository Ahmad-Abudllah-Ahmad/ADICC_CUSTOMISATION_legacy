# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure schedule diff engine - per-field categorized comparison of two snapshots.

This module is intentionally *pure*: it imports only the standard library
(plus :mod:`decimal` / :mod:`datetime`). It has **no** dependency on the
database, the ORM, FastAPI, or any service layer, which keeps it trivially
unit-testable and reusable by import/export, baseline-capture, what-if, and
forensic-delay tooling alike.

The entry point is :func:`diff_snapshots`, which takes two *normalized
envelopes* and returns a :class:`DiffResult`. An envelope is a plain dict::

    {
        "activities":    [ {<activity fields>}, ... ],
        "relationships": [ {<relationship fields>}, ... ],
        "calendars":     { "<calendar_id>": {<calendar fields>}, ... },
        "project_finish": "YYYY-MM-DD",   # optional
    }

Both inputs are treated as opaque data: callers are responsible for
flattening ORM rows (or imported files) into this shape beforehand. The
engine never mutates its inputs.

Design notes:

* **Matching** - activities are keyed on ``id`` and fall back to the
  composite ``(wbs_code, name)`` so a snapshot taken before stable ids were
  assigned still lines up. Relationships are keyed on
  ``(predecessor_id, successor_id)``. Calendars are keyed on their dict key.
* **Categories** - every changed field is tagged with one or more of the
  eight canonical categories (see :data:`CATEGORIES`). A single activity
  change record may carry several categories at once (e.g. an activity that
  both slipped and went critical), and the summary counts each category
  independently.
* **Type safety** - costs are compared as :class:`~decimal.Decimal` (so
  ``1000.10`` equals ``1000.1`` and deltas never devolve into float drift or
  string concatenation), and dates are compared as :class:`datetime.date`
  via a tolerant parser. Unparseable values degrade gracefully rather than
  raising.
* **Complexity** - all matching is via hash-indexed lookups, so the whole
  diff is O(A + R + C) in the activity / relationship / calendar counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# ── Canonical category set ─────────────────────────────────────────────────
# The order here is the canonical display order and is what
# ``DiffSummary.count_by_category`` is always pre-seeded with (so the
# front-end never has to re-fill blanks for an absent category).
CATEGORIES: tuple[str, ...] = (
    "scope",
    "dates",
    "duration",
    "progress",
    "cost",
    "constraint",
    "calendar",
    "logic",
)


# ── Tolerant value coercion (mirrors schedule_advanced.service patterns) ───
def _parse_date(value: Any) -> date | None:
    """Tolerant date parser - accepts date, datetime, or ISO string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except (ValueError, TypeError):
            return None
    return None


def _to_decimal(value: Any) -> Decimal | None:
    """Tolerant Decimal parser - ``None`` / empty / unparseable -> ``None``.

    Unlike the schedule_advanced helper (which folds empties to ``0``), the
    diff engine preserves the *absence* of a cost so that "not cost-loaded"
    is distinguishable from "costs zero". A genuine ``0`` still parses to
    ``Decimal("0")``.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        # bool is an int subclass; treat as absent rather than 0/1.
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _to_int(value: Any) -> int | None:
    """Tolerant int parser - ``None`` / empty / unparseable -> ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(Decimal(str(value)))
    except (TypeError, ValueError, InvalidOperation):
        return None


def _to_bool(value: Any) -> bool | None:
    """Tolerant bool parser - accepts native bool, 0/1, common strings."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text in ("true", "1", "yes", "y", "t"):
            return True
        if text in ("false", "0", "no", "n", "f"):
            return False
    return None


def _norm_str(value: Any) -> str:
    """Normalise a scalar to a trimmed string for raw comparison."""
    if value is None:
        return ""
    return str(value).strip()


def _activity_key(row: dict[str, Any]) -> tuple[str, str | None] | None:
    """Return a stable match key for an activity.

    Primary key is ``id``. When absent, fall back to the composite
    ``(wbs_code, name)``. The first tuple element marks which strategy was
    used so two rows can never collide across strategies. Returns ``None``
    when nothing usable is present (such rows are skipped, not matched).
    """
    raw_id = row.get("id")
    if raw_id is not None and _norm_str(raw_id):
        return ("id", _norm_str(raw_id))
    wbs = _norm_str(row.get("wbs_code"))
    name = _norm_str(row.get("name"))
    if wbs or name:
        return ("wbsname", f"{wbs}\x00{name}")
    return None


def _relationship_key(row: dict[str, Any]) -> tuple[str, str] | None:
    """Return the ``(predecessor_id, successor_id)`` match key, or ``None``."""
    pred = _norm_str(row.get("predecessor_id"))
    succ = _norm_str(row.get("successor_id"))
    if not pred or not succ:
        return None
    return (pred, succ)


# ── Field comparison spec ──────────────────────────────────────────────────
# Each entry: (field_name, comparator, (category, ...)). The comparator
# coerces both sides to a comparable, type-safe representation; equality of
# those representations means "no change". Several fields share a category,
# and ``is_critical`` carries two (it counts toward ``duration`` and also
# flips the critical-path flag on the change record).
_COMPARATORS = {
    "date": _parse_date,
    "decimal": _to_decimal,
    "int": _to_int,
    "bool": _to_bool,
    "raw": _norm_str,
}

# Fields compared on every matched activity, in a stable order.
_ACTIVITY_FIELD_SPEC: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # dates - drive net finish movement
    ("start_date", "date", ("dates",)),
    ("end_date", "date", ("dates",)),
    # duration / CPM float
    ("duration_days", "int", ("duration",)),
    ("early_start", "date", ("duration",)),
    ("early_finish", "date", ("duration",)),
    ("late_start", "date", ("duration",)),
    ("late_finish", "date", ("duration",)),
    ("total_float", "int", ("duration",)),
    ("free_float", "int", ("duration",)),
    ("is_critical", "bool", ("duration",)),
    # progress
    ("progress_pct", "decimal", ("progress",)),
    ("status", "raw", ("progress",)),
    ("actual_start", "date", ("progress",)),
    ("actual_finish", "date", ("progress",)),
    # cost - Decimal only
    ("cost_planned", "decimal", ("cost",)),
    ("cost_actual", "decimal", ("cost",)),
    # constraints
    ("constraint_type", "raw", ("constraint",)),
    ("constraint_date", "date", ("constraint",)),
    # calendar (optional per-activity assignment)
    ("calendar_id", "raw", ("calendar",)),
    # scope-level identity attributes (added/removed handled separately)
    ("wbs_code", "raw", ("scope",)),
    ("parent_id", "raw", ("scope",)),
    ("name", "raw", ("scope",)),
)

# Fields whose finish-date movement we report on a change record. We use the
# activity's own ``end_date`` (its finish) for slip ranking.
_FINISH_FIELD = "end_date"


def _fmt(value: Any) -> Any:
    """Render a coerced value for inclusion in a change record (JSON-safe)."""
    if isinstance(value, Decimal):
        # Normalise so 1000.10 and 1000.1 stringify identically.
        return str(value.normalize() + Decimal(0))
    if isinstance(value, date):
        return value.isoformat()
    return value


# ── Change records ─────────────────────────────────────────────────────────
@dataclass
class FieldChange:
    """A single field that differs between base and target."""

    field: str
    from_value: Any
    to_value: Any
    categories: tuple[str, ...]


@dataclass
class ActivityChange:
    """An activity that was added, removed, or had one or more fields change."""

    key: str
    change_type: str  # "added" | "removed" | "modified"
    categories: list[str] = field(default_factory=list)
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    finish_movement_days: int = 0
    critical_path: bool = False  # True when is_critical flipped
    name: str | None = None
    wbs_code: str | None = None


@dataclass
class RelationshipChange:
    """A dependency link that was added, removed, retyped, or re-lagged."""

    key: tuple[str, str]
    change_type: str  # "added" | "removed" | "retyped" | "relagged"
    categories: list[str] = field(default_factory=lambda: ["logic"])
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class CalendarChange:
    """A calendar that was added, removed, or whose definition changed."""

    key: str
    change_type: str  # "added" | "removed" | "changed"
    categories: list[str] = field(default_factory=lambda: ["calendar"])


@dataclass
class DiffSummary:
    """Roll-up metrics across the whole diff."""

    net_finish_movement_days: int = 0
    count_by_category: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CATEGORIES, 0))
    activities_added: int = 0
    activities_removed: int = 0
    activities_changed: int = 0
    relationships_added: int = 0
    relationships_removed: int = 0
    relationships_retyped: int = 0
    relationships_relagged: int = 0
    critical_path_in: int = 0
    critical_path_out: int = 0
    cost_planned_delta: Decimal = field(default_factory=lambda: Decimal("0"))
    cost_actual_delta: Decimal = field(default_factory=lambda: Decimal("0"))
    largest_slips: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DiffResult:
    """Full diff between two snapshots."""

    activities: list[ActivityChange] = field(default_factory=list)
    relationships: list[RelationshipChange] = field(default_factory=list)
    calendars: list[CalendarChange] = field(default_factory=list)
    summary: DiffSummary = field(default_factory=DiffSummary)


# ── Core diff ──────────────────────────────────────────────────────────────
def _index_activities(
    rows: list[dict[str, Any]] | None,
) -> dict[tuple[str, str | None], dict[str, Any]]:
    out: dict[tuple[str, str | None], dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        k = _activity_key(row)
        if k is not None and k not in out:
            out[k] = row
    return out


def _index_relationships(
    rows: list[dict[str, Any]] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        k = _relationship_key(row)
        if k is not None and k not in out:
            out[k] = row
    return out


def _compare_activity_fields(
    base: dict[str, Any], target: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], set[str], bool]:
    """Compare the fixed field list across one matched pair.

    Returns ``(field_changes, categories, critical_flip)``.
    """
    field_changes: dict[str, dict[str, Any]] = {}
    categories: set[str] = set()
    critical_flip = False

    for fname, ckind, fcats in _ACTIVITY_FIELD_SPEC:
        if fname not in base and fname not in target:
            # Neither side carries this field at all: nothing to compare.
            continue
        comparator = _COMPARATORS[ckind]
        b_val = comparator(base.get(fname))
        t_val = comparator(target.get(fname))
        if b_val == t_val:
            continue
        field_changes[fname] = {
            "from": _fmt(b_val),
            "to": _fmt(t_val),
            "categories": list(fcats),
        }
        categories.update(fcats)
        if fname == "is_critical":
            critical_flip = True

    return field_changes, categories, critical_flip


def _diff_activities(
    base_idx: dict[tuple[str, str | None], dict[str, Any]],
    target_idx: dict[tuple[str, str | None], dict[str, Any]],
    summary: DiffSummary,
) -> list[ActivityChange]:
    changes: list[ActivityChange] = []
    slips: list[tuple[int, dict[str, Any]]] = []

    base_keys = set(base_idx)
    target_keys = set(target_idx)

    # Removed (in base, not in target)
    for k in base_keys - target_keys:
        row = base_idx[k]
        changes.append(
            ActivityChange(
                key=k[1] or "",
                change_type="removed",
                categories=["scope"],
                name=_norm_str(row.get("name")) or None,
                wbs_code=_norm_str(row.get("wbs_code")) or None,
            )
        )
        summary.activities_removed += 1
        summary.count_by_category["scope"] += 1

    # Added (in target, not in base)
    for k in target_keys - base_keys:
        row = target_idx[k]
        changes.append(
            ActivityChange(
                key=k[1] or "",
                change_type="added",
                categories=["scope"],
                name=_norm_str(row.get("name")) or None,
                wbs_code=_norm_str(row.get("wbs_code")) or None,
            )
        )
        summary.activities_added += 1
        summary.count_by_category["scope"] += 1

    # Modified (in both)
    for k in base_keys & target_keys:
        b_row = base_idx[k]
        t_row = target_idx[k]
        field_changes, categories, critical_flip = _compare_activity_fields(b_row, t_row)
        if not field_changes:
            continue

        # Finish movement (signed days) from the activity's own finish date.
        finish_movement = 0
        b_finish = _parse_date(b_row.get(_FINISH_FIELD))
        t_finish = _parse_date(t_row.get(_FINISH_FIELD))
        if b_finish and t_finish:
            finish_movement = (t_finish - b_finish).days

        change = ActivityChange(
            key=k[1] or "",
            change_type="modified",
            categories=sorted(categories),
            fields=field_changes,
            finish_movement_days=finish_movement,
            critical_path=critical_flip,
            name=(_norm_str(t_row.get("name")) or _norm_str(b_row.get("name"))) or None,
            wbs_code=(_norm_str(t_row.get("wbs_code")) or _norm_str(b_row.get("wbs_code"))) or None,
        )
        changes.append(change)
        summary.activities_changed += 1

        # Per-category counters (each category counted once per change).
        for cat in categories:
            summary.count_by_category[cat] = summary.count_by_category.get(cat, 0) + 1

        # Critical-path in/out classification.
        if critical_flip:
            t_crit = _to_bool(t_row.get("is_critical"))
            b_crit = _to_bool(b_row.get("is_critical"))
            if t_crit and not b_crit:
                summary.critical_path_in += 1
            elif b_crit and not t_crit:
                summary.critical_path_out += 1

        # Per-activity cost deltas (summed at the summary level below as well,
        # but we accumulate here so non-modified activities don't contribute).
        b_planned = _to_decimal(b_row.get("cost_planned"))
        t_planned = _to_decimal(t_row.get("cost_planned"))
        summary.cost_planned_delta += (t_planned or Decimal("0")) - (b_planned or Decimal("0"))
        b_actual = _to_decimal(b_row.get("cost_actual"))
        t_actual = _to_decimal(t_row.get("cost_actual"))
        summary.cost_actual_delta += (t_actual or Decimal("0")) - (b_actual or Decimal("0"))

        if finish_movement != 0:
            slips.append(
                (
                    abs(finish_movement),
                    {
                        "key": change.key,
                        "name": change.name,
                        "wbs_code": change.wbs_code,
                        "finish_movement_days": finish_movement,
                    },
                )
            )

    # Top-10 largest slips by absolute finish movement (stable, deterministic).
    slips.sort(key=lambda item: (-item[0], item[1]["key"]))
    summary.largest_slips = [entry for _, entry in slips[:10]]

    return changes


def _diff_relationships(
    base_idx: dict[tuple[str, str], dict[str, Any]],
    target_idx: dict[tuple[str, str], dict[str, Any]],
    summary: DiffSummary,
) -> list[RelationshipChange]:
    changes: list[RelationshipChange] = []
    base_keys = set(base_idx)
    target_keys = set(target_idx)

    for k in sorted(base_keys - target_keys):
        changes.append(RelationshipChange(key=k, change_type="removed"))
        summary.relationships_removed += 1
        summary.count_by_category["logic"] += 1

    for k in sorted(target_keys - base_keys):
        changes.append(RelationshipChange(key=k, change_type="added"))
        summary.relationships_added += 1
        summary.count_by_category["logic"] += 1

    for k in sorted(base_keys & target_keys):
        b_row = base_idx[k]
        t_row = target_idx[k]
        b_type = _norm_str(b_row.get("relationship_type")).upper()
        t_type = _norm_str(t_row.get("relationship_type")).upper()
        b_lag = _to_int(b_row.get("lag_days")) or 0
        t_lag = _to_int(t_row.get("lag_days")) or 0

        fields: dict[str, dict[str, Any]] = {}
        retyped = b_type != t_type
        relagged = b_lag != t_lag
        if retyped:
            fields["relationship_type"] = {"from": b_type, "to": t_type}
        if relagged:
            fields["lag_days"] = {"from": b_lag, "to": t_lag}

        if not fields:
            continue

        # A link can be both retyped and re-lagged; we emit one record whose
        # change_type names the dominant edit (retype wins) but whose fields
        # carry both. Each distinct edit increments its own summary counter.
        change_type = "retyped" if retyped else "relagged"
        changes.append(RelationshipChange(key=k, change_type=change_type, fields=fields))
        if retyped:
            summary.relationships_retyped += 1
        if relagged:
            summary.relationships_relagged += 1
        # ``logic`` counts once per changed relationship record.
        summary.count_by_category["logic"] += 1

    return changes


def _calendar_signature(cal: Any) -> Any:
    """Build an order-independent signature for a calendar definition.

    Compares working days and holiday sets shallowly. Lists become sorted
    tuples so reordering alone is not a change; everything else falls back to
    a stable string form.
    """
    if not isinstance(cal, dict):
        return _norm_str(cal)
    sig: list[tuple[str, Any]] = []
    for key in sorted(cal.keys()):
        val = cal[key]
        if isinstance(val, (list, set, tuple)):
            sig.append((key, tuple(sorted(_norm_str(v) for v in val))))
        elif isinstance(val, dict):
            sig.append((key, tuple(sorted((str(kk), _norm_str(vv)) for kk, vv in val.items()))))
        else:
            sig.append((key, _norm_str(val)))
    return tuple(sig)


def _diff_calendars(
    base: dict[str, Any] | None,
    target: dict[str, Any] | None,
    summary: DiffSummary,
) -> list[CalendarChange]:
    changes: list[CalendarChange] = []
    base = base if isinstance(base, dict) else {}
    target = target if isinstance(target, dict) else {}
    base_keys = set(base)
    target_keys = set(target)

    for k in sorted(base_keys - target_keys):
        changes.append(CalendarChange(key=str(k), change_type="removed"))
        summary.count_by_category["calendar"] += 1

    for k in sorted(target_keys - base_keys):
        changes.append(CalendarChange(key=str(k), change_type="added"))
        summary.count_by_category["calendar"] += 1

    for k in sorted(base_keys & target_keys):
        if _calendar_signature(base[k]) != _calendar_signature(target[k]):
            changes.append(CalendarChange(key=str(k), change_type="changed"))
            summary.count_by_category["calendar"] += 1

    return changes


def diff_snapshots(base: dict[str, Any], target: dict[str, Any]) -> DiffResult:
    """Diff two normalized schedule envelopes.

    Args:
        base: The earlier / reference snapshot envelope.
        target: The later / comparison snapshot envelope.

    Both envelopes are dicts with optional keys ``activities`` (list),
    ``relationships`` (list), ``calendars`` (dict keyed by calendar id), and
    ``project_finish`` (ISO date string). Missing keys are treated as empty.

    Returns:
        A :class:`DiffResult` whose ``summary`` holds the roll-up metrics and
        whose ``activities`` / ``relationships`` / ``calendars`` hold the
        per-entity change records. Inputs are never mutated.
    """
    base = base if isinstance(base, dict) else {}
    target = target if isinstance(target, dict) else {}

    summary = DiffSummary()

    # Net finish movement (signed): target.project_finish - base.project_finish.
    b_finish = _parse_date(base.get("project_finish"))
    t_finish = _parse_date(target.get("project_finish"))
    if b_finish and t_finish:
        summary.net_finish_movement_days = (t_finish - b_finish).days

    activity_changes = _diff_activities(
        _index_activities(base.get("activities")),
        _index_activities(target.get("activities")),
        summary,
    )
    relationship_changes = _diff_relationships(
        _index_relationships(base.get("relationships")),
        _index_relationships(target.get("relationships")),
        summary,
    )
    calendar_changes = _diff_calendars(
        base.get("calendars"),
        target.get("calendars"),
        summary,
    )

    return DiffResult(
        activities=activity_changes,
        relationships=relationship_changes,
        calendars=calendar_changes,
        summary=summary,
    )
