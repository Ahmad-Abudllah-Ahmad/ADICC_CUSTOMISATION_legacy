# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure dispute-exposure scoring for change records (the dispute radar).

Which open changes are most likely to turn into a dispute, why, and what to do
about it first. The causal chain the industry data points at is blunt: when the
contemporaneous record is weak the project is far more likely to end up in an
escalated dispute - low evidence-confidence runs roughly three quarters higher
dispute-escalation risk than a well-evidenced change. This engine turns that
finding into a ranked, money-weighted watchlist.

It is a *composition* engine: it does not re-derive provability, cycle-time,
SLA-breach, ownership or cost-recovery state. Those four sibling engines already
produce those signals; the integrator gathers their outputs for one change into
a :class:`DisputeRiskInput` and feeds it in. Concretely the integrator maps:

* provability score + band from
  :mod:`app.modules.claims_evidence.provability`
  (:class:`~app.modules.claims_evidence.provability.ProvabilityScore` ``score`` /
  ``band``; band one of ``weak`` / ``moderate`` / ``strong``);
* days-overdue / aging from
  :mod:`app.modules.change_intelligence.cycle_time`
  (the ``ItemAging.overdue`` flag and the age the board already expresses in
  days);
* SLA-breach from :mod:`app.modules.approval_routes.sla_engine`
  (:attr:`~app.modules.approval_routes.sla_engine.BreachStatus.is_breached`);
* ownership ambiguity from
  :mod:`app.modules.change_intelligence.ownership_chain`
  (:attr:`~app.modules.change_intelligence.ownership_chain.OwnershipChain.ownership_ambiguous`);
* outstanding / committed money from
  :mod:`app.modules.cost_recovery.back_charge`
  (the outstanding shape its ledger produces, as :class:`decimal.Decimal`).

No database, no ORM, no ``app.*`` imports - stdlib plus ``Decimal`` only - so it
unit-tests on the local Python 3.11 runner exactly like the engines it composes.
It reads no clock: the caller supplies ``days_overdue`` (and the boolean flags),
so identical inputs always produce an identical result.

Scoring model
-------------
Each change earns an **intrinsic exposure** in ``[0, 1]`` from four weighted risk
factors, every factor expressed as a fraction in ``[0, 1]`` of how bad it is:

* evidence weakness (the dominant lever, weight :data:`W_EVIDENCE`) - derived
  from the provability score: a perfectly provable change contributes nothing,
  a zero-provability change contributes the full factor. Driven primarily by the
  numeric score, with the band only used for the cohort-spread calibration below.
* overdue age (weight :data:`W_AGE`) - ramps from 0 to 1 as ``days_overdue``
  rises to :data:`AGE_SATURATION_DAYS`, then saturates.
* SLA breach (weight :data:`W_SLA`) - all-or-nothing on the breach flag.
* ownership ambiguity (weight :data:`W_OWNERSHIP`) - all-or-nothing on the flag.

The weights sum to :data:`TOTAL_WEIGHT`; the intrinsic exposure is the
weighted sum of the four fractions divided by that total, so it stays in
``[0, 1]`` and is a transparent blend.

Money weighting
---------------
A dispute over a large committed sum matters more than the same dispute over a
trivial one, so the intrinsic exposure is scaled by a **money multiplier** in
``[1, MONEY_MAX_MULTIPLIER]`` that grows with the committed cost-at-risk and
saturates at :data:`MONEY_SATURATION_AMOUNT`. The final
:attr:`DisputeRiskItem.exposure_score` is ``intrinsic x multiplier`` mapped onto
``0..100`` (clamped). Because the multiplier depends only on money it scales
two otherwise-identical changes by the same factor - so the cohort relationship
below is preserved while a high-dollar change still outranks a low-dollar one.

