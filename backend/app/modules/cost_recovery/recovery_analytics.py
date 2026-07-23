# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure recovery-performance analytics.

How much of the cost a project was entitled to recover did it actually
recover - and does the answer depend on how traceable the responsible owner
was? The industry signal this engine operationalises is stark: when the change
owner is traceable, most projects recover the bulk of their extra costs, while
more than a third of projects that cannot trace the owner end up absorbing the
cost themselves. Firms rarely know their own recovery rate, let alone that
traceability is the lever that moves it. This engine turns the cost-recovery
ledger into that number, on the firm's own data, and splits it by traceability
cohort so the contrast is visible rather than asserted.

It consumes the same per-item facts the back-charge ledger
(:mod:`app.modules.cost_recovery.back_charge`) already holds - a chargeable
amount, how much was recovered, the currency, the commercial status - plus one
extra signal per item: the provability / traceability band
(``weak`` / ``moderate`` / ``strong``) produced by
:mod:`app.modules.claims_evidence.provability`. The band is an INPUT here, not
recomputed: the integrator scores each back-charge's evidence with
``compute_provability`` and passes ``band_for(score)`` in.

No database, no ORM, no ``app.*`` imports - stdlib plus :class:`decimal.Decimal`
only - so it unit-tests on the local Python 3.11 runner exactly like the
back-charge, apportionment and provability engines. A thin service layer
(written separately by the integrator) maps ledger rows onto :class:`RecoveryItem`
and feeds them in.

Money discipline (identical to the back-charge engine)
------------------------------------------------------
Every money total is :class:`decimal.Decimal`. Decimal sums stay exact and are
quantized to two places with half-up rounding only at the boundary. Amounts in
different currency codes are NEVER summed together: every figure this engine
returns is scoped to a single currency, and a cohort spanning two currencies
yields two rows.

Rate form (documented and exact)
--------------------------------
A recovery rate is ``recovered / chargeable`` expressed as a
:class:`decimal.Decimal` FRACTION in the inclusive range ``[0, 1]`` - 0.6900
means 69%, not 69. It is quantized to four decimal places
(:data:`RATEPLACES`) with half-up rounding, so identical inputs always yield an
identical rate and the frontend can format it as a percentage without surprise.
Honest low-n handling: when a currency or cohort has NO chargeable amount the
rate is ``None`` (an undefined ratio), never ``0`` - a project that was never
entitled to recover anything has not "recovered 0%", it simply has no rate.

Traceability cohorts (documented cut)
-------------------------------------
Each item carries a band of ``weak`` / ``moderate`` / ``strong`` (the same
vocabulary as :func:`app.modules.claims_evidence.provability.band_for`). The
engine reports three things so nothing is hidden:

* the rate for each individual band (``strong`` / ``moderate`` / ``weak``);
* a two-way HIGH-vs-LOW cohort split that reproduces the report's headline
  contrast, where HIGH = ``strong`` and LOW = ``moderate`` + ``weak``. The cut
  is drawn at the ``strong`` boundary on purpose: ``strong`` is the band a
  record reaches only with a timely notice (or equivalently complete evidence),
  i.e. a genuinely traceable owner, so "high traceability" means "would stand
  up", and everything short of that is grouped as "low" where cost tends to be
  absorbed.

Absorbed
--------
``absorbed_total`` is chargeable amount the project gave up on - items closed
without recovery (status ``waived`` or ``absorbed``) - reported per currency and
split by the same HIGH/LOW cohort, because the report's point is precisely that
absorbed cost concentrates in the low-traceability cohort. Absorbed amount is
the item's chargeable amount net of anything that was nonetheless recovered on
it before write-off.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

# --------------------------------------------------------------------------- #
# Status vocabulary. Mirrors back_charge's commercial states and adds the
# explicit "absorbed" close that the report's qualitative finding names. The
# values are duplicated as local constants (not imported) to keep this engine a
# self-contained pure module; they match back_charge's strings exactly.
# --------------------------------------------------------------------------- #

