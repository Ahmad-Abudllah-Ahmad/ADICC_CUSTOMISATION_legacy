# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure change-driver (Pareto) analytics.

Where the impact projection rolls approved change up by kind, this engine asks
the prior question every project team argues about: what is actually driving the
change, and who is responsible for it. Given every change-bearing record already
projected to a :class:`DriverRecord` (a change order's reason category, a
disruption claim's root cause, an extension-of-time claim's root-cause category,
or a risk-register category), it produces a :class:`DriverAnalytics`:

* a Pareto by originating cause - each cause's change count and cost, ranked by
  contribution descending with a running cumulative percentage, so the vital few
  causes carrying most of the cost surface at the top;
* the same Pareto rolled up by responsible party, using a transparent
  fault-allocation of the cause taxonomy (client / designer / contractor /
  external, or unclassified when the source carries no fault signal);
* a per-currency breakdown that never blends currencies; and
* a month-over-month trend of change count and cost.

Money handling mirrors the impact projection: cost is a signed
:class:`~decimal.Decimal` (a credit is negative), the ranked cost totals are a
naive sum that is exact for the common single-currency project, a
``primary_currency`` is named (largest absolute cost) for headline display, and
the honest per-currency split is always available alongside. When a project
carries no change cost at all (for example only time-based extension claims), the
Pareto falls back to ranking by count so it stays useful.

No database, no ORM, no ``app.*`` imports - stdlib only - so it unit-tests on the
local Python 3.11 runner exactly like the impact and cycle-time engines. A thin
service layer reads the change-bearing rows and feeds them in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# Stable source tokens for the change-bearing record families this engine spans.
SOURCE_CHANGE_ORDER = "change_order"
SOURCE_DISRUPTION_CLAIM = "disruption_claim"
SOURCE_EOT_CLAIM = "eot_claim"
SOURCE_RISK = "risk"

# Responsible-party buckets. Fault allocation follows the common construction
# change-cause taxonomies (an employer / client-driven change, a designer or
# consultant-driven change, a contractor-driven change, an external or neutral
# event such as an unforeseen ground condition, weather, force majeure or an
# authority requirement), or unclassified when the source carries no fault
# signal. Delay-cause categorisation into employer / contractor / neutral risk
# is the same split recognised delay protocols use.
PARTY_CLIENT = "client"
PARTY_DESIGNER = "designer"
PARTY_CONTRACTOR = "contractor"
PARTY_EXTERNAL = "external"
PARTY_UNCLASSIFIED = "unclassified"

#: Placeholder cause when a record carries no category at all.
UNSPECIFIED_CAUSE = "unspecified"

# Change-order reason categories mapped to the party at fault. Keys are the
# normalized cause tokens (lowercased, spaces / hyphens folded to underscores).
_CO_CAUSE_TO_PARTY: dict[str, str] = {
    "client_request": PARTY_CLIENT,
    "client_change": PARTY_CLIENT,
    "owner_request": PARTY_CLIENT,
    "owner_change": PARTY_CLIENT,
    "employer_request": PARTY_CLIENT,
    "scope_addition": PARTY_CLIENT,
    "scope_change": PARTY_CLIENT,
    "design_error": PARTY_DESIGNER,
    "design_change": PARTY_DESIGNER,
    "design_development": PARTY_DESIGNER,
    "design_omission": PARTY_DESIGNER,
    "coordination": PARTY_DESIGNER,
    "consultant": PARTY_DESIGNER,
    "value_engineering": PARTY_CONTRACTOR,
    "contractor_request": PARTY_CONTRACTOR,
    "means_and_methods": PARTY_CONTRACTOR,
    "workmanship": PARTY_CONTRACTOR,
    "construction_error": PARTY_CONTRACTOR,
    "site_condition": PARTY_EXTERNAL,
    "differing_site_condition": PARTY_EXTERNAL,
    "unforeseen": PARTY_EXTERNAL,
    "unforeseen_condition": PARTY_EXTERNAL,
    "weather": PARTY_EXTERNAL,
    "force_majeure": PARTY_EXTERNAL,
    "regulatory": PARTY_EXTERNAL,
    "code_compliance": PARTY_EXTERNAL,
    "authority": PARTY_EXTERNAL,
    "permit": PARTY_EXTERNAL,
    "statutory": PARTY_EXTERNAL,
    "third_party": PARTY_EXTERNAL,
}

