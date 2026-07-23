# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure bridging from per-schedule rows to the portfolio super-graph (T3.3).

Turns a set of in-scope schedules (each with its own day-0 local timeline) into
the namespaced ``Activity`` list plus ``CrossEdge`` / ``BoundaryConstraint``
inputs that :func:`app.modules.schedule_advanced.portfolio_cpm.compute_portfolio_cpm`
expects, on one shared portfolio timeline.

Two bridging concerns, both deterministic and dependency-free (stdlib + the pure
engine) so this imports and unit-tests on the local runner:

* **Id namespacing** - a portfolio mixes activities from many schedules, so each
  id becomes ``"{schedule_id}:{activity_id}"`` to stay globally unique. The
  inverse :func:`split_nid` recovers the pair for the response.
* **Start-offset anchoring** - every schedule's local CPM starts at day 0, but
  schedules begin on different calendar dates. Each schedule carries an integer
  ``offset`` (days from the portfolio's earliest start); each of its *source*
  activities (no in-schedule predecessor) gets an FS boundary floor of that
  offset, so the merged forward pass places every schedule on the shared
  timeline. Non-source activities inherit the offset transitively through their
  predecessors. (v1 uses calendar-day offsets; a calendar-aware offset is a
  later refinement.)
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.modules.schedule_advanced.portfolio_cpm import (
    Activity,
    BoundaryConstraint,
    CrossEdge,
)

#: Separator between schedule id and activity id in a namespaced id. A UUID never
#: contains a colon, so the split is unambiguous.
NS_SEP = ":"


def nid(schedule_id: Any, activity_id: Any) -> str:
    """Namespaced global id for an activity within a schedule."""
    return f"{schedule_id}{NS_SEP}{activity_id}"


def split_nid(namespaced: str) -> tuple[str, str]:
    """Inverse of :func:`nid` - ``(schedule_id, activity_id)``."""
    schedule_id, _, activity_id = namespaced.partition(NS_SEP)
    return schedule_id, activity_id


@dataclass(frozen=True)
class ActivityInput:
    """One activity of a schedule (local, pre-namespacing)."""

    activity_id: str
    duration: int = 0
    #: ``(predecessor_activity_id, dep_type, lag)`` triples, all in-schedule.
    predecessors: tuple[tuple[str, str, int], ...] = ()


@dataclass(frozen=True)
class ScheduleInput:
    """One in-scope schedule on the shared portfolio timeline."""

    schedule_id: str
    offset: int = 0
    activities: tuple[ActivityInput, ...] = field(default_factory=tuple)


def build_portfolio_inputs(
    schedules: Sequence[ScheduleInput],
    cross_links: Iterable[tuple[Any, Any, Any, Any, str, int]],
) -> tuple[list[Activity], list[CrossEdge], list[BoundaryConstraint]]:
    """Build ``(activities, cross_edges, boundaries)`` for the portfolio engine.

    Args:
        schedules: the in-scope schedules, each with its activities and the
            integer ``offset`` (days from the portfolio's earliest start).
        cross_links: ``(pred_schedule, pred_activity, succ_schedule,
            succ_activity, dep_type, lag)`` tuples. Only links whose BOTH
            endpoints are in scope become real ``CrossEdge``s; the rest are
            dropped (the caller reports the omitted count).

    Returns:
        ``(activities, cross_edges, boundaries)`` ready for
        :func:`compute_portfolio_cpm`.
    """
    in_scope = {str(s.schedule_id) for s in schedules}

    activities: list[Activity] = []
    boundaries: list[BoundaryConstraint] = []
    for s in schedules:
        sid = str(s.schedule_id)
        offset = int(s.offset)
        for a in s.activities:
            namespaced = nid(sid, a.activity_id)
            preds = [(nid(sid, p_id), dep, int(lag)) for (p_id, dep, lag) in a.predecessors]
            activities.append(Activity(id=namespaced, duration=max(0, int(a.duration)), predecessors=preds))
            # Source activity (no in-schedule predecessor) anchored to the
            # schedule's start offset on the shared timeline.
            if not preds and offset > 0:
                boundaries.append(
                    BoundaryConstraint(
                        local_activity_id=namespaced,
                        dep_type="FS",
                        boundary_index=offset,
                        lag=0,
                    )
                )

    cross_edges: list[CrossEdge] = []
    for pred_sched, pred_act, succ_sched, succ_act, dep_type, lag in cross_links:
        if str(pred_sched) in in_scope and str(succ_sched) in in_scope:
            cross_edges.append(
                CrossEdge(
                    predecessor_id=nid(pred_sched, pred_act),
                    successor_id=nid(succ_sched, succ_act),
                    dep_type=dep_type,
                    lag=int(lag),
                )
            )

    return activities, cross_edges, boundaries
