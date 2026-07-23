# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure, dependency-free Monte Carlo cost-risk and sensitivity engine for BOQ.

This module deliberately imports nothing from ``app`` (no database, no FastAPI):
it is a self-contained numeric core that can be unit-tested in isolation on any
Python interpreter, exactly like ``app/modules/takeoff/recognize.py``. The router
converts BOQ positions into :class:`PositionInput` values, runs :func:`simulate`,
and re-serialises the money fields as Decimal-as-strings (v3 §10) on the way out.

Design goals (an order of magnitude beyond the previous independent-PERT loop):

* **Correlated risk.** Real cost overruns are driven by *systemic* factors
  (material price spikes, labour shortages, FX) that move many positions
  together. A one-factor Gaussian copula, applied through Iman-Conover rank
  reordering, induces a controllable correlation between every position while
  preserving each position's exact marginal distribution. Independent sampling
  (correlation = 0) understates the spread badly because line-item risks cancel.
* **Full distribution.** P5..P95 percentiles, mean, standard deviation,
  coefficient of variation, a probability-density histogram and a cumulative
  S-curve (CDF) - the artefacts a cost engineer actually reads.
* **Honest contingency.** Contingency is reported at an explicit target
  confidence (default P80), with the probability that the deterministic base
  estimate is even achievable.
* **Variance-based sensitivity.** The tornado ranks positions by their share of
  total variance and by Spearman rank correlation to the total - not by a flat
  +/-10% poke - and shows each driver's real P10..P90 swing.
* **Reproducibility & convergence.** A seed makes any run bit-for-bit
  repeatable; a split-half check on P80 reports whether enough iterations were
  run to trust the tails.

Everything is plain ``float`` in and out; callers own all Decimal handling.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

__all__ = [
    "PositionInput",
    "DriverStat",
    "HistBin",
    "CdfPoint",
    "CostRiskResult",
    "simulate",
    "PERT_LAMBDA",
    "MAX_ITERATIONS",
    "DEFAULT_ITERATIONS",
    "DEFAULT_CORRELATION",
]

# Standard PERT shape parameter. lambda=4 makes the distribution peak ~4x more
# sharply at the mode than a triangular distribution - the textbook default.
PERT_LAMBDA = 4.0

DEFAULT_ITERATIONS = 5000
MAX_ITERATIONS = 20000
# A modest default systemic correlation: most construction estimates carry a
# real common-cause component (escalation, market, weather). 0 reproduces the
# old independent model; ~0.2 is a conservative, defensible baseline.
DEFAULT_CORRELATION = 0.2
_MAX_CORRELATION = 0.95


@dataclass
class PositionInput:
    """One BOQ position fed into the simulation.

    ``base`` is the deterministic line total (the most-likely value). When an
    explicit three-point estimate (``low``/``mode``/``high``) is supplied it is
    used verbatim; otherwise bounds are derived from ``base`` and the global
    optimistic / pessimistic percentages passed to :func:`simulate`.
    """

    ordinal: str
    description: str
    base: float
    low: float | None = None
    mode: float | None = None
    high: float | None = None
    distribution: str = "pert"  # "pert" | "triangular" | "uniform"


@dataclass
class DriverStat:
    """A position's contribution to the uncertainty of the total."""

    ordinal: str
    description: str
    contribution_pct: float  # share of total variance (drivers sum to ~100)
    rank_correlation: float  # Spearman rho of this line vs the total (-1..1)
    swing_low: float  # P10(line) - mean(line), <= 0
    swing_high: float  # P90(line) - mean(line), >= 0


@dataclass
class HistBin:
    bin_start: float
    bin_end: float
    count: int


@dataclass
class CdfPoint:
    cost: float
    cumulative_prob: float  # 0..1


