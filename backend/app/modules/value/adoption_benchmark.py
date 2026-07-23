# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure adoption-vs-non-adoption benchmark math.

Does using the platform actually move outcomes? The construction-change survey
keeps asserting that disciplined, AI-assisted change management pays off, but a
sceptical buyer wants the contrast on THEIR OWN portfolio, not an industry
average. This engine answers that question on first-party data: it scores how
heavily each project adopted the platform's change discipline, splits the
portfolio into a high-adoption and a low-adoption cohort, and compares the two
on the outcome metrics the rest of the change-intelligence suite already
computes (cost recovery, overrun, change cycle time). The output is the
firm's own "adopters did X, non-adopters did Y" table, with honest handling
when there simply are not enough projects on one side to say anything.

What "adoption" means here (documented, transparent blend)
----------------------------------------------------------
Adoption is scored per project from two signals the platform genuinely
records, blended into a single number in ``[0, 1]``:

* Activity density - how much assisted change work the project logged
  relative to how many changes it had. A project that ran ten changes and
  logged a hundred assisted actions is using the platform; one that ran ten
  changes and logged two is not. This is a saturating ratio (see
  :data:`DENSITY_SATURATION`) so a hyperactive project does not run away with
  the score - past the saturation point more activity stops adding adoption.
* Traceability ratio - the share of the project's changes that ended up
  traceable (a clear owner / contemporaneous record), i.e.
  ``traceable_change_count / change_count``. This is the discipline the survey
  ties to recovery, so it is half the blend.

The two are averaged with documented weights (:data:`DENSITY_WEIGHT` /
:data:`TRACEABILITY_WEIGHT`, summing to 1). EVERY ratio guards divide-by-zero:
a project with zero changes has traceability 0 (you cannot have traced changes
you did not have) and density 0 (no changes means no change activity to
credit); a project with zero activity has density 0. The score is therefore
always defined and always in ``[0, 1]``.

Cohorts (documented cut)
------------------------
A project is :data:`COHORT_HIGH` when its adoption score is at least
:data:`DEFAULT_ADOPTION_CUT` (0.5), else :data:`COHORT_LOW`. The cut is drawn
at the midpoint of the score range on purpose: 0.5 is the point at which a
project is, on balance, using the discipline more than not. The fixed cut is
the default because it is stable and explainable across runs; a
:func:`median_cut` helper is provided for callers who would rather split their
own portfolio at its median (useful when every project clusters high or low and
the fixed cut would put everyone on one side).

Comparisons (means ignore None, delta sign documented per metric)
-----------------------------------------------------------------
For each outcome metric the engine reports the mean over each cohort, the
number of projects that actually had a value for it (``high_n`` / ``low_n`` -
projects whose metric was ``None`` are excluded from BOTH the mean and the n,
so a missing recovery rate never drags a cohort to zero), and a ``delta``.
The delta is ALWAYS ``high_mean - low_mean``, but whether a positive delta is
GOOD depends on the metric, so each metric declares its direction
(:data:`HIGHER_IS_BETTER` / :data:`LOWER_IS_BETTER`) and a positive
``favours_high`` flag is derived from it: for recovery rate higher is better,
so a positive delta favours the adopters; for overrun and cycle time lower is
better, so a NEGATIVE delta (adopters overran less / closed changes faster)
favours the adopters. The raw signed delta is kept as-is for display; the flag
just records who the sign favours.

Confidence (documented thresholds, honest low-n)
------------------------------------------------
A comparison is only as trustworthy as the smaller cohort behind it. Confidence
is derived from ``min(high_n, low_n)`` against documented thresholds
(:data:`MIN_N_LOW` / :data:`MIN_N_MEDIUM` / :data:`MIN_N_HIGH`): below the
floor, or whenever either cohort contributed zero values for the metric, the
confidence is :data:`CONFIDENCE_NONE` - the engine refuses to dress up a
one-project-versus-one-project comparison as a finding. The overall benchmark
confidence is the WEAKEST of its comparisons (you are only as confident as your
flimsiest column), and :data:`CONFIDENCE_NONE` if there are no comparisons.

