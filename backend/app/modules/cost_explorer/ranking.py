# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Pure ranking engine for the Cost Explorer "find work by resources" mode.

Given a requested set of resource codes (optionally weighted) and, for each
candidate work item, the resources it consumes with their line costs, this
scores how well the item matches. It combines *coverage* (how much of my
resource set the work uses) with *cost weight* (how much of the work's price my
resources drive), and applies a small tie-break against items that pull in many
resources I did not ask for, so a tight match ranks above a broad one.

    score = W_COVERAGE * coverage + W_COST * cost_weight - W_EXTRA * extra

No database, ORM or app imports live here, so the engine is importable and unit
testable on any interpreter. The service layer builds :class:`CandidateItem`
values from the reverse index and hands them to :func:`rank`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# Blend weights. Coverage leads (does this work use what I have at all?), cost
# weight refines (do my resources actually drive its price?). ``W_EXTRA`` is a
# deliberately small tie-break: it nudges tight matches above broad ones without
# ever overriding a genuine coverage/cost signal.
W_COVERAGE = 0.6
W_COST = 0.4
W_EXTRA = 0.05
# Extra-resource count at which the tie-break penalty saturates. A typical CWICR
# item carries ~14 resource lines; 40 is a generous cap so ordinary items are
# barely penalised and only sprawling ones are pushed down.
_EXTRA_SATURATION = 40.0


def to_decimal(value: object) -> Decimal:
    """Parse a stored money/quantity value (string, number, or blank) to Decimal.

    Cost data stores money and quantities as Decimal-compatible strings and may
    leave them blank. Anything unparseable degrades to ``Decimal(0)`` rather
    than raising, so one malformed row never breaks a whole ranking.
    """
    if value is None or value == "":
        return Decimal(0)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


@dataclass
class ResourceLine:
    """One resource consumed by a candidate work item."""

    resource_code: str
    cost: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)
    resource_name: str = ""
    resource_type: str = ""


@dataclass
class CandidateItem:
    """A work item considered for the resource match, with its resource lines."""

    cost_item_id: str
    rate_code: str
    region: str | None
    item_total: Decimal = Decimal(0)
    lines: list[ResourceLine] = field(default_factory=list)


@dataclass
class MatchedResource:
    """A requested resource that the candidate item was found to consume."""

    resource_code: str
    resource_name: str
    cost: Decimal
    quantity: Decimal


@dataclass
class ScoredMatch:
    """The result of scoring one candidate against the requested resource set."""

    cost_item_id: str
    rate_code: str
    region: str | None
    score: float
    coverage: float
    cost_weight: float
    item_total: Decimal
    matched_cost: Decimal
    matched: list[MatchedResource]
    missing_codes: list[str]


def normalise_weights(requested: dict[str, float] | list[str]) -> dict[str, float]:
    """Coerce the requested resources to a ``{code: weight}`` map.

    A bare list of codes becomes uniform weight 1.0. Non-positive or missing
    weights are floored to 0.0 so a caller cannot invert the ranking with a
    negative weight; blank codes are dropped.
    """
    if isinstance(requested, dict):
        items = requested.items()
    else:
        items = ((code, 1.0) for code in requested)
    out: dict[str, float] = {}
    for code, weight in items:
        code = (code or "").strip()
        if not code:
            continue
        try:
            w = float(weight)
        except (TypeError, ValueError):
            w = 1.0
        out[code] = max(0.0, w)
    return out


def score_candidate(weights: dict[str, float], item: CandidateItem) -> ScoredMatch:
    """Score a single candidate work item against the weighted requested set."""
    requested_codes = set(weights)
    by_code: dict[str, ResourceLine] = {}
    for line in item.lines:
        # Keep the richest line per code (an item can list a resource once, but
        # be defensive about duplicates by preferring the higher-cost line).
        existing = by_code.get(line.resource_code)
        if existing is None or line.cost > existing.cost:
            by_code[line.resource_code] = line

    matched_codes = [c for c in requested_codes if c in by_code]
    missing_codes = sorted(c for c in requested_codes if c not in by_code)

    # Coverage = share of the requested weight this item actually carries.
    # Normalise a fully degenerate (all-zero) weight set to uniform up front, so
    # a genuine zero-weighted-only match reads as 0 coverage instead of being
    # inflated by a per-item fallback.
    raw_total = sum(weights.values())
    if raw_total > 0:
        eff_weights = weights
    else:
        eff_weights = dict.fromkeys(weights, 1.0)
        raw_total = float(len(eff_weights) or 1)
    matched_weight = sum(eff_weights[c] for c in matched_codes)
    coverage = matched_weight / raw_total if raw_total else 0.0
    coverage = max(0.0, min(1.0, coverage))

    matched_cost = sum((by_code[c].cost for c in matched_codes), Decimal(0))
    cost_weight = float(matched_cost / item.item_total) if item.item_total > 0 else 0.0
    cost_weight = max(0.0, min(1.0, cost_weight))

    extra = max(0, len(by_code) - len(matched_codes))
    extra_penalty = min(1.0, extra / _EXTRA_SATURATION)

    score = W_COVERAGE * coverage + W_COST * cost_weight - W_EXTRA * extra_penalty
    score = max(0.0, min(1.0, score))

    matched = [
        MatchedResource(
            resource_code=c,
            resource_name=by_code[c].resource_name,
            cost=by_code[c].cost,
            quantity=by_code[c].quantity,
        )
        for c in matched_codes
    ]
    matched.sort(key=lambda m: m.cost, reverse=True)

    return ScoredMatch(
        cost_item_id=item.cost_item_id,
        rate_code=item.rate_code,
        region=item.region,
        score=round(score, 4),
        coverage=round(coverage, 4),
        cost_weight=round(cost_weight, 4),
        item_total=item.item_total,
        matched_cost=matched_cost,
        matched=matched,
        missing_codes=missing_codes,
    )


def rank(
    requested: dict[str, float] | list[str],
    items: list[CandidateItem],
    limit: int = 50,
) -> list[ScoredMatch]:
    """Rank candidate work items by how well they match the requested resources.

    Only items that consume at least one requested resource are returned. Ties
    fall back to coverage, then cost weight, then fewer missing requested codes,
    so the most complete match wins. ``limit`` caps the result.
    """
    weights = normalise_weights(requested)
    if not weights:
        return []
    scored = [score_candidate(weights, it) for it in items]
    scored = [s for s in scored if s.matched]
    scored.sort(
        key=lambda s: (s.score, s.coverage, s.cost_weight, -len(s.missing_codes)),
        reverse=True,
    )
    if limit and limit > 0:
        return scored[:limit]
    return scored
