# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Predictive schedule and cost risk analytics (TOP-30 #19).

This module is a *deterministic, explainable* forecasting layer. It needs no
ML training data: every number is a closed-form Earned-Value or schedule-slip
formula, and every risk band is a fixed deterministic mapping. The product
philosophy is honoured throughout - analytics *suggest*, the human confirms;
every result carries a confidence score and a human-readable rationale, and
nothing here triggers an action.

Two layers live here:

* The **pure-logic helpers** (``compute_cost_forecast``, ``project_schedule_slip``,
  ``score_cost_overrun_risk``) operate on plain inputs (Decimals / ints) and are
  fully unit-testable without a database. They guard every division by zero and
  degrade gracefully when an input is missing.
* The :class:`ForecastService` reads from already-committed sibling modules
  (full_evm / finance EVM snapshot, schedule, risk) **read-only** and assembles
  a :class:`ProjectForecast`. It never writes - it does not duplicate the EVM
  math that persists forecast rows in ``full_evm.service``; it recomputes the
  same canonical formulas from the latest snapshot for a live, no-side-effect
  read.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
ONE = Decimal("1")
QUANTIZE_MONEY = Decimal("0.01")
QUANTIZE_INDEX = Decimal("0.0001")

# TCPI sentinel: when the to-complete index is mathematically unbounded
# (budget already fully spent but work remains) we surface this string rather
# than a misleading finite number. The UI renders it as "Not achievable".
TCPI_NOT_ACHIEVABLE = "not_achievable"

# Risk-score → RAG band thresholds (deterministic, fixed). A higher score
# means a higher chance of a cost overrun. ``green`` < 0.34 ≤ ``amber`` < 0.67
# ≤ ``red``.
RAG_AMBER_THRESHOLD = Decimal("0.34")
RAG_RED_THRESHOLD = Decimal("0.67")


# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class CostForecast:
    """Earned-value cost forecast for a project.

    All money values are strings (currency-tagged elsewhere) to avoid float
    drift; the index values are floats for easy JSON rendering. ``available``
    is False when no EVM snapshot exists - the caller then renders the
    degraded state with ``reason``.
    """

    available: bool = False
    reason: str | None = None
    currency: str = ""
    snapshot_date: str | None = None
    bac: str | None = None
    ev: str | None = None
    ac: str | None = None
    pv: str | None = None
    cpi: float | None = None
    spi: float | None = None
    eac: str | None = None
    etc: str | None = None
    vac: str | None = None
    tcpi: str | None = None
    eac_over_bac: float | None = None


@dataclass
class ScheduleSlip:
    """Forward projection of schedule finish-date variance.

    ``available`` is False when there is no schedule with dated activities.
    ``finish_variance_days`` is positive when the project is forecast to finish
    *late* (forecast finish after baseline finish).
    """

    available: bool = False
    reason: str | None = None
    activities_total: int = 0
    activities_complete: int = 0
    planned_pct_complete: float | None = None
    actual_pct_complete: float | None = None
    baseline_finish: str | None = None
    forecast_finish: str | None = None
    finish_variance_days: int | None = None
    at_risk_task_count: int = 0


@dataclass
class CostOverrunRisk:
    """Deterministic cost-overrun risk score with rationale.

    ``score`` is 0..1 (higher == riskier). ``band`` is the RAG mapping. The
    ``confidence`` reflects how much signal fed the score (more inputs present
    == higher confidence). ``rationale`` is a short human-readable bullet list
    explaining the drivers - never empty.
    """

    score: float = 0.0
    band: str = "green"
    confidence: float = 0.0
    rationale: list[str] = field(default_factory=list)


@dataclass
class ProjectForecast:
    """The complete predictive-analytics payload for one project."""

    project_id: str = ""
    project_name: str = ""
    currency: str = ""
    generated_at: str = ""
    cost: CostForecast = field(default_factory=CostForecast)
    schedule: ScheduleSlip = field(default_factory=ScheduleSlip)
    risk: CostOverrunRisk = field(default_factory=CostOverrunRisk)
    # Always-on disclaimer flag for the UI: this is a forecast, not a commitment.
    review_required: bool = True


# ── Decimal helpers ─────────────────────────────────────────────────────────


