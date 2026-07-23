# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure-Python multi-project (schedule-of-schedules) CPM engine - T3.3.

This module is a thin, deterministic *super-graph* layer on top of the
single-project kernel in :mod:`app.modules.schedule_advanced.cpm`. It imports
**only** the standard library plus that kernel - no SQLAlchemy, no FastAPI, no
DB, no third-party deps - so it can be unit-tested in isolation and reused by
the portfolio service to run "what-if" cross-project scheduling.

Two scheduling modes are supported, both reusing the same kernel:

* **Standalone** (one schedule in scope): run the local pass, but seed every
  cross-project edge whose far side is *out of scope* as a frozen *boundary
  floor* so the local critical path still reflects the external dependency
  even though the far activities are not loaded. See
  :func:`standalone_with_boundaries`.
* **Portfolio** (a node selected): the caller merges every *accessible*
  schedule under the node into one id-namespaced activity list, adds in-scope
  cross-project edges as **real** edges, and out-of-scope edges as boundary
  constraints; this module runs one global pass. See
  :func:`compute_portfolio_cpm`.

Boundary floors without touching the kernel
-------------------------------------------
The kernel has no notion of a "floor" on an activity's early start, and this
module must not edit it. To force ``ES[local] >= boundary_index + lag`` for an
out-of-scope predecessor we **inject a synthetic predecessor activity** whose
duration equals the frozen ``boundary_index`` and which itself has no
predecessors. Because a source node's ``ES`` is ``0``, the synthetic node's
``EF`` is exactly ``boundary_index``; an FS link with ``lag`` from it to the
local activity then floors the local ``ES`` at ``boundary_index + lag`` -
which is precisely the forward-pass arithmetic the kernel already applies
(``s.ES >= p.EF + lag`` for FS).

Synthetic nodes are namespaced ``__boundary__{local_id}__{n}`` and are
**stripped** from every returned result and from the returned critical path,
so callers never see them.

Boundary-index math (per link type)
-----------------------------------
A :class:`BoundaryConstraint` carries a single integer ``boundary_index`` -
the frozen *work-day index* taken from the far activity's last published dates
(the caller chooses early-finish or early-start when it builds the constraint,
per the link semantics below) - plus the link ``dep_type`` and ``lag``. The
local early-start floor each link type imposes mirrors the kernel's forward
pass exactly:

====  ==============================  =================================  =======================
Code  Kernel forward constraint       Far index the caller should pass   Resulting local ES floor
====  ==============================  =================================  =======================
FS    ``ES_local >= EF_far + lag``    far early-finish                   ``boundary_index + lag``
SS    ``ES_local >= ES_far + lag``    far early-start                    ``boundary_index + lag``
FF    ``EF_local >= EF_far + lag``    far early-finish                   ``boundary_index + lag - dur``
SF    ``EF_local >= ES_far + lag``    far early-start                    ``boundary_index + lag - dur``
====  ==============================  =================================  =======================

For FS / SS the floor is ``boundary_index + lag`` and is realised exactly by a
synthetic source of duration ``boundary_index`` linked FS with ``lag``. **v1
implements FS only** (the only link type the standalone acceptance criterion
exercises); SS reduces to the identical synthetic construction and is wired in
the same path. FF / SF bound the *finish* (hence the ``- dur`` term) and would
need either a synthetic *successor* or a duration-aware synthetic source; they
are intentionally rejected with a clear error in v1 rather than silently
mis-modelled. The dispatch table :data:`_BOUNDARY_SUPPORTED` is the single
place to extend when FF / SF land.

Determinism
-----------
No ``datetime.now()`` / no ``random``. Synthetic ids are derived solely from
the local id and a per-local counter, so a given input always yields the same
super-graph and the same results.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.modules.schedule_advanced.cpm import (
    Activity,
    CPMResult,
    CycleError,
    DepType,
    TaskNetwork,
    compute_cpm,
    critical_path,
)