@dataclass
class CostRiskResult:
    iterations: int
    base_total: float
    mean: float
    std_dev: float
    cv_pct: float  # coefficient of variation = std/mean * 100
    percentiles: dict[str, float]  # p5,p10,p25,p50,p75,p80,p90,p95
    contingency: float  # P(target) - P50
    contingency_pct: float  # contingency / P50 * 100
    recommended_budget: float  # P(target)
    target_confidence: int  # e.g. 80 -> budget at the 80th percentile
    prob_within_base: float  # P(total <= base_total) * 100
    correlation: float
    seed: int
    convergence_status: str  # "converged" | "marginal" | "insufficient"
    convergence_margin_pct: float
    histogram: list[HistBin] = field(default_factory=list)
    cdf: list[CdfPoint] = field(default_factory=list)
    drivers: list[DriverStat] = field(default_factory=list)


# ── Internal numeric helpers ────────────────────────────────────────────────


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Linear-interpolation percentile of an ascending-sorted list."""
    n = len(sorted_data)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_data[0]
    idx = pct / 100.0 * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    frac = idx - lower
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


def _sample(rng: random.Random, low: float, mode: float, high: float, dist: str) -> float:
    """Draw one sample from the requested distribution bounded by [low, high]."""
    if high <= low:
        return mode
    if dist == "uniform":
        return rng.uniform(low, high)
    if dist == "triangular":
        # random.triangular(low, high, mode)
        return rng.triangular(low, high, mode)
    # default: Beta-PERT
    span = high - low
    alpha = 1.0 + PERT_LAMBDA * (mode - low) / span
    beta = 1.0 + PERT_LAMBDA * (high - mode) / span
    return low + span * rng.betavariate(alpha, beta)


def _ranks(xs: list[float]) -> list[float]:
    """Ordinal ranks (0-based). Ties are broken by index - negligible for the
    continuous samples this engine produces."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    for r, i in enumerate(order):
        out[i] = float(r)
    return out


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    num = 0.0
    da = 0.0
    db = 0.0
    for i in range(n):
        x = a[i] - ma
        y = b[i] - mb
        num += x * y
        da += x * x
        db += y * y
    if da <= 0.0 or db <= 0.0:
        return 0.0
    return num / math.sqrt(da * db)


def _spearman(a: list[float], b: list[float]) -> float:
    return _pearson(_ranks(a), _ranks(b))


def _bounds_for(pos: PositionInput, opt_pct: float, pess_pct: float) -> tuple[float, float, float]:
    """Resolve a position's (low, mode, high) bounds.

    Explicit three-point estimates win; otherwise derive a band around the base
    using the global optimistic / pessimistic percentages.
    """
    if pos.low is not None and pos.high is not None and pos.high > pos.low:
        mode = pos.mode if pos.mode is not None else pos.base
        mode = min(max(mode, pos.low), pos.high)
        return pos.low, mode, pos.high
    base = pos.base
    low = base * (1.0 - opt_pct / 100.0)
    high = base * (1.0 + pess_pct / 100.0)
    if base < 0:  # defensive: keep ordering for credit/negative lines
        low, high = high, low
    return low, base, high


def _apply_one_factor_correlation(columns: list[list[float]], correlation: float, rng: random.Random) -> None:
    """Reorder each column in place so the lines move together with strength
    ``correlation`` via a one-factor Gaussian copula (Iman-Conover style).

    Each iteration draws a shared driver ``Zc`` and a per-position idiosyncratic
    shock ``Zi``; the combined score ``sqrt(rho)*Zc + sqrt(1-rho)*Zi`` is a unit
    normal whose pairwise correlation across positions is ``rho``. Reordering
    each column to follow the rank of its score induces that correlation while
    leaving the column's *values* (hence its marginal distribution) untouched.
    """
    iterations = len(columns[0]) if columns else 0
    if iterations == 0 or correlation <= 0.0 or len(columns) < 2:
        return
    rho = min(correlation, _MAX_CORRELATION)
    a = math.sqrt(rho)
    b = math.sqrt(1.0 - rho)
    zc = [rng.gauss(0.0, 1.0) for _ in range(iterations)]
    for col in columns:
        scores = [a * zc[k] + b * rng.gauss(0.0, 1.0) for k in range(iterations)]
        order = sorted(range(iterations), key=lambda k: scores[k])
        col_sorted = sorted(col)
        for rank, k in enumerate(order):
            col[k] = col_sorted[rank]


