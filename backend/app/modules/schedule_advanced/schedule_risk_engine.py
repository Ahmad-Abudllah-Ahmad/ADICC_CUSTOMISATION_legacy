# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure, dependency-free Monte Carlo schedule-risk engine.

This module is the schedule-side counterpart to
:mod:`app.modules.boq.cost_risk_engine`. Like that engine (and like
:mod:`app.modules.schedule_advanced.cpm`) it imports nothing from ``app``:
only the standard library, the proven numeric primitives already shipped in
``cost_risk_engine`` (percentiles, correlation copula, histogram / CDF builders,
convergence test, rank-correlation, three-point sampling, bound resolution) and
the activity-network data classes from ``cpm``. That keeps it unit-testable on
any interpreter and re-usable by "what-if" tooling.

What it does
------------
Runs a Monte Carlo over a CPM activity network whose *topology is fixed* but
whose activity *durations are uncertain*. Each iteration re-runs the critical
path arithmetic on a fresh duration vector and records the project finish and
which activities were on the critical path that iteration. From thousands of
iterations it produces:

* the finish-date distribution (P5..P95, mean, std, a probability histogram and
  a cumulative S-curve) - the schedule analogue of the cost S-curve;
* a **criticality index** per activity (the fraction of iterations in which the
  activity sat on the critical path) and a **cruciality** ranking (criticality
  weighted by the activity's rank-correlation to the finish), so path-switching
  on near-parallel chains is captured rather than hidden by a single
  deterministic critical path;
* a duration-sensitivity **tornado** (Spearman rank correlation of each
  activity's sampled duration to the finish);
* **schedule contingency** at an explicit target confidence (P80 by default)
  over the deterministic finish;
* discrete **risk events** (a probability times a three-point schedule impact,
  optionally with a cost impact) applied either in *series* (added to every
  affected activity) or in *parallel* (added once to the driving affected
  activity);
* an optional **Joint Confidence Level (JCL)**: when cost inputs are supplied,
  the fraction of iterations finishing on-time *and* on-budget, with the cost
  driven by the *same* correlation factor so schedule and cost overruns move
  together - exactly the joint cost/schedule confidence a programme office
  reports.

Performance
-----------
The expensive part of a naive implementation is rebuilding the network and
re-detecting cycles every iteration. We do the structural work ONCE: build the
:class:`~cpm.TaskNetwork`, detect cycles, compute the topological order, the
predecessor / successor adjacency and the weakly-connected components. Each
iteration then calls a lean :func:`cpm_pass` that replays only the forward /
backward *arithmetic* of :func:`cpm.compute_cpm` on the new durations. The CPM
formulas are replicated here verbatim (and cited) rather than calling
``compute_cpm`` so we never pay for re-parsing the topology.

Reproducibility
---------------
A fixed ``seed`` makes a run bit-for-bit repeatable; when no seed is given one
is derived deterministically from the inputs so repeated calls still agree.

Everything is plain ``int`` / ``float`` in and out. Durations are work-day
integers in, finish values are returned as floats (sampled durations are
continuous before the per-iteration CPM rounds them).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

# Reuse the proven numeric core from the cost engine verbatim. These helpers are
# already ``app``-free and unit-tested; re-implementing them here would only risk
# drift. The ``_shared/montecarlo.py`` extraction is deferred to a later wave.
from app.modules.boq.cost_risk_engine import (
    PERT_LAMBDA,
    CdfPoint,
    HistBin,
    _apply_one_factor_correlation,
    _bounds_for,
    _build_cdf,
    _build_histogram,
    _convergence,
    _percentile,
    _sample,
    _spearman,
)
from app.modules.schedule_advanced.cpm import (
    Activity,
    CycleError,
    TaskNetwork,
)

__all__ = [
    "ActivityDurationInput",
    "RiskEvent",
    "CostInputs",
    "CriticalityStat",
    "ScheduleDriverStat",
    "ScatterPoint",
    "ScheduleRiskResult",
    "simulate_schedule",
    "cpm_pass",
    "DEFAULT_ITERATIONS",
    "MAX_ITERATIONS",
    "DEFAULT_CORRELATION",
    "DEFAULT_OPTIMISTIC_PCT",
    "DEFAULT_PESSIMISTIC_PCT",
]

DEFAULT_ITERATIONS = 5000
MAX_ITERATIONS = 20000
# A modest systemic correlation between activity durations: the same drivers
# (weather, labour availability, design churn) tend to stretch many activities
# together. 0 reproduces a fully independent model.
DEFAULT_CORRELATION = 0.2
_MAX_CORRELATION = 0.95

# Default optimistic / pessimistic band, as a percent of the base duration, used
# when an activity has no explicit three-point estimate. Schedules are typically
# more right-skewed than costs (things slip more than they speed up), so the
# pessimistic default is wider than the optimistic one.
DEFAULT_OPTIMISTIC_PCT = 10.0
DEFAULT_PESSIMISTIC_PCT = 30.0


# ── Inputs ───────────────────────────────────────────────────────────────────


@dataclass
class ActivityDurationInput:
    """Per-activity duration uncertainty.

    ``activity_id`` must match an :class:`~cpm.Activity` id in the network.
    ``base`` is the deterministic (most-likely) duration in work days. When an
    explicit three-point estimate (``low``/``mode``/``high``) is supplied it is
    used verbatim; otherwise a band is derived from ``base`` and the global
    optimistic / pessimistic percentages passed to :func:`simulate_schedule`.

    Supported ``distribution`` values:

    ``"pert"`` (default), ``"triangular"``, ``"uniform"`` - delegated to the
    cost engine's three-point sampler; ``"lognormal"`` - right-skewed, peaked at
    the mode (good for "usually on time, occasionally a long tail"); and
    ``"normal"`` - symmetric, clamped to ``[low, high]``.
    """

    activity_id: Any
    base: float
    low: float | None = None
    mode: float | None = None
    high: float | None = None
    distribution: str = "pert"


@dataclass
class RiskEvent:
    """A discrete schedule (and optional cost) risk event.

    The event *occurs* in an iteration with probability ``probability``. When it
    occurs it adds a sampled three-point ``(impact_low, impact_mode,
    impact_high)`` number of work days to the affected activities, and (if
    cost-aware) a sampled three-point cost impact to that iteration's cost.

    ``application_mode``:

    * ``"series"`` - the delay hits every affected activity independently (e.g.
      a supplier strike that stalls each task that needs that supplier). The
      impact is added to *each* affected activity's duration that iteration.
    * ``"parallel"`` - the delay is a single shared disruption felt once on the
      governing path (e.g. a single permit hold). The impact is added once, to
      whichever affected activity is currently the most schedule-driving.
    """

    event_id: Any
    probability: float
    impact_low: float
    impact_mode: float
    impact_high: float
    affected_activity_ids: list[Any] = field(default_factory=list)
    application_mode: str = "series"  # "series" | "parallel"
    distribution: str = "pert"
    cost_impact_low: float = 0.0
    cost_impact_mode: float = 0.0
    cost_impact_high: float = 0.0


@dataclass
class CostInputs:
    """Cost side of a Joint Confidence Level run.

    ``base_cost`` is the deterministic project cost. Cost uncertainty is modelled
    as a single three-point band around the base (the line-item decomposition
    lives in the cost engine; here we only need the joint distribution). The cost
    draw shares the schedule's correlation driver so cost and schedule overruns
    move together. ``cost_target`` is the budget the JCL is measured against.
    """

    base_cost: float
    cost_low: float | None = None
    cost_mode: float | None = None
    cost_high: float | None = None
    distribution: str = "pert"
    cost_target: float | None = None
    optimistic_pct: float = 15.0
    pessimistic_pct: float = 25.0


# ── Outputs ──────────────────────────────────────────────────────────────────


@dataclass
class CriticalityStat:
    """How often an activity drives the schedule, and how strongly."""

    activity_id: Any
    criticality_index: float  # fraction of iterations on the critical path, 0..1
    cruciality: float  # criticality_index * |Spearman(duration, finish)|
    duration_sensitivity: float  # Spearman(duration, finish), -1..1
    mean_duration: float


@dataclass
class ScheduleDriverStat:
    """A tornado entry: an activity's rank correlation to the finish."""

    activity_id: Any
    rank_correlation: float  # Spearman rho of this activity's duration vs finish
    swing_low: float  # P10(duration) - mean(duration), <= 0
    swing_high: float  # P90(duration) - mean(duration), >= 0


@dataclass
class ScatterPoint:
    finish: float
    cost: float


@dataclass
class JointConfidenceResult:
    """Joint cost/schedule confidence summary."""

    target_finish: float
    target_cost: float
    jcl: float  # P(finish <= target AND cost <= target), 0..1
    prob_on_time: float  # P(finish <= target), 0..1
    prob_on_budget: float  # P(cost <= target), 0..1
    cost_mean: float
    cost_percentiles: dict[str, float]  # p5..p95
    correlation: float  # Pearson(finish, cost) actually realised
    scatter: list[ScatterPoint] = field(default_factory=list)


@dataclass
class ScheduleRiskResult:
    iterations: int
    deterministic_finish: float  # finish from the base/most-likely durations
    mean: float
    std_dev: float
    cv_pct: float  # coefficient of variation = std/mean * 100
    percentiles: dict[str, float]  # p5,p10,p25,p50,p75,p80,p90,p95
    contingency: float  # P(target) - deterministic_finish
    contingency_pct: float  # contingency / deterministic_finish * 100
    recommended_finish: float  # P(target)
    target_confidence: int  # e.g. 80 -> finish at the 80th percentile
    prob_within_deterministic: float  # P(finish <= deterministic) * 100
    correlation: float
    seed: int
    convergence_status: str  # "converged" | "marginal" | "insufficient"
    convergence_margin_pct: float
    histogram: list[HistBin] = field(default_factory=list)
    cdf: list[CdfPoint] = field(default_factory=list)
    criticality: list[CriticalityStat] = field(default_factory=list)
    drivers: list[ScheduleDriverStat] = field(default_factory=list)
    joint_confidence: JointConfidenceResult | None = None


# ── Local distribution quantiles (for Latin Hypercube inversion) ─────────────


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation).

    Accurate to ~1e-9 over the open interval (0, 1) - far better than the
    Monte-Carlo noise floor. Used to turn a stratified uniform into a normal
    quantile for Latin-Hypercube sampling of the normal and lognormal
    distributions. ``p`` is clamped just inside (0, 1) to keep the tails finite.
    """
    if p <= 0.0:
        p = 1e-12
    elif p >= 1.0:
        p = 1.0 - 1e-12
    # Coefficients for the central and tail regions.
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def _quantile(u: float, low: float, mode: float, high: float, dist: str) -> float:
    """Map a uniform ``u`` in [0, 1] to a sample of ``dist`` bounded sensibly.

    The triangular / pert / uniform branches use closed-form inverse CDFs so
    Latin-Hypercube stratification is exact. ``lognormal`` and ``normal`` are
    local extensions (the cost engine does not offer them):

    * ``normal`` - centred at ``mode`` with sigma inferred from the band
      (``(high - low) / 6`` so the band is ~+/-3 sigma), then clamped to
      ``[low, high]``.
    * ``lognormal`` - right-skewed, peaked at ``mode``. Drawn in log space around
      ``ln(mode)`` with a log-sigma inferred from the band, then clamped to
      ``[low, high]`` so it never undershoots the optimistic bound.
    """
    if high <= low:
        return mode
    u = min(max(u, 0.0), 1.0)
    if dist == "uniform":
        return low + u * (high - low)
    if dist == "triangular":
        span = high - low
        c = (mode - low) / span  # mode position in [0, 1]
        if u < c:
            return low + math.sqrt(u * span * (mode - low))
        return high - math.sqrt((1.0 - u) * span * (high - mode))
    if dist == "normal":
        sigma = (high - low) / 6.0
        if sigma <= 0.0:
            return mode
        val = mode + sigma * _norm_ppf(u)
        return min(max(val, low), high)
    if dist == "lognormal":
        # Peak (mode) of a lognormal is exp(mu - sigma^2); solving exactly for
        # (mu, sigma) from a three-point band is over-determined, so we anchor
        # the median at the mode (mu = ln(mode)) and size the log-sigma from the
        # band's right tail, which dominates a right-skewed schedule. This keeps
        # the draw peaked near the mode with a fat upper tail, then clamps.
        m = mode if mode > 0 else (low + high) / 2.0
        if m <= 0:
            return min(max(low + u * (high - low), low), high)
        mu = math.log(m)
        upper = high if high > m else m * 1.5
        # ln(upper) - mu spans ~3 log-sigma on the optimistic-to-pessimistic band.
        sigma = max((math.log(upper) - mu) / 3.0, 1e-6)
        val = math.exp(mu + sigma * _norm_ppf(u))
        return min(max(val, low), high)
    # default: Beta-PERT via the inverse regularised incomplete beta.
    span = high - low
    alpha = 1.0 + PERT_LAMBDA * (mode - low) / span
    beta = 1.0 + PERT_LAMBDA * (high - mode) / span
    return low + span * _beta_ppf(u, alpha, beta)


def _betacf(x: float, a: float, b: float) -> float:
    """Continued-fraction expansion for the incomplete beta (Numerical Recipes)."""
    max_it = 200
    eps = 3.0e-12
    fpmin = 1.0e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(x, a, b) / a
    return 1.0 - bt * _betacf(1.0 - x, b, a) / b


def _beta_ppf(u: float, a: float, b: float) -> float:
    """Inverse beta CDF by bisection on :func:`_betai`.

    Bisection is plenty fast for the modest precision we need (it converges to
    ~1e-10 in ~40 steps) and is dependency-free, unlike ``scipy.special``.
    """
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _betai(mid, a, b) < u:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _latin_hypercube(rng: random.Random, n: int, low: float, mode: float, high: float, dist: str) -> list[float]:
    """One Latin-Hypercube-stratified sample column of length ``n``.

    Partition [0, 1] into ``n`` equal strata, draw one uniform inside each, map
    it through the distribution's quantile, then shuffle so the column carries no
    artificial ordering before correlation reordering. Stratification slashes the
    sampling variance versus naive Monte Carlo for the same iteration count.
    """
    if high <= low:
        return [mode] * n
    out = [0.0] * n
    inv_n = 1.0 / n
    for i in range(n):
        u = (i + rng.random()) * inv_n
        out[i] = _quantile(u, low, mode, high, dist)
    rng.shuffle(out)
    return out


def _latin_hypercube_uniform(rng: random.Random, n: int) -> list[float]:
    """A shuffled Latin-Hypercube column of plain uniforms in [0, 1).

    Used for event hit/miss draws and event-impact magnitudes so those are
    stratified too rather than clumping.
    """
    out = [(i + rng.random()) / n for i in range(n)]
    rng.shuffle(out)
    return out


# ── Cached-topology CPM arithmetic ───────────────────────────────────────────


@dataclass
class _Topology:
    """Everything about the network that does NOT change between iterations.

    Computed once: topological order, predecessor / successor adjacency (as
    ``(id, dep_type, lag)`` triples) and the weakly-connected component root of
    every activity. Durations are the only per-iteration input to
    :func:`cpm_pass`.
    """

    order: list[Any]
    preds: dict[Any, list[tuple[Any, str, int]]]
    succs: dict[Any, list[tuple[Any, str, int]]]
    component_root: dict[Any, Any]


def _build_topology(network: TaskNetwork) -> _Topology:
    """Detect cycles once and cache topology + components.

    Raises :class:`~cpm.CycleError` if the network has a directed cycle. The
    topological sort is Kahn's algorithm (a copy of ``cpm._topological_order``,
    inlined so we keep a private snapshot of adjacency) and the component map is
    a union-find over the undirected graph, mirroring the block inside
    ``cpm.compute_cpm`` (cpm.py lines 301-326).
    """
    cycle = network.detect_cycle()
    if cycle is not None:
        raise CycleError(cycle)

    ids = network.ids()
    preds: dict[Any, list[tuple[Any, str, int]]] = {aid: network.predecessors(aid) for aid in ids}
    succs: dict[Any, list[tuple[Any, str, int]]] = {aid: network.successors(aid) for aid in ids}

    # Kahn topological sort (cpm.py:229-242).
    indeg: dict[Any, int] = {aid: len(preds[aid]) for aid in ids}
    queue: list[Any] = [aid for aid in ids if indeg[aid] == 0]
    order: list[Any] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for s_id, _dep, _lag in succs[nid]:
            indeg[s_id] -= 1
            if indeg[s_id] == 0:
                queue.append(s_id)

    # Union-find weakly-connected components (cpm.py:301-319).
    parent: dict[Any, Any] = {aid: aid for aid in order}

    def _find(x: Any) -> Any:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x: Any, y: Any) -> None:
        rx, ry = _find(x), _find(y)
        if rx != ry:
            parent[rx] = ry

    for aid in order:
        for s_id, _dep, _lag in succs[aid]:
            _union(aid, s_id)

    component_root: dict[Any, Any] = {aid: _find(aid) for aid in order}
    return _Topology(order=order, preds=preds, succs=succs, component_root=component_root)


def cpm_pass(topo: _Topology, durations: dict[Any, float]) -> tuple[float, dict[Any, bool]]:
    """Replay one forward + backward CPM pass on cached topology.

    This is the per-iteration hot path. It replicates the *arithmetic* of
    :func:`cpm.compute_cpm` exactly - the same four-link-type forward / backward
    formulas (cpm.py:267-405) - but skips cycle detection, topological sorting
    and component discovery, all of which are invariant across iterations and
    pre-computed in ``topo``.

    Durations are floats here (sampled, continuous) rather than the integer
    work-days ``compute_cpm`` coerces, so the finish is a float. Returns
    ``(project_finish, {activity_id: is_critical})`` where ``project_finish`` is
    the maximum early finish across all activities (the overall programme finish)
    and ``is_critical`` marks every activity with total float <= 0.
    """
    order = topo.order
    preds = topo.preds
    succs = topo.succs
    if not order:
        return 0.0, {}

    # ── Forward pass: ES, EF (cpm.py:277-299) ───────────────────────────────
    es: dict[Any, float] = {}
    ef: dict[Any, float] = {}
    for aid in order:
        dur = durations.get(aid, 0.0)
        if dur < 0.0:
            dur = 0.0
        candidates: list[float] = []
        for p_id, dep_type, lag in preds[aid]:
            if p_id not in es:
                continue
            if dep_type == "SS":
                candidates.append(es[p_id] + lag)
            elif dep_type == "FF":
                candidates.append(ef[p_id] + lag - dur)
            elif dep_type == "SF":
                candidates.append(es[p_id] + lag - dur)
            else:  # FS (default)
                candidates.append(ef[p_id] + lag)
        es[aid] = max(candidates) if candidates else 0.0
        ef[aid] = es[aid] + dur

    # Per-component project finish = max EF in the component (cpm.py:321-326).
    component_finish: dict[Any, float] = {}
    for aid in order:
        root = topo.component_root[aid]
        if ef[aid] > component_finish.get(root, float("-inf")):
            component_finish[root] = ef[aid]

    # ── Backward pass: LF, LS (cpm.py:338-362) ──────────────────────────────
    lf: dict[Any, float] = {}
    ls: dict[Any, float] = {}
    for aid in reversed(order):
        dur = durations.get(aid, 0.0)
        if dur < 0.0:
            dur = 0.0
        succ_candidates: list[float] = []
        for s_id, dep_type, lag in succs[aid]:
            if s_id not in ls:
                continue
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
            lf[aid] = component_finish[topo.component_root[aid]]
        ls[aid] = lf[aid] - dur

    # ── Float + critical marking (cpm.py:364-404) ───────────────────────────
    # is_critical uses total_float <= 0 with a tiny epsilon to absorb float
    # round-off (the integer engine compares exactly; our continuous durations
    # can leave a ~1e-9 residue on a genuinely critical chain).
    eps = 1e-9
    is_critical: dict[Any, bool] = {}
    project_finish = float("-inf")
    for aid in order:
        total_float = ls[aid] - es[aid]
        is_critical[aid] = total_float <= eps
        if ef[aid] > project_finish:
            project_finish = ef[aid]
    if project_finish == float("-inf"):
        project_finish = 0.0
    return project_finish, is_critical


# ── Public entry point ───────────────────────────────────────────────────────


def simulate_schedule(
    activities: list[Activity],
    relationships: Any = None,  # accepted for call-site symmetry; edges live on activities
    activity_risks: list[ActivityDurationInput] | None = None,
    events: list[RiskEvent] | None = None,
    *,
    iterations: int = DEFAULT_ITERATIONS,
    correlation: float = DEFAULT_CORRELATION,
    seed: int | None = None,
    sampling: str = "lhs",
    target_confidence: int = 80,
    optimistic_pct: float = DEFAULT_OPTIMISTIC_PCT,
    pessimistic_pct: float = DEFAULT_PESSIMISTIC_PCT,
    cost_inputs: CostInputs | None = None,
    histogram_bins: int = 24,
    cdf_points: int = 41,
    max_drivers: int = 12,
    scatter_points: int = 400,
) -> ScheduleRiskResult:
    """Run a correlated Monte Carlo schedule-risk simulation.

    Args:
        activities: The CPM activities (with their predecessor links). Topology
            is read from these once; only durations vary across iterations.
        relationships: Accepted for symmetry with persisted call sites that keep
            edges separately; ignored here because :class:`~cpm.Activity` already
            carries its predecessor links. Pass ``None``.
        activity_risks: Per-activity duration uncertainty. Activities without an
            entry fall back to a band derived from their ``Activity.duration``
            and the global optimistic / pessimistic percentages.
        events: Discrete risk events (probability x three-point impact).
        iterations: Simulation draws (clamped to [100, ``MAX_ITERATIONS``]).
        correlation: Systemic correlation between durations in [0, 0.95]; 0 =
            independent.
        seed: RNG seed; ``None`` derives one deterministically from the inputs.
        sampling: ``"lhs"`` (Latin Hypercube, default) or ``"mc"`` (plain Monte
            Carlo). LHS converges faster for the same iteration count.
        target_confidence: Percentile used for the recommended finish / JCL
            target (default 80).
        optimistic_pct: Default downside band as a percent of base duration.
        pessimistic_pct: Default upside band as a percent of base duration.
        cost_inputs: When supplied, also simulates cost (sharing the correlation
            driver) and reports a Joint Confidence Level.
        histogram_bins: Histogram resolution.
        cdf_points: Points on the cumulative S-curve.
        max_drivers: Maximum tornado drivers returned.
        scatter_points: Downsample cap for the JCL cost/finish scatter cloud.

    Returns:
        A fully populated :class:`ScheduleRiskResult`.

    Raises:
        CycleError: if the activity network contains a directed cycle.
    """
    iterations = max(100, min(int(iterations), MAX_ITERATIONS))
    activity_risks = activity_risks or []
    events = events or []
    correlation = max(0.0, min(correlation, _MAX_CORRELATION))

    network = TaskNetwork(activities)
    topo = _build_topology(network)  # raises CycleError on a cyclic network

    # Activities present in the network, in stable topological order. Durations
    # for any activity without a risk entry come from the static Activity.duration.
    valid_ids = set(topo.order)
    base_duration: dict[Any, float] = {aid: float(max(0, int(network.get(aid).duration))) for aid in topo.order}

    risk_by_id: dict[Any, ActivityDurationInput] = {
        r.activity_id: r for r in activity_risks if r.activity_id in valid_ids
    }

    # Deterministic finish from the base/most-likely durations.
    deterministic_finish, _ = cpm_pass(topo, base_duration)

    # Deterministic seed fallback so repeated identical calls agree.
    if seed is None:
        sig = (
            round(deterministic_finish, 4),
            len(topo.order),
            len(risk_by_id),
            len(events),
            round(optimistic_pct, 3),
            round(pessimistic_pct, 3),
            round(correlation, 4),
        )
        seed = (abs(hash(sig)) % 2_000_000_000) or 1
    rng = random.Random(seed)

    # Only activities that actually carry uncertainty get a sampled column; the
    # rest stay fixed at their base duration. An activity is uncertain if it has
    # an explicit/implicit band wider than zero.
    uncertain_ids: list[Any] = []
    bounds: dict[Any, tuple[float, float, float, str]] = {}
    for aid in topo.order:
        r = risk_by_id.get(aid)
        if r is not None:
            if r.low is not None and r.high is not None and r.high == r.low:
                # An explicit zero-width three-point estimate (low == high) means
                # "this duration is certain". Honour it verbatim - do NOT widen
                # it with the default percentages. cost_risk_engine._bounds_for
                # only accepts a strict ``high > low`` band and would otherwise
                # silently replace this with a +/-default% band.
                low = mode = high = float(r.low)
                dist = r.distribution
            else:
                # Reuse the cost engine's bound resolver by adapting field names.
                low, mode, high = _bounds_for(
                    _DurAdapter(r.base, r.low, r.mode, r.high), optimistic_pct, pessimistic_pct
                )
                dist = r.distribution
        else:
            b = base_duration[aid]
            low = b * (1.0 - optimistic_pct / 100.0)
            high = b * (1.0 + pessimistic_pct / 100.0)
            mode = b
            dist = "pert"
        if high > low:
            uncertain_ids.append(aid)
            bounds[aid] = (low, mode, high, dist)

    use_lhs = sampling != "mc"

    # 1) Pre-sample each uncertain duration column (one column per activity).
    columns: dict[Any, list[float]] = {}
    for aid in uncertain_ids:
        low, mode, high, dist = bounds[aid]
        if use_lhs:
            columns[aid] = _latin_hypercube(rng, iterations, low, mode, high, dist)
        else:
            columns[aid] = [_sample(rng, low, mode, high, dist) for _ in range(iterations)]

    # 2) Induce systemic correlation across the duration columns AND the cost
    #    column together, so cost and schedule share one driver. We build the
    #    cost column here (if requested) and append it to the correlation set.
    cost_col: list[float] | None = None
    if cost_inputs is not None:
        if (
            cost_inputs.cost_low is not None
            and cost_inputs.cost_high is not None
            and cost_inputs.cost_high == cost_inputs.cost_low
        ):
            # Explicit zero-width cost estimate -> certain cost (see the matching
            # guard for activity durations above).
            c_low = c_mode = c_high = float(cost_inputs.cost_low)
        else:
            c_low, c_mode, c_high = _bounds_for(
                _DurAdapter(cost_inputs.base_cost, cost_inputs.cost_low, cost_inputs.cost_mode, cost_inputs.cost_high),
                cost_inputs.optimistic_pct,
                cost_inputs.pessimistic_pct,
            )
        if c_high > c_low:
            if use_lhs:
                cost_col = _latin_hypercube(rng, iterations, c_low, c_mode, c_high, cost_inputs.distribution)
            else:
                cost_col = [_sample(rng, c_low, c_mode, c_high, cost_inputs.distribution) for _ in range(iterations)]
        else:
            cost_col = [cost_inputs.base_cost] * iterations

    corr_columns: list[list[float]] = [columns[aid] for aid in uncertain_ids]
    if cost_col is not None:
        corr_columns.append(cost_col)
    _apply_one_factor_correlation(corr_columns, correlation, rng)

    # 3) Pre-sample discrete risk events (hit booleans + impact magnitudes).
    event_plans = _plan_events(rng, events, valid_ids, iterations, use_lhs)

    # 4) Iterate: per-iteration durations = base sample + event impacts.
    finish_days = [0.0] * iterations
    crit_count: dict[Any, int] = dict.fromkeys(topo.order, 0)
    cost_series = [0.0] * iterations if cost_col is not None else None

    # Working duration dict reused each iteration (re-filled from base + samples).
    for k in range(iterations):
        durations = dict(base_duration)
        for aid in uncertain_ids:
            durations[aid] = columns[aid][k]
        # Apply discrete events for this iteration.
        event_cost_add = 0.0
        for plan in event_plans:
            if not plan.hit[k]:
                continue
            impact = plan.impact[k]
            if plan.mode == "parallel":
                # Single shared disruption: add once to the most schedule-driving
                # affected activity (the one with the largest current duration).
                target = _max_driving(plan.affected, durations)
                if target is not None:
                    durations[target] = durations.get(target, 0.0) + impact
            else:  # series
                for aid in plan.affected:
                    durations[aid] = durations.get(aid, 0.0) + impact
            event_cost_add += plan.cost_impact[k]
        finish, is_crit = cpm_pass(topo, durations)
        finish_days[k] = finish
        for aid, c in is_crit.items():
            if c:
                crit_count[aid] += 1
        if cost_series is not None and cost_col is not None:
            cost_series[k] = cost_col[k] + event_cost_add

    # 5) Statistics on the finish distribution.
    sorted_finish = sorted(finish_days)
    mean = sum(finish_days) / iterations
    var = sum((t - mean) ** 2 for t in finish_days) / iterations
    std_dev = math.sqrt(max(var, 0.0))
    cv_pct = (std_dev / mean * 100.0) if mean > 0 else 0.0

    pct_keys = (5, 10, 25, 50, 75, 80, 90, 95)
    percentiles = {f"p{p}": _percentile(sorted_finish, p) for p in pct_keys}
    budget = _percentile(sorted_finish, float(target_confidence))
    contingency = budget - deterministic_finish
    contingency_pct = (contingency / deterministic_finish * 100.0) if deterministic_finish > 0 else 0.0
    within = sum(1 for t in finish_days if t <= deterministic_finish + 1e-9)
    prob_within = within / iterations * 100.0

    histogram = _build_histogram(sorted_finish, histogram_bins)
    cdf = _build_cdf(sorted_finish, cdf_points)
    criticality = _build_criticality(topo, columns, base_duration, crit_count, finish_days, iterations)
    drivers = _build_drivers(uncertain_ids, columns, finish_days, max_drivers)
    conv_status, conv_margin = _convergence(finish_days, percentiles["p50"], target_confidence)

    joint = None
    if cost_series is not None:
        joint = _build_joint_confidence(
            finish_days,
            cost_series,
            target_finish=budget,
            cost_inputs=cost_inputs,
            target_confidence=target_confidence,
            rng=rng,
            scatter_points=scatter_points,
        )

    return ScheduleRiskResult(
        iterations=iterations,
        deterministic_finish=deterministic_finish,
        mean=mean,
        std_dev=std_dev,
        cv_pct=cv_pct,
        percentiles=percentiles,
        contingency=contingency,
        contingency_pct=contingency_pct,
        recommended_finish=budget,
        target_confidence=target_confidence,
        prob_within_deterministic=prob_within,
        correlation=correlation,
        seed=seed,
        convergence_status=conv_status,
        convergence_margin_pct=conv_margin,
        histogram=histogram,
        cdf=cdf,
        criticality=criticality,
        drivers=drivers,
        joint_confidence=joint,
    )


# ── Event planning ───────────────────────────────────────────────────────────


@dataclass
class _EventPlan:
    """Pre-sampled per-iteration realisation of one risk event."""

    affected: list[Any]
    mode: str
    hit: list[bool]
    impact: list[float]
    cost_impact: list[float]


def _plan_events(
    rng: random.Random,
    events: list[RiskEvent],
    valid_ids: set[Any],
    iterations: int,
    use_lhs: bool,
) -> list[_EventPlan]:
    """Pre-sample, for every event, its per-iteration hit flag + impact size.

    Hit/miss is a Bernoulli(``probability``) drawn from a Latin-Hypercube
    uniform column (so the realised event frequency tracks ``probability`` very
    tightly). Impact magnitude (schedule and cost) is a three-point draw, also
    LHS-stratified. Events affecting no known activity are dropped.
    """
    plans: list[_EventPlan] = []
    for ev in events:
        affected = [aid for aid in ev.affected_activity_ids if aid in valid_ids]
        if not affected:
            continue
        p = min(max(ev.probability, 0.0), 1.0)
        if use_lhs:
            hit_u = _latin_hypercube_uniform(rng, iterations)
        else:
            hit_u = [rng.random() for _ in range(iterations)]
        hit = [u < p for u in hit_u]

        if ev.impact_high > ev.impact_low:
            mode = min(max(ev.impact_mode, ev.impact_low), ev.impact_high)
            if use_lhs:
                impact = _latin_hypercube(rng, iterations, ev.impact_low, mode, ev.impact_high, ev.distribution)
            else:
                impact = [_sample(rng, ev.impact_low, mode, ev.impact_high, ev.distribution) for _ in range(iterations)]
        else:
            impact = [ev.impact_mode] * iterations

        if ev.cost_impact_high > ev.cost_impact_low:
            cmode = min(max(ev.cost_impact_mode, ev.cost_impact_low), ev.cost_impact_high)
            if use_lhs:
                cost_impact = _latin_hypercube(
                    rng, iterations, ev.cost_impact_low, cmode, ev.cost_impact_high, ev.distribution
                )
            else:
                cost_impact = [
                    _sample(rng, ev.cost_impact_low, cmode, ev.cost_impact_high, ev.distribution)
                    for _ in range(iterations)
                ]
        else:
            cost_impact = [ev.cost_impact_mode] * iterations

        plans.append(
            _EventPlan(
                affected=affected,
                mode=ev.application_mode if ev.application_mode in {"series", "parallel"} else "series",
                hit=hit,
                impact=impact,
                cost_impact=cost_impact,
            )
        )
    return plans


def _max_driving(affected: list[Any], durations: dict[Any, float]) -> Any | None:
    """The affected activity with the largest current duration (parallel mode).

    A single shared disruption only stretches the programme through its
    longest-running affected activity, so we add the impact there. Ties resolve
    to the first id for determinism.
    """
    best: Any | None = None
    best_dur = float("-inf")
    for aid in affected:
        d = durations.get(aid, 0.0)
        if d > best_dur:
            best_dur = d
            best = aid
    return best


# ── Output builders ──────────────────────────────────────────────────────────


def _build_criticality(
    topo: _Topology,
    columns: dict[Any, list[float]],
    base_duration: dict[Any, float],
    crit_count: dict[Any, int],
    finish_days: list[float],
    iterations: int,
) -> list[CriticalityStat]:
    """Criticality index + cruciality per activity.

    * criticality_index = fraction of iterations the activity was critical.
    * duration_sensitivity = Spearman(this activity's sampled duration, finish);
      activities with no sampled column (fixed duration) have 0 sensitivity.
    * cruciality = criticality_index * |duration_sensitivity| - high only when an
      activity is both often-critical AND its duration actually swings the
      finish, which is the property that distinguishes a true schedule risk from
      a long-but-low-variance task.
    """
    stats: list[CriticalityStat] = []
    for aid in topo.order:
        ci = crit_count[aid] / iterations
        col = columns.get(aid)
        if col is not None:
            sens = _spearman(col, finish_days)
            mean_dur = sum(col) / iterations
        else:
            sens = 0.0
            mean_dur = base_duration[aid]
        stats.append(
            CriticalityStat(
                activity_id=aid,
                criticality_index=ci,
                cruciality=ci * abs(sens),
                duration_sensitivity=sens,
                mean_duration=mean_dur,
            )
        )
    stats.sort(key=lambda s: (s.criticality_index, s.cruciality), reverse=True)
    return stats


def _build_drivers(
    uncertain_ids: list[Any],
    columns: dict[Any, list[float]],
    finish_days: list[float],
    max_drivers: int,
) -> list[ScheduleDriverStat]:
    """Tornado: rank each uncertain activity by |Spearman(duration, finish)|."""
    stats: list[ScheduleDriverStat] = []
    n = len(finish_days)
    for aid in uncertain_ids:
        col = columns[aid]
        col_mean = sum(col) / n
        col_sorted = sorted(col)
        stats.append(
            ScheduleDriverStat(
                activity_id=aid,
                rank_correlation=_spearman(col, finish_days),
                swing_low=_percentile(col_sorted, 10.0) - col_mean,
                swing_high=_percentile(col_sorted, 90.0) - col_mean,
            )
        )
    stats.sort(key=lambda s: abs(s.rank_correlation), reverse=True)
    return stats[:max_drivers]


def _build_joint_confidence(
    finish_days: list[float],
    cost_series: list[float],
    *,
    target_finish: float,
    cost_inputs: CostInputs,
    target_confidence: int,
    rng: random.Random,
    scatter_points: int,
) -> JointConfidenceResult:
    """Joint Confidence Level + a downsampled cost/finish scatter cloud.

    The JCL is the fraction of iterations finishing on-time *and* on-budget. The
    cost target is ``cost_inputs.cost_target`` when given, else the cost at the
    same target-confidence percentile (so the JCL reads "probability of hitting
    both the P-target schedule and the P-target budget").

    Because cost and schedule share one correlation driver, the two outputs are
    positively associated, so by the FKG inequality the JCL at the marginal
    targets is *at least* the product of the marginals: JCL >= P(on-time) *
    P(on-budget) under positive correlation (you tend to be lucky or unlucky on
    both at once), and ~equal at zero correlation. The familiar programme-office
    warning that "correlation makes the joint confidence worse" is about the
    *contingency needed to reach a fixed joint confidence* - adding the two
    single-axis P80 targets undershoots the real joint-P80 frontier when the axes
    move together - not about the probability measured at the marginal point.
    """
    n = len(finish_days)
    sorted_cost = sorted(cost_series)
    pct_keys = (5, 10, 25, 50, 75, 80, 90, 95)
    cost_percentiles = {f"p{p}": _percentile(sorted_cost, p) for p in pct_keys}
    cost_mean = sum(cost_series) / n

    if cost_inputs.cost_target is not None:
        cost_target = float(cost_inputs.cost_target)
    else:
        cost_target = _percentile(sorted_cost, float(target_confidence))

    on_time = 0
    on_budget = 0
    both = 0
    for k in range(n):
        t_ok = finish_days[k] <= target_finish + 1e-9
        c_ok = cost_series[k] <= cost_target + 1e-9
        if t_ok:
            on_time += 1
        if c_ok:
            on_budget += 1
        if t_ok and c_ok:
            both += 1

    # Realised linear correlation between the two outputs (diagnostic).
    fm = sum(finish_days) / n
    cm = cost_mean
    num = sum((finish_days[k] - fm) * (cost_series[k] - cm) for k in range(n))
    df = math.sqrt(sum((finish_days[k] - fm) ** 2 for k in range(n)))
    dc = math.sqrt(sum((cost_series[k] - cm) ** 2 for k in range(n)))
    realised_corr = (num / (df * dc)) if df > 0 and dc > 0 else 0.0

    # Downsample the scatter cloud deterministically (stride sampling keeps it
    # representative without the cost of a shuffle).
    scatter: list[ScatterPoint] = []
    cap = max(1, min(scatter_points, n))
    # Ceil-divide so the strided count never exceeds the cap; floor division
    # would overshoot (5000 // 300 = 16 yields 313 points for a cap of 300).
    stride = max(1, -(-n // cap))
    for k in range(0, n, stride):
        scatter.append(ScatterPoint(finish=finish_days[k], cost=cost_series[k]))
    del scatter[cap:]

    return JointConfidenceResult(
        target_finish=target_finish,
        target_cost=cost_target,
        jcl=both / n,
        prob_on_time=on_time / n,
        prob_on_budget=on_budget / n,
        cost_mean=cost_mean,
        cost_percentiles=cost_percentiles,
        correlation=realised_corr,
        scatter=scatter,
    )


# ── Internal adapter ─────────────────────────────────────────────────────────


@dataclass
class _DurAdapter:
    """Minimal shim exposing the field names ``_bounds_for`` reads.

    ``cost_risk_engine._bounds_for`` resolves three-point bounds from an object
    with ``.low / .mode / .high / .base`` attributes. Our duration and cost
    inputs use the same semantics under different field names, so we adapt rather
    than duplicate the (subtle, sign-aware) bound logic.
    """

    base: float
    low: float | None
    mode: float | None
    high: float | None