__all__ = [
    "BoundaryConstraint",
    "CrossEdge",
    "compute_portfolio_cpm",
    "portfolio_critical_path",
    "standalone_with_boundaries",
    "is_synthetic_id",
    "SYNTHETIC_PREFIX",
    # Re-exported for integrator convenience so it can catch the kernel's
    # cycle error without importing two modules.
    "CycleError",
    "CPMResult",
]

#: Prefix marking a synthetic boundary node. Chosen so it cannot collide with
#: real id-namespaced activity ids (which the integrator builds as
#: ``{schedule_id}:{activity_id}`` or similar) - real ids never start with a
#: double underscore in this system.
SYNTHETIC_PREFIX = "__boundary__"

#: Link types whose boundary floor is realised by a synthetic *source* node of
#: duration ``boundary_index`` linked FS - i.e. the floor is exactly
#: ``boundary_index + lag`` with no dependence on the local activity's own
#: duration. FS is the v1 target; SS shares the identical construction.
_BOUNDARY_SUPPORTED: frozenset[str] = frozenset({"FS", "SS"})

#: Boundary-link statuses. ``broken`` (far side deleted) and ``stale`` (far
#: side never computed) still constrain the local activity using the *frozen*
#: ``boundary_index`` - the critical path must never silently shorten when the
#: far project goes away. Only the provenance differs; the math is identical.
_BOUNDARY_STATUSES: frozenset[str] = frozenset({"live", "stale", "broken"})


# ── Public input dataclasses ─────────────────────────────────────────────────


@dataclass(frozen=True)
class CrossEdge:
    """An *in-scope* cross-project dependency to include as a REAL edge.

    Both endpoints are present in the merged activity list (their far side is
    inside the portfolio scope), so the edge is added verbatim to the
    successor's predecessor list and the kernel treats it like any other link -
    including for cycle detection across projects.

    Attributes:
        predecessor_id: Id of the upstream activity (already id-namespaced by
            the integrator). Must exist in the merged ``activities`` list.
        successor_id: Id of the downstream activity. Must exist in the merged
            ``activities`` list.
        dep_type: One of "FS" / "SS" / "FF" / "SF" (all honoured by the
            kernel for real edges).
        lag: Integer working-day lag (may be negative for a lead).
    """

    predecessor_id: str
    successor_id: str
    dep_type: DepType = "FS"
    lag: int = 0


@dataclass(frozen=True)
class BoundaryConstraint:
    """A frozen floor for an edge whose far side is OUT of scope.

    The far activity is not loaded (it lives in a project the caller did not /
    cannot pull into the super-graph), so instead of dropping the dependency -
    which would let the local critical path silently shorten - we pin a frozen
    *boundary floor* derived from the far side's last published dates.

    Attributes:
        local_activity_id: Id of the in-scope activity the floor applies to.
            Must exist in the merged ``activities`` list (if it does not, the
            constraint is ignored - the caller fed a partial sub-network).
        dep_type: The original link type. v1 supports "FS" (and "SS", which
            shares the construction); "FF"/"SF" raise ``ValueError`` because
            they bound the finish, not the start - see the module docstring.
        boundary_index: The frozen far-side work-day index. For FS pass the far
            activity's last published *early-finish*; for SS its *early-start*.
            This value is used even when ``status == "broken"`` (far side
            deleted) so the floor survives the far project's removal.
        lag: Integer working-day lag from the original link (may be negative).
        status: Provenance only - one of ``"live"`` / ``"stale"`` / ``"broken"``.
            Does NOT change the math: all three constrain using
            ``boundary_index``. ``stale`` = far side never computed; ``broken``
            = far side deleted (frozen snapshot retained). Invalid values raise.

    The effective local early-start floor is ``boundary_index + lag`` (FS/SS).
    """

    local_activity_id: str
    dep_type: DepType = "FS"
    boundary_index: int = 0
    lag: int = 0
    status: str = "live"

    def __post_init__(self) -> None:
        if self.dep_type not in _BOUNDARY_SUPPORTED:
            raise ValueError(
                f"BoundaryConstraint v1 supports only {sorted(_BOUNDARY_SUPPORTED)} "
                f"(got {self.dep_type!r}). FF/SF bound the finish, not the start, and "
                f"are not yet modelled as a boundary floor - see portfolio_cpm docstring."
            )
        if self.status not in _BOUNDARY_STATUSES:
            raise ValueError(
                f"BoundaryConstraint.status must be one of {sorted(_BOUNDARY_STATUSES)} (got {self.status!r})."
            )

    def floor(self) -> int:
        """The local early-start floor this constraint imposes (FS/SS)."""
        return int(self.boundary_index) + int(self.lag)