The ~75% cohort relationship
----------------------------
The report's headline ("low evidence-confidence = ~75% higher escalation risk")
is encoded directly and tested. On two changes identical in every respect except
provability, a ``weak``-band change lands :data:`TARGET_COHORT_RATIO` times the
exposure of a ``strong``-band change. This is achieved by mapping each
provability band to a fixed *evidence-weakness fraction*
(:data:`BAND_WEAKNESS`) calibrated so that, with the other (shared) factors held
at their typical mid level, the weak/strong intrinsic-exposure ratio equals the
target. See :func:`cohort_exposure_ratio`, which the test suite asserts against
:data:`TARGET_COHORT_RATIO`.

Banding
-------
:func:`band_for_exposure` maps the 0-100 exposure onto ``low`` / ``elevated`` /
``high`` using documented inclusive thresholds so a UI can colour a row without
re-deriving the cut points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# --------------------------------------------------------------------------- #
# Score scale.
# --------------------------------------------------------------------------- #

#: The maximum attainable exposure score. Exposure is points out of this.
MAX_EXPOSURE = 100

# --------------------------------------------------------------------------- #
# Intrinsic-risk factor weights (transparent blend; sum is TOTAL_WEIGHT).
# Evidence weakness deliberately dominates: it is the lever the industry data
# ties most strongly to dispute escalation, and the lever the cohort ratio is
# calibrated on.
# --------------------------------------------------------------------------- #

#: Weight of evidence weakness (low provability). The dominant factor.
W_EVIDENCE = 55

#: Weight of overdue age - how long the change has been past its due date.
W_AGE = 20

#: Weight of an approval-SLA breach being on the record.
W_SLA = 15

#: Weight of ownership ambiguity - the custody chain cannot say who is
#: accountable, which both stalls resolution and weakens any later claim.
W_OWNERSHIP = 10

#: Sum of the four factor weights; the intrinsic exposure is normalised by it.
TOTAL_WEIGHT = W_EVIDENCE + W_AGE + W_SLA + W_OWNERSHIP

# --------------------------------------------------------------------------- #
# Factor saturation / calibration constants.
# --------------------------------------------------------------------------- #

#: Days overdue at which the age factor reaches its maximum (1.0). A change a
#: full standard month past due is treated as maximally aged; further lateness
#: does not increase the age factor (other factors and money still can).
AGE_SATURATION_DAYS = 30.0

#: Committed cost-at-risk (in the change's own currency) at which the money
#: multiplier saturates at :data:`MONEY_MAX_MULTIPLIER`. Deliberately a round,
#: defensible figure; the integrator can localise it per deployment if needed.
MONEY_SATURATION_AMOUNT = Decimal("250000")

#: The most the money weighting can amplify intrinsic exposure. A change with no
#: committed cost-at-risk uses the floor (1.0 - no amplification); one at or
#: above saturation uses this ceiling. Kept modest so money tilts the ranking
#: without letting a single large number swamp a genuinely well-evidenced change.
MONEY_MAX_MULTIPLIER = 1.6

# --------------------------------------------------------------------------- #
# Cohort calibration: the ~75% relationship from the report, encoded exactly.
# --------------------------------------------------------------------------- #

BAND_WEAK = "weak"
BAND_MODERATE = "moderate"
BAND_STRONG = "strong"

#: The cohort relationship the report states and this engine reproduces: a
#: low-evidence-confidence change lands ~75% higher exposure (1.75x) than a
#: comparable high-confidence one.
TARGET_COHORT_RATIO = 1.75

#: The mid level the *other* (shared) intrinsic factors are assumed to sit at
#: when calibrating / reasoning about the cohort ratio: a typical at-risk change
#: is somewhat overdue and may or may not have tripped SLA / ownership. Used by
#: the strong-anchor derivation below and by :func:`cohort_exposure_ratio` (and
#: its test), never in live scoring.
COHORT_SHARED_FACTOR_LEVEL = 0.5

