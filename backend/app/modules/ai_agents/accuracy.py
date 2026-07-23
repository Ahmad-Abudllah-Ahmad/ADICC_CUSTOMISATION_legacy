# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure scoring engine for an AI accuracy scoreboard.

This module scores probabilistic AI predictions against binary actual
outcomes. Each prediction carries the model's stated confidence (the
probability it assigns to its own answer being correct, in [0, 1]) and the
realized outcome (True if the answer turned out correct, False otherwise).

From a stream of such predictions the engine derives, per agent:

- The Brier score: the mean squared error between stated confidence and the
  realized 0/1 outcome. Lower is better; 0.0 is perfect, 1.0 is worst.
- Reliability (calibration) bins: predictions grouped into equal-width
  confidence buckets, each reporting how often the agent was actually right
  versus how confident it claimed to be.
- The expected calibration error (ECE): the count-weighted average gap
  between stated confidence and observed correctness across the bins. Lower
  is better; 0.0 means the agent's confidence matches reality.

The engine is intentionally dependency-free (standard library only) so it can
be unit tested in isolation and wired into a service layer without pulling in
the web or database stack.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AccuracyScore",
    "CalibrationBin",
    "Prediction",
    "brier_score",
    "calibration_bins",
    "clamp01",
    "expected_calibration_error",
    "score_agent",
    "score_by_agent",
]


def clamp01(x: float) -> float:
    """Clamp a value into the closed unit interval [0.0, 1.0]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


@dataclass(frozen=True)
class Prediction:
    """A single probabilistic prediction and its realized outcome.

    Attributes:
        agent_name: Identifier of the agent that made the prediction.
        confidence: The model's stated probability that its answer was
            correct, expected in [0, 1]. Values outside the range are
            clamped by the scoring functions before use.
        outcome: True if the answer turned out to be correct, else False.
        predicted_at: Optional timestamp string for when the prediction was
            made. Not used in scoring; carried for traceability.
    """

    agent_name: str
    confidence: float
    outcome: bool
    predicted_at: str | None = None


@dataclass(frozen=True)
class CalibrationBin:
    """One reliability bucket over the confidence range.

    Attributes:
        lower: Inclusive lower edge of the confidence band.
        upper: Upper edge of the confidence band.
        count: Number of predictions that fell into this band.
        mean_confidence: Mean clamped confidence of predictions in the band.
        observed_rate: Fraction of predictions in the band that were correct.
    """

    lower: float
    upper: float
    count: int
    mean_confidence: float
    observed_rate: float


@dataclass(frozen=True)
class AccuracyScore:
    """Aggregate accuracy and calibration summary for one agent.

    Attributes:
        agent_name: Identifier of the scored agent.
        count: Number of predictions scored.
        brier_score: Mean squared error of confidence versus outcome.
        mean_confidence: Mean clamped confidence across all predictions.
        observed_rate: Fraction of predictions that were correct.
        calibration_error: Expected calibration error (ECE).
        bins: Non-empty reliability bins, ordered from low to high confidence.
    """

    agent_name: str
    count: int
    brier_score: float
    mean_confidence: float
    observed_rate: float
    calibration_error: float
    bins: list[CalibrationBin] = field(default_factory=list)


def brier_score(predictions: list[Prediction]) -> float:
    """Return the mean Brier score of the given predictions.

    The Brier score for a single prediction is
    ``(clamp01(confidence) - target) ** 2`` where ``target`` is 1.0 when the
    outcome is True and 0.0 otherwise. The result is the mean over all
    predictions. An empty input returns 0.0.
    """
    if not predictions:
        return 0.0
    total = 0.0
    for prediction in predictions:
        confidence = clamp01(prediction.confidence)
        target = 1.0 if prediction.outcome else 0.0
        total += (confidence - target) ** 2
    return total / len(predictions)


def calibration_bins(predictions: list[Prediction], n_bins: int = 10) -> list[CalibrationBin]:
    """Group predictions into equal-width confidence bins.

    The unit interval is split into ``n_bins`` equal-width bands. A
    prediction with clamped confidence ``c`` lands in bin index
    ``min(int(c * n_bins), n_bins - 1)`` so that a confidence of exactly 1.0
    falls into the top bin rather than overflowing. Only bins that contain at
    least one prediction are returned, ordered from low to high confidence.

    Args:
        predictions: Predictions to bucket.
        n_bins: Number of equal-width bins; must be at least 1.

    Returns:
        The non-empty bins, each carrying its count, mean confidence, and
        observed correctness rate.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    if not predictions:
        return []

    width = 1.0 / n_bins
    counts = [0] * n_bins
    confidence_sums = [0.0] * n_bins
    correct_counts = [0] * n_bins

    for prediction in predictions:
        confidence = clamp01(prediction.confidence)
        index = min(int(confidence * n_bins), n_bins - 1)
        counts[index] += 1
        confidence_sums[index] += confidence
        if prediction.outcome:
            correct_counts[index] += 1

    bins: list[CalibrationBin] = []
    for index in range(n_bins):
        count = counts[index]
        if count == 0:
            continue
        lower = index * width
        upper = 1.0 if index == n_bins - 1 else (index + 1) * width
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=count,
                mean_confidence=confidence_sums[index] / count,
                observed_rate=correct_counts[index] / count,
            )
        )
    return bins