No database, no ORM, no ``app.*`` imports - stdlib plus :class:`decimal.Decimal`
only - so it unit-tests on the local Python 3.11 runner exactly like the other
pure value / cost-recovery engines. The outcome metrics here are unitless rates
and durations (recovery rate and overrun are fractions; cycle time is days), so
averaging them across projects is sound; this engine deliberately handles NO
money and never blends across currencies - that discipline lives in the
recovery engine that produces the recovery_rate fed in here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

# --------------------------------------------------------------------------- #
# Cohort labels + the adoption cut.
# --------------------------------------------------------------------------- #

#: Cohort label for projects that adopted the platform's change discipline.
COHORT_HIGH = "high"

#: Cohort label for projects that did not.
COHORT_LOW = "low"

#: The documented default cut: adoption score >= this is HIGH, below is LOW.
#: 0.5 is the midpoint of the [0, 1] score range - the point at which a project
#: is, on balance, using the discipline more than not. See the module docstring.
DEFAULT_ADOPTION_CUT = 0.5

# --------------------------------------------------------------------------- #
# Adoption-score blend weights + density saturation. Kept as module constants so
# a test can assert the blend and a service can introspect / tune it.
# --------------------------------------------------------------------------- #

#: Weight on activity density in the adoption blend.
DENSITY_WEIGHT = 0.5

#: Weight on the traceability ratio in the adoption blend. With
#: :data:`DENSITY_WEIGHT` these sum to 1 so the blend stays in [0, 1].
TRACEABILITY_WEIGHT = 0.5

#: Activity-per-change ratio at which density saturates to 1.0. A project that
#: logged this many assisted actions per change (or more) is treated as fully
#: engaged; past it, additional activity adds no further adoption credit. Chosen
#: conservatively: roughly a handful of assisted touches per change (notice,
#: clarify, digest, evidence, recovery) is what a disciplined change looks like.
DENSITY_SATURATION = 5.0

# --------------------------------------------------------------------------- #
# Outcome-metric direction. Each metric declares whether a higher value is the
# better outcome; the cohort delta's sign is interpreted through this.
# --------------------------------------------------------------------------- #

HIGHER_IS_BETTER = "higher_is_better"
LOWER_IS_BETTER = "lower_is_better"

#: Metric keys. These name the fields on :class:`ProjectAdoption` that carry an
#: outcome value and are reported one comparison each, in this order.
METRIC_RECOVERY_RATE = "recovery_rate"
METRIC_OVERRUN_PCT = "overrun_pct"
METRIC_AVG_CYCLE_DAYS = "avg_cycle_days"

#: The outcome metrics compared, each with its better-direction. Ordered so the
#: comparison tuple is deterministic. recovery_rate: collecting more of what you
#: were owed is better. overrun_pct / avg_cycle_days: overrunning less and
#: closing changes faster are better.
OUTCOME_METRICS: tuple[tuple[str, str], ...] = (
    (METRIC_RECOVERY_RATE, HIGHER_IS_BETTER),
    (METRIC_OVERRUN_PCT, LOWER_IS_BETTER),
    (METRIC_AVG_CYCLE_DAYS, LOWER_IS_BETTER),
)

# --------------------------------------------------------------------------- #
# Confidence vocabulary + cohort-size thresholds. The thresholds are on the
# SMALLER cohort's contributing-value count (min of high_n / low_n), since a
# comparison is only as strong as its weaker side.
# --------------------------------------------------------------------------- #

CONFIDENCE_NONE = "none"
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

#: Minimum contributing projects per cohort to claim ANY confidence. Below this
#: (including zero on either side) a comparison is :data:`CONFIDENCE_NONE` - one
#: project versus one project is an anecdote, not a benchmark.
MIN_N_LOW = 2

#: Minimum per cohort for :data:`CONFIDENCE_MEDIUM`.
MIN_N_MEDIUM = 5

#: Minimum per cohort for :data:`CONFIDENCE_HIGH`.
MIN_N_HIGH = 10