STATUS_PROPOSED = "proposed"
STATUS_AGREED = "agreed"
STATUS_DISPUTED = "disputed"
STATUS_RECOVERED = "recovered"
STATUS_WAIVED = "waived"

#: An explicit "closed, cost absorbed by the project" status. back_charge models
#: a write-off as ``waived``; some callers distinguish a deliberate absorb. Both
#: count as absorbed here.
STATUS_ABSORBED = "absorbed"

#: Statuses for a back-charge still live and potentially recoverable.
OPEN_STATUSES = frozenset({STATUS_PROPOSED, STATUS_AGREED, STATUS_DISPUTED})

#: Statuses where the project gave up the chargeable amount it did not collect.
ABSORBED_STATUSES = frozenset({STATUS_WAIVED, STATUS_ABSORBED})

#: Statuses for a back-charge that is settled, whether collected or absorbed.
CLOSED_STATUSES = frozenset({STATUS_RECOVERED, STATUS_WAIVED, STATUS_ABSORBED})

# --------------------------------------------------------------------------- #
# Traceability bands (same vocabulary as provability.band_for) + the HIGH/LOW
# cohort cut. Kept as constants so a test can assert the cut and a service can
# introspect it.
# --------------------------------------------------------------------------- #

BAND_WEAK = "weak"
BAND_MODERATE = "moderate"
BAND_STRONG = "strong"

#: All recognised bands, ordered strongest-first for stable reporting.
TRACEABILITY_BANDS: tuple[str, ...] = (BAND_STRONG, BAND_MODERATE, BAND_WEAK)

#: Cohort labels for the two-way split.
COHORT_HIGH = "high"
COHORT_LOW = "low"

#: The documented cut: only ``strong`` counts as HIGH traceability; ``moderate``
#: and ``weak`` are LOW. See the module docstring for the rationale.
HIGH_BANDS = frozenset({BAND_STRONG})
LOW_BANDS = frozenset({BAND_MODERATE, BAND_WEAK})

#: Band used for an item whose traceability band is blank / unrecognised. Scored
#: conservatively as ``weak`` (and therefore LOW) so an unwired subject never
#: inflates the high-traceability recovery rate.
DEFAULT_BAND = BAND_WEAK

# --------------------------------------------------------------------------- #
# Money + rate quanta.
# --------------------------------------------------------------------------- #

#: Two-decimal-place quantum for money rounding (matches back_charge.TWOPLACES).
TWOPLACES = Decimal("0.01")

#: Four-decimal-place quantum for recovery RATES (a fraction in [0, 1]).
RATEPLACES = Decimal("0.0001")

_ZERO = Decimal("0")
_ONE = Decimal("1")


def quantize_money(amount: Decimal) -> Decimal:
    """Round *amount* to two decimal places using half-up rounding.

    Identical behaviour to ``back_charge.quantize_money`` - kept local so this
    module imports nothing from the rest of the app.
    """
    return amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def quantize_rate(rate: Decimal) -> Decimal:
    """Round a recovery *rate* (a fraction) to four decimal places, half-up."""
    return rate.quantize(RATEPLACES, rounding=ROUND_HALF_UP)


def normalise_band(band: str) -> str:
    """Map an arbitrary band string to a recognised band.

    Comparison is case-insensitive and whitespace-tolerant. Anything not one of
    :data:`TRACEABILITY_BANDS` (including blank) becomes :data:`DEFAULT_BAND`
    (``weak``), so an item with a missing or junk band is treated as the least
    traceable rather than silently trusted.
    """
    cleaned = (band or "").strip().lower()
    if cleaned in (BAND_STRONG, BAND_MODERATE, BAND_WEAK):
        return cleaned
    return DEFAULT_BAND