# ── Public entry point ──────────────────────────────────────────────────────


def simulate(
    positions: list[PositionInput],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    optimistic_pct: float = 15.0,
    pessimistic_pct: float = 25.0,
    correlation: float = DEFAULT_CORRELATION,
    seed: int | None = None,
    target_confidence: int = 80,
    histogram_bins: int = 24,
    cdf_points: int = 41,
    max_drivers: int = 12,
) -> CostRiskResult:
    """Run a correlated Monte Carlo cost-risk simulation over ``positions``.

    Args:
        positions: Non-section BOQ positions with a positive base total.
        iterations: Simulation draws (clamped to [100, ``MAX_ITERATIONS``]).
        optimistic_pct: Default downside band as a percent of base (when no
            explicit three-point estimate is set on the position).
        pessimistic_pct: Default upside band as a percent of base.
        correlation: Systemic correlation in [0, 0.95]; 0 = independent lines.
        seed: RNG seed for reproducibility; ``None`` derives one deterministically
            so repeated calls with the same inputs still agree.
        target_confidence: Percentile used for the recommended budget (default 80).
        histogram_bins: Histogram resolution.
        cdf_points: Number of points on the cumulative S-curve.
        max_drivers: Maximum tornado drivers returned.

    Returns:
        A fully populated :class:`CostRiskResult`.
    """
    iterations = max(100, min(int(iterations), MAX_ITERATIONS))
    n = len(positions)
    base_total = sum(p.base for p in positions)

    if n == 0 or base_total == 0:
        return CostRiskResult(
            iterations=iterations,
            base_total=base_total,
            mean=base_total,
            std_dev=0.0,
            cv_pct=0.0,
            percentiles=dict.fromkeys(("p5", "p10", "p25", "p50", "p75", "p80", "p90", "p95"), base_total),
            contingency=0.0,
            contingency_pct=0.0,
            recommended_budget=base_total,
            target_confidence=target_confidence,
            prob_within_base=100.0,
            correlation=correlation,
            seed=seed or 0,
            convergence_status="insufficient",
            convergence_margin_pct=0.0,
        )

    # Deterministic seed fallback so the panel does not flicker between renders.
    if seed is None:
        seed = (
            abs(hash((round(base_total, 2), n, round(optimistic_pct, 3), round(pessimistic_pct, 3)))) % 2_000_000_000
        ) or 1
    rng = random.Random(seed)

    bounds = [(*_bounds_for(p, optimistic_pct, pessimistic_pct), p.distribution) for p in positions]

    # 1) Independent marginal samples, one column per position.
    columns: list[list[float]] = []
    for low, mode, high, dist in bounds:
        columns.append([_sample(rng, low, mode, high, dist) for _ in range(iterations)])

    # 2) Induce systemic correlation across positions (preserves marginals).
    correlation = max(0.0, min(correlation, _MAX_CORRELATION))
    _apply_one_factor_correlation(columns, correlation, rng)

    # 3) Per-iteration totals (kept in iteration order for the convergence test).
    totals = [0.0] * iterations
    for col in columns:
        for k in range(iterations):
            totals[k] += col[k]

    sorted_totals = sorted(totals)
    mean = sum(totals) / iterations
    var = sum((t - mean) ** 2 for t in totals) / iterations
    std_dev = math.sqrt(max(var, 0.0))
    cv_pct = (std_dev / mean * 100.0) if mean > 0 else 0.0

    pct_keys = (5, 10, 25, 50, 75, 80, 90, 95)
    percentiles = {f"p{p}": _percentile(sorted_totals, p) for p in pct_keys}
    p50 = percentiles["p50"]
    budget = _percentile(sorted_totals, float(target_confidence))
    contingency = budget - p50
    contingency_pct = (contingency / p50 * 100.0) if p50 > 0 else 0.0

    # Probability the deterministic base estimate is even achievable.
    within = sum(1 for t in totals if t <= base_total)
    prob_within_base = within / iterations * 100.0

    histogram = _build_histogram(sorted_totals, histogram_bins)
    cdf = _build_cdf(sorted_totals, cdf_points)
    drivers = _build_drivers(columns, totals, var, positions, max_drivers)
    conv_status, conv_margin = _convergence(totals, p50, target_confidence)

    return CostRiskResult(
        iterations=iterations,
        base_total=base_total,
        mean=mean,
        std_dev=std_dev,
        cv_pct=cv_pct,
        percentiles=percentiles,
        contingency=contingency,
        contingency_pct=contingency_pct,
        recommended_budget=budget,
        target_confidence=target_confidence,
        prob_within_base=prob_within_base,
        correlation=correlation,
        seed=seed,
        convergence_status=conv_status,
        convergence_margin_pct=conv_margin,
        histogram=histogram,
        cdf=cdf,
        drivers=drivers,
    )