#: Confidence ordering, weakest first, so the overall confidence can be taken as
#: the minimum across comparisons.
CONFIDENCE_ORDER: tuple[str, ...] = (
    CONFIDENCE_NONE,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)

# --------------------------------------------------------------------------- #
# Quantum for the adoption score / means we report.
# --------------------------------------------------------------------------- #

#: Four-decimal-place quantum for the adoption score and the cohort means, so
#: identical inputs always yield identical floats and a frontend can format them
#: without surprise.
FOURPLACES = Decimal("0.0001")


def _quantize4(value: float) -> float:
    """Round *value* to four decimal places, half-up, returned as a float.

    Goes through :class:`Decimal` so the rounding is exact and deterministic
    rather than subject to binary-float representation, then back to ``float``
    because the adoption score and metric means are unitless ratios / durations
    (not money) and are reported as plain floats.
    """
    return float(Decimal(repr(value)).quantize(FOURPLACES, rounding=ROUND_HALF_UP))


def _clamp01(value: float) -> float:
    """Clamp *value* into the closed unit interval [0.0, 1.0]."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


@dataclass(frozen=True)
class ProjectAdoption:
    """Present-state projection of one project's adoption + outcome facts.

    The integrator builds this per project from existing data (see the wiring
    note): ``activity_count`` is how many assisted change-related actions the
    project logged, ``change_count`` how many changes it had, and
    ``traceable_change_count`` how many of those changes reached a traceable /
    well-evidenced state. The three outcome metrics are OPTIONAL (``None`` when
    the project has no value for them - for example a project that was never
    entitled to recover anything has no ``recovery_rate``): a ``None`` metric is
    excluded from the cohort mean rather than counted as zero.

    The outcome metrics are unitless rates / durations, never money:
    ``recovery_rate`` and ``overrun_pct`` are fractions (0.69 means 69%, not
    69); ``avg_cycle_days`` is a mean duration in days. ``project_id`` is an
    opaque identifier carried through to the per-project score.
    """

    project_id: str
    activity_count: int
    change_count: int
    traceable_change_count: int
    recovery_rate: Decimal | None = None
    overrun_pct: Decimal | None = None
    avg_cycle_days: float | None = None


@dataclass(frozen=True)
class ProjectScore:
    """One project's adoption score and the cohort it falls in.

    ``adoption`` is the blended score in ``[0, 1]`` (four decimal places);
    ``cohort`` is :data:`COHORT_HIGH` or :data:`COHORT_LOW` at the cut that was
    applied.
    """

    project_id: str
    adoption: float
    cohort: str


@dataclass(frozen=True)
class CohortComparison:
    """High-vs-low comparison of the two cohorts on one outcome metric.

    ``metric`` is the metric key (one of :data:`METRIC_RECOVERY_RATE` /
    :data:`METRIC_OVERRUN_PCT` / :data:`METRIC_AVG_CYCLE_DAYS`).
    ``high_mean`` / ``low_mean`` are the mean of that metric over the projects in
    each cohort that HAD a value (``None`` values excluded), or ``None`` when no
    project in the cohort had one. ``high_n`` / ``low_n`` are those contributing
    counts. ``delta`` is ``high_mean - low_mean`` (``None`` if either mean is
    ``None``); ``higher_is_better`` records the metric's direction and
    ``favours_high`` is ``True`` when the sign of the delta favours the
    high-adoption cohort under that direction (``None`` when ``delta`` is
    ``None`` or exactly zero). ``confidence`` is this comparison's confidence
    from the smaller cohort's contributing count.
    """

    metric: str
    high_mean: float | None
    low_mean: float | None
    delta: float | None
    high_n: int
    low_n: int
    higher_is_better: bool
    favours_high: bool | None
    confidence: str


@dataclass(frozen=True)
class AdoptionBenchmark:
    """The portfolio's adoption benchmark: per-project scores + comparisons.

    ``project_scores`` is one :class:`ProjectScore` per input project, ordered
    by descending adoption then ``project_id`` so the heaviest adopters lead and
    ties are stable. ``comparisons`` is one :class:`CohortComparison` per outcome
    metric, in :data:`OUTCOME_METRICS` order. ``confidence`` is the overall
    confidence: the WEAKEST of the per-comparison confidences (you are only as
    confident as your flimsiest column), or :data:`CONFIDENCE_NONE` when there
    are no comparisons. ``high_count`` / ``low_count`` are how many projects fell
    in each cohort.
    """

    project_scores: tuple[ProjectScore, ...]
    comparisons: tuple[CohortComparison, ...]
    confidence: str
    high_count: int = 0
    low_count: int = 0


def traceability_ratio(traceable_change_count: int, change_count: int) -> float:
    """Share of a project's changes that became traceable, in ``[0, 1]``.

    ``traceable_change_count / change_count``, guarded: a project with zero (or
    negative) changes has a ratio of 0 - you cannot have traced changes you did
    not have, and crediting traceability to a project with no changes would
    invent adoption. The result is clamped to ``[0, 1]`` so a miscount that
    reports more traceable changes than total changes cannot push the ratio
    above 1.
    """
    if change_count <= 0:
        return 0.0
    return _clamp01(traceable_change_count / change_count)


def activity_density(
    activity_count: int,
    change_count: int,
    *,
    saturation: float = DENSITY_SATURATION,
) -> float:
    """Saturating assisted-activity-per-change ratio, in ``[0, 1]``.

    Computes ``(activity_count / change_count) / saturation`` clamped to
    ``[0, 1]``: a project that logged *saturation* assisted actions per change
    (or more) scores a full 1.0, and below that the credit scales linearly.
    Guarded both ways - zero (or negative) changes yields 0 (no changes means
    no change activity to credit, regardless of how many stray actions were
    logged), and a non-positive *saturation* would be a misconfiguration so it
    also yields 0 rather than dividing by zero. Negative activity is floored at
    zero.
    """
    if change_count <= 0:
        return 0.0
    if saturation <= 0.0:
        return 0.0
    acts = activity_count if activity_count > 0 else 0
    return _clamp01((acts / change_count) / saturation)


def adoption_score(
    project: ProjectAdoption,
    *,
    saturation: float = DENSITY_SATURATION,
    density_weight: float = DENSITY_WEIGHT,
    traceability_weight: float = TRACEABILITY_WEIGHT,
) -> float:
    """Blended adoption score for one project, a float in ``[0, 1]``.

    The documented blend is a weighted average of two guarded ratios:
    :func:`activity_density` (how much assisted change work the project logged
    per change, saturating) and :func:`traceability_ratio` (the share of its
    changes that became traceable). With the default equal weights this is
    simply their mean. The weights are normalised by their sum so any positive
    pair behaves sensibly and the result stays in ``[0, 1]``; if both weights
    are non-positive the score is 0. Every underlying ratio guards
    divide-by-zero, so a project with zero changes or zero activity scores 0
    rather than raising. The result is quantized to four decimal places so it is
    deterministic.
    """
    density = activity_density(project.activity_count, project.change_count, saturation=saturation)
    trace = traceability_ratio(project.traceable_change_count, project.change_count)

    weight_sum = density_weight + traceability_weight
    if weight_sum <= 0.0:
        return 0.0
    blended = (density * density_weight + trace * traceability_weight) / weight_sum
    return _quantize4(_clamp01(blended))


def cohort_for_score(adoption: float, *, cut: float = DEFAULT_ADOPTION_CUT) -> str:
    """Classify an *adoption* score into the HIGH / LOW cohort at *cut*.

    ``adoption >= cut`` is :data:`COHORT_HIGH`; below it is :data:`COHORT_LOW`.
    The comparison is inclusive at the cut so a project sitting exactly on the
    boundary counts as an adopter.
    """
    return COHORT_HIGH if adoption >= cut else COHORT_LOW


def median_cut(scores: Iterable[float]) -> float:
    """Median of *scores*, for callers who want to split at their own median.

    Returns the median adoption score, suitable to pass as ``cut`` to
    :func:`compute_adoption_benchmark` when a portfolio clusters and the fixed
    :data:`DEFAULT_ADOPTION_CUT` would put every project on one side. For an even
    count the median is the mean of the two middle values; for empty input it is
    :data:`DEFAULT_ADOPTION_CUT` (there is nothing to split, so fall back to the
    documented default). The result is quantized to four places.
    """
    ordered = sorted(scores)
    n = len(ordered)
    if n == 0:
        return DEFAULT_ADOPTION_CUT
    mid = n // 2
    if n % 2 == 1:
        median = ordered[mid]
    else:
        median = (ordered[mid - 1] + ordered[mid]) / 2.0
    return _quantize4(median)


def _confidence_for(min_n: int) -> str:
    """Map the smaller cohort's contributing count to a confidence band.

    ``min_n`` is ``min(high_n, low_n)``. Below :data:`MIN_N_LOW` (including
    zero) there is :data:`CONFIDENCE_NONE`; the thresholds then step up through
    low / medium / high. See the module docstring for the rationale.
    """
    if min_n < MIN_N_LOW:
        return CONFIDENCE_NONE
    if min_n < MIN_N_MEDIUM:
        return CONFIDENCE_LOW
    if min_n < MIN_N_HIGH:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_HIGH


def _weakest(confidences: Iterable[str]) -> str:
    """Return the weakest confidence in *confidences* by :data:`CONFIDENCE_ORDER`.

    Empty input is :data:`CONFIDENCE_NONE`. An unrecognised value is treated as
    the weakest (index 0) so a junk band can never inflate the overall figure.
    """
    rank = {label: i for i, label in enumerate(CONFIDENCE_ORDER)}
    weakest_rank: int | None = None
    for c in confidences:
        r = rank.get(c, 0)
        if weakest_rank is None or r < weakest_rank:
            weakest_rank = r
    if weakest_rank is None:
        return CONFIDENCE_NONE
    return CONFIDENCE_ORDER[weakest_rank]


def _metric_value(project: ProjectAdoption, metric: str) -> float | None:
    """Read one outcome *metric* off a project as a float, or ``None``.

    The metric fields are stored as ``Decimal | None`` (rates) or ``float |
    None`` (cycle days). Decimals are converted to float for averaging - these
    are unitless ratios / durations, never money, so float averaging is sound.
    A missing value stays ``None`` so the caller can exclude it from the mean.
    """
    raw = getattr(project, metric)
    if raw is None:
        return None
    return float(raw)


def _mean_ignoring_none(values: list[float | None]) -> tuple[float | None, int]:
    """Mean of the non-``None`` *values* and how many contributed.

    Returns ``(mean, n)`` where ``n`` is the count of non-``None`` values and
    ``mean`` is their quantized arithmetic mean, or ``(None, 0)`` when none
    contributed. Excluding ``None`` from BOTH the numerator and the count is the
    honest behaviour: a project with no recovery rate must not drag its cohort
    toward zero.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None, 0
    return _quantize4(sum(present) / len(present)), len(present)