def cohort_for(band: str) -> str:
    """Classify a traceability *band* into the HIGH / LOW cohort.

    ``strong`` -> :data:`COHORT_HIGH`; ``moderate`` / ``weak`` (and anything
    unrecognised, via :func:`normalise_band`) -> :data:`COHORT_LOW`. This is the
    documented cut the headline high-vs-low contrast is drawn on.
    """
    return COHORT_HIGH if normalise_band(band) in HIGH_BANDS else COHORT_LOW


def recovery_rate(recovered: Decimal, chargeable: Decimal) -> Decimal | None:
    """Recovered over chargeable as a quantized fraction, or ``None``.

    Returns ``recovered / chargeable`` quantized to :data:`RATEPLACES`. When
    *chargeable* is zero (or negative - a nonsensical entitlement) the ratio is
    undefined and ``None`` is returned rather than a misleading zero: a project
    that was never entitled to recover anything has no recovery rate. The result
    is clamped to ``[0, 1]`` so an over-recovery on the input cannot report a
    rate above 100%.
    """
    if chargeable <= _ZERO:
        return None
    rate = recovered / chargeable
    if rate < _ZERO:
        rate = _ZERO
    elif rate > _ONE:
        rate = _ONE
    return quantize_rate(rate)


@dataclass(frozen=True)
class RecoveryItem:
    """Present-state projection of one back-charge record for this engine.

    The integrator maps a ledger row onto this: ``chargeable`` is the amount the
    project judged recoverable (i.e. ``BackChargeItem.chargeable_amount``, gross
    already scaled by the chargeable percentage); ``recovered`` is how much has
    actually been collected; ``currency`` is the ISO code the two are denominated
    in; ``traceability_band`` is the provability band
    (``weak`` / ``moderate`` / ``strong``) of the evidence behind the item, from
    :func:`app.modules.claims_evidence.provability.band_for`; ``status`` is the
    commercial state (one of the ``STATUS_*`` constants).

    Recovered is interpreted only up to the chargeable amount in every rollup
    (an over-recovery on a single item never inflates a total beyond what was
    chargeable), mirroring ``build_ledger``. A blank / unrecognised band is
    treated as :data:`DEFAULT_BAND`.
    """

    chargeable: Decimal
    recovered: Decimal
    currency: str
    traceability_band: str
    status: str

    @property
    def band(self) -> str:
        """The normalised traceability band (blank / junk -> ``weak``)."""
        return normalise_band(self.traceability_band)

    @property
    def cohort(self) -> str:
        """The HIGH / LOW traceability cohort this item falls in."""
        return cohort_for(self.traceability_band)

    @property
    def is_absorbed(self) -> bool:
        """True when the item was closed without recovering the full charge.

        An item is absorbed when its status is ``waived`` / ``absorbed``. The
        absorbed *amount* (see :attr:`absorbed_amount`) is the chargeable net of
        anything recovered before write-off, so a partial recovery followed by a
        waiver only counts the uncollected remainder as absorbed.
        """
        return self.status in ABSORBED_STATUSES

    @property
    def clamped_chargeable(self) -> Decimal:
        """Chargeable amount floored at zero (a negative charge is nonsensical)."""
        return self.chargeable if self.chargeable > _ZERO else _ZERO

    @property
    def clamped_recovered(self) -> Decimal:
        """Recovered amount clamped to ``[0, chargeable]`` (mirrors build_ledger)."""
        rec = self.recovered
        if rec < _ZERO:
            return _ZERO
        charge = self.clamped_chargeable
        return charge if rec > charge else rec

    @property
    def absorbed_amount(self) -> Decimal:
        """Chargeable the project gave up: chargeable minus recovered, or zero.

        Zero unless the item is absorbed (:attr:`is_absorbed`). For an absorbed
        item it is the clamped chargeable net of whatever was recovered before
        write-off, floored at zero.
        """
        if not self.is_absorbed:
            return _ZERO
        remainder = self.clamped_chargeable - self.clamped_recovered
        return remainder if remainder > _ZERO else _ZERO