# Extension-of-time root-cause categories mapped to the party at fault. The
# employer / contractor / neutral split is the recognised delay-risk taxonomy.
_EOT_CAUSE_TO_PARTY: dict[str, str] = {
    "employer": PARTY_CLIENT,
    "employer_risk": PARTY_CLIENT,
    "client": PARTY_CLIENT,
    "owner": PARTY_CLIENT,
    "contractor": PARTY_CONTRACTOR,
    "contractor_risk": PARTY_CONTRACTOR,
    "neutral": PARTY_EXTERNAL,
    "neutral_risk": PARTY_EXTERNAL,
    "concurrent": PARTY_EXTERNAL,
    "weather": PARTY_EXTERNAL,
    "force_majeure": PARTY_EXTERNAL,
}

_WS = re.compile(r"[\s\-]+")


def normalize_cause(value: str | None) -> str:
    """Normalize a raw cause label to a stable token.

    Lowercases, trims, and folds runs of whitespace or hyphens to a single
    underscore so ``"Design Error"`` and ``"design-error"`` bucket together. A
    blank value becomes :data:`UNSPECIFIED_CAUSE`. Long free-text causes (a
    disruption claim stores a free-text root cause) are truncated so one verbose
    entry cannot dominate the key space.
    """
    if value is None:
        return UNSPECIFIED_CAUSE
    text = _WS.sub("_", value.strip().lower()).strip("_")
    if not text:
        return UNSPECIFIED_CAUSE
    return text[:80]


def responsible_party_for(source: str, cause: str) -> str:
    """Map a (source, normalized cause) to its responsible-party bucket.

    Only the change-order reason categories and the extension-of-time root-cause
    categories are genuine fault taxonomies, so only those are allocated to a
    party; a disruption claim's free-text root cause and a risk-register
    category carry no fault signal and fall to :data:`PARTY_UNCLASSIFIED`. An
    unrecognised cause on a mapped source is also unclassified rather than
    guessed.
    """
    if source == SOURCE_CHANGE_ORDER:
        return _CO_CAUSE_TO_PARTY.get(cause, PARTY_UNCLASSIFIED)
    if source == SOURCE_EOT_CLAIM:
        return _EOT_CAUSE_TO_PARTY.get(cause, PARTY_UNCLASSIFIED)
    return PARTY_UNCLASSIFIED


@dataclass(frozen=True)
class DriverRecord:
    """One change-bearing record projected for driver analytics.

    ``cause`` is the raw originating-cause label (normalized by the engine).
    ``cost`` is a signed :class:`~decimal.Decimal` in ``currency`` (zero when the
    source carries no cost, for example a time-only extension claim). ``month``
    is the ``YYYY-MM`` bucket the record falls in for the trend.
    """

    source: str
    cause: str
    cost: Decimal
    currency: str
    month: str


@dataclass(frozen=True)
class ParetoRow:
    """One driver's contribution in a ranked Pareto.

    ``cost`` is the signed :class:`~decimal.Decimal` total; ``cost_pct`` is its
    share of the ranking basis and ``cumulative_pct`` the running share through
    this row. When there is no cost anywhere the basis is the record count, so
    the percentages still describe the ranking.
    """

    key: str
    count: int
    cost: Decimal
    cost_pct: float
    cumulative_pct: float


@dataclass(frozen=True)
class CurrencyTotal:
    """Signed change-cost total carried by one currency (never blended)."""

    currency: str
    count: int
    cost: Decimal


@dataclass(frozen=True)
class TrendPoint:
    """Change count and signed cost for one ``YYYY-MM`` month."""

    month: str
    count: int
    cost: Decimal


@dataclass(frozen=True)
class DriverAnalytics:
    """Pareto + trend roll-up of a project's change drivers."""

    total_count: int
    total_cost: Decimal
    primary_currency: str
    by_cause: list[ParetoRow]
    by_party: list[ParetoRow]
    by_currency: list[CurrencyTotal]
    trend: list[TrendPoint]