def _favours_high(delta: float | None, higher_is_better: bool) -> bool | None:
    """Whether the *delta*'s sign favours the high-adoption cohort.

    ``delta`` is ``high_mean - low_mean``. When higher is better, a positive
    delta (adopters scored higher) favours the high cohort; when lower is better
    a negative delta (adopters' figure is lower, e.g. less overrun) favours it.
    Returns ``None`` when ``delta`` is ``None`` or exactly zero (a tie favours
    neither side).
    """
    if delta is None or delta == 0.0:
        return None
    if higher_is_better:
        return delta > 0.0
    return delta < 0.0


def _compare_metric(
    metric: str,
    higher_is_better: bool,
    high: list[ProjectAdoption],
    low: list[ProjectAdoption],
) -> CohortComparison:
    """Build one :class:`CohortComparison` for *metric* over the two cohorts."""
    high_mean, high_n = _mean_ignoring_none([_metric_value(p, metric) for p in high])
    low_mean, low_n = _mean_ignoring_none([_metric_value(p, metric) for p in low])

    if high_mean is None or low_mean is None:
        delta: float | None = None
    else:
        delta = _quantize4(high_mean - low_mean)

    # Confidence rests on the SMALLER contributing cohort; if either side
    # contributed no values for this metric the comparison is unsupported.
    if high_n == 0 or low_n == 0:
        confidence = CONFIDENCE_NONE
    else:
        confidence = _confidence_for(min(high_n, low_n))

    return CohortComparison(
        metric=metric,
        high_mean=high_mean,
        low_mean=low_mean,
        delta=delta,
        high_n=high_n,
        low_n=low_n,
        higher_is_better=higher_is_better,
        favours_high=_favours_high(delta, higher_is_better),
        confidence=confidence,
    )


