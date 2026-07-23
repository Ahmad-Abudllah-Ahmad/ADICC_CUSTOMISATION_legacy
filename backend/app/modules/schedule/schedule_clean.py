# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure normalise-on-import cleaner for schedule interchange documents (T1.1).

Repairs the structural defects a foreign schedule routinely arrives with - the
same class of hygiene checks a forensic scheduler runs before trusting a file -
and returns the cleaned document plus an itemised report of every change and a
block of advisory metrics. Stdlib only, so it imports and unit-tests on the
local Python 3.11 runner.

Repairs (each mutation is recorded as a :class:`CleanAction`):

* de-duplicate activity refs so the import ref->id map can never collapse two
  activities into one;
* clamp a negative ``duration_days`` to zero and an out-of-range
  ``progress_pct`` into ``[0, 100]`` (a non-numeric percent resets to ``0``);
* clear a ``parent_ref`` that points at a missing activity, and break any parent
  cycle by cutting the edge that closes it;
* on relationships: coerce an unknown ``relationship_type`` to ``FS``, normalise
  ``lag_days`` to an int, drop self-links and links whose endpoints are missing,
  and drop duplicate ``(predecessor, successor)`` pairs (the database enforces
  that pair uniquely).

Advisory metrics never mutate the document - they count leads (negative lag),
hard date constraints, and activities missing a predecessor or successor
(dangling logic) so the caller can judge the schedule's health.

Leads (negative lag) are preserved, not "fixed": a lead is legitimate CPM logic,
so removing it would corrupt the network. The cleaner only counts them.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.modules.schedule.schedule_interchange import (
    VALID_RELATIONSHIP_TYPES,
    ParsedDocument,
)

#: Date constraints that hard-anchor an activity (DCMA "hard constraint" family).
#: Counted as an advisory metric - a high count is a schedule-quality smell.
_HARD_CONSTRAINTS = frozenset(
    {
        "must_start_on",
        "must_finish_on",
        "start_no_later",
        "finish_no_later",
        "mandatory_start",
        "mandatory_finish",
    }
)


@dataclass(frozen=True)
class CleanAction:
    """One repair the cleaner applied."""

    code: str
    target: str
    detail: str


@dataclass
class CleanResult:
    """Outcome of :func:`clean_document`."""

    document: ParsedDocument
    actions: list[CleanAction] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


def _coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion that never raises."""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _clamp_progress(value: Any) -> tuple[str, bool]:
    """Clamp a percent string into ``[0, 100]``.

    Returns ``(normalised_string, changed)``. A non-numeric value resets to
    ``"0"``. A whole number re-emits without a decimal point so a clean value is
    left byte-identical.
    """
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "0", str(value) != "0"
    clamped = min(100.0, max(0.0, num))
    text = str(int(clamped)) if clamped == int(clamped) else str(clamped)
    return text, text != str(value)


def _dedupe_refs(activities: list[dict[str, Any]], actions: list[CleanAction]) -> int:
    """Rename later activities that reuse an earlier ref. Returns the fix count."""
    seen: set[str] = set()
    fixed = 0
    for i, a in enumerate(activities):
        ref = a.get("ref")
        if not isinstance(ref, str) or not ref:
            ref = f"ACT-{i}"
            a["ref"] = ref
            actions.append(CleanAction("assign_missing_ref", ref, f"activity[{i}] had no ref"))
            fixed += 1
        if ref in seen:
            new_ref = f"{ref}#{i}"
            while new_ref in seen:
                new_ref = f"{new_ref}_"
            a["ref"] = new_ref
            actions.append(CleanAction("dedupe_ref", new_ref, f"ref {ref!r} already used; renamed to {new_ref!r}"))
            seen.add(new_ref)
            fixed += 1
        else:
            seen.add(ref)
    return fixed


def _break_parent_cycles(
    activities: list[dict[str, Any]],
    ref_set: set[str],
    actions: list[CleanAction],
) -> tuple[int, int]:
    """Clear dangling parents and break parent cycles in place.

    Returns ``(parents_cleared, cycles_broken)``. A parent pointing at a missing
    ref is cleared first; then any activity whose ancestor walk revisits a node
    has that closing edge cut.
    """
    by_ref = {a["ref"]: a for a in activities if isinstance(a.get("ref"), str)}

    cleared = 0
    for a in activities:
        parent = a.get("parent_ref")
        if parent is not None and parent not in ref_set:
            a["parent_ref"] = None
            actions.append(CleanAction("clear_dangling_parent", str(a.get("ref")), f"parent_ref {parent!r} not found"))
            cleared += 1

    cycles = 0
    for start in list(by_ref):
        seen: set[str] = set()
        cur: str | None = start
        while cur is not None:
            if cur in seen:
                node = by_ref.get(cur)
                if node is not None and node.get("parent_ref") is not None:
                    actions.append(
                        CleanAction(
                            "break_parent_cycle",
                            cur,
                            f"parent chain from {start!r} cycles at {cur!r}; parent cleared",
                        )
                    )
                    node["parent_ref"] = None
                    cycles += 1
                break
            seen.add(cur)
            node = by_ref.get(cur)
            cur = node.get("parent_ref") if node is not None else None

    return cleared, cycles


def _clean_relationships(
    relationships: list[dict[str, Any]],
    ref_set: set[str],
    actions: list[CleanAction],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Coerce types, drop self / dangling / duplicate edges. Returns (kept, counts)."""
    counts = {
        "relationship_types_coerced": 0,
        "relationships_dropped_self": 0,
        "relationships_dropped_dangling": 0,
        "relationships_deduped": 0,
    }
    kept: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, rel in enumerate(relationships):
        pred = rel.get("predecessor_ref")
        succ = rel.get("successor_ref")

        if pred == succ:
            actions.append(CleanAction("drop_self_relationship", str(pred), f"relationship[{i}] is self-referential"))
            counts["relationships_dropped_self"] += 1
            continue

        if pred not in ref_set or succ not in ref_set:
            missing = pred if pred not in ref_set else succ
            actions.append(
                CleanAction("drop_dangling_relationship", f"{pred}->{succ}", f"endpoint {missing!r} not found")
            )
            counts["relationships_dropped_dangling"] += 1
            continue

        rtype = str(rel.get("relationship_type") or "FS").upper()
        if rtype not in VALID_RELATIONSHIP_TYPES:
            actions.append(
                CleanAction("coerce_relationship_type", f"{pred}->{succ}", f"{rel.get('relationship_type')!r} -> FS")
            )
            rtype = "FS"
            counts["relationship_types_coerced"] += 1
        rel["relationship_type"] = rtype
        rel["lag_days"] = _coerce_int(rel.get("lag_days"), 0)

        pair = (str(pred), str(succ))
        if pair in seen_pairs:
            actions.append(
                CleanAction("dedupe_relationship", f"{pred}->{succ}", "duplicate predecessor/successor pair")
            )
            counts["relationships_deduped"] += 1
            continue
        seen_pairs.add(pair)
        kept.append(rel)

    return kept, counts


