# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure predictive delay / overrun risk scoring for change records.

Which open changes are most likely to blow their response deadline (or the
schedule float behind it), why, and - because this is the moat - how well those
predictions actually held up against reality. The industry data behind the
"Change & AI" roadmap is blunt: a change that already dwells far past its service
target, sitting with a holder who routinely runs overdue and is buried under a
stack of other open changes, is the one that overruns. This engine turns those
signals into a ranked, explainable risk and then scores the predictions against
the recorded outcome.

It is a *composition* engine: it does not re-derive dwell time, SLA targets,
holder performance, change size or a holder's open-work count. The sibling
cycle-time, SLA, ownership / hand-off-history and cost engines already produce
those; the integrator gathers their outputs for one change into a
:class:`DelayRiskInput` and feeds it in. Concretely the integrator maps:

* ``step_mean_dwell_days`` - how long the change has actually sat at its current
  step, from the cycle-time board / hand-off history (the #5 resolved-outcome
  ledger records per-step dwell when a change is handed off or closed);
* ``step_sla_days`` - the service target for that step, from the approval-route
  SLA engine;
* ``holder_overdue_rate`` - the fraction of this holder's past changes that
  finished overdue, from the #5 hand-off-history (resolved outcomes per holder),
  already a rate in ``[0, 1]``;
* ``change_size_ratio`` - change value divided by contract value (a non-negative
  fraction), from the cost / BOQ ledger;
* ``holder_open_change_count`` - how many other changes this holder currently
  owns open, a count from the cycle-time board.

No database, no ORM, no ``app.*`` imports and no clock or randomness - stdlib
floats only - so it unit-tests on the local Python 3.11 runner exactly like the
engines it composes. Identical inputs always produce an identical result.

Scoring model
-------------
Each feature is first mapped to a normalized sub-score in ``[0, 1]`` (1 == worst)
by a documented, monotonic transform, then blended with documented weights into
a single risk in ``[0, 1]``. Every transform is non-decreasing in the feature, so
worsening any one feature can never lower the risk (see the per-feature
monotonicity tests). The transforms:

* **dwell pressure** (weight :data:`W_DWELL`, the dominant lever) - the ratio of
  actual dwell to the step SLA. At or below the SLA the change is on time and
  contributes nothing; above it the sub-score ramps linearly and saturates at
  :data:`DWELL_RATIO_SATURATION` times the SLA (a change running that many times
  over its target is treated as maximally late). A non-positive SLA is treated
  as "any dwell is over target", so a positive dwell saturates immediately.
* **holder overdue rate** (weight :data:`W_HOLDER_RATE`) - used directly: the
  rate already lives in ``[0, 1]`` and is clamped to it.
* **change size** (weight :data:`W_SIZE`) - the size ratio ramps linearly from 0
  and saturates at :data:`SIZE_RATIO_SATURATION` (a change worth that fraction of
  the whole contract, or more, is treated as maximally large). Larger changes
  carry more scope to slip and more scrutiny before they clear.
* **holder load** (weight :data:`W_LOAD`) - the open-change count ramps linearly
  from 0 and saturates at :data:`LOAD_SATURATION_COUNT` (a holder juggling that
  many open changes, or more, is treated as maximally loaded).

The weights sum to :data:`TOTAL_WEIGHT`; the risk is the weighted sum of the four
sub-scores divided by that total, so it stays in ``[0, 1]`` and is a transparent
blend. :func:`score` returns the risk together with the ranked factor
contributions, so a UI can show *why* a change is at risk without re-deriving
anything.

Banding
-------
:func:`band_for_risk` maps the ``[0, 1]`` risk onto ``low`` / ``elevated`` /
``high`` using documented inclusive lower-bound thresholds on the same 0-1 scale,
so a UI can colour a row without re-deriving the cut points.

Backtest (the moat: predictions scored against reality)
-------------------------------------------------------
A risk number is only worth trusting if it has been checked against what actually
happened. :func:`backtest` takes a stream of :class:`Prediction` (the risk we
published for a change, paired with whether that change ultimately delayed) and
returns:

* the **Brier score** - the mean squared error between predicted risk and the
  realized 0/1 outcome (``mean((p - actual) ** 2)``); lower is better, 0.0 is
  perfect, 1.0 is worst;