def expected_calibration_error(predictions: list[Prediction], n_bins: int = 10) -> float:
    """Return the expected calibration error (ECE) of the predictions.

    The ECE is the count-weighted average over the non-empty bins of the
    absolute gap between each bin's mean confidence and its observed
    correctness rate:
    ``sum (count / total) * abs(mean_confidence - observed_rate)``.
    A lower value indicates better calibration; an empty input returns 0.0.
    """
    if not predictions:
        return 0.0
    total = len(predictions)
    bins = calibration_bins(predictions, n_bins)
    error = 0.0
    for bucket in bins:
        weight = bucket.count / total
        error += weight * abs(bucket.mean_confidence - bucket.observed_rate)
    return error


def _mean_confidence(predictions: list[Prediction]) -> float:
    """Return the mean clamped confidence, or 0.0 for an empty input."""
    if not predictions:
        return 0.0
    total = sum(clamp01(prediction.confidence) for prediction in predictions)
    return total / len(predictions)


def _observed_rate(predictions: list[Prediction]) -> float:
    """Return the fraction of predictions with a True outcome, or 0.0."""
    if not predictions:
        return 0.0
    correct = sum(1 for prediction in predictions if prediction.outcome)
    return correct / len(predictions)


def score_agent(agent_name: str, predictions: list[Prediction], n_bins: int = 10) -> AccuracyScore:
    """Compute the accuracy summary for a single agent.

    The caller is responsible for passing only the predictions belonging to
    ``agent_name``; this function does not filter by agent. All metrics are
    computed over the supplied predictions.

    Args:
        agent_name: Identifier recorded on the returned score.
        predictions: The agent's predictions to score.
        n_bins: Number of equal-width calibration bins.

    Returns:
        An AccuracyScore. For an empty input the count is 0 and every numeric
        metric is 0.0 with no bins.
    """
    return AccuracyScore(
        agent_name=agent_name,
        count=len(predictions),
        brier_score=brier_score(predictions),
        mean_confidence=_mean_confidence(predictions),
        observed_rate=_observed_rate(predictions),
        calibration_error=expected_calibration_error(predictions, n_bins),
        bins=calibration_bins(predictions, n_bins),
    )


def score_by_agent(predictions: list[Prediction], n_bins: int = 10) -> dict[str, AccuracyScore]:
    """Group predictions by agent name and score each group.

    Grouping preserves the order in which agent names first appear in the
    input, making the result deterministic for a given input ordering.

    Args:
        predictions: Predictions from one or more agents.
        n_bins: Number of equal-width calibration bins.

    Returns:
        A mapping from agent name to that agent's AccuracyScore.
    """
    grouped: dict[str, list[Prediction]] = {}
    for prediction in predictions:
        grouped.setdefault(prediction.agent_name, []).append(prediction)
    return {agent_name: score_agent(agent_name, group, n_bins) for agent_name, group in grouped.items()}
