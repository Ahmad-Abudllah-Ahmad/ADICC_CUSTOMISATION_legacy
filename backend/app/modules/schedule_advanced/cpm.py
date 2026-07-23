# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure-Python Critical Path Method (CPM) engine - Slice 1.

This module is intentionally self-contained: no SQLAlchemy, no FastAPI,
no third-party deps (no scipy / networkx). Everything is plain ``dataclass``
+ ``list`` / ``dict`` so the engine can be unit-tested in isolation and
also imported by services that want to run "what-if" scheduling.

Scope:
    * Activities with integer ``duration`` (working days).
    * All four PDM dependency types with optional integer lag (may be
      negative for lead time):

      ====  ==================  =============================================
      Code  Name                Forward-pass constraint on successor ``s``
      ====  ==================  =============================================
      FS    Finish-to-Start     ``s.ES >= p.EF + lag``
      SS    Start-to-Start      ``s.ES >= p.ES + lag``
      FF    Finish-to-Finish    ``s.EF >= p.EF + lag``
      SF    Start-to-Finish     ``s.EF >= p.ES + lag``
      ====  ==================  =============================================

      The backward pass mirrors each constraint to bound the predecessor's
      late dates (see :func:`compute_cpm`).
    * Forward pass → ES / EF.
    * Backward pass → LS / LF.
    * Total float = LS − ES (== LF − EF).
    * Free float  = max slip from early dates before any successor's early
      dates move, computed per link type (0 for terminal nodes when at the
      component finish).
    * Critical path marking (total_float <= 0).
    * Cycle detection via DFS (raises :class:`CycleError`).
    * Disconnected sub-networks supported - every weakly-connected
      component is scheduled independently from t=0.

The existing ``service.cpm_forward_backward_pass`` helper that powers the
stateless ``POST /cpm`` endpoint stays in place; this new engine is the
canonical reference implementation used by the new persisted
``compute-cpm`` endpoint and by the resource-leveling heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

# Dependency type codes - all four PDM link types are honoured in both
# the forward pass (ES/EF) and the backward pass (LS/LF).
DepType = Literal["FS", "SS", "FF", "SF"]

#: The unit every ``duration`` and ``lag`` value in this engine is expressed in:
#: whole working days as counted by the active working calendar (see
#: :class:`OffsetCalendar`). Durations are never elapsed calendar days and never
#: hours. A caller working in another unit (hours, shifts, elapsed days) must
#: convert to working days before building an :class:`Activity`. Exposed as a
#: constant so reports and API responses can label the unit in one place instead
#: of hard-coding the word "days" in scattered strings.
DURATION_UNIT: str = "working_day"

#: The four allowed dependency (precedence) types. Kept as a runtime set so
#: validation can check user-supplied link types without relying on the static
#: ``Literal`` type alias above.
VALID_DEP_TYPES: frozenset[str] = frozenset({"FS", "SS", "FF", "SF"})

#: Plain-language name for each dependency type, for UI, reports and error
#: messages so a planner never has to memorise the two-letter codes.
DEP_TYPE_NAMES: dict[str, str] = {
    "FS": "Finish-to-Start (this activity starts after its predecessor finishes)",
    "SS": "Start-to-Start (this activity starts after its predecessor starts)",
    "FF": "Finish-to-Finish (this activity finishes after its predecessor finishes)",
    "SF": "Start-to-Finish (this activity finishes after its predecessor starts)",
}


def dependency_type_label(dep_type: str) -> str:
    """Return the plain-language name of a dependency type code.

    Falls back to a clear "unknown type" message so an invalid code coming from
    imported data never surfaces to the user as a bare two-letter string.
    """
    return DEP_TYPE_NAMES.get(dep_type, f"Unknown dependency type '{dep_type}' (expected FS, SS, FF or SF)")


# ── Exceptions ─────────────────────────────────────────────────────────────


class CycleError(ValueError):
    """Raised when the activity network contains a directed cycle.

    ``cycle_path`` is the list of activity ids that close the loop (in
    traversal order). The first id is repeated at the end so callers can
    render ``A → B → C → A`` without further bookkeeping.
    """

    def __init__(self, cycle_path: list[Any]) -> None:
        self.cycle_path: list[Any] = list(cycle_path)
        super().__init__(f"Cycle detected in activity network: {' → '.join(map(str, self.cycle_path))}")


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Activity:
    """One scheduled activity.

    Attributes:
        id: Unique identifier (any hashable - typically a UUID string or
            a short code like ``"A"``).
        duration: Working-day duration. Coerced to ``max(0, int(duration))``
            at network-build time - negative durations behave like
            milestones.
        predecessors: List of ``(predecessor_id, dep_type, lag_days)``
            triples. ``dep_type`` is "FS" / "SS" / "FF" / "SF" (all four
            are honoured). ``lag_days`` may be negative (lead time).
        required_resources: Mapping of resource code → integer count
            consumed by this activity for its full duration. Used by
            :mod:`leveling`. Empty dict means "no resource constraints".
    """

    id: Any
    duration: int = 0
    predecessors: list[tuple[Any, DepType, int]] = field(default_factory=list)
    required_resources: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CPMResult:
    """Per-activity CPM output.

    All values are integer work-day indices (0-based). ``es``/``ef`` come
    from the forward pass, ``ls``/``lf`` from the backward pass.
    ``total_float`` and ``free_float`` are always ``>= 0`` (clamped) for
    valid acyclic networks.
    """

    es: int
    ef: int
    ls: int
    lf: int
    total_float: int
    free_float: int
    is_critical: bool


# ── Task network ───────────────────────────────────────────────────────────