* a **calibration** breakdown - predictions bucketed into equal-width risk bands
  over ``[0, 1]``, each reporting how often the change actually delayed versus
  the mean risk we predicted, so over- and under-confidence are visible per band.

Floats throughout (no money flows through this engine), fully deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Risk-factor weights (transparent blend; sum is TOTAL_WEIGHT).
# Dwell pressure deliberately dominates: a change already running far past its
# service target is the single strongest signal that it will overrun, and it is
# the lever the rest of the model is calibrated around.
# --------------------------------------------------------------------------- #

#: Weight of dwell pressure (actual dwell vs the step SLA). The dominant factor.
W_DWELL = 45

#: Weight of the holder's historical overdue rate.
W_HOLDER_RATE = 25

#: Weight of the change size (its value as a fraction of the contract).
W_SIZE = 15

#: Weight of the holder's current open-change load.
W_LOAD = 15

#: Sum of the four factor weights; the risk is normalised by it.
TOTAL_WEIGHT = W_DWELL + W_HOLDER_RATE + W_SIZE + W_LOAD

# --------------------------------------------------------------------------- #
# Feature saturation / calibration constants. Each is the point at which the
# corresponding sub-score reaches its maximum of 1.0; beyond it the sub-score
# stays at 1.0 (the other factors and the banding still carry the signal).
# --------------------------------------------------------------------------- #

#: Multiple of the step SLA at which the dwell-pressure sub-score saturates. A
#: change that has dwelt this many times its service target (or more) is treated
#: as maximally late. The ramp starts at the SLA itself: dwell == SLA -> 0.0,
#: dwell == DWELL_RATIO_SATURATION * SLA -> 1.0.
DWELL_RATIO_SATURATION = 3.0

#: Size ratio (change value / contract value) at which the size sub-score
#: saturates. A change worth a fifth of the whole contract, or more, is treated
#: as maximally large.
SIZE_RATIO_SATURATION = 0.20

#: Open-change count at which the holder-load sub-score saturates. A holder
#: carrying this many open changes, or more, is treated as maximally loaded.
LOAD_SATURATION_COUNT = 10.0

# --------------------------------------------------------------------------- #
# Risk band thresholds (inclusive lower bounds) on the 0-1 risk scale.
# --------------------------------------------------------------------------- #

BAND_HIGH = "high"
BAND_ELEVATED = "elevated"
BAND_LOW = "low"

#: At or above HIGH_THRESHOLD -> "high"; at or above ELEVATED_THRESHOLD (but
#: below high) -> "elevated"; anything lower -> "low". Inclusive lower bounds on
#: the [0, 1] risk scale.
HIGH_THRESHOLD = 0.60
ELEVATED_THRESHOLD = 0.35

# --------------------------------------------------------------------------- #
# Stable factor names. score() ranks RiskFactor entries by contribution; these
# tokens let a UI label / theme each factor without parsing prose.
# --------------------------------------------------------------------------- #

FACTOR_DWELL = "dwell_pressure"
FACTOR_HOLDER_RATE = "holder_overdue_rate"
FACTOR_SIZE = "change_size"
FACTOR_LOAD = "holder_load"


@dataclass(frozen=True)
class DelayRiskInput:
    """Composite per-change input the integrator assembles from sibling engines.

    Every field is a plain primitive so the engine stays ORM-free and
    3.11-testable. See the module docstring for the exact source-engine mapping.

    Attributes
    ----------
    change_id:
        Stable identifier of the change record (used for tie-break ordering and
        echoed onto the result).
    step_mean_dwell_days:
        How long the change has actually sat at its current step, in days, from
        the cycle-time board / #5 hand-off history. Non-negative; a negative
        value is clamped to zero.
    step_sla_days:
        The service target for that step, in days, from the SLA engine. A
        non-positive target is treated as "any dwell is already over target".
    holder_overdue_rate:
        Fraction of this holder's past changes that finished overdue, already a
        rate in ``[0, 1]`` from the #5 hand-off history. Clamped to ``[0, 1]``.
    change_size_ratio:
        Change value divided by contract value, a non-negative fraction from the
        cost / BOQ ledger. A negative value is clamped to zero.
    holder_open_change_count:
        How many other changes this holder currently owns open, from the
        cycle-time board. Negative counts are clamped to zero.
    """

    change_id: str
    step_mean_dwell_days: float
    step_sla_days: float
    holder_overdue_rate: float
    change_size_ratio: float
    holder_open_change_count: int