def _build_histogram(sorted_totals: list[float], num_bins: int) -> list[HistBin]:
    min_val = sorted_totals[0]
    max_val = sorted_totals[-1]
    if max_val <= min_val:
        return [HistBin(bin_start=min_val, bin_end=max_val, count=len(sorted_totals))]
    width = (max_val - min_val) / num_bins
    bins = [HistBin(bin_start=min_val + i * width, bin_end=min_val + (i + 1) * width, count=0) for i in range(num_bins)]
    for val in sorted_totals:
        i = int((val - min_val) / width)
        if i >= num_bins:
            i = num_bins - 1
        bins[i].count += 1
    return bins


def _build_cdf(sorted_totals: list[float], points: int) -> list[CdfPoint]:
    points = max(2, points)
    out: list[CdfPoint] = []
    for j in range(points):
        prob = j / (points - 1)
        out.append(CdfPoint(cost=_percentile(sorted_totals, prob * 100.0), cumulative_prob=prob))
    return out


def _build_drivers(
    columns: list[list[float]],
    totals: list[float],
    total_variance: float,
    positions: list[PositionInput],
    max_drivers: int,
) -> list[DriverStat]:
    iterations = len(totals)
    mean_total = sum(totals) / iterations
    stats: list[DriverStat] = []
    for idx, col in enumerate(columns):
        col_mean = sum(col) / iterations
        # Covariance of this line with the total. Because cov(sum_i X_i, T) ==
        # var(T), per-line covariances sum to the total variance -> shares
        # add up to 100%, an honest variance decomposition.
        cov = sum((col[k] - col_mean) * (totals[k] - mean_total) for k in range(iterations)) / iterations
        contribution = (cov / total_variance * 100.0) if total_variance > 0 else 0.0
        col_sorted = sorted(col)
        swing_low = _percentile(col_sorted, 10.0) - col_mean
        swing_high = _percentile(col_sorted, 90.0) - col_mean
        stats.append(
            DriverStat(
                ordinal=positions[idx].ordinal,
                description=positions[idx].description,
                contribution_pct=contribution,
                rank_correlation=_spearman(col, totals),
                swing_low=swing_low,
                swing_high=swing_high,
            )
        )
    stats.sort(key=lambda s: s.contribution_pct, reverse=True)
    return stats[:max_drivers]


def _convergence(totals: list[float], p50: float, target_confidence: int) -> tuple[str, float]:
    """Split-half stability check on the budget percentile.

    Splits the iterations into two halves (in draw order), computes the target
    percentile on each, and reports the gap as a percentage of P50. A small gap
    means the tail estimate is stable enough to trust.
    """
    n = len(totals)
    if n < 1000:
        return "insufficient", 0.0
    half = n // 2
    a = sorted(totals[:half])
    b = sorted(totals[half:])
    pa = _percentile(a, float(target_confidence))
    pb = _percentile(b, float(target_confidence))
    margin_pct = (abs(pa - pb) / p50 * 100.0) if p50 > 0 else 0.0
    if margin_pct < 0.5:
        status = "converged"
    elif margin_pct < 2.0:
        status = "marginal"
    else:
        status = "insufficient"
    return status, margin_pct