def _pareto(buckets: dict[str, tuple[int, Decimal]]) -> list[ParetoRow]:
    """Rank *buckets* (key -> (count, cost)) into a Pareto with cumulative %.

    Rows sort by absolute cost descending, then count descending, then key
    ascending. Percentages are taken over the summed absolute cost when any
    cost exists, otherwise over the summed count. Normalising on absolute cost
    keeps the cumulative monotonic and within 0..100 even when the change set
    mixes additions with credits (a value-engineering saving is a negative
    cost): a credit's magnitude still drives its rank and share, while its
    signed value is reported verbatim in ``cost``. The headline
    ``DriverAnalytics.total_cost`` stays the net signed sum.
    """
    total_abs_cost = sum((abs(cost) for _c, cost in buckets.values()), Decimal("0"))
    total_count = sum(count for count, _cost in buckets.values())
    use_cost = total_abs_cost != 0

    ordered = sorted(buckets.items(), key=lambda kv: (-abs(kv[1][1]), -kv[1][0], kv[0]))

    rows: list[ParetoRow] = []
    running_abs_cost = Decimal("0")
    running_count = 0
    for key, (count, cost) in ordered:
        running_abs_cost += abs(cost)
        running_count += count
        if use_cost:
            cost_pct = float(abs(cost) / total_abs_cost * 100)
            cumulative_pct = float(running_abs_cost / total_abs_cost * 100)
        else:
            cost_pct = float(count / total_count * 100) if total_count else 0.0
            cumulative_pct = float(running_count / total_count * 100) if total_count else 0.0
        rows.append(
            ParetoRow(
                key=key,
                count=count,
                cost=cost,
                cost_pct=round(cost_pct, 2),
                cumulative_pct=round(cumulative_pct, 2),
            )
        )
    return rows


def build_driver_analytics(records: list[DriverRecord]) -> DriverAnalytics:
    """Roll *records* into a :class:`DriverAnalytics`.

    Costs are summed exactly as :class:`~decimal.Decimal`; the ranked cost is a
    naive sum across currencies (exact for a single-currency project, matching
    the impact projection's by-kind roll-up) while the per-currency breakdown
    keeps currencies separate. The primary currency is the one carrying the
    largest absolute cost, ties broken by currency string.
    """
    cause_buckets: dict[str, tuple[int, Decimal]] = {}
    party_buckets: dict[str, tuple[int, Decimal]] = {}
    currency_buckets: dict[str, tuple[int, Decimal]] = {}
    month_buckets: dict[str, tuple[int, Decimal]] = {}

    total_cost = Decimal("0")
    for rec in records:
        cause = normalize_cause(rec.cause)
        party = responsible_party_for(rec.source, cause)
        total_cost += rec.cost

        c_count, c_cost = cause_buckets.get(cause, (0, Decimal("0")))
        cause_buckets[cause] = (c_count + 1, c_cost + rec.cost)

        p_count, p_cost = party_buckets.get(party, (0, Decimal("0")))
        party_buckets[party] = (p_count + 1, p_cost + rec.cost)

        cur_count, cur_cost = currency_buckets.get(rec.currency, (0, Decimal("0")))
        currency_buckets[rec.currency] = (cur_count + 1, cur_cost + rec.cost)

        m_count, m_cost = month_buckets.get(rec.month, (0, Decimal("0")))
        month_buckets[rec.month] = (m_count + 1, m_cost + rec.cost)

    by_currency = [
        CurrencyTotal(currency=currency, count=count, cost=cost)
        for currency, (count, cost) in sorted(currency_buckets.items())
    ]
    if by_currency:
        primary = min(by_currency, key=lambda b: (-abs(b.cost), b.currency))
        primary_currency = primary.currency
    else:
        primary_currency = ""

    trend = [TrendPoint(month=month, count=count, cost=cost) for month, (count, cost) in sorted(month_buckets.items())]

    return DriverAnalytics(
        total_count=len(records),
        total_cost=total_cost,
        primary_currency=primary_currency,
        by_cause=_pareto(cause_buckets),
        by_party=_pareto(party_buckets),
        by_currency=by_currency,
        trend=trend,
    )


__all__ = [
    "PARTY_CLIENT",
    "PARTY_CONTRACTOR",
    "PARTY_DESIGNER",
    "PARTY_EXTERNAL",
    "PARTY_UNCLASSIFIED",
    "SOURCE_CHANGE_ORDER",
    "SOURCE_DISRUPTION_CLAIM",
    "SOURCE_EOT_CLAIM",
    "SOURCE_RISK",
    "UNSPECIFIED_CAUSE",
    "CurrencyTotal",
    "DriverAnalytics",
    "DriverRecord",
    "ParetoRow",
    "TrendPoint",
    "build_driver_analytics",
    "normalize_cause",
    "responsible_party_for",
]