# ── Synthetic-node helpers ───────────────────────────────────────────────────


def is_synthetic_id(activity_id: Any) -> bool:
    """True iff ``activity_id`` is an injected synthetic boundary node."""
    return isinstance(activity_id, str) and activity_id.startswith(SYNTHETIC_PREFIX)


def _synthetic_id(local_id: Any, n: int) -> str:
    """Deterministic, namespaced id for the n-th boundary node of ``local_id``."""
    return f"{SYNTHETIC_PREFIX}{local_id}__{n}"


# ── Super-graph construction ─────────────────────────────────────────────────


def _build_super_network(
    activities: Sequence[Activity],
    cross_edges: Iterable[CrossEdge],
    boundaries: Iterable[BoundaryConstraint],
) -> TaskNetwork:
    """Merge local activities + cross edges + boundary synthetics into a network.

    * Each real activity is rebuilt with its original predecessors **plus** any
      :class:`CrossEdge` whose successor is this activity (in-scope far side ->
      real edge).
    * Each :class:`BoundaryConstraint` for a present local activity injects one
      synthetic source node (duration ``boundary_index``, no predecessors) and
      an FS link ``(synthetic_id, "FS", lag)`` onto that local activity, which
      floors its ES at ``boundary_index + lag`` (see module docstring).

    Constraints / edges that reference an unknown local id are ignored, matching
    the kernel's own "drop refs to unknown activities" tolerance so a partial
    sub-network never crashes.
    """
    # Index the real activities (preserve first occurrence, like the kernel).
    by_id: dict[Any, Activity] = {}
    order: list[Any] = []
    for a in activities:
        if a.id not in by_id:
            by_id[a.id] = a
            order.append(a.id)

    # Group in-scope cross edges by successor so we extend its predecessor list.
    extra_preds: dict[Any, list[tuple[Any, DepType, int]]] = {}
    for e in cross_edges:
        if e.successor_id not in by_id:
            # Far side (or near side) not in the merged scope - the caller
            # should have passed a BoundaryConstraint instead. Drop quietly,
            # consistent with the kernel dropping unknown-pred edges.
            continue
        extra_preds.setdefault(e.successor_id, []).append((e.predecessor_id, e.dep_type, int(e.lag)))

    # Build synthetic boundary sources + the FS links onto their local nodes.
    # A per-local counter keeps synthetic ids deterministic and unique even
    # when one activity carries several boundary constraints.
    synthetic_nodes: list[Activity] = []
    boundary_links: dict[Any, list[tuple[Any, DepType, int]]] = {}
    per_local_count: dict[Any, int] = {}
    for b in boundaries:
        if b.local_activity_id not in by_id:
            continue  # partial sub-network: nothing to floor.
        n = per_local_count.get(b.local_activity_id, 0)
        per_local_count[b.local_activity_id] = n + 1
        syn_id = _synthetic_id(b.local_activity_id, n)
        # Synthetic source: duration == frozen boundary index, no predecessors,
        # so EF == boundary_index. The FS lag then yields ES_local floor.
        synthetic_nodes.append(Activity(id=syn_id, duration=max(0, int(b.boundary_index))))
        boundary_links.setdefault(b.local_activity_id, []).append((syn_id, "FS", int(b.lag)))

    # Rebuild each real activity with merged predecessors. Activity is frozen,
    # so we construct fresh instances rather than mutating in place.
    merged: list[Activity] = []
    for aid in order:
        a = by_id[aid]
        preds: list[tuple[Any, DepType, int]] = list(a.predecessors)
        preds.extend(extra_preds.get(aid, ()))
        preds.extend(boundary_links.get(aid, ()))
        merged.append(
            Activity(
                id=a.id,
                duration=a.duration,
                predecessors=preds,
                required_resources=dict(a.required_resources),
            )
        )

    # Synthetic sources go FIRST so they are guaranteed present before the
    # local nodes reference them (the kernel drops edges to unknown ids).
    return TaskNetwork(synthetic_nodes + merged)