# --------------------------------------------------------------------------- #
# Provability-band -> evidence-weakness fraction (the cohort anchors).
#
# The weakness fraction is "how much of the evidence factor a change of this
# band contributes": a strong-band change contributes little, a weak-band change
# a lot. The WEAK anchor is fixed at an intuitive near-maximal value; the STRONG
# anchor is *derived* from TARGET_COHORT_RATIO so the weak/strong intrinsic
# exposure ratio equals the target exactly (not approximately) when the other
# three factors sit at COHORT_SHARED_FACTOR_LEVEL. The MODERATE anchor is the
# midpoint of the two. Deriving rather than hand-tuning keeps the report's stated
# relationship true by construction even if a weight is later re-balanced.
#
# Derivation (with E = W_EVIDENCE, S = (W_AGE + W_SLA + W_OWNERSHIP) and
# L = COHORT_SHARED_FACTOR_LEVEL): the shared factors contribute S*L to both
# cohorts, so
#     (E*weak + S*L) / (E*strong + S*L) = TARGET_COHORT_RATIO
# solving for strong:
#     strong = ((E*weak + S*L) / TARGET_COHORT_RATIO - S*L) / E
#
# For a change whose numeric provability score is supplied, the engine uses the
# score directly for a smooth weakness fraction and only falls back to these
# band anchors when no score is given; the cohort calibration is expressed and
# tested through the band anchors so the relationship is explicit and stable.
# --------------------------------------------------------------------------- #

#: Evidence-weakness fraction for a weak-band record: near-maximal but not 1.0
#: (even the weakest practical record is rarely a total absence of any trace).
WEAKNESS_WEAK = 0.90

_SHARED_WEIGHT = W_AGE + W_SLA + W_OWNERSHIP
_SHARED_CONTRIB = _SHARED_WEIGHT * COHORT_SHARED_FACTOR_LEVEL

#: Strong-band weakness, derived so weak/strong intrinsic exposure == target.
WEAKNESS_STRONG = ((W_EVIDENCE * WEAKNESS_WEAK + _SHARED_CONTRIB) / TARGET_COHORT_RATIO - _SHARED_CONTRIB) / W_EVIDENCE

#: Moderate-band weakness: the midpoint between the strong and weak anchors.
WEAKNESS_MODERATE = (WEAKNESS_STRONG + WEAKNESS_WEAK) / 2.0

#: Evidence-weakness fraction per provability band (the cohort anchors).
BAND_WEAKNESS: dict[str, float] = {
    BAND_STRONG: WEAKNESS_STRONG,
    BAND_MODERATE: WEAKNESS_MODERATE,
    BAND_WEAK: WEAKNESS_WEAK,
}

# --------------------------------------------------------------------------- #
# Exposure band thresholds (inclusive lower bounds) for the 0-100 score.
# --------------------------------------------------------------------------- #

EXPOSURE_HIGH = "high"
EXPOSURE_ELEVATED = "elevated"
EXPOSURE_LOW = "low"

#: At or above HIGH_THRESHOLD -> "high"; at or above ELEVATED_THRESHOLD (but
#: below high) -> "elevated"; anything lower -> "low".
HIGH_THRESHOLD = 60
ELEVATED_THRESHOLD = 35

# --------------------------------------------------------------------------- #
# Stable driver / cure tokens. ``dominant_driver`` is always one of the DRIVER_*
# values; the matching cure copy lives in CURE_BY_DRIVER.
# --------------------------------------------------------------------------- #

DRIVER_EVIDENCE = "weak_evidence"
DRIVER_AGE = "overdue_age"
DRIVER_SLA = "sla_breach"
DRIVER_OWNERSHIP = "ownership_ambiguous"
DRIVER_NONE = "none"

