# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure "value realized" composition.

Every other engine in this module answers one slice of the change-and-AI value
question - how much cost a change committed, how much of an entitlement was
recovered, how many admin hours assisted actions gave back. This engine does no
new measurement of its own; it composes those already-computed figures into a
single project (and portfolio) "value realized" summary that a dashboard can
show without re-deriving anything. The honesty of the roll-up is the whole
point: it never blends currencies, it never invents a figure for work it cannot
account for, and every headline carries a confidence label so a low-evidence
number is not dressed up as a firm one.

What it composes
----------------
* ``overrun_exposure_managed`` - the committed cost of approved change impacts,
  i.e. the budget movement the project is now controlling rather than
  discovering late. Reported PER CURRENCY.
* ``recovered_total`` / ``absorbed_total`` / ``recovery_rate`` - the
  cost-recovery position, summarised straight from the recovery ledger figures,
  PER CURRENCY. The rate is ``recovered / chargeable`` as a Decimal fraction in
  ``[0, 1]`` to four places, or ``None`` when nothing was chargeable (an honest
  undefined ratio, never a misleading zero).
* ``estimated_hours_saved`` - the admin time given back, a single currency-
  independent figure in hours to two places (the hours-saved engine already did
  the minute-factor work; this only carries the total).
* ``dispute_risk_reduction`` - a documented PROXY in ``[0, 1]`` for how much
  dispute exposure the firm's traceability + recovery posture has bought down.
  It is a derived indicator, not a measured probability, and is labelled as
  such.

Money discipline (identical to the recovery + back-charge engines)
------------------------------------------------------------------
Every money total is :class:`decimal.Decimal`, summed exactly and quantized to
two places half-up only at the boundary. Amounts in different currency codes are
NEVER summed together: each money figure this engine returns is scoped to a
single currency, and a project (or portfolio) spanning two currencies yields two
:class:`CurrencyValue` rows. The currency-independent headlines (hours saved, the
risk proxy, confidence labels) are the only cross-currency figures, and they
carry no money denominated in a single code.

Rate form (documented and exact)
--------------------------------
A recovery rate is ``recovered / chargeable`` as a Decimal FRACTION in
``[0, 1]`` - 0.6900 means 69%, not 69 - quantized to four places
(:data:`RATEPLACES`) half-up, clamped to ``[0, 1]``. Identical inputs always
yield an identical rate. This mirrors
:func:`app.modules.cost_recovery.recovery_analytics.recovery_rate` exactly; the
convention is duplicated locally (not imported) to keep this engine a
self-contained pure module.

Confidence (honest low-n rule, documented thresholds)
-----------------------------------------------------
Each headline carries one of ``"high"`` / ``"medium"`` / ``"low"`` / ``"none"``
derived ONLY from how much evidence stands behind it - never from whether the
number looks good. The sample count ``n`` is the number of records the figure
rests on (approved impacts for exposure, chargeable items for recovery,
saving-bearing activity rows for hours). The cut is deliberately conservative:

* ``none``   - ``n == 0``: there is nothing to be confident about.
* ``low``    - ``1 <= n < 3``: one or two records; directional at best.
* ``medium`` - ``3 <= n < 10``: enough to be indicative.
* ``high``   - ``n >= 10``: a body of records.

The thresholds live in :data:`CONFIDENCE_LOW_MIN` / :data:`CONFIDENCE_MEDIUM_MIN`
/ :data:`CONFIDENCE_HIGH_MIN` so a service can introspect them and a test can
assert the boundaries.

No database, no ORM, no ``app.*`` imports - stdlib plus :class:`decimal.Decimal`
only - so it unit-tests on the local Python 3.11 runner exactly like the
back-charge, apportionment, recovery-analytics and hours-saved engines. A thin
service layer (written separately by the integrator) gathers approved impacts,
recovery-ledger rows, the hours-saved total, the cost-position percentile and an
activity count, projects them onto the input value objects below, and calls in
here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# Money + rate quanta. Duplicated as local constants (not imported) so this
# engine stays self-contained; the values match recovery_analytics.TWOPLACES /
# RATEPLACES exactly.
# --------------------------------------------------------------------------- #