@dataclass(frozen=True)
class RiskFactor:
    """One factor's contribution to the blended risk.

    ``value`` is the factor's normalized sub-score in ``[0, 1]`` (1 == worst);
    ``contribution`` is its share of the final ``[0, 1]`` risk, i.e.
    ``value * weight / TOTAL_WEIGHT``. The factors of a result sum (within
    rounding) to the result's ``risk``, and they are returned ranked by
    ``contribution`` descending so the top driver is first.
    """

    name: str
    value: float
    contribution: float


@dataclass(frozen=True)
class DelayRiskResult:
    """The graded delay / overrun risk of one change.

    Attributes
    ----------
    change_id:
        Carried through from the input for display and stable ordering.
    risk:
        The blended risk in ``[0, 1]`` (1 == most likely to overrun).
    band:
        ``low`` / ``elevated`` / ``high`` per :func:`band_for_risk`.
    top_factors:
        All four :class:`RiskFactor` contributions, ranked by ``contribution``
        descending (ties broken by the fixed factor order), so the dominant
        driver is first.
    """

    change_id: str
    risk: float
    band: str
    top_factors: tuple[RiskFactor, ...] = field(default_factory=tuple)


def clamp01(value: float) -> float:
    """Clamp a value into the closed unit interval ``[0.0, 1.0]``."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def band_for_risk(risk: float) -> str:
    """Classify a ``[0, 1]`` risk into a band.

    ``risk >= HIGH_THRESHOLD`` -> :data:`BAND_HIGH`;
    ``risk >= ELEVATED_THRESHOLD`` -> :data:`BAND_ELEVATED`;
    otherwise :data:`BAND_LOW`. Thresholds are inclusive lower bounds on the
    0-1 scale.
    """
    if risk >= HIGH_THRESHOLD:
        return BAND_HIGH
    if risk >= ELEVATED_THRESHOLD:
        return BAND_ELEVATED
    return BAND_LOW


def dwell_pressure(step_mean_dwell_days: float, step_sla_days: float) -> float:
    """Dwell-pressure sub-score in ``[0, 1]`` (1 == maximally late).

    Compares actual dwell to the step SLA. At or below the SLA the change is on
    time and contributes 0.0; above it the sub-score ramps linearly with the
    over-target multiple and saturates at :data:`DWELL_RATIO_SATURATION` times
    the SLA. Formally, with ``r = dwell / sla`` the sub-score is
    ``clamp01((r - 1) / (DWELL_RATIO_SATURATION - 1))``.

    A non-positive ``step_sla_days`` means there is no positive target to be
    within, so any positive dwell is over target and saturates immediately to
    1.0 (a zero dwell against no target is still 0.0). A negative dwell is
    clamped to zero.
    """
    dwell = step_mean_dwell_days if step_mean_dwell_days > 0.0 else 0.0
    if step_sla_days <= 0.0:
        return 1.0 if dwell > 0.0 else 0.0
    ratio = dwell / step_sla_days
    return clamp01((ratio - 1.0) / (DWELL_RATIO_SATURATION - 1.0))


def size_pressure(change_size_ratio: float) -> float:
    """Change-size sub-score in ``[0, 1]`` (1 == maximally large).

    Ramps linearly from 0 at a zero-value change and saturates at 1.0 once the
    change is worth :data:`SIZE_RATIO_SATURATION` of the contract (or more). A
    negative ratio is clamped to zero.
    """
    if change_size_ratio <= 0.0:
        return 0.0
    return clamp01(change_size_ratio / SIZE_RATIO_SATURATION)


def load_pressure(holder_open_change_count: int) -> float:
    """Holder-load sub-score in ``[0, 1]`` (1 == maximally loaded).

    Ramps linearly from 0 at no open changes and saturates at 1.0 once the
    holder carries :data:`LOAD_SATURATION_COUNT` open changes (or more). A
    negative count is clamped to zero.
    """
    if holder_open_change_count <= 0:
        return 0.0
    return clamp01(holder_open_change_count / LOAD_SATURATION_COUNT)


# Fixed factor order: dwell first (dominant), then holder rate, size, load. The
# contribution-ranking tie-break follows this order (earlier factor wins a tie).
_FACTOR_SPECS: tuple[tuple[str, int], ...] = (
    (FACTOR_DWELL, W_DWELL),
    (FACTOR_HOLDER_RATE, W_HOLDER_RATE),
    (FACTOR_SIZE, W_SIZE),
    (FACTOR_LOAD, W_LOAD),
)


def score(inp: DelayRiskInput) -> DelayRiskResult:
    """Grade one change's delay / overrun risk into a :class:`DelayRiskResult`.

    Maps each feature to its normalized sub-score, blends them with the
    documented weights into a ``[0, 1]`` risk, bands it, and returns the four
    factor contributions ranked by contribution descending (ties broken by the
    fixed factor order, earlier wins). Pure and deterministic - no clock, no
    randomness: identical input always yields an identical result. Monotonic by
    construction: every sub-score is non-decreasing in its feature, so worsening
    any one feature never lowers the risk.
    """
    sub_scores = {
        FACTOR_DWELL: dwell_pressure(inp.step_mean_dwell_days, inp.step_sla_days),
        FACTOR_HOLDER_RATE: clamp01(inp.holder_overdue_rate),
        FACTOR_SIZE: size_pressure(inp.change_size_ratio),
        FACTOR_LOAD: load_pressure(inp.holder_open_change_count),
    }

    risk = 0.0
    factors: list[RiskFactor] = []
    for name, weight in _FACTOR_SPECS:
        value = sub_scores[name]
        contribution = value * weight / float(TOTAL_WEIGHT)
        risk += contribution
        factors.append(RiskFactor(name=name, value=round(value, 6), contribution=round(contribution, 6)))

    risk = clamp01(risk)

    # Rank by contribution descending; the fixed factor order is the stable
    # tie-break (Python's sort is stable, and _FACTOR_SPECS is already in that
    # order), so an earlier factor wins a contribution tie.
    ranked = tuple(sorted(factors, key=lambda f: -f.contribution))

    return DelayRiskResult(
        change_id=inp.change_id,
        risk=round(risk, 6),
        band=band_for_risk(risk),
        top_factors=ranked,
    )


def rank(inputs: list[DelayRiskInput]) -> list[DelayRiskResult]:
    """Score every change and return them sorted by risk, highest first.

    Ties on risk are broken by ``change_id`` ascending for a fully deterministic
    order. Empty input yields an empty list.
    """
    results = [score(inp) for inp in inputs]
    results.sort(key=lambda r: (-r.risk, r.change_id))
    return results


# --------------------------------------------------------------------------- #
# Backtest: predictions scored against the recorded outcome (the moat).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Prediction:
    """A published delay-risk prediction paired with the realized outcome.

    Attributes
    ----------
    predicted_risk:
        The ``[0, 1]`` risk this engine published for a change. Values outside
        the range are clamped by the scoring functions before use.
    actual_delayed:
        ``True`` if the change ultimately delayed / overran, else ``False``.
        Sourced from the #5 resolved-outcome ledger.
    """

    predicted_risk: float
    actual_delayed: bool


@dataclass(frozen=True)
class CalibrationBucket:
    """One calibration bucket over the ``[0, 1]`` predicted-risk range.

    Attributes
    ----------
    lower:
        Inclusive lower edge of the predicted-risk band.
    upper:
        Upper edge of the predicted-risk band (the top bucket's upper edge is
        exactly 1.0).
    n:
        Number of predictions that fell into this band.
    mean_predicted:
        Mean clamped predicted risk of the predictions in the band.
    observed_rate:
        Fraction of predictions in the band whose change actually delayed.
    """

    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_rate: float


@dataclass(frozen=True)
class BacktestResult:
    """Backtest summary for a stream of delay-risk predictions.

    Attributes
    ----------
    count:
        Number of predictions scored.
    brier_score:
        Mean squared error of predicted risk versus the 0/1 outcome
        (``mean((p - actual) ** 2)``). Lower is better; 0.0 is perfect, 1.0 is
        worst. ``0.0`` for an empty input.
    calibration:
        The non-empty calibration buckets, ordered from low to high predicted
        risk. Empty buckets are omitted.
    """

    count: int
    brier_score: float
    calibration: tuple[CalibrationBucket, ...] = field(default_factory=tuple)


def brier_score(predictions: list[Prediction]) -> float:
    """Return the mean Brier score of the given predictions.

    The Brier score for a single prediction is
    ``(clamp01(predicted_risk) - target) ** 2`` where ``target`` is 1.0 when the
    change actually delayed and 0.0 otherwise. The result is the mean over all
    predictions. An empty input returns 0.0.
    """
    if not predictions:
        return 0.0
    total = 0.0
    for prediction in predictions:
        predicted = clamp01(prediction.predicted_risk)
        target = 1.0 if prediction.actual_delayed else 0.0
        total += (predicted - target) ** 2
    return total / len(predictions)


def calibration_buckets(predictions: list[Prediction], buckets: int = 10) -> tuple[CalibrationBucket, ...]:
    """Group predictions into equal-width predicted-risk buckets.

    The unit interval is split into ``buckets`` equal-width bands. A prediction
    with clamped risk ``p`` lands in bucket index ``min(int(p * buckets),
    buckets - 1)`` so that a risk of exactly 1.0 falls into the top bucket rather
    than overflowing. Only buckets that contain at least one prediction are
    returned, ordered from low to high predicted risk.

    Args:
        predictions: Predictions to bucket.
        buckets: Number of equal-width buckets; must be at least 1.

    Returns:
        The non-empty buckets, each carrying its count, mean predicted risk, and
        observed delay rate.
    """
    if buckets < 1:
        raise ValueError("buckets must be at least 1")
    if not predictions:
        return ()

    width = 1.0 / buckets
    counts = [0] * buckets
    predicted_sums = [0.0] * buckets
    delayed_counts = [0] * buckets

    for prediction in predictions:
        predicted = clamp01(prediction.predicted_risk)
        index = min(int(predicted * buckets), buckets - 1)
        counts[index] += 1
        predicted_sums[index] += predicted
        if prediction.actual_delayed:
            delayed_counts[index] += 1

    out: list[CalibrationBucket] = []
    for index in range(buckets):
        count = counts[index]
        if count == 0:
            continue
        lower = index * width
        upper = 1.0 if index == buckets - 1 else (index + 1) * width
        out.append(
            CalibrationBucket(
                lower=lower,
                upper=upper,
                n=count,
                mean_predicted=predicted_sums[index] / count,
                observed_rate=delayed_counts[index] / count,
            )
        )
    return tuple(out)


def backtest(predictions: list[Prediction], *, buckets: int = 10) -> BacktestResult:
    """Score a stream of delay-risk predictions against their outcomes.

    Returns the Brier score (mean squared error of predicted risk versus the 0/1
    realized outcome) and the calibration breakdown (predictions bucketed into
    ``buckets`` equal-width predicted-risk bands, each with its observed delay
    rate). Pure and deterministic. An empty input yields a zero count, a 0.0
    Brier score and no buckets.
    """
    return BacktestResult(
        count=len(predictions),
        brier_score=brier_score(predictions),
        calibration=calibration_buckets(predictions, buckets),
    )


__all__ = [
    "W_DWELL",
    "W_HOLDER_RATE",
    "W_SIZE",
    "W_LOAD",
    "TOTAL_WEIGHT",
    "DWELL_RATIO_SATURATION",
    "SIZE_RATIO_SATURATION",
    "LOAD_SATURATION_COUNT",
    "BAND_HIGH",
    "BAND_ELEVATED",
    "BAND_LOW",
    "HIGH_THRESHOLD",
    "ELEVATED_THRESHOLD",
    "FACTOR_DWELL",
    "FACTOR_HOLDER_RATE",
    "FACTOR_SIZE",
    "FACTOR_LOAD",
    "DelayRiskInput",
    "RiskFactor",
    "DelayRiskResult",
    "Prediction",
    "CalibrationBucket",
    "BacktestResult",
    "clamp01",
    "band_for_risk",
    "dwell_pressure",
    "size_pressure",
    "load_pressure",
    "score",
    "rank",
    "brier_score",
    "calibration_buckets",
    "backtest",
]