#: Recommended cure per dominant driver - the single most useful next action.
CURE_BY_DRIVER: dict[str, str] = {
    DRIVER_EVIDENCE: (
        "Strengthen the contemporaneous record: serve or back-fill the "
        "governing notice, link the controlling instruction, and close any "
        "chronology gaps before this change is contested."
    ),
    DRIVER_AGE: (
        "Resolve the overdue change now: it is well past its response due date, "
        "and every additional day of delay compounds the dispute risk."
    ),
    DRIVER_SLA: ("Escalate the breached approval to the next authority so the decision stops aging in a single court."),
    DRIVER_OWNERSHIP: (
        "Assign and record a clear owner: the custody chain cannot currently "
        "say who is accountable, which stalls resolution and weakens any claim."
    ),
    DRIVER_NONE: ("No dominant dispute driver - keep the record current and monitor."),
}

#: Two-decimal-place quantum for money rounding (mirrors the cost-recovery engine).
TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class DisputeRiskInput:
    """Composite per-change input the integrator assembles from sibling engines.

    Every field is a plain primitive (or :class:`Decimal` for money) so the
    engine stays ORM-free and 3.11-testable. The integrator fills it from the
    provability, cycle-time, SLA, ownership-chain and cost-recovery outputs for
    one change (see the module docstring for the exact mapping).

    Attributes
    ----------
    change_id:
        Stable identifier of the change record (used for tie-break ordering).
    change_ref:
        Human-facing code / reference for display (e.g. ``"CO-014"``).
    kind:
        Change-family kind token (mirrors
        :mod:`app.modules.change_intelligence.cycle_time` ``KIND_*``); carried
        through for display and not used in the maths.
    title:
        Human title of the change, carried through for display.
    provability_score:
        The 0-100 provability score from the provability engine. ``None`` when
        no score is available, in which case ``provability_band`` drives the
        evidence factor (and an unknown / unrecognised band is treated as the
        weakest, scoring conservatively).
    provability_band:
        ``weak`` / ``moderate`` / ``strong`` from the provability engine. Used
        for the evidence factor when ``provability_score`` is ``None`` and for
        the documented cohort calibration. An unknown value is treated as
        ``weak``.
    days_overdue:
        Days the change is past its response due date, from the cycle-time
        board. ``0`` (or negative) means not overdue. The engine never reads a
        clock; this is supplied.
    sla_breached:
        Whether an approval-SLA breach is on the record for this change
        (:attr:`~app.modules.approval_routes.sla_engine.BreachStatus.is_breached`).
    ownership_ambiguous:
        Whether the ownership chain is ambiguous
        (:attr:`~app.modules.change_intelligence.ownership_chain.OwnershipChain.ownership_ambiguous`).
    outstanding_amount:
        Still-recoverable / outstanding money tied to this change, from the
        cost-recovery ledger. Used for display and, when
        ``committed_cost_at_risk`` is not given, as the money-weight basis.
    currency:
        ISO currency code for the money fields. Exposure is currency-blind (a
        pure 0-100), but the per-currency summary never blends across codes.
    committed_cost_at_risk:
        The committed sum genuinely at risk if this change becomes a dispute
        (e.g. the committed BOQ / EVM cost of the disputed scope). This is the
        money-weight basis when present; when ``None`` the engine falls back to
        ``outstanding_amount`` so a money weight is always available.
    """

    change_id: str
    change_ref: str
    kind: str
    title: str
    provability_score: int | None
    provability_band: str
    days_overdue: float = 0.0
    sla_breached: bool = False
    ownership_ambiguous: bool = False
    outstanding_amount: Decimal = Decimal("0")
    currency: str = ""
    committed_cost_at_risk: Decimal | None = None

    @property
    def money_basis(self) -> Decimal:
        """Money figure the weighting uses: committed-at-risk, else outstanding.

        Never negative - a negative basis is clamped to zero so it cannot pull
        the multiplier below its 1.0 floor.
        """
        basis = self.committed_cost_at_risk if self.committed_cost_at_risk is not None else self.outstanding_amount
        if basis < Decimal("0"):
            return Decimal("0")
        return basis