def to_decimal(value: object, default: Decimal = ZERO) -> Decimal:
    """Best-effort convert any value to ``Decimal`` (never raises).

    Empty strings and ``None`` fall back to ``default``; an unparseable value
    also returns ``default`` so a single bad row never breaks a forecast.
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return default


def _q_money(value: Decimal) -> str:
    """Quantize a money Decimal to 2 places and render as a string."""
    return str(value.quantize(QUANTIZE_MONEY, rounding=ROUND_HALF_UP))


def _q_index(value: Decimal) -> float:
    """Quantize an index Decimal to 4 places and render as a float."""
    return float(value.quantize(QUANTIZE_INDEX, rounding=ROUND_HALF_UP))


# ── Pure-logic: cost forecast ───────────────────────────────────────────────


def compute_cost_forecast(
    *,
    bac: Decimal,
    ev: Decimal,
    ac: Decimal,
    pv: Decimal,
    currency: str = "",
    snapshot_date: str | None = None,
) -> CostForecast:
    """Compute the canonical Earned-Value forecast from raw EVM inputs.

    Formulas (PMBOK):
        CPI  = EV / AC
        SPI  = EV / PV
        EAC  = BAC / CPI            (CPI-based, the standard "typical" method)
        ETC  = EAC - AC
        VAC  = BAC - EAC
        TCPI = (BAC - EV) / (BAC - AC)

    Every division guards its denominator. When CPI cannot be computed (AC is
    zero, i.e. no actuals yet) EAC falls back to BAC and the indices are
    reported as ``None`` so the UI shows "not enough data" rather than a
    misleading 0. ``TCPI`` returns the :data:`TCPI_NOT_ACHIEVABLE` sentinel
    when the budget is fully consumed yet work remains.

    Args:
        bac: Budget at completion.
        ev: Earned value (budgeted cost of work performed).
        ac: Actual cost.
        pv: Planned value (budgeted cost of work scheduled).
        currency: ISO currency code, carried through for display only.
        snapshot_date: The date the EVM inputs were captured.

    Returns:
        A populated :class:`CostForecast` (``available=True``).
    """
    forecast = CostForecast(
        available=True,
        currency=currency,
        snapshot_date=snapshot_date,
        bac=_q_money(bac),
        ev=_q_money(ev),
        ac=_q_money(ac),
        pv=_q_money(pv),
    )

    # CPI = EV / AC - undefined with no actuals.
    cpi: Decimal | None = (ev / ac) if ac != ZERO else None
    spi: Decimal | None = (ev / pv) if pv != ZERO else None
    forecast.cpi = _q_index(cpi) if cpi is not None else None
    forecast.spi = _q_index(spi) if spi is not None else None

    # EAC = BAC / CPI (typical method). Without a CPI we cannot project, so we
    # fall back to BAC (the original plan) - an honest neutral default.
    if cpi is not None and cpi != ZERO:
        eac = bac / cpi
    else:
        eac = bac
    forecast.eac = _q_money(eac)

    # ETC = EAC - AC (work still to fund). VAC = BAC - EAC (the projected
    # budget overrun, negative == over budget).
    forecast.etc = _q_money(eac - ac)
    forecast.vac = _q_money(bac - eac)

    # TCPI = (BAC - EV) / (BAC - AC). Denominator zero with work remaining ==
    # unachievable; with no work remaining the index is a clean 1.0.
    remaining = bac - ev
    denominator = bac - ac
    if denominator != ZERO:
        forecast.tcpi = str((remaining / denominator).quantize(QUANTIZE_INDEX, rounding=ROUND_HALF_UP))
    elif remaining > ZERO:
        forecast.tcpi = TCPI_NOT_ACHIEVABLE
    else:
        forecast.tcpi = "1.0"

    forecast.eac_over_bac = _q_index(eac / bac) if bac != ZERO else None
    return forecast


def degraded_cost_forecast(reason: str, currency: str = "") -> CostForecast:
    """Return an unavailable cost forecast carrying a human-readable reason."""
    return CostForecast(available=False, reason=reason, currency=currency)


# ── Pure-logic: schedule slip ───────────────────────────────────────────────


def _parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` (tolerant of a trailing time)."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def project_schedule_slip(
    *,
    activities: list[dict],
    baseline_finish: str | None,
    data_date: str | None = None,
) -> ScheduleSlip:
    """Project a finish-date variance from per-activity progress.

    Deterministic linear projection: from the aggregate planned-vs-actual
    percent complete we derive a Schedule Performance Index against duration
    (SPI_t = actual% / planned%) and stretch the remaining baseline duration
    by ``1 / SPI_t``. A project running behind (actual < planned) projects a
    later finish; running ahead projects an earlier one.

    ``activities`` is a list of dicts with keys ``planned_pct`` (0..100),
    ``actual_pct`` (0..100) and ``end_date`` (ISO). The aggregate percents are
    duration-unweighted means - simple and explainable; an unweighted mean is
    a deliberate, documented choice (per-activity durations are not always
    reliable on imported schedules).

    Args:
        activities: Per-activity planned/actual progress + planned finish.
        baseline_finish: The schedule's baseline (planned) finish date, ISO.
        data_date: The "as-of" date the progress reflects; defaults to today
            via the caller. Used to compute the elapsed/forecast spans.

    Returns:
        A populated :class:`ScheduleSlip`. ``available=False`` when there are
        no dated activities to project from.
    """
    if not activities:
        return ScheduleSlip(available=False, reason="no_schedule_activities")

    total = len(activities)
    planned_values = [to_decimal(a.get("planned_pct")) for a in activities]
    actual_values = [to_decimal(a.get("actual_pct")) for a in activities]

    planned_mean = sum(planned_values, ZERO) / Decimal(total)
    actual_mean = sum(actual_values, ZERO) / Decimal(total)

    complete = sum(1 for v in actual_values if v >= Decimal("100"))

    slip = ScheduleSlip(
        available=True,
        activities_total=total,
        activities_complete=complete,
        planned_pct_complete=_q_index(planned_mean),
        actual_pct_complete=_q_index(actual_mean),
        baseline_finish=baseline_finish,
    )

    # An activity is "at risk" when it is materially behind its planned
    # progress (actual lags planned by more than 10 percentage points) and is
    # not yet complete.
    behind_threshold = Decimal("10")
    slip.at_risk_task_count = sum(
        1
        for planned, actual in zip(planned_values, actual_values, strict=True)
        if actual < Decimal("100") and (planned - actual) > behind_threshold
    )

    # Schedule performance against the plan. With no planned progress yet we
    # cannot project a variance (SPI_t undefined) - leave the dates None.
    bl_finish = _parse_iso_date(baseline_finish)
    as_of = _parse_iso_date(data_date) or date.today()

    if planned_mean <= ZERO or bl_finish is None:
        slip.reason = "insufficient_progress_or_no_baseline_finish"
        return slip

    spi_t = actual_mean / planned_mean if planned_mean != ZERO else ONE
    # Remaining baseline span from the data date to the baseline finish.
    remaining_days = (bl_finish - as_of).days
    if remaining_days <= 0:
        # Past the baseline finish already; the variance is the overshoot
        # scaled by how far behind we are.
        remaining_days = 0

    # Stretch the remaining span by 1/SPI_t. SPI_t == 0 (no actuals at all)
    # means we cannot meaningfully project a faster-than-zero rate, so we treat
    # the remaining work as unbounded-but-capped at double the remaining span.
    if spi_t <= ZERO:
        projected_remaining = remaining_days * 2
    else:
        projected_remaining = int((Decimal(remaining_days) / spi_t).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    from datetime import timedelta

    forecast_finish = as_of + timedelta(days=projected_remaining)
    slip.forecast_finish = forecast_finish.isoformat()
    slip.finish_variance_days = (forecast_finish - bl_finish).days
    return slip


# ── Pure-logic: cost-overrun risk score ─────────────────────────────────────


def _rag_band(score: Decimal) -> str:
    """Map a 0..1 risk score to a RAG band (deterministic thresholds)."""
    if score >= RAG_RED_THRESHOLD:
        return "red"
    if score >= RAG_AMBER_THRESHOLD:
        return "amber"
    return "green"


def score_cost_overrun_risk(
    *,
    cpi: float | None,
    spi: float | None,
    vac: Decimal | None,
    bac: Decimal | None,
    finish_variance_days: int | None,
    open_high_severity_risks: int,
) -> CostOverrunRisk:
    """Deterministically score the cost-overrun risk (0..1) with rationale.

    The score blends four weighted signals, each normalised to 0..1:

    * **CPI shortfall** (weight 0.35): how far CPI is below 1.0.
    * **SPI shortfall** (weight 0.20): how far SPI is below 1.0 (schedule
      pressure feeds cost pressure).
    * **VAC ratio** (weight 0.25): projected overrun as a fraction of BAC.
    * **Open high-severity risks** (weight 0.20): saturating at 5 risks.

    Schedule finish variance nudges the score up (capped) when present. Only
    the signals that are actually available contribute, and the weights are
    re-normalised over the present signals so a project with only a CPI still
    gets an honest score. ``confidence`` is the share of total possible signal
    weight that was present.

    Returns:
        A :class:`CostOverrunRisk` with score, RAG band, confidence and a
        non-empty rationale list.
    """
    weights = {"cpi": Decimal("0.35"), "spi": Decimal("0.20"), "vac": Decimal("0.25"), "risks": Decimal("0.20")}
    present_weight = ZERO
    weighted_sum = ZERO
    rationale: list[str] = []

    # CPI shortfall - the strongest single cost signal.
    if cpi is not None:
        cpi_d = Decimal(str(cpi))
        shortfall = max(ZERO, ONE - cpi_d)
        # Normalise: a CPI of 0.5 (50% over) saturates the signal.
        signal = min(ONE, shortfall / Decimal("0.5"))
        weighted_sum += signal * weights["cpi"]
        present_weight += weights["cpi"]
        if cpi_d < ONE:
            rationale.append(f"Cost performance index is below plan (CPI {cpi:.2f}).")
        else:
            rationale.append(f"Cost performance index is on or above plan (CPI {cpi:.2f}).")

    # SPI shortfall - schedule pressure.
    if spi is not None:
        spi_d = Decimal(str(spi))
        shortfall = max(ZERO, ONE - spi_d)
        signal = min(ONE, shortfall / Decimal("0.5"))
        weighted_sum += signal * weights["spi"]
        present_weight += weights["spi"]
        if spi_d < ONE:
            rationale.append(f"Schedule performance index is behind plan (SPI {spi:.2f}).")

    # VAC ratio - projected overrun versus budget.
    if vac is not None and bac is not None and bac != ZERO:
        overrun_ratio = max(ZERO, -vac / bac)  # negative VAC == over budget
        # A 20% overrun saturates the signal.
        signal = min(ONE, overrun_ratio / Decimal("0.20"))
        weighted_sum += signal * weights["vac"]
        present_weight += weights["vac"]
        if vac < ZERO:
            pct = (overrun_ratio * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            rationale.append(f"Forecast variance at completion is negative ({pct}% over budget).")

    # Open high-severity risks - saturates at 5.
    risks_d = Decimal(max(0, open_high_severity_risks))
    risk_signal = min(ONE, risks_d / Decimal("5"))
    weighted_sum += risk_signal * weights["risks"]
    present_weight += weights["risks"]
    if open_high_severity_risks > 0:
        rationale.append(
            f"{open_high_severity_risks} open high-severity risk"
            f"{'s' if open_high_severity_risks != 1 else ''} without mitigation."
        )

    # Base score over the present signals (re-normalised).
    score = (weighted_sum / present_weight) if present_weight != ZERO else ZERO

    # Schedule slip nudge - a late forecast finish adds up to +0.10.
    if finish_variance_days is not None and finish_variance_days > 0:
        nudge = min(Decimal("0.10"), Decimal(finish_variance_days) / Decimal("300"))
        score = min(ONE, score + nudge)
        rationale.append(f"Schedule is forecast to finish {finish_variance_days} day(s) late.")

    # Confidence: how much of the possible signal weight was present. Risks
    # always contribute (weight 0.20 is always counted), so confidence floors
    # at that share.
    total_weight = sum(weights.values(), ZERO)
    confidence = (present_weight / total_weight) if total_weight != ZERO else ZERO

    if not rationale:
        rationale.append("No cost or schedule pressure detected from the available data.")

    return CostOverrunRisk(
        score=_q_index(score),
        band=_rag_band(score),
        confidence=_q_index(confidence),
        rationale=rationale,
    )