@dataclass(frozen=True)
class CohortRecovery:
    """Recovery performance for one traceability cohort, in one currency.

    ``cohort`` is either a HIGH/LOW label (:data:`COHORT_HIGH` /
    :data:`COHORT_LOW`) or an individual band (:data:`BAND_STRONG` /
    :data:`BAND_MODERATE` / :data:`BAND_WEAK`), depending on which collection it
    appears in. ``rate`` is the cohort's recovery rate as a fraction in
    ``[0, 1]`` (see :func:`recovery_rate`), or ``None`` when the cohort has no
    chargeable amount.
    """

    cohort: str
    currency: str
    item_count: int
    chargeable_total: Decimal
    recovered_total: Decimal
    outstanding_total: Decimal
    absorbed_total: Decimal
    rate: Decimal | None


@dataclass(frozen=True)
class CurrencyRecovery:
    """Recovery performance for one currency across all cohorts.

    ``rate`` is the overall recovery rate for the currency (a fraction in
    ``[0, 1]``), or ``None`` when nothing was chargeable in it. ``by_cohort`` is
    the HIGH/LOW split and ``by_band`` the three-band breakdown, both scoped to
    this currency; every band / cohort that has at least one item appears (with a
    ``None`` rate if it had no chargeable amount), strongest / HIGH first.
    """

    currency: str
    item_count: int
    chargeable_total: Decimal
    recovered_total: Decimal
    outstanding_total: Decimal
    absorbed_total: Decimal
    rate: Decimal | None
    by_cohort: tuple[CohortRecovery, ...] = field(default_factory=tuple)
    by_band: tuple[CohortRecovery, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RecoveryPerformance:
    """The project's recovery position, per currency, never blended.

    ``primary_currency`` is the currency carrying the greatest chargeable total
    (ties broken alphabetically); ``primary_rate`` is that currency's overall
    recovery rate (a fraction, or ``None``) - a single headline figure that
    never mixes currencies. Empty input yields an empty primary currency, a
    ``None`` headline rate and no currency rows.
    """

    item_count: int
    primary_currency: str
    primary_rate: Decimal | None
    by_currency: tuple[CurrencyRecovery, ...] = field(default_factory=tuple)


@dataclass
class _Acc:
    """Mutable accumulator for one grouping key. Decimal sums stay exact."""

    item_count: int = 0
    chargeable: Decimal = field(default_factory=lambda: Decimal("0"))
    recovered: Decimal = field(default_factory=lambda: Decimal("0"))
    outstanding: Decimal = field(default_factory=lambda: Decimal("0"))
    absorbed: Decimal = field(default_factory=lambda: Decimal("0"))

    def add(self, item: RecoveryItem) -> None:
        """Fold one item's clamped money into the accumulator."""
        charge = item.clamped_chargeable
        recovered = item.clamped_recovered
        absorbed = item.absorbed_amount
        # Outstanding = still-collectable chargeable on a live item. A closed
        # item (recovered or absorbed) has nothing outstanding.
        if item.status in CLOSED_STATUSES:
            outstanding = _ZERO
        else:
            remaining = charge - recovered
            outstanding = remaining if remaining > _ZERO else _ZERO

        self.item_count += 1
        self.chargeable += charge
        self.recovered += recovered
        self.outstanding += outstanding
        self.absorbed += absorbed


def _cohort_row(cohort: str, currency: str, acc: _Acc) -> CohortRecovery:
    """Quantize one accumulator into an immutable :class:`CohortRecovery`."""
    chargeable = quantize_money(acc.chargeable)
    recovered = quantize_money(acc.recovered)
    return CohortRecovery(
        cohort=cohort,
        currency=currency,
        item_count=acc.item_count,
        chargeable_total=chargeable,
        recovered_total=recovered,
        outstanding_total=quantize_money(acc.outstanding),
        absorbed_total=quantize_money(acc.absorbed),
        # Rate is computed from the EXACT (pre-quantize) sums then quantized, so
        # rounding of the money totals never perturbs the ratio.
        rate=recovery_rate(acc.recovered, acc.chargeable),
    )


def compute_recovery_performance(
    items: Iterable[RecoveryItem],
) -> RecoveryPerformance:
    """Compute recovery performance from a set of recovery items.

    Groups items by currency (never blending across currency codes) and, within
    each currency, by the HIGH/LOW traceability cohort and by the individual
    band. For each scope it returns chargeable / recovered / outstanding /
    absorbed totals (Decimal, two places, half-up) and a recovery rate
    (recovered over chargeable, a fraction in ``[0, 1]`` to four places, or
    ``None`` when nothing was chargeable).

    The currency rows are ordered by descending chargeable total then currency;
    within a currency, cohort rows are HIGH then LOW and band rows are
    ``strong`` -> ``moderate`` -> ``weak``, with empty bands / cohorts omitted.
    ``primary_currency`` / ``primary_rate`` report the largest-chargeable
    currency's overall rate as a single headline. The computation is pure and
    deterministic: identical input always yields an identical result.
    """
    items = list(items)

    cur_acc: dict[str, _Acc] = defaultdict(_Acc)
    cohort_acc: dict[tuple[str, str], _Acc] = defaultdict(_Acc)
    band_acc: dict[tuple[str, str], _Acc] = defaultdict(_Acc)

    for it in items:
        currency = it.currency
        cur_acc[currency].add(it)
        cohort_acc[(currency, it.cohort)].add(it)
        band_acc[(currency, it.band)].add(it)

    by_currency: list[CurrencyRecovery] = []
    for currency, acc in cur_acc.items():
        # HIGH/LOW cohorts present in this currency, HIGH first.
        cohorts: list[CohortRecovery] = []
        for cohort in (COHORT_HIGH, COHORT_LOW):
            key = (currency, cohort)
            if key in cohort_acc:
                cohorts.append(_cohort_row(cohort, currency, cohort_acc[key]))

        # Individual bands present in this currency, strongest first.
        bands: list[CohortRecovery] = []
        for band in TRACEABILITY_BANDS:
            key = (currency, band)
            if key in band_acc:
                bands.append(_cohort_row(band, currency, band_acc[key]))

        by_currency.append(
            CurrencyRecovery(
                currency=currency,
                item_count=acc.item_count,
                chargeable_total=quantize_money(acc.chargeable),
                recovered_total=quantize_money(acc.recovered),
                outstanding_total=quantize_money(acc.outstanding),
                absorbed_total=quantize_money(acc.absorbed),
                rate=recovery_rate(acc.recovered, acc.chargeable),
                by_cohort=tuple(cohorts),
                by_band=tuple(bands),
            )
        )

    by_currency.sort(key=lambda r: (-r.chargeable_total, r.currency))

    if by_currency:
        primary = by_currency[0]
        primary_currency = primary.currency
        primary_rate = primary.rate
    else:
        primary_currency = ""
        primary_rate = None

    return RecoveryPerformance(
        item_count=len(items),
        primary_currency=primary_currency,
        primary_rate=primary_rate,
        by_currency=tuple(by_currency),
    )


__all__ = [
    "STATUS_PROPOSED",
    "STATUS_AGREED",
    "STATUS_DISPUTED",
    "STATUS_RECOVERED",
    "STATUS_WAIVED",
    "STATUS_ABSORBED",
    "OPEN_STATUSES",
    "ABSORBED_STATUSES",
    "CLOSED_STATUSES",
    "BAND_WEAK",
    "BAND_MODERATE",
    "BAND_STRONG",
    "TRACEABILITY_BANDS",
    "COHORT_HIGH",
    "COHORT_LOW",
    "HIGH_BANDS",
    "LOW_BANDS",
    "DEFAULT_BAND",
    "TWOPLACES",
    "RATEPLACES",
    "quantize_money",
    "quantize_rate",
    "normalise_band",
    "cohort_for",
    "recovery_rate",
    "RecoveryItem",
    "CohortRecovery",
    "CurrencyRecovery",
    "RecoveryPerformance",
    "compute_recovery_performance",
]