@dataclass(frozen=True)
class RiskFactor:
    """One weighted risk factor's contribution to the intrinsic exposure.

    ``fraction`` is the factor's severity in ``[0, 1]``; ``weight`` is its share
    of :data:`TOTAL_WEIGHT`; ``weighted`` is ``fraction * weight`` (the points it
    contributed before normalisation). ``is_driver`` marks the factor that drove
    the score most (the largest ``weighted``).
    """

    name: str
    weight: int
    fraction: float
    weighted: float
    is_driver: bool


@dataclass(frozen=True)
class DisputeRiskItem:
    """The graded dispute exposure of one change.

    Attributes
    ----------
    change_id / change_ref / kind / title:
        Carried through from the input for display + stable ordering.
    exposure_score:
        Integer 0-100. ``intrinsic exposure x money multiplier`` mapped onto the
        scale and clamped.
    band:
        ``low`` / ``elevated`` / ``high`` per :func:`band_for_exposure`.
    dominant_driver:
        The :data:`DRIVER_*` token for the factor that contributed most (or
        :data:`DRIVER_NONE` for an entirely clean change).
    recommended_cure:
        The single most useful next action, from :data:`CURE_BY_DRIVER`.
    intrinsic_exposure:
        The pre-money exposure fraction in ``[0, 1]`` - useful for the cohort
        relationship and for explaining how much of the score is money tilt.
    money_multiplier:
        The applied money multiplier in ``[1, MONEY_MAX_MULTIPLIER]``.
    money_basis:
        The money figure the multiplier was derived from (committed-at-risk,
        else outstanding), as a quantized :class:`Decimal`.
    currency:
        The input currency (so a UI can render ``money_basis`` correctly).
    factors:
        All four :class:`RiskFactor` contributions, in a fixed order, with the
        dominant one flagged.
    """

    change_id: str
    change_ref: str
    kind: str
    title: str
    exposure_score: int
    band: str
    dominant_driver: str
    recommended_cure: str
    intrinsic_exposure: float
    money_multiplier: float
    money_basis: Decimal
    currency: str
    factors: list[RiskFactor] = field(default_factory=list)


@dataclass(frozen=True)
class CurrencyExposure:
    """Exposure-weighted money at risk for a single currency.

    ``exposure_weighted_amount`` sums each change's ``money_basis`` scaled by its
    exposure fraction (``exposure_score / 100``) - a one-number "how much money
    is at meaningful dispute risk" figure for this currency. Never blended across
    currencies; one row per currency code.
    """

    currency: str
    item_count: int
    money_basis_total: Decimal
    exposure_weighted_amount: Decimal