def compute_adoption_benchmark(
    projects: Iterable[ProjectAdoption],
    *,
    cut: float = DEFAULT_ADOPTION_CUT,
    saturation: float = DENSITY_SATURATION,
    density_weight: float = DENSITY_WEIGHT,
    traceability_weight: float = TRACEABILITY_WEIGHT,
) -> AdoptionBenchmark:
    """Score adoption per project and compare the high / low cohorts.

    Each project is scored with :func:`adoption_score` and placed in the HIGH or
    LOW cohort at *cut* (:data:`DEFAULT_ADOPTION_CUT` by default; pass
    :func:`median_cut` of the scores for a median split). For each metric in
    :data:`OUTCOME_METRICS` the two cohorts' means are compared, with ``None``
    values excluded from both the mean and the contributing count, and a
    confidence derived from the smaller cohort's contributing count. The overall
    confidence is the weakest comparison's.

    The per-project scores are returned ordered by descending adoption then
    ``project_id``; the comparisons are in metric order. The computation is pure
    and deterministic: identical input always yields an identical result. Empty
    input yields no scores, one comparison per metric with ``None`` means and
    :data:`CONFIDENCE_NONE`, and an overall :data:`CONFIDENCE_NONE`.
    """
    projects = list(projects)

    scores: list[ProjectScore] = []
    high: list[ProjectAdoption] = []
    low: list[ProjectAdoption] = []
    for p in projects:
        score = adoption_score(
            p,
            saturation=saturation,
            density_weight=density_weight,
            traceability_weight=traceability_weight,
        )
        cohort = cohort_for_score(score, cut=cut)
        scores.append(ProjectScore(project_id=p.project_id, adoption=score, cohort=cohort))
        if cohort == COHORT_HIGH:
            high.append(p)
        else:
            low.append(p)

    scores.sort(key=lambda s: (-s.adoption, s.project_id))

    comparisons = tuple(
        _compare_metric(metric, higher_is_better == HIGHER_IS_BETTER, high, low)
        for metric, higher_is_better in OUTCOME_METRICS
    )

    overall = _weakest(c.confidence for c in comparisons) if comparisons else CONFIDENCE_NONE

    return AdoptionBenchmark(
        project_scores=tuple(scores),
        comparisons=comparisons,
        confidence=overall,
        high_count=len(high),
        low_count=len(low),
    )


__all__ = [
    "COHORT_HIGH",
    "COHORT_LOW",
    "DEFAULT_ADOPTION_CUT",
    "DENSITY_WEIGHT",
    "TRACEABILITY_WEIGHT",
    "DENSITY_SATURATION",
    "HIGHER_IS_BETTER",
    "LOWER_IS_BETTER",
    "METRIC_RECOVERY_RATE",
    "METRIC_OVERRUN_PCT",
    "METRIC_AVG_CYCLE_DAYS",
    "OUTCOME_METRICS",
    "CONFIDENCE_NONE",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_HIGH",
    "MIN_N_LOW",
    "MIN_N_MEDIUM",
    "MIN_N_HIGH",
    "CONFIDENCE_ORDER",
    "FOURPLACES",
    "ProjectAdoption",
    "ProjectScore",
    "CohortComparison",
    "AdoptionBenchmark",
    "traceability_ratio",
    "activity_density",
    "adoption_score",
    "cohort_for_score",
    "median_cut",
    "compute_adoption_benchmark",
]