#: Two-decimal-place quantum for money rounding (matches recovery_analytics.TWOPLACES).
TWOPLACES = Decimal("0.01")

#: Four-decimal-place quantum for rates and the risk proxy (a fraction in [0, 1]).
RATEPLACES = Decimal("0.0001")

_ZERO = Decimal("0")
_ONE = Decimal("1")

# --------------------------------------------------------------------------- #
# Confidence labels + the documented low-n thresholds. See the module docstring
# for the rationale; kept as module-level constants so a service can introspect
# them and a test can assert the exact boundaries.
# --------------------------------------------------------------------------- #

CONFIDENCE_NONE = "none"
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

#: Smallest sample that earns a label above ``none``.
CONFIDENCE_LOW_MIN = 1
#: Smallest sample that earns ``medium``.
CONFIDENCE_MEDIUM_MIN = 3
#: Smallest sample that earns ``high``.
CONFIDENCE_HIGH_MIN = 10

# --------------------------------------------------------------------------- #
# Dispute-risk-reduction proxy weights. The proxy is a documented blend of two
# levers the change-and-AI report identifies as moving dispute exposure: how much
# of the entitlement the firm actually recovered, and how traceable its records
# are. Both are fractions in [0, 1]; the blend is a fixed convex combination so
# the result also lands in [0, 1]. The weights are exposed for introspection.
# --------------------------------------------------------------------------- #