class TaskNetwork:
    """A directed activity network.

    The network owns its activities and computes its own predecessor /
    successor adjacency on construction. Edges referencing unknown
    predecessor ids are silently dropped (so callers can feed partial
    sub-networks without crashing).
    """

    def __init__(self, activities: list[Activity]) -> None:
        # Index by id (preserve first occurrence on duplicate ids).
        seen: dict[Any, Activity] = {}
        for a in activities:
            if a.id not in seen:
                seen[a.id] = a
        self._activities: dict[Any, Activity] = seen
        # Preserve a stable iteration order = insertion order.
        self._order: list[Any] = list(seen.keys())

        # Build adjacency dropping refs to unknown activities + self-loops.
        self._preds: dict[Any, list[tuple[Any, DepType, int]]] = {}
        self._succs: dict[Any, list[tuple[Any, DepType, int]]] = {}
        for aid in self._order:
            self._preds[aid] = []
            self._succs[aid] = []
        for aid, a in self._activities.items():
            for p_id, dep_type, lag in a.predecessors:
                if p_id == aid:
                    continue
                if p_id not in self._activities:
                    continue
                triple: tuple[Any, DepType, int] = (p_id, dep_type, int(lag))
                self._preds[aid].append(triple)
                self._succs[p_id].append((aid, dep_type, int(lag)))

    # ── Accessors ──

    @property
    def activities(self) -> list[Activity]:
        return [self._activities[aid] for aid in self._order]

    def get(self, activity_id: Any) -> Activity | None:
        return self._activities.get(activity_id)

    def predecessors(self, activity_id: Any) -> list[tuple[Any, DepType, int]]:
        return list(self._preds.get(activity_id, []))

    def successors(self, activity_id: Any) -> list[tuple[Any, DepType, int]]:
        return list(self._succs.get(activity_id, []))

    def ids(self) -> list[Any]:
        return list(self._order)

    # ── Cycle detection ──

    def detect_cycle(self) -> list[Any] | None:
        """Return a cycle path if one exists, else ``None``.

        Iterative DFS using three colours (white / grey / black). Closing
        a grey edge produces the cycle; the path is reconstructed from
        the DFS parent map.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        colour: dict[Any, int] = dict.fromkeys(self._order, WHITE)
        parent: dict[Any, Any] = {}

        for root in self._order:
            if colour[root] != WHITE:
                continue
            # Iterative DFS - (node, iterator-over-children)
            stack: list[tuple[Any, list[tuple[Any, DepType, int]]]] = [(root, list(self._succs[root]))]
            colour[root] = GREY
            while stack:
                node, children = stack[-1]
                if not children:
                    colour[node] = BLACK
                    stack.pop()
                    continue
                child_id, _dep, _lag = children.pop(0)
                if colour[child_id] == WHITE:
                    parent[child_id] = node
                    colour[child_id] = GREY
                    stack.append((child_id, list(self._succs[child_id])))
                elif colour[child_id] == GREY:
                    # Cycle: child_id → ... → node → child_id.
                    # Walk the parent chain from `node` back to `child_id`.
                    # Guard: when `child_id` is the DFS-tree root it has no
                    # entry in ``parent``; the old ``cur in parent`` guard
                    # terminated early and left the first node of the cycle
                    # out of the path (producing A → B → A instead of the
                    # correct A → B → C → A when A was the root). We now
                    # stop when we either reach `child_id` again OR exhaust
                    # the parent chain - the closing ``child_id`` appended
                    # below always completes the ring regardless.
                    cycle = [child_id]
                    cur = node
                    while cur != child_id:
                        cycle.append(cur)
                        if cur not in parent:
                            break
                        cur = parent[cur]
                    cycle.append(child_id)
                    cycle.reverse()
                    return cycle
                # BLACK: already fully explored - skip.
        return None


# ── CPM computation ────────────────────────────────────────────────────────


def _topological_order(network: TaskNetwork) -> list[Any]:
    """Kahn's algorithm - assumes the network is acyclic (caller's job)."""
    indeg: dict[Any, int] = {aid: len(network.predecessors(aid)) for aid in network.ids()}
    # Use a list as a FIFO; the network is small so O(n) pop(0) is fine.
    queue: list[Any] = [aid for aid in network.ids() if indeg[aid] == 0]
    order: list[Any] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for s_id, _dep, _lag in network.successors(n):
            indeg[s_id] -= 1
            if indeg[s_id] == 0:
                queue.append(s_id)
    return order


def compute_cpm(network: TaskNetwork) -> dict[Any, CPMResult]:
    """Run forward + backward pass on ``network``.

    Returns a dict keyed by activity id.

    Raises:
        CycleError: if the network contains a directed cycle.

    Disconnected sub-networks are scheduled independently: each
    sub-network's "sinks" (nodes with no successors) have their LF
    pinned to the project finish of that sub-network only, NOT to the
    global project finish across sub-networks. This matches desktop
    scheduling tool behaviour for unrelated activity islands.
    """
    cycle = network.detect_cycle()
    if cycle is not None:
        raise CycleError(cycle)

    order = _topological_order(network)
    if not order:
        return {}

    # ── Forward pass: ES, EF ─────────────────────────────────────────────
    # Each predecessor link yields a lower bound on this activity's ES.
    # Constraints that naturally bound the FINISH (FF / SF) are converted
    # to an ES bound by subtracting this activity's own duration, since
    # EF = ES + duration:
    #
    #     FS: s.ES >= p.EF + lag                      → es_bound = ef[p] + lag
    #     SS: s.ES >= p.ES + lag                      → es_bound = es[p] + lag
    #     FF: s.EF >= p.EF + lag → s.ES >= p.EF+lag-d → es_bound = ef[p] + lag - dur
    #     SF: s.EF >= p.ES + lag → s.ES >= p.ES+lag-d → es_bound = es[p] + lag - dur
    durations: dict[Any, int] = {}
    es: dict[Any, int] = {}
    ef: dict[Any, int] = {}
    for aid in order:
        a = network.get(aid)
        assert a is not None
        dur = max(0, int(a.duration))
        durations[aid] = dur
        candidates: list[int] = []
        for p_id, dep_type, lag in network.predecessors(aid):
            if p_id not in es:
                continue
            lag = int(lag)
            if dep_type == "SS":
                candidates.append(es[p_id] + lag)
            elif dep_type == "FF":
                candidates.append(ef[p_id] + lag - dur)
            elif dep_type == "SF":
                candidates.append(es[p_id] + lag - dur)
            else:  # FS (default)
                candidates.append(ef[p_id] + lag)
        es[aid] = max(candidates) if candidates else 0
        ef[aid] = es[aid] + dur

    # ── Identify weakly-connected components for per-island project_finish ─
    # We do a union-find over the undirected version of the graph so the
    # backward pass anchors each island to its own finish.
    component_root: dict[Any, Any] = {aid: aid for aid in order}

    def _find(x: Any) -> Any:
        while component_root[x] != x:
            component_root[x] = component_root[component_root[x]]
            x = component_root[x]
        return x

    def _union(x: Any, y: Any) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            component_root[rx] = ry

    for aid in order:
        for s_id, _dep, _lag in network.successors(aid):
            _union(aid, s_id)

    # Per-component project finish = max EF of any node in the component.
    component_finish: dict[Any, int] = {}
    for aid in order:
        root = _find(aid)
        if ef[aid] > component_finish.get(root, -1):
            component_finish[root] = ef[aid]

    # ── Backward pass: LF, LS ────────────────────────────────────────────
    # Mirror of the forward pass: each successor link yields an UPPER bound
    # on this predecessor's LF. Constraints that naturally bound the
    # predecessor's START (SS / SF) are converted to an LF bound by adding
    # this activity's own duration, since LF = LS + duration:
    #
    #     FS: p.LF <= s.LS - lag                      → lf_bound = ls[s] - lag
    #     FF: p.LF <= s.LF - lag                      → lf_bound = lf[s] - lag
    #     SS: p.LS <= s.LS - lag → p.LF <= s.LS-lag+d → lf_bound = ls[s] - lag + dur
    #     SF: p.LS <= s.LF - lag → p.LF <= s.LF-lag+d → lf_bound = lf[s] - lag + dur
    lf: dict[Any, int] = {}
    ls: dict[Any, int] = {}
    for aid in reversed(order):
        a = network.get(aid)
        assert a is not None
        dur = durations[aid]
        succ_candidates: list[int] = []
        for s_id, dep_type, lag in network.successors(aid):
            if s_id not in ls:
                continue
            lag = int(lag)
            if dep_type == "SS":
                succ_candidates.append(ls[s_id] - lag + dur)
            elif dep_type == "FF":
                succ_candidates.append(lf[s_id] - lag)
            elif dep_type == "SF":
                succ_candidates.append(lf[s_id] - lag + dur)
            else:  # FS (default)
                succ_candidates.append(ls[s_id] - lag)
        if succ_candidates:
            lf[aid] = min(succ_candidates)
        else:
            # Sink → pin to own component finish.
            lf[aid] = component_finish[_find(aid)]
        ls[aid] = lf[aid] - dur

    # ── Float + critical marking ─────────────────────────────────────────
    results: dict[Any, CPMResult] = {}
    for aid in order:
        total_float = ls[aid] - es[aid]
        # Free float: how long this activity can slip from its EARLY dates
        # before pushing the early dates of any immediate successor. Each
        # link type imposes a slack on this activity's EF (mirrors the
        # forward pass with successors' early dates). For a sink it's the
        # slack to its own component finish.
        dur_aid = durations[aid]
        slack_bounds: list[int] = []
        for s_id, dep_type, lag in network.successors(aid):
            if s_id not in es:
                continue
            lag = int(lag)
            if dep_type == "SS":
                slack_bounds.append((es[s_id] - lag + dur_aid) - ef[aid])
            elif dep_type == "FF":
                slack_bounds.append((ef[s_id] - lag) - ef[aid])
            elif dep_type == "SF":
                slack_bounds.append((ef[s_id] - lag + dur_aid) - ef[aid])
            else:  # FS (default)
                slack_bounds.append((es[s_id] - lag) - ef[aid])
        if slack_bounds:
            free_float = min(slack_bounds)
        else:
            free_float = component_finish[_find(aid)] - ef[aid]
        results[aid] = CPMResult(
            es=es[aid],
            ef=ef[aid],
            ls=ls[aid],
            lf=lf[aid],
            total_float=max(0, total_float),
            free_float=max(0, free_float),
            # Use <= 0 (not == 0) so activities with negative total float
            # (possible when lag constraints push a successor earlier than
            # the predecessor's EF) are correctly marked critical. Using
            # == 0 silently misses these activities and produces an
            # incomplete / wrong critical path.
            is_critical=(total_float <= 0),
        )
    return results


# ── Convenience helpers ────────────────────────────────────────────────────


def es_ef_durations(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
) -> tuple[dict[Any, int], dict[Any, int], dict[Any, int]]:
    """Project a CPM ``results`` dict back into ``(es, ef, durations)`` maps.

    The claims-grade post-processors below take ``es`` / ``ef`` / ``durations``
    as plain dicts so they never depend on a particular result container. This
    helper extracts them from a :func:`compute_cpm` (or
    :func:`out_of_sequence_cpm`) run plus the network, so callers do not repeat
    the forward-pass bookkeeping. ``durations`` is the network's clamped
    ``max(0, int(duration))`` per activity.
    """
    es = {aid: r.es for aid, r in results.items()}
    ef = {aid: r.ef for aid, r in results.items()}
    durations: dict[Any, int] = {}
    for aid in results:
        a = network.get(aid)
        durations[aid] = max(0, int(a.duration)) if a is not None else (ef[aid] - es[aid])
    return es, ef, durations


def critical_path(
    network: TaskNetwork,
    results: dict[Any, CPMResult] | None = None,
) -> list[Any]:
    """Return ONE critical path through the network, in topological order.

    If multiple critical paths exist, the first one (lowest topological
    rank at every fork) is returned. Disconnected critical activities
    that don't belong to the longest chain are still included as
    standalone single-node paths appended at the end (stable order).
    """
    if results is None:
        results = compute_cpm(network)
    critical_ids = {aid for aid, r in results.items() if r.is_critical}
    if not critical_ids:
        return []

    order = _topological_order(network)
    path: list[Any] = []
    seen: set[Any] = set()
    for aid in order:
        if aid in critical_ids and aid not in seen:
            # Greedily extend forward through critical successors.
            cur = aid
            while cur is not None and cur not in seen:
                path.append(cur)
                seen.add(cur)
                next_cur: Any = None
                # Follow any critical successor regardless of link type.
                for s_id, _dep_type, _lag in network.successors(cur):
                    if s_id in critical_ids and s_id not in seen:
                        next_cur = s_id
                        break
                cur = next_cur
    return path


# ════════════════════════════════════════════════════════════════════════════
# Claims-grade CPM extensions (T1.2)
# ────────────────────────────────────────────────────────────────────────────
# Everything below is ADDITIVE and pure. It post-processes the output of
# ``compute_cpm`` (plus the network adjacency) to produce forensic-grade
# scheduling artefacts that survive expert scrutiny in delay-claim review:
#
#   * Longest Path (the date-driving chain, independent of the float rule)
#   * Multiple float paths (the driving chain + secondary near-driving chains)
#   * Driving-predecessor identification (which logic link actually set ES)
#   * Out-of-sequence forward passes (Retained Logic / Progress Override /
#     Actual Dates) keyed off a data date + per-activity progress
#   * A scheduling-quality findings log (open ends, hard constraints, out of
#     sequence, large / negative lags)
#   * Human-readable explain strings derived strictly from the numbers
#
# All thresholds live in module-level constants so the behaviour is auditable
# and tunable in exactly one place.
# ════════════════════════════════════════════════════════════════════════════


# ── Tunable constants (single source of truth for QA thresholds) ─────────────

#: A lag whose absolute value exceeds this many working days is flagged
#: LARGE_LAG by :func:`scheduling_qa_log`. Long lags are a classic way to
#: hide sequencing logic and are a standard forensic review target.
LARGE_LAG_THRESHOLD_DAYS: int = 10

#: Default total-float threshold (working days) for ``"total_float"`` critical
#: marking via :func:`select_critical`. Matches ``compute_cpm``'s ``<= 0`` rule.
DEFAULT_CRITICAL_FLOAT_THRESHOLD: int = 0

#: Default caps for :func:`multiple_float_paths`.
DEFAULT_MAX_FLOAT_PATHS: int = 10
DEFAULT_MIN_FLOAT_PATH_LEN: int = 1

#: QA finding severities. Higher sorts first (more urgent). Used both as the
#: ``severity`` field on a finding and as the primary sort key.
SEVERITY_HIGH: int = 3
SEVERITY_MEDIUM: int = 2
SEVERITY_LOW: int = 1

#: Critical-path selection modes for :func:`select_critical`.
CriticalMode = Literal["total_float", "longest_path"]


# ── Topological rank (deterministic ordering helper) ─────────────────────────


def _topo_rank(network: TaskNetwork) -> dict[Any, int]:
    """Map each activity id to its position in the topological order.

    Lower rank == earlier in the schedule logic. Used as the primary,
    fully-deterministic tie-break when several edges or activities are
    otherwise equal. Activities not reachable by Kahn's algorithm (only
    possible for cyclic networks, which the callers reject first) are
    appended in stable insertion order with ranks after every ordered node.
    """
    order = _topological_order(network)
    rank: dict[Any, int] = {aid: i for i, aid in enumerate(order)}
    if len(rank) != len(network.ids()):
        nxt = len(rank)
        for aid in network.ids():
            if aid not in rank:
                rank[aid] = nxt
                nxt += 1
    return rank


def _forward_bound(
    dep_type: DepType,
    p_es: int,
    p_ef: int,
    lag: int,
    dur: int,
) -> int:
    """Lower bound this link places on the successor's ES.

    Mirrors the forward-pass arithmetic in :func:`compute_cpm` EXACTLY so
    that "the predecessor whose bound equals ES" is well defined. FF / SF
    naturally bound the finish, so they are converted to an ES bound by
    subtracting the successor's own duration (EF = ES + dur).
    """
    if dep_type == "SS":
        return p_es + lag
    if dep_type == "FF":
        return p_ef + lag - dur
    if dep_type == "SF":
        return p_es + lag - dur
    return p_ef + lag  # FS (default)


def driving_predecessor(
    network: TaskNetwork,
    es: dict[Any, int],
    ef: dict[Any, int],
    durations: dict[Any, int],
    s: Any,
    *,
    topo_rank: dict[Any, int] | None = None,
) -> tuple[Any, DepType, int] | None:
    """Return the single predecessor edge that DROVE ``s``'s early start.

    The driving edge is the ``(predecessor_id, dep_type, lag)`` triple whose
    forward-pass bound equals ``es[s]`` - i.e. the logic link that actually
    set this activity's early start. When several edges tie on the bound the
    tie is broken deterministically:

        1. lowest predecessor topological rank (earliest logic wins), then
        2. lowest predecessor id rendered as a string.

    Returns ``None`` for an "open start": an activity with no scheduled
    predecessor that produced its ES (it floats to its component start, t=0,
    or to its actual start in an out-of-sequence pass). Edges whose
    predecessor lacks an ES entry (dropped / out-of-component) are ignored.
    """
    if topo_rank is None:
        topo_rank = _topo_rank(network)
    target = es.get(s)
    if target is None:
        return None
    dur = durations.get(s, 0)
    best: tuple[Any, DepType, int] | None = None
    best_key: tuple[int, str] | None = None
    for p_id, dep_type, lag in network.predecessors(s):
        if p_id not in es or p_id not in ef:
            continue
        bound = _forward_bound(dep_type, es[p_id], ef[p_id], int(lag), dur)
        if bound != target:
            continue
        key = (topo_rank.get(p_id, len(topo_rank)), str(p_id))
        if best_key is None or key < best_key:
            best_key = key
            best = (p_id, dep_type, int(lag))
    return best


def driving_chain(
    network: TaskNetwork,
    es: dict[Any, int],
    ef: dict[Any, int],
    durations: dict[Any, int],
    start: Any,
    *,
    topo_rank: dict[Any, int] | None = None,
    allowed: set[Any] | None = None,
) -> list[Any]:
    """Walk backward from ``start`` over driving edges; return forward order.

    Follows :func:`driving_predecessor` from ``start`` until an open start
    (no driving predecessor) is reached, a node repeats (defensive - the
    driving relation is acyclic for an acyclic network), or the driving
    predecessor falls outside ``allowed`` (when given). The returned list is
    in forward (topological) order: chain head first, ``start`` last.
    """
    if topo_rank is None:
        topo_rank = _topo_rank(network)
    chain: list[Any] = []
    seen: set[Any] = set()
    cur: Any = start
    while cur is not None and cur not in seen:
        chain.append(cur)
        seen.add(cur)
        edge = driving_predecessor(network, es, ef, durations, cur, topo_rank=topo_rank)
        if edge is None:
            break
        p_id = edge[0]
        if allowed is not None and p_id not in allowed:
            break
        cur = p_id
    chain.reverse()
    return chain


def longest_path(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
    durations: dict[Any, int],
    es: dict[Any, int],
    ef: dict[Any, int],
) -> list[Any]:
    """Return the Longest Path (date-driving chain) in forward order.

    The Longest Path is the chain of activities that controls the project
    finish date, found purely from the forward pass and therefore correct
    even when calendars, constraints or multiple float values would make the
    float-based critical set disagree. The seed is the activity (or, on ties,
    the lowest-(topo-rank, id) activity) whose EF equals the maximum EF in the
    network; the chain is then traced back over driving edges.

    ``results`` is accepted for signature symmetry with the other helpers and
    to let callers pass the exact CPM run the chain belongs to; the chain
    itself is derived from ``es`` / ``ef`` / ``durations``.
    """
    if not ef:
        return []
    topo_rank = _topo_rank(network)
    max_ef = max(ef.values())
    seeds = sorted(
        (aid for aid, v in ef.items() if v == max_ef),
        key=lambda a: (topo_rank.get(a, len(topo_rank)), str(a)),
    )
    seed = seeds[0]
    return driving_chain(network, es, ef, durations, seed, topo_rank=topo_rank)


@dataclass(frozen=True)
class FloatPath:
    """One float path: the driving chain (index 0) or a near-driving chain.

    Attributes:
        index: 0-based rank. Path 0 is the Longest Path.
        activity_ids: Activities on the path in forward (topological) order.
        length_days: Summed working-day duration of the path's activities.
        relative_float: ``min`` total float over the path's activities. Path 0
            (the driving chain) is always ``0``; later paths are
            non-decreasing - the float you would buy back by driving that
            path's logic to zero. This is the standard "float path" reading
            used in forensic schedule review.
    """

    index: int
    activity_ids: list[Any]
    length_days: int
    relative_float: int


def multiple_float_paths(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
    durations: dict[Any, int],
    es: dict[Any, int],
    ef: dict[Any, int],
    *,
    max_paths: int = DEFAULT_MAX_FLOAT_PATHS,
    min_len: int = DEFAULT_MIN_FLOAT_PATH_LEN,
) -> list[FloatPath]:
    """Decompose the network into ranked float paths (driving + secondary).

    Float path 1 (index 0) is the Longest Path. Each subsequent path is the
    longest remaining driving chain among activities not yet claimed by an
    earlier path, peeled off in descending summed-duration order. This is the
    "float path" decomposition used to rank near-critical work: lower-index
    paths threaten the finish date sooner.

    Args:
        max_paths: hard cap on the number of paths returned.
        min_len: drop any path with fewer than this many activities.

    Returns:
        A list of :class:`FloatPath`, index 0 first. ``relative_float`` is 0
        for index 0 and non-decreasing thereafter.
    """
    if not ef or max_paths <= 0:
        return []
    topo_rank = _topo_rank(network)

    def _length(ids: list[Any]) -> int:
        return sum(durations.get(a, 0) for a in ids)

    def _rel_float(ids: list[Any]) -> int:
        floats = [results[a].total_float for a in ids if a in results]
        return min(floats) if floats else 0

    paths: list[FloatPath] = []
    claimed: set[Any] = set()

    # Path 1 = the Longest Path (over the full, unclaimed network).
    lp = longest_path(network, results, durations, es, ef)
    if lp:
        paths.append(FloatPath(index=0, activity_ids=lp, length_days=_length(lp), relative_float=0))
        claimed.update(lp)

    # Subsequent paths: among unclaimed activities, take the one with the
    # greatest EF as a seed, trace its driving chain restricted to unclaimed
    # nodes, and keep the longest such chain. Repeat until caps are hit.
    while len(paths) < max_paths:
        remaining = [aid for aid in network.ids() if aid not in claimed and aid in ef]
        if not remaining:
            break
        # Seed candidates ordered by EF desc, then (topo-rank, id) for ties so
        # the peel is deterministic regardless of input ordering.
        remaining.sort(key=lambda a: (-ef[a], topo_rank.get(a, len(topo_rank)), str(a)))
        best_chain: list[Any] = []
        best_key: tuple[int, int, str] | None = None
        for seed in remaining:
            chain = driving_chain(network, es, ef, durations, seed, topo_rank=topo_rank, allowed=set(remaining))
            length = _length(chain)
            # Longest by days, then most activities, then lowest head rank.
            head_rank = topo_rank.get(chain[0], len(topo_rank)) if chain else len(topo_rank)
            key = (length, len(chain), -head_rank)
            cmp_key = (-key[0], -key[1], -key[2])
            if best_key is None or cmp_key < best_key:
                best_key = cmp_key
                best_chain = chain
        if not best_chain:
            break
        if len(best_chain) >= min_len:
            paths.append(
                FloatPath(
                    index=len(paths),
                    activity_ids=best_chain,
                    length_days=_length(best_chain),
                    relative_float=_rel_float(best_chain),
                )
            )
        claimed.update(best_chain)

    # Drop the seed path too if it failed the min_len gate (keeps the contract
    # that every returned path has >= min_len activities).
    return [p for p in paths if len(p.activity_ids) >= min_len]


# ── Out-of-sequence forward passes ───────────────────────────────────────────
# When a schedule is updated, work often progresses out of the planned logical
# order ("out of sequence"). Different schedulers resolve this differently;
# the three industry-standard retained-logic options are implemented below as
# pure forward passes that produce ES/EF. They all reduce EXACTLY to the
# planning forward pass of :func:`compute_cpm` when ``data_date`` is ``None``
# and no activity carries actuals, so the unchanged backward pass can run on
# top of any of them.


@dataclass(frozen=True)
class Progress:
    """Per-activity status as of the data date (all values optional).

    Attributes:
        actual_start: Work-day index the activity actually started, or None.
        actual_finish: Work-day index the activity actually finished, or None.
        progress_pct: Percent complete in ``[0, 100]`` (used to derive
            remaining duration when ``remaining_duration`` is not given).
        remaining_duration: Explicit remaining working days. Takes precedence
            over ``progress_pct`` when provided.
    """

    actual_start: int | None = None
    actual_finish: int | None = None
    progress_pct: float = 0.0
    remaining_duration: int | None = None


OutOfSeqMode = Literal["retained_logic", "progress_override", "actual_dates"]


def _is_started(p: Progress | None) -> bool:
    """True iff the activity has begun (actual start or any progress)."""
    if p is None:
        return False
    if p.actual_start is not None:
        return True
    if p.actual_finish is not None:
        return True
    return p.progress_pct > 0


def _is_finished(p: Progress | None) -> bool:
    """True iff the activity is complete (actual finish or 100%)."""
    if p is None:
        return False
    if p.actual_finish is not None:
        return True
    return p.progress_pct >= 100


def _remaining_days(p: Progress | None, dur: int) -> int:
    """Remaining working days for an activity.

    ``remaining_duration`` wins when supplied; otherwise derive it from
    percent complete: ``round(dur * (1 - pct/100))``. Always clamped to
    ``[0, dur]`` so a finished or over-reported activity never has negative
    remaining work.
    """
    if p is not None and p.remaining_duration is not None:
        return max(0, min(dur, int(p.remaining_duration)))
    pct = 0.0 if p is None else max(0.0, min(100.0, float(p.progress_pct)))
    rem = round(dur * (1.0 - pct / 100.0))
    return max(0, min(dur, int(rem)))


def _oos_forward_pass(
    network: TaskNetwork,
    mode: OutOfSeqMode,
    data_date: int | None,
    progress: dict[Any, Progress],
) -> tuple[dict[Any, int], dict[Any, int], dict[Any, int]]:
    """Forward pass honouring actuals + a data date under ``mode``.

    Returns ``(durations, es, ef)``. ``durations`` is the planned duration
    (unchanged) - the *remaining* work is folded into ES/EF only.

    Two parallel timelines are tracked per activity:

    * a **logic timeline** (``logic_es`` / ``logic_ef``) that ALWAYS uses the
      full planned duration from the later of the data date and predecessor
      logic (a finished activity contributes its actual finish). Successors
      are bound by this timeline in every mode, which is the precise meaning
      of "successors stay bound by full logic".
    * the **displayed** ``es`` / ``ef`` the activity itself reports, which is
      where the three modes diverge.

    Semantics (DD = ``data_date``; defaults to 0 when None so the pass
    reduces to planning - and with no actuals all three modes are identical
    to :func:`compute_cpm`):

    * **retained_logic** - finished activities pin to actuals; a started but
      unfinished activity shows its actual ES while its remaining work still
      waits for the later of DD and predecessor logic (``rem_start + rem``).
      Predecessor logic is fully retained, so this is the latest finish.
    * **progress_override** - a started activity's remaining work runs straight
      from DD (``DD + rem``), ignoring incomplete predecessor logic for its own
      finish. This is the earliest finish.
    * **actual_dates** - actual start / finish are honoured where present; an
      in-progress activity keeps its actual ES and runs its remaining work from
      DD (so it finishes no later than retained logic and no earlier than
      progress override). Successors stay bound by full logic.
    """
    cycle = network.detect_cycle()
    if cycle is not None:
        raise CycleError(cycle)
    order = _topological_order(network)
    dd = 0 if data_date is None else int(data_date)
    has_dd = data_date is not None

    durations: dict[Any, int] = {}
    es: dict[Any, int] = {}
    ef: dict[Any, int] = {}
    # Logic timeline - drives successors uniformly across all three modes.
    logic_es_map: dict[Any, int] = {}
    logic_ef_map: dict[Any, int] = {}

    for aid in order:
        a = network.get(aid)
        assert a is not None
        dur = max(0, int(a.duration))
        durations[aid] = dur
        p = progress.get(aid)

        # Lower bound from predecessor LOGIC dates (full-duration timeline).
        # Identical arithmetic to the planning forward pass, but reading the
        # logic timeline so overridden actuals never leak into successor logic.
        logic_candidates: list[int] = []
        for p_id, dep_type, lag in network.predecessors(aid):
            if p_id not in logic_es_map:
                continue
            logic_candidates.append(_forward_bound(dep_type, logic_es_map[p_id], logic_ef_map[p_id], int(lag), dur))
        pred_logic_es = max(logic_candidates) if logic_candidates else 0

        # Finished: pin to actuals in every mode; the logic timeline takes the
        # actual finish so downstream logic keys off when work really ended.
        if _is_finished(p):
            assert p is not None
            a_finish = p.actual_finish if p.actual_finish is not None else max(dd, pred_logic_es + dur)
            a_start = p.actual_start if p.actual_start is not None else (a_finish - dur)
            es[aid] = a_start
            ef[aid] = a_finish
            logic_es_map[aid] = a_start
            logic_ef_map[aid] = a_finish
            continue

        rem = _remaining_days(p, dur)
        started = _is_started(p)

        # Logic timeline for an unfinished activity: full duration from the
        # later of DD and predecessor logic (planning when no DD).
        logic_start = max(dd, pred_logic_es) if has_dd else pred_logic_es
        logic_es_map[aid] = logic_start
        logic_ef_map[aid] = logic_start + dur

        if not started:
            # Not started in any mode = planning placement on the logic timeline.
            es[aid] = logic_start
            ef[aid] = logic_start + dur
            continue

        a_start = p.actual_start if (p is not None and p.actual_start is not None) else dd

        if mode == "progress_override":
            # Own remaining work runs straight from the data date.
            es[aid] = a_start
            ef[aid] = (dd + rem) if has_dd else (a_start + dur)
        elif mode == "actual_dates":
            es[aid] = a_start
            if p is not None and p.actual_finish is not None:
                ef[aid] = p.actual_finish
            else:
                # Remaining from DD (between override and retained); successors
                # are unaffected because they read the logic timeline above.
                ef[aid] = (dd + rem) if has_dd else (a_start + dur)
        else:  # retained_logic (default)
            es[aid] = a_start
            # Remaining work waits for the later of DD and predecessor logic.
            ef[aid] = (logic_start + rem) if has_dd else (a_start + dur)

    return durations, es, ef


def _predecessor_should_block(dep_type: DepType) -> bool:
    """True iff an incomplete predecessor on this link blocks the successor's start.

    Start-controlling links (FS, SF) require the predecessor to finish before
    the successor may start, so an unfinished predecessor on such a link while
    the successor already has progress is genuinely out of sequence. SS / FF
    only relate starts / finishes and are not treated as start-blocking here.
    """
    return dep_type in ("FS", "SF")


def detect_out_of_sequence(
    network: TaskNetwork,
    data_date: int | None,
    progress: dict[Any, Progress],
) -> set[Any]:
    """Return the set of activities progressing out of sequence at the data date.

    An activity is out of sequence when it has progress (started or finished)
    while a predecessor that should block its start (FS / SF link) is not
    complete as of the data date. Pure - reads only ``progress`` + adjacency.
    """
    oos: set[Any] = set()
    for aid in network.ids():
        p = progress.get(aid)
        if not _is_started(p):
            continue
        for p_id, dep_type, _lag in network.predecessors(aid):
            if not _predecessor_should_block(dep_type):
                continue
            if not _is_finished(progress.get(p_id)):
                oos.add(aid)
                break
    return oos


def out_of_sequence_cpm(
    network: TaskNetwork,
    *,
    mode: OutOfSeqMode = "retained_logic",
    data_date: int | None = None,
    progress: dict[Any, Progress] | None = None,
) -> dict[Any, CPMResult]:
    """Full CPM (forward + backward + float) under an out-of-sequence ``mode``.

    Runs the mode-specific forward pass, then the UNCHANGED backward-pass and
    float arithmetic from :func:`compute_cpm` on top of it, so the four modes
    differ only in how progress + the data date reshape early dates. With
    ``data_date is None`` and empty ``progress`` the result is identical to
    :func:`compute_cpm`.
    """
    progress = progress or {}
    durations, es, ef = _oos_forward_pass(network, mode, data_date, progress)
    order = _topological_order(network)
    if not order:
        return {}

    # ── Per-island finish via union-find (mirrors compute_cpm) ──
    component_root: dict[Any, Any] = {aid: aid for aid in order}

    def _find(x: Any) -> Any:
        while component_root[x] != x:
            component_root[x] = component_root[component_root[x]]
            x = component_root[x]
        return x

    def _union(x: Any, y: Any) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            component_root[rx] = ry

    for aid in order:
        for s_id, _dep, _lag in network.successors(aid):
            _union(aid, s_id)

    component_finish: dict[Any, int] = {}
    for aid in order:
        root = _find(aid)
        if ef[aid] > component_finish.get(root, -1):
            component_finish[root] = ef[aid]

    # ── Backward pass (identical arithmetic to compute_cpm) ──
    lf: dict[Any, int] = {}
    ls: dict[Any, int] = {}
    for aid in reversed(order):
        dur = durations[aid]
        succ_candidates: list[int] = []
        for s_id, dep_type, lag in network.successors(aid):
            if s_id not in ls:
                continue
            lag = int(lag)
            if dep_type == "SS":
                succ_candidates.append(ls[s_id] - lag + dur)
            elif dep_type == "FF":
                succ_candidates.append(lf[s_id] - lag)
            elif dep_type == "SF":
                succ_candidates.append(lf[s_id] - lag + dur)
            else:  # FS (default)
                succ_candidates.append(ls[s_id] - lag)
        lf[aid] = min(succ_candidates) if succ_candidates else component_finish[_find(aid)]
        ls[aid] = lf[aid] - dur

    # ── Float + critical marking (identical arithmetic to compute_cpm) ──
    results: dict[Any, CPMResult] = {}
    for aid in order:
        total_float = ls[aid] - es[aid]
        dur_aid = durations[aid]
        slack_bounds: list[int] = []
        for s_id, dep_type, lag in network.successors(aid):
            if s_id not in es:
                continue
            lag = int(lag)
            if dep_type == "SS":
                slack_bounds.append((es[s_id] - lag + dur_aid) - ef[aid])
            elif dep_type == "FF":
                slack_bounds.append((ef[s_id] - lag) - ef[aid])
            elif dep_type == "SF":
                slack_bounds.append((ef[s_id] - lag + dur_aid) - ef[aid])
            else:  # FS (default)
                slack_bounds.append((es[s_id] - lag) - ef[aid])
        free_float = min(slack_bounds) if slack_bounds else component_finish[_find(aid)] - ef[aid]
        results[aid] = CPMResult(
            es=es[aid],
            ef=ef[aid],
            ls=ls[aid],
            lf=lf[aid],
            total_float=max(0, total_float),
            free_float=max(0, free_float),
            is_critical=(total_float <= 0),
        )
    return results


# ── Scheduling-quality findings log ──────────────────────────────────────────


@dataclass(frozen=True)
class QAFinding:
    """One scheduling-quality finding (a row in the QA log).

    Attributes:
        code: Machine-readable finding code (e.g. ``"OPEN_START"``).
        severity: One of :data:`SEVERITY_HIGH` / ``_MEDIUM`` / ``_LOW``.
        activity_id: The activity the finding is about.
        message: Human-readable one-line description.
    """

    code: str
    severity: int
    activity_id: Any
    message: str


@dataclass(frozen=True)
class QAOptions:
    """Inputs to :func:`scheduling_qa_log` beyond the network + results.

    Attributes:
        start_milestones: Activity ids that are legitimately open at the start
            (project start milestones) - suppresses OPEN_START.
        finish_milestones: Activity ids legitimately open at the finish -
            suppresses OPEN_FINISH.
        hard_constrained: Activity ids carrying a hard date constraint
            (e.g. Must-Finish-On). Reported HARD_CONSTRAINT for visibility.
        data_date: Data date for out-of-sequence detection (optional).
        progress: Per-activity progress for out-of-sequence detection.
        large_lag_threshold: Override for :data:`LARGE_LAG_THRESHOLD_DAYS`.
    """

    start_milestones: set[Any] = field(default_factory=set)
    finish_milestones: set[Any] = field(default_factory=set)
    hard_constrained: set[Any] = field(default_factory=set)
    data_date: int | None = None
    progress: dict[Any, Progress] = field(default_factory=dict)
    large_lag_threshold: int = LARGE_LAG_THRESHOLD_DAYS


def scheduling_qa_log(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
    options: QAOptions | None = None,
) -> list[QAFinding]:
    """Return scheduling-quality findings, sorted by (severity desc, id).

    Pure analysis of the network logic + ``options`` - never mutates either.
    Findings raised:

    * **OPEN_START** (medium) - no predecessors and not a start milestone.
    * **OPEN_FINISH** (medium) - no successors and not a finish milestone.
    * **HARD_CONSTRAINT** (low) - activity flagged hard-constrained.
    * **OUT_OF_SEQUENCE** (high) - progressed ahead of a blocking predecessor.
    * **LARGE_LAG** (low) - a link lag whose magnitude exceeds the threshold.
    * **NEGATIVE_LAG** (medium) - a negative lag (lead) on any link.

    The sort is ``(-severity, str(activity_id), code)`` so the log is stable
    and deterministic regardless of input activity / edge ordering.
    """
    opts = options or QAOptions()
    findings: list[QAFinding] = []

    oos = detect_out_of_sequence(network, opts.data_date, opts.progress)

    for aid in network.ids():
        preds = network.predecessors(aid)
        succs = network.successors(aid)

        if not preds and aid not in opts.start_milestones:
            findings.append(
                QAFinding(
                    code="OPEN_START",
                    severity=SEVERITY_MEDIUM,
                    activity_id=aid,
                    message=f"Activity {aid} has no predecessors and is not a start milestone (open start).",
                )
            )
        if not succs and aid not in opts.finish_milestones:
            findings.append(
                QAFinding(
                    code="OPEN_FINISH",
                    severity=SEVERITY_MEDIUM,
                    activity_id=aid,
                    message=f"Activity {aid} has no successors and is not a finish milestone (open finish).",
                )
            )
        if aid in opts.hard_constrained:
            findings.append(
                QAFinding(
                    code="HARD_CONSTRAINT",
                    severity=SEVERITY_LOW,
                    activity_id=aid,
                    message=f"Activity {aid} carries a hard date constraint that overrides network logic.",
                )
            )
        if aid in oos:
            findings.append(
                QAFinding(
                    code="OUT_OF_SEQUENCE",
                    severity=SEVERITY_HIGH,
                    activity_id=aid,
                    message=f"Activity {aid} has progress while a blocking predecessor is incomplete (out of sequence).",
                )
            )

        # Lag findings are attributed to the SUCCESSOR (the activity the link
        # constrains), one per offending incoming edge.
        for p_id, dep_type, lag in preds:
            lag = int(lag)
            if lag < 0:
                findings.append(
                    QAFinding(
                        code="NEGATIVE_LAG",
                        severity=SEVERITY_MEDIUM,
                        activity_id=aid,
                        message=f"Link {p_id} -> {aid} ({dep_type}) has a negative lag of {lag} days (lead).",
                    )
                )
            elif abs(lag) > opts.large_lag_threshold:
                findings.append(
                    QAFinding(
                        code="LARGE_LAG",
                        severity=SEVERITY_LOW,
                        activity_id=aid,
                        message=(
                            f"Link {p_id} -> {aid} ({dep_type}) has a large lag of {lag} days "
                            f"(threshold {opts.large_lag_threshold})."
                        ),
                    )
                )

    findings.sort(key=lambda f: (-f.severity, str(f.activity_id), f.code))
    return findings


# ── Critical-set selection (mode switch) ─────────────────────────────────────


def select_critical(
    results: dict[Any, CPMResult],
    mode: CriticalMode = "total_float",
    *,
    threshold: int = DEFAULT_CRITICAL_FLOAT_THRESHOLD,
    longest_path_ids: list[Any] | set[Any] | None = None,
) -> set[Any]:
    """Return the set of critical activity ids under ``mode``.

    * ``"total_float"`` - every activity with ``total_float <= threshold``.
      With the default ``threshold == 0`` this exactly reproduces
      :func:`compute_cpm`'s ``is_critical`` set.
    * ``"longest_path"`` - the activities on the Longest Path. ``longest_path_ids``
      must be supplied (compute it once via :func:`longest_path` and pass it
      in) so this helper stays a pure, network-free selector.
    """
    if mode == "longest_path":
        return set(longest_path_ids or ())
    return {aid for aid, r in results.items() if r.total_float <= threshold}


# ── Generated explain strings ────────────────────────────────────────────────


def why_critical(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
    durations: dict[Any, int],
    es: dict[Any, int],
    ef: dict[Any, int],
    activity_id: Any,
) -> str:
    """One-line, numbers-faithful explanation of an activity's criticality.

    Derived strictly from the float value and the driving edge, so the text
    can never contradict the computed schedule. Non-critical activities get a
    float statement; critical activities additionally name the driving logic
    link (or "project start" for an open start).
    """
    r = results.get(activity_id)
    if r is None:
        return f"Activity {activity_id} is not in the schedule."
    if not r.is_critical:
        return (
            f"Activity {activity_id} is not critical: it has {r.total_float} day(s) of total float "
            f"(early start day {r.es}, late start day {r.ls})."
        )
    edge = driving_predecessor(network, es, ef, durations, activity_id)
    if edge is None:
        return (
            f"Activity {activity_id} is critical (total float {r.total_float}): it is driven from "
            f"project start with no float, finishing on day {r.ef}."
        )
    p_id, dep_type, lag = edge
    lag_txt = "" if lag == 0 else f" with a {lag}-day lag"
    return (
        f"Activity {activity_id} is critical (total float {r.total_float}): its early start (day {r.es}) "
        f"is driven by {p_id} through a {dep_type} link{lag_txt}."
    )


def float_explanation(
    network: TaskNetwork,
    results: dict[Any, CPMResult],
    durations: dict[Any, int],
    es: dict[Any, int],
    ef: dict[Any, int],
    activity_id: Any,
) -> str:
    """One-line explanation of an activity's total + free float.

    States total float, free float, and (when the activity has any total
    float) which successor logic the float is measured against, all read from
    the computed numbers so the prose tracks the schedule exactly.
    """
    r = results.get(activity_id)
    if r is None:
        return f"Activity {activity_id} is not in the schedule."
    if r.total_float <= 0:
        return (
            f"Activity {activity_id} has no total float: any slip from its early start (day {r.es}) "
            f"delays the project finish."
        )
    return (
        f"Activity {activity_id} can slip up to {r.total_float} day(s) in total "
        f"(free float {r.free_float} day(s)) from its early start (day {r.es}) "
        f"before affecting the project finish; late finish is day {r.lf}."
    )


# ════════════════════════════════════════════════════════════════════════════
# Working-day (calendar-aware) offset arithmetic - additive helper
# ────────────────────────────────────────────────────────────────────────────
# The CPM passes above run entirely in plain calendar-day offsets: a duration of
# ``d`` always advances an offset by exactly ``d`` (``ef = es + dur``). That is
# correct when every day is a working day, but a follow-up was noted to let the
# engine honour per-activity working calendars (skip weekends / holidays).
#
# Retrofitting that into ``compute_cpm`` is NOT a small change: the forward pass,
# backward pass, ``_forward_bound``, the free-float math, all three
# out-of-sequence forward passes and every claims-grade post-processor that
# reconstructs dates rely on the exact ``ef == es + dur`` / ``es == ef - dur``
# identity (and on ``+ lag - dur`` / ``- lag + dur`` link conversions). Honouring
# calendars means replacing every one of those with a calendar-aware inverse,
# which would destabilise the green claims-grade engine and its tests.
#
# So the calendar support starts here as a small, fully-tested, behaviour-neutral
# PRIMITIVE keyed by the same integer day-offsets the engine speaks. Nothing
# above calls it yet; a future integration can adopt it to translate a
# working-day ``duration`` into an elapsed-day finish offset and back. With the
# trivial seven-working-day calendar it reproduces plain offset arithmetic
# exactly, so adopting it is a no-op for projects without a real calendar.
#
# The inclusivity convention is identical to ``app/core/cpm.py`` and
# ``app/modules/schedule/progress_math.py`` so all three agree:
# ``working_days_between`` counts working days strictly AFTER ``start`` up to and
# INCLUDING ``end`` (exclusive start, inclusive end).
# ════════════════════════════════════════════════════════════════════════════


#: Weekday indices that are working days under the default calendar (Mon-Fri).
#: ``0 == Monday`` .. ``6 == Sunday`` (matches :meth:`datetime.date.weekday`).
DEFAULT_WORK_WEEKDAYS: frozenset[int] = frozenset({0, 1, 2, 3, 4})


@dataclass(frozen=True)
class OffsetCalendar:
    """A pure working-day calendar that speaks the engine's integer day offsets.

    The claims-grade CPM passes carry every date as an integer offset (in
    elapsed days) from a single project epoch. This helper maps a working-day
    *duration* onto those offsets so non-working days (weekends + holidays) are
    skipped, without changing how the passes store or compare offsets.

    It is intentionally NOT the ISO-string ``WorkCalendar`` in
    ``app/modules/schedule/progress_math.py``: that one is keyed by
    ``YYYY-MM-DD`` strings, whereas the CPM engine never materialises calendar
    dates - it works in offsets relative to ``epoch``. The two share the same
    inclusivity convention so a value computed by one can be reasoned about with
    the other once an epoch is fixed.

    Attributes:
        epoch: The calendar date that offset ``0`` maps to. Offsets are elapsed
            days from this date; ``epoch`` itself need not be a working day.
        work_weekdays: Weekday indices (``0=Mon`` .. ``6=Sun``) that are working
            days. Defaults to Monday-Friday.
        holidays: ``YYYY-MM-DD`` strings that are NOT working days even when they
            fall on a working weekday.

    A calendar whose ``work_weekdays`` covers all seven days and that has no
    holidays makes every method reduce to plain integer arithmetic
    (``working_finish_offset(es, d) == es + d`` and so on), so an adopter can
    opt out of calendar effects simply by handing it such a calendar - the
    engine's current behaviour is recovered byte for byte. :data:`ALL_DAYS_CALENDAR`
    is exactly that calendar, pre-built.
    """

    epoch: date = date(2000, 1, 3)  # a Monday, so default offset 0 is a working day
    work_weekdays: frozenset[int] = DEFAULT_WORK_WEEKDAYS
    holidays: frozenset[str] = frozenset()

    def _date_at(self, offset: int) -> date:
        """Calendar date for an integer day ``offset`` from :attr:`epoch`."""
        return self.epoch + timedelta(days=int(offset))

    def _is_working_date(self, d: date) -> bool:
        return d.weekday() in self.work_weekdays and d.isoformat() not in self.holidays

    def is_working_offset(self, offset: int) -> bool:
        """Return ``True`` when the day at ``offset`` is a working day."""
        return self._is_working_date(self._date_at(offset))

    def working_finish_offset(self, start_offset: int, duration: int) -> int:
        """Finish offset that is ``duration`` working days after ``start_offset``.

        The calendar-aware replacement for ``start_offset + duration`` (the
        ``EF = ES + dur`` identity the plain passes use). Counting begins the day
        AFTER ``start_offset`` - consistent with the exclusive-start convention -
        so a ``duration`` of ``0`` returns ``start_offset`` unchanged (a
        milestone keeps its offset). For ``duration > 0`` the returned offset is
        always a working day. ``duration`` is clamped to ``max(0, int(...))`` so
        a negative duration behaves like a milestone, matching the engine's
        ``max(0, int(a.duration))`` clamp.
        """
        dur = max(0, int(duration))
        if dur == 0:
            return int(start_offset)
        current = int(start_offset)
        added = 0
        while added < dur:
            current += 1
            if self.is_working_offset(current):
                added += 1
        return current

    def working_start_offset(self, finish_offset: int, duration: int) -> int:
        """Start offset that is ``duration`` working days before ``finish_offset``.

        The calendar-aware replacement for ``finish_offset - duration`` (the
        ``LS = LF - dur`` identity the backward pass uses) and the exact inverse
        of :meth:`working_finish_offset`: for any working ``finish_offset``,
        ``working_finish_offset(working_start_offset(f, d), d) == f``. Counting
        steps backward from the day BEFORE ``finish_offset``; ``duration <= 0``
        returns ``finish_offset`` unchanged.
        """
        dur = max(0, int(duration))
        if dur == 0:
            return int(finish_offset)
        current = int(finish_offset)
        removed = 0
        while removed < dur:
            current -= 1
            if self.is_working_offset(current):
                removed += 1
        return current

    def working_days_between(self, start_offset: int, end_offset: int) -> int:
        """Count working days in ``(start_offset, end_offset]``.

        Exclusive of ``start_offset``, inclusive of ``end_offset`` - the same
        convention as ``app/core/cpm.py`` and ``progress_math.WorkCalendar``.
        Returns ``0`` when ``end_offset <= start_offset`` (an empty or inverted
        span contributes nothing). This is the working-day analogue of the raw
        offset gap ``end_offset - start_offset`` and round-trips a finish offset:
        ``working_finish_offset(s, working_days_between(s, f)) == f`` whenever
        ``f`` is a working offset on or after ``s``.
        """
        start = int(start_offset)
        end = int(end_offset)
        if end <= start:
            return 0
        count = 0
        current = start
        while current < end:
            current += 1
            if self.is_working_offset(current):
                count += 1
        return count

    def nth_working_day(self, project_start: date, index: int) -> date:
        """Calendar date of the 0-based working-day ``index`` from a project start.

        This is how a CPM early/late-start index (which counts working days,
        not calendar days) becomes a real date on the wall calendar. Index 0 is
        the first working day on or after ``project_start``; each later index
        advances by one working day, skipping non-working weekdays and holidays.
        A negative index raises ``ValueError`` because there is no working day
        before the project starts.
        """
        if index < 0:
            raise ValueError(
                f"Working-day index must be 0 or greater, got {index}. "
                "An activity cannot start before the project start date."
            )
        current = project_start
        while not self._is_working_date(current):
            current += timedelta(days=1)
        remaining = index
        while remaining > 0:
            current += timedelta(days=1)
            if self._is_working_date(current):
                remaining -= 1
        return current


#: A calendar where every day is a working day and there are no holidays. Every
#: :class:`OffsetCalendar` method on it equals the plain offset arithmetic the
#: CPM passes already use, so it is the explicit "no calendar effects" calendar
#: an adopter can pass to recover today's behaviour exactly.
ALL_DAYS_CALENDAR = OffsetCalendar(work_weekdays=frozenset(range(7)))

#: Default working-day calendar: Monday-Friday, no holidays, offset 0 on a Monday.
DEFAULT_OFFSET_CALENDAR = OffsetCalendar()


def offset_calendar_from_work_days(
    work_days: list[int] | None = None,
    holidays: list[str] | None = None,
    *,
    epoch: date = date(2000, 1, 3),
) -> OffsetCalendar:
    """Build an :class:`OffsetCalendar` from a project's stored calendar fields.

    This is the bridge from the persisted ``Calendar`` model (which keeps
    ``work_days`` as weekday integers and ``holidays`` as ISO date strings) to
    the pure engine, so every country can drive the schedule with its own work
    week and public holidays instead of a hidden assumption.

    Args:
        work_days: Weekday numbers that are working days, Monday=0 .. Sunday=6.
            ``None`` or an empty list falls back to Monday-Friday, the worldwide
            default work week. A weekday outside 0..6 raises ``ValueError`` that
            names the bad value.
        holidays: ISO 8601 (YYYY-MM-DD) date strings that are never working days
            even when they fall on a working weekday. Each entry is validated;
            anything that is not a real ISO date raises ``ValueError`` naming the
            offending entry so the planner can correct it. Locale day/month
            orders (for example DD/MM/YYYY) are rejected on purpose.
        epoch: Calendar date that engine offset 0 maps to. Defaults to a Monday.

    Returns:
        An :class:`OffsetCalendar` ready to project working-day indices onto real
        dates via :func:`to_calendar_dates`.
    """
    if not work_days:
        weekdays = DEFAULT_WORK_WEEKDAYS
    else:
        cleaned: set[int] = set()
        for wd in work_days:
            wd_int = int(wd)
            if wd_int < 0 or wd_int > 6:
                raise ValueError(
                    f"Work day '{wd}' is not a valid weekday. Use whole numbers from 0 (Monday) to 6 (Sunday)."
                )
            cleaned.add(wd_int)
        weekdays = frozenset(cleaned)

    normalised_holidays: set[str] = set()
    for h in holidays or []:
        try:
            parsed = date.fromisoformat(str(h))
        except ValueError as exc:
            raise ValueError(
                f"Holiday '{h}' is not a valid ISO 8601 date. Use the YYYY-MM-DD format, for example 2026-12-25."
            ) from exc
        normalised_holidays.add(parsed.isoformat())

    return OffsetCalendar(epoch=epoch, work_weekdays=weekdays, holidays=frozenset(normalised_holidays))


@dataclass(frozen=True)
class CalendarDates:
    """A CPM activity's four key dates as ISO 8601 (YYYY-MM-DD) strings.

    The CPM passes work in working-day indices; this projects them onto the wall
    calendar so users see plain dates. ``early_finish`` / ``late_finish`` are the
    date of the LAST working day the activity occupies (its finish day), so a
    one-day activity has ``early_start == early_finish`` and a zero-day milestone
    reports the same date for start and finish. Dates are always ISO 8601 and
    never a locale day/month order.
    """

    early_start: str
    early_finish: str
    late_start: str
    late_finish: str


def to_calendar_dates(
    results: dict[Any, CPMResult],
    calendar: OffsetCalendar,
    project_start: date,
) -> dict[Any, CalendarDates]:
    """Project a :func:`compute_cpm` result onto real ISO 8601 dates.

    Each activity's early/late start and finish working-day indices are mapped
    through ``calendar`` so weekends and holidays are skipped. ``project_start``
    is the calendar date working-day index 0 lands on (the first working day on
    or after it). Any index that would fall before the project start (possible
    only with a negative lag / lead) is clamped to the project start for display;
    :func:`validate_network` reports that situation separately so it is never
    silently hidden.
    """
    out: dict[Any, CalendarDates] = {}
    for aid, r in results.items():
        es_idx = max(0, r.es)
        # Finish day = last working day the activity occupies. EF is an
        # exclusive-end index, so the last occupied day is EF - 1; a milestone
        # (EF == ES) reports its start day.
        ef_idx = max(0, max(r.es, r.ef - 1))
        ls_idx = max(0, r.ls)
        lf_idx = max(0, max(r.ls, r.lf - 1))
        out[aid] = CalendarDates(
            early_start=calendar.nth_working_day(project_start, es_idx).isoformat(),
            early_finish=calendar.nth_working_day(project_start, ef_idx).isoformat(),
            late_start=calendar.nth_working_day(project_start, ls_idx).isoformat(),
            late_finish=calendar.nth_working_day(project_start, lf_idx).isoformat(),
        )
    return out


# ════════════════════════════════════════════════════════════════════════════
# Conservative network validation (plain-language, pre-computation)
# ────────────────────────────────────────────────────────────────────────────
# The CPM engine is deliberately forgiving: it drops self-loops and links to
# unknown activities, and clamps negative durations to zero, so a partial
# network never crashes the passes. That forgiveness is right for computation
# but wrong for the user, who needs to be told what is off and how to fix it.
# :func:`validate_network` is the pure, side-effect-free counterpart: it never
# mutates or raises, it just reports the real problems a planner hits, in plain
# language, so the UI can surface them before or alongside a schedule run.
# ════════════════════════════════════════════════════════════════════════════

#: Issue severities returned by :func:`validate_network`. ``error`` means the
#: schedule cannot be trusted until it is fixed; ``warning`` means the run will
#: proceed but the result may surprise the planner; ``info`` is a neutral note.
ISSUE_ERROR: str = "error"
ISSUE_WARNING: str = "warning"
ISSUE_INFO: str = "info"

#: Sort weight per severity (higher shows first) for a stable, readable log.
_ISSUE_SEVERITY_ORDER: dict[str, int] = {ISSUE_ERROR: 3, ISSUE_WARNING: 2, ISSUE_INFO: 1}


@dataclass(frozen=True)
class NetworkIssue:
    """One problem found in an activity network by :func:`validate_network`.

    Attributes:
        code: Stable machine-readable code (for example ``"SELF_DEPENDENCY"``).
        severity: :data:`ISSUE_ERROR`, :data:`ISSUE_WARNING` or :data:`ISSUE_INFO`.
        activity_id: The activity the issue is about, or ``None`` for a
            whole-schedule issue such as an empty network.
        message: A plain-language, self-contained sentence that also says what to
            do next.
    """

    code: str
    severity: str
    activity_id: Any | None
    message: str


def validate_network(activities: list[Activity]) -> list[NetworkIssue]:
    """Check an activity network for the real problems a scheduler hits.

    Pure and total: it never mutates ``activities`` and never raises. It returns
    a deterministic, severity-sorted list of :class:`NetworkIssue` so the UI can
    show a clear "fix these first" list. Checks performed:

    * ``EMPTY_NETWORK`` (info) - no activities to schedule yet.
    * ``DUPLICATE_ACTIVITY_ID`` (error) - the same id used twice; only the first
      is scheduled and the rest are ignored.
    * ``NEGATIVE_DURATION`` (warning) - a duration below zero is treated as a
      zero-day milestone.
    * ``ZERO_DURATION`` (info) - a zero-day activity behaves as a milestone.
    * ``SELF_DEPENDENCY`` (error) - an activity linked to itself.
    * ``MISSING_PREDECESSOR`` (error) - a link to an activity not in the network.
    * ``UNKNOWN_DEPENDENCY_TYPE`` (error) - a link type other than FS/SS/FF/SF.
    * ``CIRCULAR_DEPENDENCY`` (error) - activities that form a loop that can
      never finish; the loop is spelled out in the message.
    * ``STARTS_BEFORE_PROJECT_START`` (warning) - a negative lag (lead) pulls an
      early start before day 0 of the project.
    """
    issues: list[NetworkIssue] = []

    if not activities:
        return [
            NetworkIssue(
                code="EMPTY_NETWORK",
                severity=ISSUE_INFO,
                activity_id=None,
                message="The schedule has no activities yet. Add at least one activity to calculate dates.",
            )
        ]

    seen_ids: set[Any] = set()
    known_ids: set[Any] = set()
    for a in activities:
        known_ids.add(a.id)

    for a in activities:
        if a.id in seen_ids:
            issues.append(
                NetworkIssue(
                    code="DUPLICATE_ACTIVITY_ID",
                    severity=ISSUE_ERROR,
                    activity_id=a.id,
                    message=(
                        f"Activity id '{a.id}' is used more than once. Give each activity a unique id; "
                        "only the first one with this id is scheduled and the others are ignored."
                    ),
                )
            )
            continue
        seen_ids.add(a.id)

        dur = int(a.duration)
        if dur < 0:
            issues.append(
                NetworkIssue(
                    code="NEGATIVE_DURATION",
                    severity=ISSUE_WARNING,
                    activity_id=a.id,
                    message=(
                        f"Activity '{a.id}' has a negative duration of {dur} working days and will be "
                        "treated as a 0-day milestone. Set a duration of 0 or more working days."
                    ),
                )
            )
        elif dur == 0:
            issues.append(
                NetworkIssue(
                    code="ZERO_DURATION",
                    severity=ISSUE_INFO,
                    activity_id=a.id,
                    message=(
                        f"Activity '{a.id}' has a duration of 0 working days, so it is treated as a "
                        "milestone (a point in time with no work). Give it a duration if that is not intended."
                    ),
                )
            )

        for p_id, dep_type, _lag in a.predecessors:
            if p_id == a.id:
                issues.append(
                    NetworkIssue(
                        code="SELF_DEPENDENCY",
                        severity=ISSUE_ERROR,
                        activity_id=a.id,
                        message=(
                            f"Activity '{a.id}' depends on itself. Remove the self-dependency; an activity "
                            "cannot wait for its own completion."
                        ),
                    )
                )
            elif p_id not in known_ids:
                issues.append(
                    NetworkIssue(
                        code="MISSING_PREDECESSOR",
                        severity=ISSUE_ERROR,
                        activity_id=a.id,
                        message=(
                            f"Activity '{a.id}' depends on '{p_id}', which is not in the schedule. Add that "
                            "activity or remove the link."
                        ),
                    )
                )
            if dep_type not in VALID_DEP_TYPES:
                issues.append(
                    NetworkIssue(
                        code="UNKNOWN_DEPENDENCY_TYPE",
                        severity=ISSUE_ERROR,
                        activity_id=a.id,
                        message=(
                            f"The link from '{p_id}' to '{a.id}' uses an unknown dependency type "
                            f"'{dep_type}'. Use FS, SS, FF or SF."
                        ),
                    )
                )

    # Loop detection and negative-early-start detection both need the built
    # network. TaskNetwork drops self-loops and unknown links, so the cycle
    # check here is about genuine multi-activity loops among valid links.
    network = TaskNetwork(activities)
    cycle = network.detect_cycle()
    if cycle is not None:
        loop_text = " -> ".join(str(x) for x in cycle)
        issues.append(
            NetworkIssue(
                code="CIRCULAR_DEPENDENCY",
                severity=ISSUE_ERROR,
                activity_id=cycle[0] if cycle else None,
                message=(
                    f"These activities form a loop that can never finish: {loop_text}. Break the loop by "
                    "removing one of the links."
                ),
            )
        )
    else:
        # Only meaningful when the network is acyclic (otherwise compute_cpm
        # would raise). A negative early start means a lead (negative lag)
        # pulled an activity before the project start.
        results = compute_cpm(network)
        for aid, r in results.items():
            if r.es < 0:
                issues.append(
                    NetworkIssue(
                        code="STARTS_BEFORE_PROJECT_START",
                        severity=ISSUE_WARNING,
                        activity_id=aid,
                        message=(
                            f"Activity '{aid}' is scheduled to start {-r.es} working day(s) before the "
                            "project start because of a negative lag (lead). Reduce the lead or move the "
                            "project start earlier."
                        ),
                    )
                )

    issues.sort(key=lambda i: (-_ISSUE_SEVERITY_ORDER.get(i.severity, 0), str(i.activity_id), i.code))
    return issues