def _strip_synthetic(results: Mapping[Any, CPMResult]) -> dict[Any, CPMResult]:
    """Drop synthetic boundary nodes from a results mapping."""
    return {aid: r for aid, r in results.items() if not is_synthetic_id(aid)}


# ── Public engine API ────────────────────────────────────────────────────────


def compute_portfolio_cpm(
    activities: Sequence[Activity],
    *,
    cross_edges: Iterable[CrossEdge] = (),
    boundaries: Iterable[BoundaryConstraint] = (),
) -> dict[str, CPMResult]:
    """Run one global CPM pass over the merged portfolio super-graph.

    Args:
        activities: Local activities already merged across every in-scope
            schedule, each :class:`Activity`-shaped with id-namespaced string
            ids and predecessor triples ``(pred_id, dep_type, lag)``. The
            integrator is responsible for namespacing ids so they are unique
            across schedules.
        cross_edges: In-scope cross-project dependencies to include as **real**
            edges (both endpoints present in ``activities``).
        boundaries: Frozen floors for edges whose far side is **out** of scope
            (see :class:`BoundaryConstraint`).

    Returns:
        A ``dict[str, CPMResult]`` keyed by real activity id - synthetic
        boundary nodes are stripped. The :class:`CPMResult` fields are exactly
        those of the kernel: ``es``, ``ef``, ``ls``, ``lf``, ``total_float``,
        ``free_float``, ``is_critical``.

    Raises:
        CycleError: if the super-graph contains a directed cycle - including a
            cycle that exists only across projects (the cross edges close the
            loop). The error's ``cycle_path`` may include nothing synthetic
            (synthetic nodes are sources and cannot be part of a cycle).
        ValueError: via :class:`BoundaryConstraint` validation for an
            unsupported link type or status.
    """
    network = _build_super_network(activities, cross_edges, boundaries)
    results = compute_cpm(network)  # propagates CycleError on a cross-project cycle
    return _strip_synthetic(results)


def portfolio_critical_path(
    activities: Sequence[Activity],
    *,
    cross_edges: Iterable[CrossEdge] = (),
    boundaries: Iterable[BoundaryConstraint] = (),
) -> list[str]:
    """Return one critical path across the portfolio super-graph, in topo order.

    Synthetic boundary nodes are never part of the returned path: they are
    sources with zero total float, but the kernel's :func:`critical_path` walks
    *forward* over critical successors from each critical seed, and a synthetic
    node's only successor (the floored local activity) is critical only when the
    boundary actually drives it - so the path is filtered to real ids here
    regardless, as a belt-and-braces guarantee.

    Same ``Raises`` contract as :func:`compute_portfolio_cpm`.
    """
    network = _build_super_network(activities, cross_edges, boundaries)
    results = compute_cpm(network)  # propagates CycleError
    path = critical_path(network, results)
    return [aid for aid in path if not is_synthetic_id(aid)]


def standalone_with_boundaries(
    activities: Sequence[Activity],
    boundaries: Iterable[BoundaryConstraint],
) -> dict[str, CPMResult]:
    """Single-schedule CPM with frozen cross-project boundary floors applied.

    The standalone case (acceptance #5): exactly one schedule is in scope, but
    its activities still depend on activities in *other* projects that are not
    loaded. Each such dependency is supplied as a :class:`BoundaryConstraint`
    whose frozen ``boundary_index`` floors the local activity's early start, so
    the local critical path reflects the external dependency even though the far
    side is absent - and continues to do so when the far link's status is
    ``stale`` or ``broken``.

    This is a thin alias over :func:`compute_portfolio_cpm` with no cross edges;
    it exists to name the standalone intent at the call site. Returns the same
    stripped ``dict[str, CPMResult]``.
    """
    return compute_portfolio_cpm(activities, cross_edges=(), boundaries=boundaries)