#: Weight on the recovery rate in the dispute-risk-reduction proxy.
RISK_WEIGHT_RECOVERY = Decimal("0.6")
#: Weight on the traceability share in the dispute-risk-reduction proxy.
RISK_WEIGHT_TRACEABILITY = Decimal("0.4")


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding.

    Identical behaviour to ``recovery_analytics.quantize_money`` - kept local so
    this module imports nothing from the rest of the app.
    """
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def quantize_rate(rate: Decimal) -> Decimal:
    """Round a *rate* / proxy (a fraction in [0, 1]) to four places, half-up."""
    return rate.quantize(RATEPLACES, rounding=ROUND_HALF_UP)


def recovery_rate(recovered: Decimal, chargeable: Decimal) -> Decimal | None:
    """Recovered over chargeable as a quantized fraction in ``[0, 1]``, or ``None``.

    Mirrors :func:`app.modules.cost_recovery.recovery_analytics.recovery_rate`:
    when *chargeable* is zero or negative the ratio is undefined and ``None`` is
    returned rather than a misleading zero. The result is clamped to ``[0, 1]``
    so an over-recovery cannot report a rate above 100%, and quantized to
    :data:`RATEPLACES`.
    """
    if chargeable <= _ZERO:
        return None
    rate = recovered / chargeable
    if rate < _ZERO:
        rate = _ZERO
    elif rate > _ONE:
        rate = _ONE
    return quantize_rate(rate)


def confidence_for(n: int) -> str:
    """Label the confidence in a figure resting on *n* records.

    Pure function of the sample size, by the documented low-n rule (see the
    module docstring): ``n <= 0`` -> :data:`CONFIDENCE_NONE`; ``1..2`` ->
    :data:`CONFIDENCE_LOW`; ``3..9`` -> :data:`CONFIDENCE_MEDIUM`; ``>= 10`` ->
    :data:`CONFIDENCE_HIGH`. A negative count is treated as zero.
    """
    if n < CONFIDENCE_LOW_MIN:
        return CONFIDENCE_NONE
    if n < CONFIDENCE_MEDIUM_MIN:
        return CONFIDENCE_LOW
    if n < CONFIDENCE_HIGH_MIN:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_HIGH


#: Confidence labels ordered weakest-to-strongest, so a portfolio roll-up can
#: take the minimum (the most cautious) across its projects by index.
_CONFIDENCE_ORDER: tuple[str, ...] = (
    CONFIDENCE_NONE,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_HIGH,
)
_CONFIDENCE_RANK: dict[str, int] = {label: i for i, label in enumerate(_CONFIDENCE_ORDER)}


def weakest_confidence(labels: Iterable[str]) -> str:
    """Return the most cautious (weakest) of several confidence *labels*.

    Used to roll a per-project confidence up to a portfolio: the portfolio is
    only as trustworthy as its least-supported member, so the minimum on the
    :data:`_CONFIDENCE_ORDER` scale is taken. An empty input, or labels that are
    all unrecognised, yields :data:`CONFIDENCE_NONE`. Unrecognised individual
    labels are treated as :data:`CONFIDENCE_NONE` (rank 0).
    """
    worst = len(_CONFIDENCE_ORDER) - 1
    seen = False
    for label in labels:
        seen = True
        rank = _CONFIDENCE_RANK.get(label, 0)
        if rank < worst:
            worst = rank
    if not seen:
        return CONFIDENCE_NONE
    return _CONFIDENCE_ORDER[worst]


# --------------------------------------------------------------------------- #
# Input value objects. The integrator maps already-computed records onto these;
# the engine never imports the ORM. Each is frozen so a summary is reproducible
# from its inputs.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ImpactInput:
    """One approved change's committed impact.

    ``kind`` is a free-text category (for example an RFI / CO type) carried for
    context only - it does not affect the math. ``committed_cost`` is the budget
    movement the approved change committed, denominated in ``currency``;
    ``schedule_days`` is the committed schedule movement in days (carried as a
    headline of programme exposure managed, never mixed into money). Both are
    :class:`decimal.Decimal`. Only impacts the caller has already filtered to
    "approved" should be passed in - this engine does not re-judge approval.
    """

    kind: str
    currency: str
    committed_cost: Decimal
    schedule_days: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass(frozen=True)
class RecoveryInput:
    """One currency's slice of the recovery ledger, already summarised.

    ``chargeable`` is the amount judged recoverable, ``recovered`` is what was
    collected, and ``absorbed`` is the chargeable the project gave up on - all
    denominated in ``currency`` and all :class:`decimal.Decimal`. These mirror
    the totals :class:`app.modules.cost_recovery.recovery_analytics.CurrencyRecovery`
    already produces; the integrator can pass one ``RecoveryInput`` per currency
    straight from that, or one per ledger row (they aggregate identically here).
    """

    currency: str
    chargeable: Decimal
    recovered: Decimal
    absorbed: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass(frozen=True)
class HoursSavedInput:
    """The admin hours given back, already totalled by the hours-saved engine.

    ``hours`` is a :class:`decimal.Decimal` count of hours (the output of
    :func:`app.modules.value.time_saved.total_hours`). ``sample`` is how many
    saving-bearing activity rows the figure rests on, used only to label the
    figure's confidence; it defaults to zero (unknown -> ``none``).
    """

    hours: Decimal
    sample: int = 0


@dataclass(frozen=True)
class BenchmarkInput:
    """The project's cost-position percentile, if one was computed.

    ``percentile`` is a float in ``[0, 100]`` (or ``None`` when no benchmark was
    available). It is OPTIONAL context for the dashboard and a secondary input to
    the dispute-risk proxy's traceability term only when a recovery rate is
    absent; it is never turned into money.
    """

    percentile: float | None = None


@dataclass(frozen=True)
class ActivityInput:
    """Activity-volume context for the project.

    ``count`` is the number of activity rows seen (optional, for the dashboard's
    "this is computed over N actions" line and as the sample backing the
    hours-saved confidence when :class:`HoursSavedInput` carries none).
    """

    count: int = 0


# --------------------------------------------------------------------------- #
# Output value objects.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CurrencyValue:
    """The money side of a value summary, scoped to one currency (never blended).

    ``overrun_exposure_managed`` is the committed cost of approved impacts in
    this currency; ``recovered_total`` / ``absorbed_total`` come straight from
    the recovery figures; ``chargeable_total`` is carried so the rate is
    auditable; ``recovery_rate`` is ``recovered / chargeable`` as a fraction in
    ``[0, 1]`` (or ``None`` when nothing was chargeable). ``schedule_days_managed``
    is the committed schedule movement in days for this currency's impacts - a
    programme figure kept beside the money, never folded into it. ``impact_count``
    and ``recovery_item_count`` are the samples behind the figures.
    """

    currency: str
    overrun_exposure_managed: Decimal
    chargeable_total: Decimal
    recovered_total: Decimal
    absorbed_total: Decimal
    recovery_rate: Decimal | None
    schedule_days_managed: Decimal
    impact_count: int
    recovery_item_count: int


@dataclass(frozen=True)
class ValueSummary:
    """A project's (or portfolio's) composed "value realized" position.

    The money lives in :attr:`by_currency` - one :class:`CurrencyValue` per
    currency, never blended, ordered by descending exposure then currency code.
    The currency-independent headlines are:

    * ``estimated_hours_saved`` - hours given back (Decimal, two places);
    * ``dispute_risk_reduction`` - the documented proxy in ``[0, 1]`` (four
      places), or ``None`` when there is no evidence to base it on;
    * a confidence label per headline metric:
      ``exposure_confidence`` / ``recovery_confidence`` / ``hours_confidence`` /
      ``risk_confidence``, each one of ``high`` / ``medium`` / ``low`` / ``none``.

    ``primary_currency`` is the currency carrying the greatest exposure (ties
    broken alphabetically), ``""`` when there is no money at all. ``cost_position_percentile``
    echoes the benchmark input for the dashboard. ``impact_count`` /
    ``recovery_item_count`` / ``hours_sample`` / ``activity_count`` are the
    samples the summary rests on.
    """

    by_currency: tuple[CurrencyValue, ...]
    primary_currency: str
    estimated_hours_saved: Decimal
    dispute_risk_reduction: Decimal | None
    exposure_confidence: str
    recovery_confidence: str
    hours_confidence: str
    risk_confidence: str
    cost_position_percentile: float | None
    impact_count: int
    recovery_item_count: int
    hours_sample: int
    activity_count: int


# --------------------------------------------------------------------------- #
# Internal accumulators (mutable; Decimal sums stay exact).
# --------------------------------------------------------------------------- #


@dataclass
class _ImpactAcc:
    """Approved-impact accumulator for one currency."""

    count: int = 0
    committed_cost: Decimal = field(default_factory=lambda: Decimal("0"))
    schedule_days: Decimal = field(default_factory=lambda: Decimal("0"))


@dataclass
class _RecoveryAcc:
    """Recovery-ledger accumulator for one currency."""

    count: int = 0
    chargeable: Decimal = field(default_factory=lambda: Decimal("0"))
    recovered: Decimal = field(default_factory=lambda: Decimal("0"))
    absorbed: Decimal = field(default_factory=lambda: Decimal("0"))


def _traceability_share_from_percentile(percentile: float | None) -> Decimal | None:
    """Map a cost-position *percentile* (0..100) to a [0, 1] traceability proxy.

    Used only as a fallback term for the dispute-risk proxy when no recovery rate
    is available. A higher percentile (a better-evidenced, better-controlled cost
    position) implies more traceable records, so the share is ``percentile / 100``
    clamped to ``[0, 1]``. ``None`` in, ``None`` out. The conversion goes through
    :class:`str` so a binary float never pollutes the Decimal.
    """
    if percentile is None:
        return None
    share = Decimal(str(percentile)) / Decimal("100")
    if share < _ZERO:
        return _ZERO
    if share > _ONE:
        return _ONE
    return share


def dispute_risk_reduction(
    recovery_rate_value: Decimal | None,
    traceability_share: Decimal | None,
) -> Decimal | None:
    """Compose the documented dispute-risk-reduction proxy in ``[0, 1]``.

    The proxy is a fixed convex blend of two levers the change-and-AI report ties
    to dispute exposure: the recovery rate (weight
    :data:`RISK_WEIGHT_RECOVERY`) and a traceability share (weight
    :data:`RISK_WEIGHT_TRACEABILITY`). Because the weights sum to one and each
    term is in ``[0, 1]``, the result is in ``[0, 1]`` and is quantized to
    :data:`RATEPLACES`.

    It is deliberately tolerant of missing terms, because a young project often
    has one signal and not the other:

    * both present  -> the full weighted blend;
    * only one term -> that term alone (its weight is renormalised to one), so a
      single available lever still yields a proxy rather than ``None``;
    * neither       -> ``None`` (nothing to base a figure on).

    It is a derived INDICATOR, not a measured probability; callers should label
    it as such. The value rises with both better recovery and better
    traceability, which is the directional claim the report supports.
    """
    have_recovery = recovery_rate_value is not None
    have_trace = traceability_share is not None
    if not have_recovery and not have_trace:
        return None
    if have_recovery and not have_trace:
        return quantize_rate(_clamp_unit(recovery_rate_value))  # type: ignore[arg-type]
    if have_trace and not have_recovery:
        return quantize_rate(_clamp_unit(traceability_share))  # type: ignore[arg-type]
    blended = (
        RISK_WEIGHT_RECOVERY * _clamp_unit(recovery_rate_value)  # type: ignore[arg-type]
        + RISK_WEIGHT_TRACEABILITY * _clamp_unit(traceability_share)  # type: ignore[arg-type]
    )
    return quantize_rate(_clamp_unit(blended))


def _clamp_unit(value: Decimal) -> Decimal:
    """Clamp a Decimal to the inclusive unit interval ``[0, 1]``."""
    if value < _ZERO:
        return _ZERO
    if value > _ONE:
        return _ONE
    return value


def _build_currency_rows(
    impacts: dict[str, _ImpactAcc],
    recoveries: dict[str, _RecoveryAcc],
) -> tuple[CurrencyValue, ...]:
    """Merge per-currency impact and recovery accumulators into output rows.

    A currency appears if it has either an approved impact or a recovery slice.
    Rows are ordered by descending exposure managed, then by currency code, so
    the heaviest exposure leads and ties are stable.
    """
    currencies = set(impacts) | set(recoveries)
    rows: list[CurrencyValue] = []
    for currency in currencies:
        imp = impacts.get(currency, _ImpactAcc())
        rec = recoveries.get(currency, _RecoveryAcc())
        rows.append(
            CurrencyValue(
                currency=currency,
                overrun_exposure_managed=quantize_money(imp.committed_cost),
                chargeable_total=quantize_money(rec.chargeable),
                recovered_total=quantize_money(rec.recovered),
                absorbed_total=quantize_money(rec.absorbed),
                # Rate from the EXACT pre-quantize sums, so money rounding never
                # perturbs the ratio.
                recovery_rate=recovery_rate(rec.recovered, rec.chargeable),
                schedule_days_managed=imp.schedule_days,
                impact_count=imp.count,
                recovery_item_count=rec.count,
            )
        )
    rows.sort(key=lambda r: (-r.overrun_exposure_managed, r.currency))
    return tuple(rows)


def compose_value_summary(
    impacts: Sequence[ImpactInput],
    recoveries: Sequence[RecoveryInput],
    hours: HoursSavedInput | None = None,
    benchmark: BenchmarkInput | None = None,
    activity: ActivityInput | None = None,
) -> ValueSummary:
    """Compose a project's "value realized" summary from already-computed inputs.

    Sums approved-impact committed cost and schedule days per currency, carries
    the recovery figures per currency and derives each currency's recovery rate,
    and rolls the currency-independent headlines (hours saved, the dispute-risk
    proxy) up across the whole project. Currencies are NEVER blended: the money
    lives in one :class:`CurrencyValue` per currency.

    Confidence is assigned from sample sizes by :func:`confidence_for`:

    * exposure - number of approved impacts;
    * recovery - number of recovery items (the chargeable-bearing rows);
    * hours    - the hours-saved sample (falling back to the activity count when
      the hours input carries no sample of its own);
    * risk     - the smaller of the recovery and exposure samples, since the
      proxy leans on both posture signals.

    The dispute-risk proxy blends the project's overall recovery rate (computed
    from the summed chargeable / recovered across all currencies, since the rate
    is a unitless fraction and so is currency-agnostic) with a traceability share
    taken from the benchmark percentile when present. With neither signal the
    proxy is ``None`` and its confidence is ``none``. Pure and deterministic:
    identical input always yields an identical summary.
    """
    impact_acc: dict[str, _ImpactAcc] = defaultdict(_ImpactAcc)
    for imp in impacts:
        acc = impact_acc[imp.currency]
        acc.count += 1
        acc.committed_cost += imp.committed_cost
        acc.schedule_days += imp.schedule_days

    recovery_acc: dict[str, _RecoveryAcc] = defaultdict(_RecoveryAcc)
    for rec in recoveries:
        racc = recovery_acc[rec.currency]
        racc.count += 1
        racc.chargeable += rec.chargeable
        racc.recovered += rec.recovered
        racc.absorbed += rec.absorbed

    by_currency = _build_currency_rows(impact_acc, recovery_acc)
    primary_currency = by_currency[0].currency if by_currency else ""

    # Sample sizes (counts, never money) drive the confidence labels.
    impact_count = sum(a.count for a in impact_acc.values())
    recovery_item_count = sum(a.count for a in recovery_acc.values())

    # Hours headline + its sample. The hours input is the source of truth for the
    # figure; its sample (else the activity count) backs the confidence.
    hours_value = quantize_money(hours.hours) if hours is not None else Decimal("0.00")
    hours_sample = hours.sample if hours is not None else 0
    activity_count = activity.count if activity is not None else 0
    effective_hours_sample = hours_sample if hours_sample > 0 else activity_count

    # Overall recovery rate for the risk proxy: a unitless fraction, so it may be
    # taken across the summed chargeable / recovered of every currency without
    # blending money in a way that matters (the ratio is currency-agnostic).
    total_chargeable = sum((a.chargeable for a in recovery_acc.values()), _ZERO)
    total_recovered = sum((a.recovered for a in recovery_acc.values()), _ZERO)
    overall_rate = recovery_rate(total_recovered, total_chargeable)

    percentile = benchmark.percentile if benchmark is not None else None
    traceability_share = _traceability_share_from_percentile(percentile)
    risk_proxy = dispute_risk_reduction(overall_rate, traceability_share)

    exposure_confidence = confidence_for(impact_count)
    recovery_confidence = confidence_for(recovery_item_count)
    hours_confidence = confidence_for(effective_hours_sample)
    # The risk proxy leans on both recovery and traceability posture; label it by
    # the weaker of the two evidence bases it actually used. When the proxy rests
    # only on the benchmark (no recovery items) we fall back to the impact count
    # as the project-maturity proxy, but never above the recovery confidence when
    # recovery items exist.
    if risk_proxy is None:
        risk_confidence = CONFIDENCE_NONE
    elif recovery_item_count > 0:
        risk_confidence = confidence_for(min(recovery_item_count, max(impact_count, recovery_item_count)))
    else:
        risk_confidence = confidence_for(impact_count)

    return ValueSummary(
        by_currency=by_currency,
        primary_currency=primary_currency,
        estimated_hours_saved=hours_value,
        dispute_risk_reduction=risk_proxy,
        exposure_confidence=exposure_confidence,
        recovery_confidence=recovery_confidence,
        hours_confidence=hours_confidence,
        risk_confidence=risk_confidence,
        cost_position_percentile=percentile,
        impact_count=impact_count,
        recovery_item_count=recovery_item_count,
        hours_sample=hours_sample,
        activity_count=activity_count,
    )


def compose_portfolio_summary(
    per_project: Iterable[ValueSummary],
) -> ValueSummary:
    """Aggregate several project summaries into one portfolio summary.

    Money is summed PER CURRENCY across the projects and never blended across
    currency codes: every project's :class:`CurrencyValue` rows are folded into
    per-currency accumulators, exposure and the recovery figures add up, and each
    currency's portfolio recovery rate is recomputed from the summed exact totals
    (a rate cannot be averaged - 1/2 and 1/2 is 2/4, not the mean of two rates).

    The currency-independent headlines roll up too: hours saved sum; the
    dispute-risk proxy is recomputed from the portfolio-wide recovery rate so it
    stays a true blend rather than an average of per-project proxies; sample
    counts add. Confidence is the MORE CAUTIOUS of (the label implied by the
    pooled sample size) and (the weakest per-project label), so neither a large
    pool of weak projects nor one strong project alone can over-state the
    portfolio's confidence.

    Accepts any iterable of :class:`ValueSummary` (typically one per project from
    :func:`compose_value_summary`). Empty input yields an empty summary
    (no currencies, zero hours, a ``None`` proxy, all confidences ``none``).
    Pure and deterministic.
    """
    projects = list(per_project)

    cur_impacts: dict[str, _ImpactAcc] = defaultdict(_ImpactAcc)
    cur_recoveries: dict[str, _RecoveryAcc] = defaultdict(_RecoveryAcc)

    total_hours = Decimal("0")
    impact_count = 0
    recovery_item_count = 0
    hours_sample = 0
    activity_count = 0

    exposure_labels: list[str] = []
    recovery_labels: list[str] = []
    hours_labels: list[str] = []
    risk_labels: list[str] = []

    for proj in projects:
        for row in proj.by_currency:
            imp = cur_impacts[row.currency]
            imp.count += row.impact_count
            imp.committed_cost += row.overrun_exposure_managed
            imp.schedule_days += row.schedule_days_managed

            rec = cur_recoveries[row.currency]
            rec.count += row.recovery_item_count
            rec.chargeable += row.chargeable_total
            rec.recovered += row.recovered_total
            rec.absorbed += row.absorbed_total

        total_hours += proj.estimated_hours_saved
        impact_count += proj.impact_count
        recovery_item_count += proj.recovery_item_count
        hours_sample += proj.hours_sample
        activity_count += proj.activity_count

        exposure_labels.append(proj.exposure_confidence)
        recovery_labels.append(proj.recovery_confidence)
        hours_labels.append(proj.hours_confidence)
        risk_labels.append(proj.risk_confidence)

    by_currency = _build_currency_rows(cur_impacts, cur_recoveries)
    primary_currency = by_currency[0].currency if by_currency else ""

    # Portfolio recovery rate from the summed exact totals, then the proxy from
    # that rate. We carry no portfolio benchmark percentile (it is a per-project
    # position), so the proxy rests on the recovery rate alone here.
    total_chargeable = sum((a.chargeable for a in cur_recoveries.values()), _ZERO)
    total_recovered = sum((a.recovered for a in cur_recoveries.values()), _ZERO)
    overall_rate = recovery_rate(total_recovered, total_chargeable)
    risk_proxy = dispute_risk_reduction(overall_rate, None)

    effective_hours_sample = hours_sample if hours_sample > 0 else activity_count

    # Confidence: the more cautious of the pooled-sample label and the weakest
    # member label, per metric.
    exposure_confidence = _min_label(confidence_for(impact_count), weakest_confidence(exposure_labels))
    recovery_confidence = _min_label(confidence_for(recovery_item_count), weakest_confidence(recovery_labels))
    hours_confidence = _min_label(confidence_for(effective_hours_sample), weakest_confidence(hours_labels))
    if risk_proxy is None:
        risk_confidence = CONFIDENCE_NONE
    else:
        risk_confidence = _min_label(confidence_for(recovery_item_count), weakest_confidence(risk_labels))

    return ValueSummary(
        by_currency=by_currency,
        primary_currency=primary_currency,
        estimated_hours_saved=quantize_money(total_hours),
        dispute_risk_reduction=risk_proxy,
        exposure_confidence=exposure_confidence,
        recovery_confidence=recovery_confidence,
        hours_confidence=hours_confidence,
        risk_confidence=risk_confidence,
        cost_position_percentile=None,
        impact_count=impact_count,
        recovery_item_count=recovery_item_count,
        hours_sample=hours_sample,
        activity_count=activity_count,
    )


def _min_label(a: str, b: str) -> str:
    """Return the weaker (more cautious) of two confidence labels."""
    return weakest_confidence((a, b))


__all__ = [
    "TWOPLACES",
    "RATEPLACES",
    "CONFIDENCE_NONE",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW_MIN",
    "CONFIDENCE_MEDIUM_MIN",
    "CONFIDENCE_HIGH_MIN",
    "RISK_WEIGHT_RECOVERY",
    "RISK_WEIGHT_TRACEABILITY",
    "quantize_money",
    "quantize_rate",
    "recovery_rate",
    "confidence_for",
    "weakest_confidence",
    "dispute_risk_reduction",
    "ImpactInput",
    "RecoveryInput",
    "HoursSavedInput",
    "BenchmarkInput",
    "ActivityInput",
    "CurrencyValue",
    "ValueSummary",
    "compose_value_summary",
    "compose_portfolio_summary",
]