@dataclass(frozen=True)
class DisputeExposureSummary:
    """Portfolio roll-up over a set of ranked dispute-risk items.

    Attributes
    ----------
    item_count:
        Number of changes assessed.
    band_counts:
        Count of items in each exposure band, keyed by the :data:`EXPOSURE_*`
        tokens (every band key is always present, zero when none).
    by_currency:
        Per-currency exposure-weighted money at risk, ordered by descending
        exposure-weighted amount then currency. Currencies are never blended.
    top_driver_counts:
        How many items each :data:`DRIVER_*` token was the dominant driver for
        (only drivers that occur are present), so a UI can show what is driving
        portfolio risk overall.
    """

    item_count: int
    band_counts: dict[str, int]
    by_currency: tuple[CurrencyExposure, ...] = field(default_factory=tuple)
    top_driver_counts: dict[str, int] = field(default_factory=dict)


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding."""
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def band_for_exposure(score: int) -> str:
    """Classify a 0-100 exposure score into a band.

    ``score >= HIGH_THRESHOLD`` -> :data:`EXPOSURE_HIGH`;
    ``score >= ELEVATED_THRESHOLD`` -> :data:`EXPOSURE_ELEVATED`;
    otherwise :data:`EXPOSURE_LOW`. Thresholds are inclusive lower bounds.
    """
    if score >= HIGH_THRESHOLD:
        return EXPOSURE_HIGH
    if score >= ELEVATED_THRESHOLD:
        return EXPOSURE_ELEVATED
    return EXPOSURE_LOW


def _clamp_fraction(value: float) -> float:
    """Clamp a value into the inclusive ``[0.0, 1.0]`` range."""
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _weakness_from_band(band: str) -> float:
    """Evidence-weakness fraction for a provability band (cohort anchors).

    An unknown / unrecognised band is treated as the weakest so an unwired or
    mis-mapped change is scored conservatively (high risk) rather than waved
    through.
    """
    return BAND_WEAKNESS.get(band, BAND_WEAKNESS[BAND_WEAK])


def evidence_weakness(provability_score: int | None, provability_band: str) -> float:
    """How weak the evidence is, as a fraction in ``[0, 1]`` (1 == weakest).

    When a numeric ``provability_score`` is supplied it drives the fraction
    smoothly: ``1 - score/100`` (a perfectly provable 100 contributes no
    weakness, a 0 contributes the maximum). When no score is available the
    provability *band* drives it through the calibrated :data:`BAND_WEAKNESS`
    anchors. The band anchors are also what the cohort-ratio calibration is
    expressed and tested on.
    """
    if provability_score is not None:
        return _clamp_fraction(1.0 - (provability_score / float(MAX_EXPOSURE)))
    return _weakness_from_band(provability_band)


def age_fraction(days_overdue: float) -> float:
    """Overdue-age severity as a fraction in ``[0, 1]``.

    Ramps linearly from 0 at not-overdue to 1.0 at :data:`AGE_SATURATION_DAYS`,
    then saturates. A zero or negative ``days_overdue`` contributes nothing.
    """
    if days_overdue <= 0.0:
        return 0.0
    return _clamp_fraction(days_overdue / AGE_SATURATION_DAYS)


def money_multiplier(money_basis: Decimal) -> float:
    """Money amplification factor in ``[1, MONEY_MAX_MULTIPLIER]``.

    Grows linearly with ``money_basis`` from 1.0 (no money at risk) to
    :data:`MONEY_MAX_MULTIPLIER` at :data:`MONEY_SATURATION_AMOUNT`, then
    saturates. Because it depends only on money, it scales two otherwise
    identical changes by the same factor - preserving the evidence cohort ratio
    while still ranking a high-dollar change above a low-dollar one.
    """
    if money_basis <= Decimal("0"):
        return 1.0
    ratio = float(money_basis / MONEY_SATURATION_AMOUNT)
    if ratio > 1.0:
        ratio = 1.0
    return 1.0 + ratio * (MONEY_MAX_MULTIPLIER - 1.0)


# Fixed factor order: evidence first (dominant), then age, SLA, ownership. The
# dominant-driver tie-break follows this order (earlier factor wins a tie).
_FACTOR_SPECS: list[tuple[str, int, str]] = [
    ("evidence", W_EVIDENCE, DRIVER_EVIDENCE),
    ("overdue_age", W_AGE, DRIVER_AGE),
    ("sla_breach", W_SLA, DRIVER_SLA),
    ("ownership", W_OWNERSHIP, DRIVER_OWNERSHIP),
]


def _intrinsic_exposure_from_fractions(
    evidence: float,
    age: float,
    sla: float,
    ownership: float,
) -> float:
    """Normalised weighted blend of the four factor fractions, in ``[0, 1]``."""
    weighted = evidence * W_EVIDENCE + age * W_AGE + sla * W_SLA + ownership * W_OWNERSHIP
    return weighted / float(TOTAL_WEIGHT)


def cohort_exposure_ratio() -> float:
    """Weak-band / strong-band intrinsic-exposure ratio at the shared mid level.

    Reproduces the report's "low evidence-confidence = ~75% higher escalation"
    relationship and is asserted against :data:`TARGET_COHORT_RATIO` in the test
    suite. Both cohorts are scored with the *other* three factors held at
    :data:`COHORT_SHARED_FACTOR_LEVEL` (a typical at-risk change) and differ
    only in their provability band, so the ratio isolates the evidence lever.

    Returns the ratio ``weak_exposure / strong_exposure``.
    """
    shared = COHORT_SHARED_FACTOR_LEVEL
    weak = _intrinsic_exposure_from_fractions(BAND_WEAKNESS[BAND_WEAK], shared, shared, shared)
    strong = _intrinsic_exposure_from_fractions(BAND_WEAKNESS[BAND_STRONG], shared, shared, shared)
    if strong <= 0.0:
        return 0.0
    return weak / strong


def assess_dispute_risk(item: DisputeRiskInput) -> DisputeRiskItem:
    """Grade one change's dispute exposure into a :class:`DisputeRiskItem`.

    Computes the four factor fractions, blends them into the intrinsic exposure,
    applies the money multiplier, maps the result onto 0-100, picks the dominant
    driver (largest weighted contribution; ties broken by factor order, earlier
    wins) and selects its cure. Pure and deterministic - no clock, no
    randomness: identical input always yields an identical result.
    """
    evidence_f = evidence_weakness(item.provability_score, item.provability_band)
    age_f = age_fraction(item.days_overdue)
    sla_f = 1.0 if item.sla_breached else 0.0
    ownership_f = 1.0 if item.ownership_ambiguous else 0.0

    fractions = {
        "evidence": evidence_f,
        "overdue_age": age_f,
        "sla_breach": sla_f,
        "ownership": ownership_f,
    }

    intrinsic = _intrinsic_exposure_from_fractions(evidence_f, age_f, sla_f, ownership_f)

    basis = item.money_basis
    multiplier = money_multiplier(basis)

    raw = intrinsic * multiplier * MAX_EXPOSURE
    exposure_score = int(round(raw))
    if exposure_score < 0:
        exposure_score = 0
    elif exposure_score > MAX_EXPOSURE:
        exposure_score = MAX_EXPOSURE

    # Dominant driver = factor with the greatest weighted contribution. A change
    # with no risk at all (every weighted contribution zero) has no driver.
    weighted = {name: fractions[name] * weight for name, weight, _ in _FACTOR_SPECS}
    best_name = ""
    best_value = 0.0
    for name, _weight, _token in _FACTOR_SPECS:
        if weighted[name] > best_value:
            best_value = weighted[name]
            best_name = name

    if best_value <= 0.0:
        dominant_driver = DRIVER_NONE
    else:
        dominant_driver = next(token for name, _w, token in _FACTOR_SPECS if name == best_name)

    factors = [
        RiskFactor(
            name=name,
            weight=weight,
            fraction=round(fractions[name], 4),
            weighted=round(fractions[name] * weight, 4),
            is_driver=(dominant_driver != DRIVER_NONE and token == dominant_driver),
        )
        for name, weight, token in _FACTOR_SPECS
    ]

    return DisputeRiskItem(
        change_id=item.change_id,
        change_ref=item.change_ref,
        kind=item.kind,
        title=item.title,
        exposure_score=exposure_score,
        band=band_for_exposure(exposure_score),
        dominant_driver=dominant_driver,
        recommended_cure=CURE_BY_DRIVER[dominant_driver],
        intrinsic_exposure=round(intrinsic, 4),
        money_multiplier=round(multiplier, 4),
        money_basis=quantize_money(basis),
        currency=item.currency,
        factors=factors,
    )


def rank_dispute_exposure(items: list[DisputeRiskInput]) -> list[DisputeRiskItem]:
    """Assess every change and return them sorted by exposure, highest first.

    The sort is stable on the descending exposure score, with ties broken by
    descending money basis (the larger sum at risk ranks first), then by
    ``change_ref`` and ``change_id`` for a fully deterministic order. Empty
    input yields an empty list.
    """
    assessed = [assess_dispute_risk(it) for it in items]
    assessed.sort(
        key=lambda r: (
            -r.exposure_score,
            -r.money_basis,
            r.change_ref,
            r.change_id,
        )
    )
    return assessed


def summarize_dispute_exposure(items: list[DisputeRiskItem]) -> DisputeExposureSummary:
    """Roll a set of assessed items into a portfolio :class:`DisputeExposureSummary`.

    Counts items per exposure band; sums per-currency money basis and
    exposure-weighted money at risk (each item's ``money_basis`` times its
    ``exposure_score / 100``) without ever blending currencies; and counts how
    often each driver was dominant. Currency rows are ordered by descending
    exposure-weighted amount, then currency code. Empty input yields zeroed
    counts and no currency rows.
    """
    band_counts: dict[str, int] = {
        EXPOSURE_HIGH: 0,
        EXPOSURE_ELEVATED: 0,
        EXPOSURE_LOW: 0,
    }
    driver_counts: dict[str, int] = {}

    cur_basis: dict[str, Decimal] = {}
    cur_weighted: dict[str, Decimal] = {}
    cur_items: dict[str, int] = {}

    for it in items:
        band_counts[it.band] = band_counts.get(it.band, 0) + 1
        driver_counts[it.dominant_driver] = driver_counts.get(it.dominant_driver, 0) + 1

        currency = it.currency
        # Exposure-weighted money: basis scaled by the exposure fraction. Decimal
        # throughout so money stays exact; quantize at the end.
        weight_fraction = Decimal(it.exposure_score) / Decimal(MAX_EXPOSURE)
        cur_basis[currency] = cur_basis.get(currency, Decimal("0")) + it.money_basis
        cur_weighted[currency] = cur_weighted.get(currency, Decimal("0")) + it.money_basis * weight_fraction
        cur_items[currency] = cur_items.get(currency, 0) + 1

    by_currency = tuple(
        CurrencyExposure(
            currency=currency,
            item_count=cur_items[currency],
            money_basis_total=quantize_money(cur_basis[currency]),
            exposure_weighted_amount=quantize_money(cur_weighted[currency]),
        )
        for currency in cur_items
    )
    by_currency = tuple(sorted(by_currency, key=lambda c: (-c.exposure_weighted_amount, c.currency)))

    return DisputeExposureSummary(
        item_count=len(items),
        band_counts=band_counts,
        by_currency=by_currency,
        top_driver_counts=driver_counts,
    )


__all__ = [
    "MAX_EXPOSURE",
    "W_EVIDENCE",
    "W_AGE",
    "W_SLA",
    "W_OWNERSHIP",
    "TOTAL_WEIGHT",
    "AGE_SATURATION_DAYS",
    "MONEY_SATURATION_AMOUNT",
    "MONEY_MAX_MULTIPLIER",
    "BAND_WEAK",
    "BAND_MODERATE",
    "BAND_STRONG",
    "BAND_WEAKNESS",
    "WEAKNESS_WEAK",
    "WEAKNESS_MODERATE",
    "WEAKNESS_STRONG",
    "COHORT_SHARED_FACTOR_LEVEL",
    "TARGET_COHORT_RATIO",
    "EXPOSURE_HIGH",
    "EXPOSURE_ELEVATED",
    "EXPOSURE_LOW",
    "HIGH_THRESHOLD",
    "ELEVATED_THRESHOLD",
    "DRIVER_EVIDENCE",
    "DRIVER_AGE",
    "DRIVER_SLA",
    "DRIVER_OWNERSHIP",
    "DRIVER_NONE",
    "CURE_BY_DRIVER",
    "TWOPLACES",
    "DisputeRiskInput",
    "RiskFactor",
    "DisputeRiskItem",
    "CurrencyExposure",
    "DisputeExposureSummary",
    "quantize_money",
    "band_for_exposure",
    "evidence_weakness",
    "age_fraction",
    "money_multiplier",
    "cohort_exposure_ratio",
    "assess_dispute_risk",
    "rank_dispute_exposure",
    "summarize_dispute_exposure",
]