def _advisory_stats(
    activities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, int]:
    """Compute non-mutating health metrics over the cleaned document."""
    with_pred = {str(r.get("successor_ref")) for r in relationships}
    with_succ = {str(r.get("predecessor_ref")) for r in relationships}
    refs = [a["ref"] for a in activities if isinstance(a.get("ref"), str)]

    return {
        "activities": len(activities),
        "relationships": len(relationships),
        "lead_count": sum(1 for r in relationships if _coerce_int(r.get("lag_days")) < 0),
        "hard_constraint_count": sum(1 for a in activities if a.get("constraint_type") in _HARD_CONSTRAINTS),
        "activities_missing_predecessor": sum(1 for ref in refs if ref not in with_pred),
        "activities_missing_successor": sum(1 for ref in refs if ref not in with_succ),
    }


def clean_document(doc: ParsedDocument) -> CleanResult:
    """Normalise and repair an interchange document; never mutates the input.

    Args:
        doc: a parsed (envelope-validated) document.

    Returns:
        A :class:`CleanResult` with the cleaned document, an ordered list of the
        repairs applied, and advisory health metrics. Running the cleaner again
        on its own output produces no further actions (idempotent).
    """
    activities = copy.deepcopy(doc.activities)
    relationships = copy.deepcopy(doc.relationships)
    actions: list[CleanAction] = []

    duplicate_refs_fixed = _dedupe_refs(activities, actions)

    progress_clamped = 0
    duration_clamped = 0
    for a in activities:
        new_dur = max(0, _coerce_int(a.get("duration_days"), 0))
        if new_dur != a.get("duration_days"):
            actions.append(CleanAction("clamp_duration", str(a.get("ref")), f"{a.get('duration_days')!r} -> {new_dur}"))
            a["duration_days"] = new_dur
            duration_clamped += 1
        new_pct, changed = _clamp_progress(a.get("progress_pct", "0"))
        if changed:
            actions.append(
                CleanAction("clamp_progress", str(a.get("ref")), f"{a.get('progress_pct')!r} -> {new_pct!r}")
            )
            a["progress_pct"] = new_pct
            progress_clamped += 1

    ref_set = {a["ref"] for a in activities if isinstance(a.get("ref"), str)}
    parents_cleared, cycles_broken = _break_parent_cycles(activities, ref_set, actions)

    relationships, rel_counts = _clean_relationships(relationships, ref_set, actions)

    cleaned = ParsedDocument(
        format_version=doc.format_version,
        schedule=copy.deepcopy(doc.schedule),
        activities=activities,
        relationships=relationships,
        extra=copy.deepcopy(doc.extra),
    )

    stats = _advisory_stats(activities, relationships)
    stats.update(
        {
            "duplicate_refs_fixed": duplicate_refs_fixed,
            "duration_clamped": duration_clamped,
            "progress_clamped": progress_clamped,
            "parents_cleared": parents_cleared,
            "parent_cycles_broken": cycles_broken,
            **rel_counts,
        }
    )

    return CleanResult(document=cleaned, actions=actions, stats=stats)
